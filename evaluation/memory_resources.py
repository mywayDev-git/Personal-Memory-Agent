"""Read-only process RSS and total GPU usage; no model lifecycle changes."""

import ctypes
import os
import subprocess
import time
from contextlib import contextmanager
from unittest.mock import patch
from urllib.parse import urlsplit

import requests


@contextmanager
def observe_http():
    """Count actual requests including nested chat budgets, in this evaluator only."""
    calls = []
    original = requests.Session.request

    def request(session, method, url, *args, **kwargs):
        started = time.perf_counter()
        try:
            return original(session, method, url, *args, **kwargs)
        finally:
            calls.append(
                {
                    "method": method,
                    "operation": urlsplit(url).path,
                    "seconds": round(time.perf_counter() - started, 4),
                }
            )

    with patch.object(requests.Session, "request", request):
        yield calls


def snapshot():
    result = {}
    if os.name == "nt":

        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak_rss",
                    "rss",
                    "peak_pool",
                    "pool",
                    "peak_nonpaged",
                    "nonpaged",
                    "pagefile",
                    "peak_pagefile",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = ctypes.c_void_p
        read = ctypes.windll.psapi.GetProcessMemoryInfo
        read.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if read(current(), ctypes.byref(counters), counters.cb):
            result.update(python_rss_bytes=counters.rss, python_peak_rss_bytes=counters.peak_rss)
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        result["gpu_total_used_mib"] = [int(line) for line in output.splitlines()]
    except OSError, subprocess.SubprocessError, ValueError:
        result["gpu_total_used_mib"] = None
    return result
