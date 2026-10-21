"""Dashboard controls with fake child processes; never run an actual evaluation."""

import json
import shutil
import subprocess
from dataclasses import replace
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.requests import Request

from evaluation.main_suite import runner, runtime
from pma.evaluation_api import StartEvaluation
from pma.evaluation_execution import EvaluationExecutor, ExecutionError
from pma.settings import AppSettings


class Process:
    pid = 12345
    returncode = None

    def poll(self):
        return self.returncode


@pytest.fixture
def control(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    server = tmp_path / "server.exe"
    server.write_bytes(b"fake server")
    model = tmp_path / "fake-model.gguf"
    model.write_bytes(b"not a real model")
    spec = {"path": str(model), "sha256": "fixed", "context": 16384, "threads": 0, "gpu_layers": 0}
    manifest = tmp_path / "models.json"
    manifest.write_text(json.dumps({"generation": {"baseline": spec, "candidate": spec},
                                    "embedding": {"baseline": spec, "other": spec}}), "utf-8")
    settings = replace(AppSettings(), data_dir=tmp_path / "app", evaluation_enabled=True)
    calls, process = [], Process()
    def spawn(command, **kwargs):
        calls.append((command, kwargs))
        return process
    executor = EvaluationExecutor(settings, root=root, models=manifest, server=server, popen=spawn)
    return SimpleNamespace(executor=executor, calls=calls, process=process, settings=settings,
                           root=root, manifest=manifest, server=server)


def test_options_and_status_do_not_launch_or_create_a_job(control):
    assert control.executor.status()["status"] == "idle"
    options = control.executor.options()
    assert options["profiles"]["core"]["automated"] == options["profiles"]["core"]["cases"]
    assert options["profiles"]["core"]["review"] == 0
    assert options["server_available"]
    assert not control.calls
    assert not control.executor.state_path.exists()


def test_start_uses_only_registered_models_and_is_idempotent(control):
    value = control.executor.start("request-1", "compare", ["baseline", "candidate"], ["baseline"])
    assert value["status"] == "running"
    command, kwargs = control.calls[0]
    assert command[1:4] == ["-m", "evaluation.main_suite", "--execute"]
    assert kwargs["cwd"] == control.root
    assert "shell" not in kwargs
    output = Path(command[command.index("--output") + 1])
    assert output.parent == control.root / ".local/main-suite"
    selected = json.loads((output / "models.json").read_text("utf-8"))
    assert set(selected["generation"]) == {"baseline", "candidate"}
    assert set(selected["embedding"]) == {"baseline"}
    assert control.executor.start("request-1", "compare", ["baseline", "candidate"], ["baseline"])["id"] == value["id"]
    assert len(control.calls) == 1
    assert not (control.settings.data_dir / "memory.db").exists()


def test_active_job_blocks_duplicate_and_conflicting_requests(control):
    control.executor.start("one", "core", ["baseline"], ["baseline"])
    with pytest.raises(ExecutionError, match="진행 중"):
        control.executor.start("two", "core", ["baseline"], ["baseline"])
    with pytest.raises(ExecutionError, match="이미 사용"):
        control.executor.start("one", "final", ["candidate"], ["baseline"])
    assert len(control.calls) == 1


@pytest.mark.parametrize("profile,generation,embedding", [
    ("invalid", ["baseline"], ["baseline"]),
    ("final", ["C:/arbitrary-model.gguf"], ["baseline"]),
    ("compare", ["candidate"], ["baseline"]),
    ("compare", ["baseline"], ["baseline"]),
    ("compare", ["baseline", "baseline"], ["baseline"]),
    ("final", [], ["baseline"]),
])
def test_invalid_selection_never_spawns(control, profile, generation, embedding):
    with pytest.raises(ExecutionError):
        control.executor.start("request", profile, generation, embedding)
    assert not control.calls


def test_missing_program_never_starts(control):
    control.executor.server = control.root / "missing.exe"
    with pytest.raises(ExecutionError) as error:
        control.executor.start("request", "core", ["baseline"], ["baseline"])
    assert error.value.code == "SERVER_NOT_FOUND"
    assert not control.calls


def test_cancel_is_cooperative_and_preserves_outputs(control):
    job = control.executor.start("one", "core", ["baseline"], ["baseline"])
    output = Path(control.executor.state["output"])
    result = output / "preserved.json"
    result.write_text('{"finished":1}', "utf-8")
    assert control.executor.cancel(job["id"])["status"] == "cancelling"
    assert (output / "cancel.request").exists()
    assert result.exists()
    # Fake child deliberately has no terminate/kill method.
    assert control.process.poll() is None
    (output / "execution-status.json").write_text('{"status":"cancelled"}', "utf-8")
    assert control.executor.status()["status"] == "cancelled"
    assert result.exists()


def test_page_reload_recovers_active_job_without_starting_again(control, monkeypatch):
    job = control.executor.start("one", "core", ["baseline"], ["baseline"])
    monkeypatch.setattr("pma.evaluation_execution.alive", lambda pid: True)
    restored = EvaluationExecutor(control.settings, root=control.root, models=control.manifest,
                                  server=control.server, popen=lambda *a, **k: pytest.fail("auto-start"))
    assert restored.status()["id"] == job["id"]
    assert restored.status()["status"] == "running"
    with pytest.raises(ExecutionError):
        restored.start("two", "core", ["baseline"], ["baseline"])
    restored.cancel(job["id"])
    assert len(control.calls) == 1


def test_failed_child_is_not_shown_as_success(control):
    control.executor.start("one", "core", ["baseline"], ["baseline"])
    control.process.returncode = 1
    assert control.executor.status()["status"] == "failed"


def test_shutdown_requests_cancellation_only_for_current_job(control):
    job = control.executor.start("one", "core", ["baseline"], ["baseline"])
    control.executor.shutdown()
    assert control.executor.status()["id"] == job["id"]
    assert control.executor.status()["status"] == "cancelling"
    assert len(control.calls) == 1


@pytest.mark.parametrize("extra", [{"output":"C:/private"}, {"server":"arbitrary.exe"}, {"execute": True}])
def test_api_does_not_accept_arbitrary_paths_or_arguments(extra):
    with pytest.raises(ValidationError):
        StartEvaluation(request_id="test", **extra)


def routes_of(app):
    routes = []
    for route in app.routes:
        routes.extend(route.original_router.routes if hasattr(route, "original_router") else [route])
    return {(r.path, method): r for r in routes if hasattr(r, "path") for method in (getattr(r, "methods", None) or [])}


def finish_without_io(coroutine):
    # All test awaitables are immediate; avoids environment-dependent event-loop/socket setup.
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("unexpected asynchronous IO in offline middleware test")


def test_real_session_origin_and_csrf_protect_start_action(control, monkeypatch):
    from pma import evaluation_api
    from pma.web import SessionInput, create_app

    monkeypatch.setattr(evaluation_api, "EvaluationExecutor", lambda settings: control.executor)
    app = create_app(control.settings, run_worker=False)
    routes = routes_of(app)
    assert routes["/api/eval/execution/options", "GET"].endpoint()["server_available"]
    assert not control.calls
    response = Response()
    session = routes["/api/v1/session", "POST"].endpoint(SessionInput(token=app.state.bootstrap_token), response)
    cookie = SimpleCookie(response.headers["set-cookie"])["pma_session"].value
    middleware = next(m.kwargs["dispatch"] for m in app.user_middleware if "dispatch" in m.kwargs)
    payload = json.dumps({"request_id": "ui-click", "profile": "core"}).encode()
    async def next_handler(request):
        data = StartEvaluation.model_validate_json(await request.body())
        return JSONResponse(routes["/api/eval/execution", "POST"].endpoint(data), status_code=202)
    def request(headers):
        async def receive():
            return {"type":"http.request", "body":payload, "more_body":False}
        return Request({"type":"http", "method":"POST", "path":"/api/eval/execution", "query_string":b"",
                        "headers":[(k.encode(),v.encode()) for k,v in headers.items()]}, receive=receive)
    base = {"host":"127.0.0.1:8765", "origin":"http://127.0.0.1:8765", "content-type":"application/json"}
    assert finish_without_io(middleware(request(base), next_handler)).status_code == 401
    logged = {**base, "cookie":f"pma_session={cookie}"}
    assert finish_without_io(middleware(request(logged), next_handler)).status_code == 403
    correct = {**logged, "x-csrf-token":session["csrf"]}
    assert finish_without_io(middleware(request({**correct, "origin":"https://other.example"}), next_handler)).status_code == 403
    assert not control.calls
    assert finish_without_io(middleware(request(correct), next_handler)).status_code == 202
    assert len(control.calls) == 1


def test_api_maps_busy_error_to_409(control, monkeypatch):
    from fastapi import FastAPI

    from pma import evaluation_api
    monkeypatch.setattr(evaluation_api, "EvaluationExecutor", lambda settings: control.executor)
    app = FastAPI()
    evaluation_api.install(app, control.settings, Path("pma/static"))
    route = routes_of(app)["/api/eval/execution", "POST"]
    route.endpoint(StartEvaluation(request_id="one"))
    with pytest.raises(HTTPException) as error:
        route.endpoint(StartEvaluation(request_id="two"))
    assert error.value.status_code == 409


def test_original_text_display_requires_session_and_csrf_without_starting_tests(control, monkeypatch):
    from pma import evaluation_api
    from pma.web import SessionInput, create_app

    monkeypatch.setattr(evaluation_api, "EvaluationExecutor", lambda settings: control.executor)
    app = create_app(control.settings, run_worker=False)
    routes = routes_of(app)
    response = Response()
    session = routes["/api/v1/session", "POST"].endpoint(SessionInput(token=app.state.bootstrap_token), response)
    cookie = SimpleCookie(response.headers["set-cookie"])["pma_session"].value
    middleware = next(m.kwargs["dispatch"] for m in app.user_middleware if "dispatch" in m.kwargs)
    async def next_handler(request):
        data = evaluation_api.EvaluationDisplay.model_validate_json(await request.body())
        return JSONResponse(routes["/api/eval/display", "PUT"].endpoint(data))
    def request(headers):
        async def receive():
            return {"type":"http.request", "body":b'{"show_originals":true}', "more_body":False}
        return Request({"type":"http", "method":"PUT", "path":"/api/eval/display", "query_string":b"",
                        "headers":[(k.encode(),v.encode()) for k,v in headers.items()]}, receive=receive)
    base = {"host":"127.0.0.1:8765", "origin":"http://127.0.0.1:8765", "content-type":"application/json"}
    assert finish_without_io(middleware(request(base), next_handler)).status_code == 401
    logged = {**base, "cookie":f"pma_session={cookie}"}
    assert finish_without_io(middleware(request(logged), next_handler)).status_code == 403
    assert not routes["/api/eval/display", "GET"].endpoint()["show_originals"]
    correct = {**logged, "x-csrf-token":session["csrf"]}
    assert finish_without_io(middleware(request(correct), next_handler)).status_code == 200
    assert routes["/api/eval/display", "GET"].endpoint()["show_originals"]
    assert not control.calls


@pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
def test_runner_persists_completion_without_running_a_model(tmp_path, monkeypatch, status):
    monkeypatch.setattr(runner, "checked_root", lambda path: path.resolve())
    def fake(args):
        if status == "cancelled":
            raise KeyboardInterrupt()
        if status == "failed":
            raise ValueError("synthetic failure")
        return 0
    monkeypatch.setattr(runner, "_main", fake)
    output = tmp_path / "run"
    arguments = ["--execute", "--output", str(output), "--completion-file", str(output / "execution-status.json")]
    if status == "failed":
        with pytest.raises(ValueError):
            runner.main(arguments)
    else:
        assert runner.main(arguments) == (130 if status == "cancelled" else 0)
    assert json.loads((output / "execution-status.json").read_text("utf-8"))["status"] == status


def test_cancellation_during_model_startup_cleans_only_owned_child(tmp_path, monkeypatch):
    from contextlib import nullcontext
    class ServerProcess(Process):
        terminated = False
        def terminate(self):
            self.terminated = True
        def wait(self, timeout=None):
            self.returncode = 0
    process, checks = ServerProcess(), 0
    monkeypatch.setattr(runtime.socket, "socket", lambda: nullcontext(SimpleNamespace(bind=lambda *a: None)))
    commands = []
    def spawn(command, **kwargs):
        commands.append(command)
        return process
    monkeypatch.setattr(runtime.subprocess, "Popen", spawn)
    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 3
    spec = {"path":"fake-model", "context":16384, "gpu_layers":0, "threads":0}
    with pytest.raises(KeyboardInterrupt):
        with runtime.servers("fake-server", spec, spec, tmp_path, cancelled=cancelled):
            pytest.fail("server should not be ready")
    assert process.terminated
    assert "--no-op-offload" in commands[0] and "--no-kv-offload" in commands[0]
    assert commands[0][commands[0].index("--device") + 1] == "none"


def test_dashboard_controls_offline_dom():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for offline UI checks")
    result = subprocess.run([node, str(Path(__file__).with_name("evaluation_execution_ui.mjs"))],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
