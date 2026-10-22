"""Offline checks: no model processes, personal DB, or main suite are used."""
import json
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scripts import user_test_app as manual
from scripts import user_test_console as console


class FakeState:
    def __init__(self):
        self.calls = []
    def snapshot(self):
        return {"kind": "pma-user-test-console", "job": None, "app_status": "stopped"}
    def open_app(self, profile):
        self.calls.append(("app", profile))
        return {"url": "http://127.0.0.1:18765/"}
    def start(self, data):
        self.calls.append(("run", data))
        return {"run": "fake-only"}
    def cancel(self):
        self.calls.append(("cancel",))
        return {"requested": True}
    def stop_app(self):
        self.calls.append(("stop",))
        return True


ORIGIN = "http://127.0.0.1:18760"
HEADERS = {"x-test-token": "fixed-offline-token", "origin": ORIGIN}


def test_view_poll_reload_and_report_never_start_a_job_or_app():
    state = FakeState()
    with TestClient(console.create_console(state, token=HEADERS["x-test-token"]), base_url=ORIGIN) as client:
        for _ in range(3):
            assert client.get("/").status_code == 200
            assert client.get("/api/status", headers=HEADERS).status_code == 200
            assert client.get("/api/examples", headers=HEADERS).status_code == 200
        assert client.get("/report/identity_evidence_optimization.html", headers=HEADERS).status_code == 200
    assert state.calls == []


@pytest.mark.parametrize("headers", [{}, {"origin": ORIGIN},
    {"x-test-token": "fixed-offline-token", "origin": "https://other.example"},
    {**HEADERS, "sec-fetch-site": "cross-site"}])
def test_start_requires_explicit_authenticated_same_origin_post(headers):
    state = FakeState()
    with TestClient(console.create_console(state, token=HEADERS["x-test-token"]), base_url=ORIGIN) as client:
        assert client.post("/api/run", headers=headers, json={"pause_models": True}).status_code in {401, 403}
        assert client.post("/api/open-app", headers=headers, json={}).status_code in {401, 403}
    assert not state.calls


def test_only_a_valid_start_action_dispatches_and_cookie_alone_cannot_start():
    state = FakeState()
    with TestClient(console.create_console(state, token=HEADERS["x-test-token"]), base_url=ORIGIN) as client:
        assert client.post("/api/session", headers=HEADERS, json={}).status_code == 200
        assert client.get("/api/status").status_code == 200
        assert client.post("/api/run", headers={"origin": ORIGIN}, json={"pause_models": True}).status_code == 401
        assert client.post("/api/run", headers=HEADERS, json={"device": "arbitrary"}).status_code == 422
        assert client.post("/api/run", headers=HEADERS, json={"pause_models": "false"}).status_code == 422
        assert not state.calls
        assert client.post("/api/run", headers=HEADERS, json={"pause_models": True}).status_code == 200
    assert len(state.calls) == 1 and state.calls[0][0] == "run"


def test_artifacts_cannot_expose_databases_or_escape_the_results_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(console, "ROOT", tmp_path)
    folder = tmp_path / ".local/latency-goal/demo/gpu"
    folder.mkdir(parents=True)
    (folder / "answers.html").write_text("safe review", encoding="utf-8")
    (folder / "secret.db").write_bytes(b"db")
    with TestClient(console.create_console(FakeState(), token=HEADERS["x-test-token"]), base_url=ORIGIN) as client:
        assert client.get("/results/demo/gpu/answers.html").status_code == 401
        assert client.get("/results/demo/gpu/answers.html", headers=HEADERS).text == "safe review"
        assert client.get("/results/demo/gpu/secret.db", headers=HEADERS).status_code == 404
        assert client.get("/results/demo/%2e%2e/%2e%2e/elsewhere.json", headers=HEADERS).status_code == 404


@pytest.mark.parametrize("kind", ["first", "repeat"])
def test_comparison_preserves_quality_and_separates_cold_and_repeated_requests(kind):
    config = console.benchmark_config("gpu", kind, "five", "simple", True, "python.exe", "demo")
    assert config["PlanningBaseline"] and config["SharedCompactFormats"]
    assert config["ScopedIdentitySearch"] and config["VerifiedSourceSearch"]
    assert config["Samples"] == 5 and config["Cases"] == ["dev_fact", "dev_date"]
    assert ("ColdInterpretations" in config) is (kind == "first")
    assert ("InterpretationReuse" in config) is (kind == "repeat")
    assert "main_suite" not in str(config)


def test_failing_cpu_followup_is_screened_not_repeated_five_times():
    with pytest.raises(ValueError, match="빠른 확인"):
        console.benchmark_config("cpu", "first", "five", "followup", True, "python", "demo")


def test_server_pause_is_never_inferred_from_opening_the_screen(tmp_path, monkeypatch):
    monkeypatch.setattr(console, "WORK", tmp_path)
    state = console.State()
    monkeypatch.setattr(console.threading, "Thread", lambda **kw: pytest.fail("Must not dispatch"))
    with pytest.raises(ValueError, match="임시 중지"):
        state.start(console.Trial())
    assert state.job is None


def test_cancel_before_start_never_launches_a_child(tmp_path, monkeypatch):
    monkeypatch.setattr(console, "WORK", tmp_path)
    monkeypatch.setattr(console.subprocess, "Popen", lambda *a, **kw: pytest.fail("Must not start"))
    state = console.State()
    state.job = {"cancel_requested": True, "status": "cancelling"}
    state._run({"RunName": "cancel-before"})
    assert state.job["status"] == "cancelled"


def test_cancel_during_trial_uses_sentinel_and_never_terminates_restoration(tmp_path, monkeypatch):
    monkeypatch.setattr(console, "WORK", tmp_path / "work")
    monkeypatch.setattr(console, "ROOT", tmp_path)
    monkeypatch.setattr(console.shutil, "which", lambda name: "pwsh.exe")
    monkeypatch.setattr(console, "ready", lambda port: False)
    monkeypatch.setattr(console, "listening", lambda port: False)
    state = console.State()
    state.job = {"cancel_requested": False, "status": "running"}
    output = tmp_path / ".local/latency-goal/demo/cpu"
    class Process:
        returncode = 1
        calls = 0
        def __init__(self, *args, **kwargs):
            assert not output.parent.exists()  # Launcher must own output creation.
            output.mkdir(parents=True)
        def poll(self):
            self.calls += 1
            if self.calls == 1:
                state.cancel()
                return None
            return 1
    monkeypatch.setattr(console.subprocess, "Popen", Process)
    monkeypatch.setattr(console.time, "sleep", lambda seconds: None)
    state._run({"RunName": "demo"})
    assert (output / "cancel.request").is_file()
    assert state.job["status"] == "cancelled"
    saved = json.loads((tmp_path / "work/demo/configuration.json").read_text(encoding="utf-8"))
    assert saved["PauseOrdinaryModels"] is False


def seed_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(manual, "ROOT", tmp_path)
    monkeypatch.setattr(manual, "WORK", tmp_path / "work")
    seed = tmp_path / "only-synthetic.db"
    monkeypatch.setattr(manual, "SEED", seed)
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation/source_completion_cases.json").write_text(json.dumps({
        "splits": {"confirmation": {"documents": [["one", "합성 원문", "", ""]]}}}), encoding="utf-8")
    metadata = tmp_path / ".local/latency-goal/source-completion-gpu-confirmation/gpu"
    metadata.mkdir(parents=True)
    (metadata / "results.json").write_text(json.dumps({"hashes": {"embedding": "1" * 64}}), encoding="utf-8")
    with sqlite3.connect(seed) as db:
        db.executescript("CREATE TABLE revisions(text TEXT); CREATE TABLE jobs(status TEXT); CREATE TABLE embeddings(model_key TEXT);")
        db.execute("INSERT INTO revisions VALUES(?)", ("합성 원문",))
        db.execute("INSERT INTO jobs VALUES('succeeded')")
        db.execute("INSERT INTO embeddings VALUES(?)", ("bge-m3:" + "1" * 64 + ":1024",))
    return seed


def test_manual_app_copies_only_checked_synthetic_sources(tmp_path, monkeypatch):
    seed = seed_fixture(tmp_path, monkeypatch)
    before = seed.read_bytes()
    target = manual.prepare_database(tmp_path / "work/app-new")
    assert target.is_file() and seed.read_bytes() == before
    with sqlite3.connect(target) as db:
        db.execute("UPDATE revisions SET text='edited test copy'")
    with sqlite3.connect(seed) as db:
        assert db.execute("SELECT text FROM revisions").fetchone()[0] == "합성 원문"
    with pytest.raises(ValueError, match="전용 폴더"):
        manual.prepare_database(tmp_path / "personal")
    with pytest.raises(FileExistsError):
        manual.prepare_database(tmp_path / "work/app-new")


@pytest.mark.parametrize("mutation,match", [
    ("UPDATE revisions SET text='unknown source'", "합성 원문"),
    ("UPDATE jobs SET status='queued'", "미완료"),
    ("UPDATE embeddings SET model_key='other model'", "임베딩 모델")])
def test_incorrect_seed_never_starts_auto_extraction_or_reembedding(tmp_path, monkeypatch, mutation, match):
    seed = seed_fixture(tmp_path, monkeypatch)
    with sqlite3.connect(seed) as db:
        db.execute(mutation)
    with pytest.raises(ValueError, match=match):
        manual.prepare_database(tmp_path / "work/app-no")
    assert not (tmp_path / "work/app-no").exists()


def test_manual_app_cookie_is_distinct_and_viewing_never_calls_models(tmp_path, monkeypatch):
    seed_fixture(tmp_path, monkeypatch)
    class NoModels:
        def extract(self, *a, **kw): pytest.fail("No inference")
        def embed(self, *a, **kw): pytest.fail("No inference")
    app, isolated = manual.make_app(tmp_path / "empty-app", 18765, "baseline",
                                    models=NoModels(), run_worker=False)
    assert not app.state.settings.evaluation_enabled
    assert not app.state.settings.scoped_identity_search
    assert not app.state.settings.verified_source_search
    with TestClient(isolated, base_url="http://127.0.0.1:18765") as client:
        client.cookies.set("pma_session", "ordinary-app-cookie", domain="127.0.0.1", path="/")
        response = client.get("/")
        assert "합성 테스트" in response.text
        response = client.post("/api/v1/session", json={"token": app.state.bootstrap_token},
                               headers={"origin": "http://127.0.0.1:18765"})
        assert response.status_code == 200
        assert "pma_manual_test_18765=" in response.headers["set-cookie"]
        assert client.cookies.get("pma_session") == "ordinary-app-cookie"
        assert client.get("/api/v1/session").status_code == 200


def test_json_to_powershell_bridge_runs_plan_only_without_models(tmp_path):
    shell = shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell7 unavailable")
    config = console.benchmark_config("gpu", "first", "five", "simple", False,
                                      "nonexistent-python-not-run", "offline-user-plan")
    config["Execute"] = False
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    result = subprocess.run([shell, "-NoProfile", "-File", str(console.ROOT / "scripts/run_user_test_job.ps1"),
        "-Configuration", str(path)], capture_output=True, text=True, encoding="utf-8", timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr
    assert "Plan only" in result.stdout
    command = json.loads(result.stdout.splitlines()[-1])
    start = command.index("--cases") + 1
    assert command[start:start + 2] == ["dev_fact", "dev_date"]
    assert "--anchor-templates" in command and "--seed-template" in command
    assert not (console.ROOT / ".local/latency-goal/offline-user-plan").exists()
