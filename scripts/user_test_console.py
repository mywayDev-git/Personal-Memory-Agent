"""Local, authenticated buttons for manual questions and opt-in synthetic trials."""
import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, StrictBool
from typing import Literal

from .user_test_app import ROOT, WORK
from .user_test_models import ManualModels, listening, ready

ACTIVE = {"starting", "running", "restoring", "cancelling"}


def health_ready():
    try:
        for port in (8081, 8082):
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
                if response.status != 200:
                    return False
        return True
    except OSError:
        return False


def benchmark_config(device, kind, preset, group, pause, python, run):
    if device in {"cpu", "both"} and group == "followup" and preset == "five":
        raise ValueError("CPU 후속 기준은 시간 초과가 확인됐습니다. 이 항목은 빠른 확인으로 실행해 주세요.")
    config = dict(Placement=device, PlanningBaseline=True, CompactJson=True, CompactReview=True,
        SharedCompactFormats=True, ScopedIdentitySearch=True, VerifiedSourceSearch=True,
        GenerationBatchThreads=24, DisableCpuRepacking=True, FixtureSplit="development",
        Cases=["dev_fact", "dev_date"] if group == "simple" else ["dev_pronoun"],
        AnchorTemplates=str(ROOT / ".local/latency-goal/identity-reuse-gpu-pilot/gpu/results.json"),
        SeedTemplate=str(ROOT / ".local/latency-goal/identity-reuse-gpu-pilot/gpu/synthetic-seed.db"),
        PythonExe=python, RunName=run, PauseOrdinaryModels=pause, Execute=True)
    if kind == "first":
        config["ColdInterpretations"] = True
    else:
        config["InterpretationReuse"] = True
    if preset == "quick":
        config["QualityScreen"] = True
    else:
        config["Samples"] = 5
    return config


class State:
    def __init__(self, python=None):
        executable = Path(sys.executable).with_name("python.exe")
        self.python = python or (str(executable) if executable.is_file() else sys.executable)
        self.lock = threading.RLock()
        self.job = None
        self.app_process = None
        self.app_directory = None
        self.app_status = "stopped"
        self.app_profile = None
        self.closed = False
        self.models = ManualModels(ROOT, WORK)
        WORK.mkdir(parents=True, exist_ok=True)

    def snapshot(self):
        with self.lock:
            if self.app_process and self.app_process.poll() is not None:
                self.app_status = "stopped"
            job = dict(self.job) if self.job else None
            if job:
                job.pop("config", None)
            return {"kind": "pma-user-test-console", "job": job,
                    "app_status": self.app_status, "app_profile": self.app_profile,
                    "model_source": self.models.source,
                    "app_url": "http://127.0.0.1:18765/" if self.app_status == "running" else None}

    def stop_app(self):
        with self.lock:
            process, directory = self.app_process, self.app_directory
            if not process or process.poll() is not None:
                self.app_status = "stopped"
                self.models.stop()
                return True
            self.app_status = "stopping"
            directory.with_suffix(".stop").touch()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            return False
        with self.lock:
            self.app_status = "stopped"
            self.models.stop()
        return True

    def open_app(self, profile):
        with self.lock:
            if self.job and self.job["status"] in ACTIVE:
                raise ValueError("속도 비교가 끝난 뒤 직접 질문 앱을 열어 주세요.")
            if self.app_status in {"starting", "stopping"}:
                raise ValueError("앱 준비 또는 종료가 끝날 때까지 기다려 주세요.")
            if self.app_process and self.app_process.poll() is None:
                if self.app_profile != profile:
                    raise ValueError("다른 경로를 사용하려면 직접 질문 앱을 먼저 닫아 주세요.")
                return {"url": "http://127.0.0.1:18765/"}
            self.app_status = "starting"
        try:
            with socket.socket() as check:
                check.bind(("127.0.0.1", 18765))
            generation_port, embedding_port = self.models.ensure()
            directory = WORK / ("app-" + secrets.token_hex(6))
            log = (WORK / (directory.name + ".log")).open("wb")
            try:
                process = subprocess.Popen([self.python, "-u", "-m", "scripts.user_test_app",
                    "--directory", str(directory), "--profile", profile,
                    "--generation-port", str(generation_port), "--embedding-port", str(embedding_port)], cwd=ROOT,
                    stdout=log, stderr=subprocess.STDOUT, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            finally:
                log.close()
            with self.lock:
                self.app_process, self.app_directory, self.app_profile = process, directory, profile
            for _ in range(200):
                if process.poll() is not None:
                    raise ValueError("별도 앱 준비에 실패했습니다. 테스트 도구 폴더의 앱 로그를 확인해 주세요.")
                ready = directory / "ready.json"
                if ready.is_file():
                    value = json.loads(ready.read_text(encoding="utf-8"))
                    with self.lock:
                        self.app_status = "running"
                    return value
                time.sleep(.1)
            # Stop only this owned app; never leave a hidden startup pending.
            directory.with_suffix(".stop").touch()
            raise ValueError("앱 준비 시간이 지났습니다. 종료 후 다시 열어 주세요.")
        except Exception:
            with self.lock:
                self.app_status = "stopping" if self.app_process and self.app_process.poll() is None else "stopped"
                if self.app_status == "stopped":
                    self.models.stop()
            raise

    def start(self, data):
        run = "user-" + datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3)
        config = benchmark_config(data.device, data.kind, data.preset, data.group,
                                  data.pause_models, self.python, run)
        if not data.pause_models:
            raise ValueError("16GB 비교 환경에서는 일반 모델 서버의 임시 중지·복구 선택이 필요합니다. 체크한 뒤 실행해 주세요.")
        with self.lock:
            if self.job and self.job["status"] in ACTIVE:
                raise ValueError("이미 비교가 실행 중입니다.")
            if self.app_status in {"starting", "stopping"}:
                raise ValueError("직접 질문 앱의 준비·종료가 끝난 뒤 실행해 주세요.")
            self.job = {"run": run, "status": "starting", "cancel_requested": False,
                        "message": "비교 준비 중", "config": config}
        threading.Thread(target=self._run, args=(config,), daemon=True).start()
        return {"run": run}

    def cancel(self):
        with self.lock:
            if self.job and self.job["status"] in ACTIVE:
                self.job.update(cancel_requested=True, status="cancelling",
                    message="중단 요청됨 · 현재 질문 처리 뒤 서버를 복구합니다")
        return {"requested": True}

    def _run(self, config):
        run = config["RunName"]
        directory = WORK / run
        try:
            directory.mkdir(exist_ok=False)
            if not self.stop_app():
                raise ValueError("직접 질문 앱이 아직 응답 중입니다. 대화를 취소하고 앱을 닫은 뒤 다시 비교해 주세요.")
            with self.lock:
                if self.job["cancel_requested"]:
                    self.job.update(status="cancelled", message="실행 전 중단됨 · 모델을 구동하지 않았습니다")
                    return
            if ready(8081) and ready(8082):
                config["PauseOrdinaryModels"] = True
            elif listening(8081) or listening(8082):
                raise ValueError("일반 서버 일부만 준비돼 측정을 시작하지 않았습니다.")
            else:
                config["PauseOrdinaryModels"] = False  # Nothing to pause; own trial models only.
            config_file = directory / "configuration.json"
            config_file.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            shell = shutil.which("pwsh")
            if not shell:
                raise ValueError("PowerShell 7이 필요합니다. 기존 프로젝트 실행 환경을 확인해 주세요.")
            with (directory / "execution.log").open("wb") as log:
                process = subprocess.Popen([shell, "-NoLogo", "-NoProfile", "-File",
                    str(ROOT / "scripts/run_user_test_job.ps1"), "-Configuration", str(config_file)],
                    cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, stdout=log,
                    stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                with self.lock:
                    if not self.job["cancel_requested"]:
                        self.job.update(status="running", message="측정 중 · 일반 AI는 끝난 뒤 복구됩니다")
                while process.poll() is None:
                    with self.lock:
                        cancel = self.job["cancel_requested"]
                    if cancel:
                        for mode in ("cpu", "gpu"):
                            path = ROOT / ".local/latency-goal" / run / mode
                            if path.is_dir():
                                (path / "cancel.request").touch()
                    time.sleep(.25)
            with self.lock:
                cancelled = self.job["cancel_requested"]
                self.job.update(status="cancelled" if cancelled else "finished" if process.returncode == 0 else "failed",
                    message="중단 후 복구 절차 종료 · 결과 확인" if cancelled else
                    "비교 실행 종료 · 품질·실패·서버 복구 결과를 확인해 주세요" if process.returncode == 0 else
                    "실행 실패 · 복구 상태와 실행 로그를 확인해 주세요")
        except Exception as exc:
            with self.lock:
                self.job.update(status="failed", message=str(exc) if isinstance(exc, ValueError)
                                else "실행기 오류 · 테스트 폴더의 로그를 확인해 주세요")


class Trial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device: Literal["cpu", "gpu", "both"] = "gpu"
    kind: Literal["first", "repeat"] = "first"
    preset: Literal["quick", "five"] = "quick"
    group: Literal["simple", "followup"] = "simple"
    pause_models: StrictBool = False


class AppChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Literal["baseline", "candidate"] = "baseline"


def create_console(state=None, *, port=18760, token=None):
    state = state or State()
    token = token or secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{port}"
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.tool, app.state.token = state, token

    @app.middleware("http")
    async def auth(request: Request, call_next):
        if request.headers.get("host") != f"127.0.0.1:{port}":
            return JSONResponse({"message": "허용하지 않은 호스트"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"message": "다른 사이트에서 실행할 수 없습니다"}, status_code=403)
        supplied = request.headers.get("x-test-token", "")
        protected = request.url.path.startswith(("/api/", "/results/", "/report/", "/archive/", "/job-log/"))
        valid = secrets.compare_digest(supplied, token)
        if protected and not valid and (request.method != "GET" or not secrets.compare_digest(
                request.cookies.get("pma_test_console", ""), token)):
            return JSONResponse({"message": "테스트 실행 파일에서 화면을 다시 열어 주세요"}, status_code=401)
        if request.method != "GET" and (not valid or request.headers.get("origin") != origin or
                request.headers.get("content-type", "").split(";")[0] != "application/json"):
            return JSONResponse({"message": "로컬 실행 버튼에서 요청해 주세요"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def page():
        return FileResponse(ROOT / "scripts/user_test_console.html")

    @app.post("/api/session")
    def session():
        response = JSONResponse({"ready": True})
        response.set_cookie("pma_test_console", token, httponly=True, samesite="strict")
        return response

    @app.get("/api/status")
    def status():
        return state.snapshot()

    @app.get("/api/examples")
    def examples():
        value = json.loads((ROOT / "evaluation/source_completion_cases.json").read_text(encoding="utf-8"))
        return {"items": [{"question": c["question"], "anchor": c.get("anchor")}
                          for c in value["splits"]["confirmation"]["cases"].values()]}

    @app.post("/api/open-app")
    def open_app(data: AppChoice):
        try:
            return state.open_app(data.profile)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/stop-app")
    def stop_app():
        if state.snapshot()["app_status"] == "starting":
            raise HTTPException(409, "모델·앱 준비가 끝난 뒤 닫아 주세요.")
        return {"stopped": state.stop_app()}

    @app.post("/api/run")
    def run(data: Trial):
        try:
            return state.start(data)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/cancel")
    def cancel():
        return state.cancel()

    def results_root(run):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run):
            raise HTTPException(400)
        return ROOT / ".local/latency-goal" / run

    @app.get("/api/results/{run}")
    def results(run: str):
        from .summarize_identity_optimization import summarize
        folder = results_root(run)
        groups, answers = [], []
        for mode in ("cpu", "gpu"):
            path = folder / mode / "results.json"
            if path.is_file():
                try:
                    data = summarize(path)
                    groups.extend({"placement": mode, **g} for g in data["groups"])
                except (ValueError, OSError):
                    pass  # The writer may be replacing its current snapshot.
            if (folder / mode / "answers.html").is_file():
                answers.append({"placement": mode, "url": f"/results/{run}/{mode}/answers.html"})
        restoration = None
        health = folder / "ordinary-models-health.json"
        if health.is_file():
            restoration = json.loads(health.read_text(encoding="utf-8-sig"))
        return {"groups": groups, "answers": answers, "restoration": restoration,
                "log_url": f"/job-log/{run}" if (WORK / run / "execution.log").is_file() else None}

    @app.get("/job-log/{run}")
    def job_log(run: str):
        results_root(run)  # Apply the same strict run-name validation.
        path = WORK / run / "execution.log"
        if not path.is_file():
            raise HTTPException(404)
        with path.open("rb") as log:
            log.seek(0, 2)
            log.seek(max(0, log.tell() - 65536))
            return PlainTextResponse(log.read().decode("utf-8", errors="replace"))

    @app.get("/results/{run}/{path:path}")
    def artifact(run: str, path: str):
        folder = results_root(run).resolve()
        file = (folder / path).resolve()
        if not file.is_relative_to(folder) or file.suffix not in {".html", ".json", ".rst"} or not file.is_file():
            raise HTTPException(404)
        return FileResponse(file)

    @app.get("/report/{name}")
    def report(name: str):
        allowed = {"identity_evidence_optimization.html", "identity_evidence_optimization_results.rst",
                   "identity_evidence_optimization_summary.json"}
        if name not in allowed:
            raise HTTPException(404)
        if name.endswith(".html"):
            text = (ROOT / "docs" / name).read_text(encoding="utf-8").replace(
                "../.local/identity-optimization-review/index.html", "/archive/index")
            return HTMLResponse(text)
        return FileResponse(ROOT / "docs" / name)

    @app.get("/archive/index")
    def archived_index():
        path = ROOT / ".local/identity-optimization-review/index.html"
        if not path.is_file():
            raise HTTPException(404)
        text = path.read_text(encoding="utf-8").replace(
            (ROOT / ".local/latency-goal").as_uri() + "/", "/results/")
        return HTMLResponse(text)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    ready = WORK / "console.json"
    if ready.is_file():
        try:
            previous = json.loads(ready.read_text(encoding="utf-8"))
            req = urllib.request.Request(previous["origin"] + "/api/status",
                                         headers={"x-test-token": previous["token"]})
            with urllib.request.urlopen(req, timeout=2) as response:
                if json.load(response).get("kind") == "pma-user-test-console":
                    if not args.no_browser:
                        webbrowser.open(previous["url"])
                    return
        except (OSError, ValueError, KeyError):
            pass
    state = State()
    app = create_console(state)
    import uvicorn
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=18760,
        access_log=False, log_level="warning"))

    @app.post("/api/exit")
    def exit_console():
        if state.snapshot()["app_status"] in {"starting", "stopping"}:
            raise HTTPException(409, "앱 준비·종료가 끝난 뒤 도구를 종료해 주세요.")
        if state.snapshot()["job"] and state.snapshot()["job"]["status"] in ACTIVE:
            raise HTTPException(409, "측정을 중단하고 복구가 끝난 뒤 종료해 주세요.")
        if not state.stop_app():
            raise HTTPException(409, "직접 질문이 끝난 뒤 종료해 주세요.")
        server.should_exit = True
        return {"closing": True}

    def opened():
        while not server.started and not server.should_exit:
            time.sleep(.1)
        if server.started:
            value = {"origin": "http://127.0.0.1:18760", "token": app.state.token,
                     "url": "http://127.0.0.1:18760/#token=" + app.state.token, "pid": os.getpid()}
            ready.write_text(json.dumps(value), encoding="utf-8")
            if not args.no_browser:
                webbrowser.open(value["url"])
    threading.Thread(target=opened, daemon=True).start()
    try:
        server.run()
    finally:
        state.stop_app()
        if ready.is_file() and json.loads(ready.read_text(encoding="utf-8")).get("pid") == os.getpid():
            ready.unlink()


if __name__ == "__main__":
    main()
