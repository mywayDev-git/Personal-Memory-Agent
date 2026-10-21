import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario", ["plan", "failure", "restore-first-failure", "unset"])
def test_latency_goal_requires_execute_and_restores_owned_servers(tmp_path, scenario):
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell 7 unavailable")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    # Even a lost mock cannot select the real ordinary model servers.
    launcher = Path("scripts/run_latency_goal.ps1").read_text(encoding="utf-8")
    launcher = launcher.replace(r"C:\llama.cpp\llama-server.exe", r"C:\pma-test-only\llama-server.exe")
    (scripts / "run_latency_goal.ps1").write_text(launcher, encoding="utf-8")
    fake = tmp_path / "fake-python.ps1"
    fake.write_text("[Environment]::GetEnvironmentVariable('LLAMA_ARG_REPACK', 'Process') | "
                    "Set-Content (Join-Path $PSScriptRoot 'during-trial.txt')\n"
                    "$global:LASTEXITCODE = 1\n", encoding="utf-8")
    check = Path(__file__).with_name("latency_goal_launcher.ps1").resolve()
    result = subprocess.run([executable, "-NoProfile", "-File", str(check),
                             "-Root", str(tmp_path), "-Scenario", scenario],
                            capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "latency goal launcher passed" in result.stdout

