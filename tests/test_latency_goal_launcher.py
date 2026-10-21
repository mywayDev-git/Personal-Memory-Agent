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


def test_baseline_only_plan_cannot_include_or_start_a_candidate():
    import json
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell 7 unavailable")
    result = subprocess.run([executable, "-NoProfile", "-File", "scripts/run_latency_goal.ps1",
                             "-Placement", "cpu", "-BaselineOnly"],
                            capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
    command = json.loads(next(line for line in result.stdout.splitlines() if line.startswith("[")))
    start = command.index("--variants") + 1
    assert command[start:start + 2] == ["current", "--candidate-options"]
    assert command[command.index("--baseline-options") + 1:] == ["compact_ids", "source_facts", "--cases", "simple_search", "simple_answer"]
    warm = subprocess.run([executable, "-NoProfile", "-File", "scripts/run_latency_goal.ps1",
                           "-BaselineOnly", "-InterpretationReuse"],
                          capture_output=True, text=True, encoding="utf-8", timeout=20, check=True)
    command = json.loads(next(line for line in warm.stdout.splitlines() if line.startswith("[")))
    assert command[command.index("--baseline-options") + 1:][:3] == ["compact_ids", "source_facts", "interpretation_cache"]


def test_candidate_only_plan_keeps_exact_requested_profile_and_anchor_provenance():
    import json
    executable = shutil.which('pwsh')
    if executable is None:
        pytest.skip('PowerShell 7 unavailable')
    result = subprocess.run([executable, '-NoProfile', '-File', 'scripts/run_latency_goal.ps1',
        '-CandidateOnly', '-IntermediatePlanning', '-ContextShortcut', '-AnchorTemplates', 'saved/results.json'],
        capture_output=True, text=True, encoding='utf-8', timeout=20, check=True)
    command = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('[')))
    assert command[command.index('--variants') + 1:][:2] == ['candidate', '--candidate-options']
    assert 'context_shortcut' in command and 'intermediate' in command
    assert command[command.index('--anchor-templates') + 1] == 'saved/results.json'

