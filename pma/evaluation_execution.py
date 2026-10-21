"""Explicit dashboard actions supervise an isolated evaluation subprocess.

No models are loaded by imports, construction, options, or status queries.
Cancellation is cooperative: only the child owns/cleans its model processes.
"""

import ctypes
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from evaluation.main_suite.catalog import DATA, PROFILES, select_cases
from evaluation.schema import content_hash

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {"running", "cancelling", "detached"}


class ExecutionError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def now():
    return datetime.now(timezone.utc).isoformat()


def alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class EvaluationExecutor:
    def __init__(self, settings, *, popen=subprocess.Popen, root=ROOT, models=None, server=None):
        self.settings, self.root, self.popen = settings, Path(root).resolve(), popen
        self.models_path = Path(models or os.getenv("PMA_EVALUATION_MODELS", str(DATA / "models.json")))
        self.server = Path(server or os.getenv("PMA_EVALUATION_SERVER", "C:/llama.cpp/llama-server.exe"))
        self.state_path = settings.data_dir / "evaluation" / "execution.json"
        self.lock, self.process = threading.RLock(), None
        self.state, self.state_error = None, False
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text("utf-8"))
                expected = self.root / ".local/main-suite" / ("ui-" + state["id"])
                if (len(state["id"]) != 32 or any(c not in "0123456789abcdef" for c in state["id"])
                        or Path(state["output"]).resolve() != expected.resolve()
                        or state["profile"] not in PROFILES
                        or state["status"] not in ACTIVE | {"completed", "failed", "cancelled", "interrupted"}):
                    raise ValueError()
                self.state = state
            except (OSError, ValueError, TypeError, KeyError):
                self.state_error = True

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False), "utf-8")
        temporary.replace(self.state_path)

    def _registry(self):
        try:
            registry = json.loads(self.models_path.read_text("utf-8"))
            if any(not isinstance(registry.get(role), dict) or not registry[role] for role in ("generation", "embedding")):
                raise ValueError()
            for role in ("generation", "embedding"):
                for name, spec in registry[role].items():
                    if "--" in name or not name.replace("-", "").replace("_", "").isalnum():
                        raise ValueError()
                    if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
                        raise ValueError()
            return registry
        except (OSError, ValueError, TypeError):
            raise ExecutionError("INVALID_REGISTRY", "등록된 평가 모델 목록을 읽을 수 없습니다.", 503) from None

    def options(self):
        registry = self._registry()
        profiles = {}
        for name, profile in PROFILES.items():
            selected = select_cases(name)
            profiles[name] = {**profile, "cases": len(selected),
                              "automated": sum(c["adapter"] != "review" for c in selected),
                              "review": sum(c["adapter"] == "review" for c in selected),
                              "partial_coverage": sum(bool(c.get("coverage_gaps")) for c in selected)}
        return {"profiles": profiles, "server_available": self.server.is_file() and not self.state_error,
                "generation": [{"id": name, "label": Path(spec["path"]).name,
                                "available": Path(spec["path"]).is_file()} for name, spec in registry["generation"].items()],
                "embedding": [{"id": name, "label": Path(spec["path"]).name,
                               "available": Path(spec["path"]).is_file()} for name, spec in registry["embedding"].items()],
                "policy": "실행 버튼을 누른 경우에만 합성 데이터와 별도 모델 서버로 평가합니다."}

    def _reconcile(self):
        if not self.state or self.state["status"] not in ACTIVE:
            return
        output = Path(self.state["output"])
        marker = output / "execution-status.json"
        if marker.exists():
            value = json.loads(marker.read_text("utf-8"))
            if value.get("status") in {"completed", "failed", "cancelled"}:
                self.state.update(status=value["status"], finished_at=value.get("finished_at", now()))
                self._close_incomplete_runs()
                self._save()
                return
        returncode = self.process.poll() if self.process is not None else None
        if self.process is not None and returncode is not None:
            self.state.update(status="cancelled" if returncode == 130 else "completed" if returncode == 0 else "failed",
                              finished_at=now())
            self._close_incomplete_runs()
            self._save()
        elif self.process is None and not alive(self.state.get("pid")):
            self.state.update(status="interrupted", finished_at=now())
            self._close_incomplete_runs()
            self._save()

    def _close_incomplete_runs(self):
        if self.state["status"] not in {"failed", "cancelled", "interrupted"}:
            return
        from evaluation.repository import Repository
        destination = self.settings.data_dir / "evaluation/evaluation.db"
        if not destination.exists():
            return
        repo = Repository(destination)
        prefix = str(destination.resolve()) + ":"
        for path in Path(self.state["output"]).glob("*/published.json"):
            for key, rid in json.loads(path.read_text("utf-8")).items():
                if key.startswith(prefix) and repo.get_run(rid)["status"] in {"pending", "running"}:
                    repo.update_run_status(rid, "cancelled" if self.state["status"] == "cancelled" else "failed",
                                           "EVALUATION_PROCESS_INTERRUPTED")

    def status(self):
        with self.lock:
            self._reconcile()
            if self.state_error:
                return {"status": "unavailable", "run_ids": []}
            if not self.state:
                return {"status": "idle", "run_ids": []}
            # Only public job metadata and authorized dashboard result IDs leave this controller.
            value = {key: self.state.get(key) for key in (
                "id", "status", "profile", "generation", "embedding", "started_at", "finished_at")}
            run_ids = []
            for path in sorted(Path(self.state["output"]).glob("*/published.json"), key=lambda p: p.stat().st_mtime):
                mapping = json.loads(path.read_text("utf-8"))
                destination = str((self.settings.data_dir / "evaluation/evaluation.db").resolve()) + ":"
                run_ids.extend(rid for key, rid in mapping.items() if key.startswith(destination))
            value["run_ids"] = list(dict.fromkeys(run_ids))
            return value

    def start(self, request_id, profile, generation, embedding):
        with self.lock:
            self._reconcile()
            if self.state_error:
                raise ExecutionError("INVALID_EXECUTION_STATE", "이전 평가 실행 정보를 확인할 수 없습니다.", 503)
            registry = self._registry()
            if profile not in PROFILES:
                raise ExecutionError("INVALID_PROFILE", "테스트 범위를 선택해 주세요.")
            if profile in {"core", "extended"}:
                generation, embedding = ["baseline"], ["baseline"]
            selected = {"generation": generation, "embedding": embedding}
            for role, names in selected.items():
                if not names or len(set(names)) != len(names) or not set(names) <= registry[role].keys():
                    raise ExecutionError("INVALID_CANDIDATES", "등록된 모델을 선택해 주세요.")
            if profile == "compare" and any("baseline" not in names for names in selected.values()):
                raise ExecutionError("BASELINE_REQUIRED", "모델 비교에는 기준 모델을 함께 선택해 주세요.")
            if profile == "compare" and sum(len(names) for names in selected.values()) < 3:
                raise ExecutionError("COMPARISON_CANDIDATE_REQUIRED", "비교할 다른 모델을 하나 이상 선택해 주세요.")
            fingerprint = content_hash({"profile": profile, **selected})
            if self.state and self.state.get("request_id") == request_id:
                if self.state["fingerprint"] != fingerprint:
                    raise ExecutionError("REQUEST_CONFLICT", "이미 사용한 실행 요청입니다.", 409)
                return self.status()
            if self.state and self.state["status"] in ACTIVE:
                raise ExecutionError("EVALUATION_BUSY", "진행 중인 테스트를 마치거나 중단한 후 다시 실행해 주세요.", 409)
            if not self.server.is_file():
                raise ExecutionError("SERVER_NOT_FOUND", "평가용 모델 실행 프로그램을 찾을 수 없습니다.", 503)
            for role, names in selected.items():
                for name in names:
                    if not Path(registry[role][name]["path"]).is_file():
                        raise ExecutionError("MODEL_NOT_FOUND", "선택한 모델 파일을 찾을 수 없습니다.", 503)
            job_id = uuid4().hex
            output = self.root / ".local/main-suite" / ("ui-" + job_id)
            if not output.resolve().is_relative_to(self.root / ".local/main-suite"):
                raise ExecutionError("UNSAFE_OUTPUT_PATH", "평가 전용 저장 위치를 사용할 수 없습니다.", 503)
            personal = self.settings.data_dir.resolve()
            if output.resolve().is_relative_to(personal) or personal.is_relative_to(output.resolve()):
                raise ExecutionError("UNSAFE_OUTPUT_PATH", "개인 데이터와 평가 실행 위치는 분리되어야 합니다.", 503)
            output.mkdir(parents=True, exist_ok=False)
            manifest = {role: {name: registry[role][name] for name in names} for role, names in selected.items()}
            models_path = output / "models.json"
            models_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8")
            command = [sys.executable, "-m", "evaluation.main_suite", "--execute", "--profile", profile,
                       "--models", str(models_path), "--server", str(self.server), "--output", str(output),
                       "--publish-to", str(self.settings.data_dir / "evaluation/evaluation.db"),
                       "--cancel-file", str(output / "cancel.request"),
                       "--completion-file", str(output / "execution-status.json")]
            self.state = {"id": job_id, "request_id": request_id, "fingerprint": fingerprint,
                          "profile": profile, **selected, "pid": None, "output": str(output),
                          "status": "running", "started_at": now(), "finished_at": None}
            self._save()  # A writable control record is required before launching anything.
            with (output / "execution.log").open("ab") as log:
                try:
                    process = self.popen(command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT,
                                         creationflags=0x08000000 if os.name == "nt" else 0)
                except OSError:
                    self.state.update(status="failed", finished_at=now())
                    self._save()
                    raise ExecutionError("START_FAILED", "평가를 시작하지 못했습니다. 다시 시도해 주세요.", 503) from None
            self.process = process
            self.state["pid"] = process.pid
            try:
                self._save()
            except OSError:
                (output / "cancel.request").write_text("실행 정보 저장 오류로 중단을 요청했습니다.", "utf-8")
                self.state["status"] = "cancelling"
                raise ExecutionError("CONTROL_STORAGE_FAILED", "실행 정보를 저장하지 못해 중단을 요청했습니다.", 503) from None
            return self.status()

    def cancel(self, job_id):
        with self.lock:
            self._reconcile()
            if not self.state or self.state["id"] != job_id:
                raise ExecutionError("JOB_NOT_FOUND", "해당 평가 실행을 찾을 수 없습니다.", 404)
            if self.state["status"] in ACTIVE:
                (Path(self.state["output"]) / "cancel.request").write_text("사용자가 중단을 요청했습니다.", "utf-8")
                self.state["status"] = "cancelling"
                self._save()
            return self.status()

    def shutdown(self):
        with self.lock:
            if self.state and self.state["status"] in ACTIVE:
                self.cancel(self.state["id"])
