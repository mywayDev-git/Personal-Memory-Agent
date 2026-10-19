import shutil
import subprocess
from pathlib import Path

import pytest


def test_launcher_modes_and_failed_startup_cleanup():
    executable = shutil.which("pwsh")
    if executable is None:
        pytest.skip("PowerShell 7 unavailable")
    script = Path(__file__).with_name("launcher_modes.ps1")
    result = subprocess.run([executable, "-NoProfile", "-File", str(script)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "launcher tests passed" in result.stdout
