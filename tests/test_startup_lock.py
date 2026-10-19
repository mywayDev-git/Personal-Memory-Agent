import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pma.lock import DataDirectoryInUse, DataLock


class StartupLockTests(unittest.TestCase):
    def test_contention_and_reacquisition_without_file_growth(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.lock"
            for _ in range(3):
                with DataLock(path):
                    with self.assertRaises(DataDirectoryInUse):
                        with DataLock(path):
                            self.fail("Second owner acquired the lock")
            self.assertEqual(path.stat().st_size, 0)

    def test_process_exit_releases_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.lock"
            child = subprocess.run(
                [sys.executable, "-B", "-c",
                 "import os, sys; from pathlib import Path; "
                 "from pma.lock import DataLock; "
                 "lock = DataLock(Path(sys.argv[1])); lock.__enter__(); os._exit(0)",
                 str(path)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(child.returncode, 0, child.stderr)
            with DataLock(path):
                pass

    def test_cli_reports_contention_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "PMA_DATA_DIR": directory}
            with DataLock(Path(directory) / "app.lock"):
                for arguments in (["--check-startup"], ["--no-browser"]):
                    result = subprocess.run(
                        [sys.executable, "-B", "-m", "pma", *arguments],
                        env=env, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=30,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("Ctrl+C", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
            result = subprocess.run(
                [sys.executable, "-B", "-m", "pma", "--check-startup"],
                env=env, capture_output=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_unrelated_os_error_is_not_reported_as_contention(self):
        import errno

        target = "msvcrt.locking" if os.name == "nt" else "fcntl.flock"
        with tempfile.TemporaryDirectory() as directory:
            lock = DataLock(Path(directory) / "app.lock")
            with patch(target, side_effect=OSError(errno.EIO, "I/O error")):
                with self.assertRaises(OSError):
                    lock.__enter__()
            self.assertIsNone(lock.file)


if __name__ == "__main__":
    unittest.main()
