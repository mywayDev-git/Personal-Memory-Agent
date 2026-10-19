"""OS-released lock: a crashed process cannot strand the data directory."""

import errno
import os


class DataDirectoryInUse(RuntimeError):
    """Another process holds the data directory lock."""


class DataLock:
    def __init__(self, path):
        self.path = path
        self.file = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        # Windows supports locking beyond EOF; do not write before acquiring
        # the lock (or append another byte on every startup).
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            self.file = None
            if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                raise DataDirectoryInUse(
                    f"이미 실행 중인 PMA가 데이터 폴더를 사용하고 있습니다: {self.path.parent}\n"
                    "기존 PMA 실행 창에서 Ctrl+C로 종료한 뒤 다시 실행하세요. "
                    "잠금 파일을 삭제해도 실행 중인 프로세스의 잠금은 해제되지 않습니다."
                ) from exc
            raise
        return self

    def __exit__(self, *args):
        if self.file:
            self.file.close()
            self.file = None
