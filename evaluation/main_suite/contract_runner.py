"""Execute allowlisted product contracts in a disposable offline test process.

Functional doubles must never contribute to generation/embedding accuracy.
This adapter is called only by explicit evaluation execution, never plan reads.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from .runtime import cancel_point

ROOT = Path(__file__).resolve().parents[2]


def checks_passed(code, checks):
    return bool(code == 0 and checks and all(c["outcome"] == "passed" for c in checks))


def execute_contract_tests(contract, directory, cancelled=None):
    from .behavior_contracts import contracts

    registered = contracts()[contract["variable_id"]]
    if contract != registered:
        raise ValueError("UNREGISTERED_BEHAVIOR_CONTRACT")
    directory.mkdir(parents=True, exist_ok=False)
    report = directory / "checks.json"
    command = [sys.executable, "-m", "pytest", "-q", "-p", "evaluation.main_suite.contract_plugin",
               "--contract-report", str(report.resolve()), "--basetemp", str((directory / "temporary").resolve()),
               *contract["tests"]]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PMA_CONTRACT_OFFLINE": "1"}
    log = directory / "checks.log"
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                   creationflags=0x08000000 if os.name == "nt" else 0)
        try:
            deadline = time.monotonic() + 300
            while True:
                cancel_point(cancelled)
                if time.monotonic() > deadline:
                    raise TimeoutError("BEHAVIOR_CONTRACT_TIMEOUT")
                try:
                    code = process.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
    if not report.exists():
        raise RuntimeError("F-EXECUTION:CONTRACT_REPORT_MISSING")
    checks = json.loads(report.read_text("utf-8"))
    passed = checks_passed(code, checks["checks"])
    return {"probe": {"passed": bool(passed), "unsupported": bool(passed and contract.get("unsupported")),
                       "scope": contract["scope"], "variable_id": contract["variable_id"],
                       "expected_checks": contract["assertions"], "checks": checks["checks"],
                       "model_accuracy_sample": False, "model_mode": "offline_doubles",
                       "support_reference": contract.get("support_reference"), "report": str(report), "log": str(log)}}
