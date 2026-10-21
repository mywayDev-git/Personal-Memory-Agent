import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario", ["plan", "failure", "restore-first-failure"])
def test_latency_goal_requires_execute_and_restores_owned_servers(tmp_path, scenario):
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell 7 unavailable")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(Path("scripts/run_latency_goal.ps1"), scripts / "run_latency_goal.ps1")
    fake = tmp_path / "fake-python.ps1"
    fake.write_text("$global:LASTEXITCODE = 1\n", encoding="utf-8")
    check = Path(__file__).with_name("latency_goal_launcher.ps1").resolve()
    result = subprocess.run([executable, "-NoProfile", "-File", str(check),
                             "-Root", str(tmp_path), "-Scenario", scenario],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "latency goal launcher passed" in result.stdout

