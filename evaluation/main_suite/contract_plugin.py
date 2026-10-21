"""Offline contract process: real application operations, no personal DB or network."""

import json
import socket
from pathlib import Path

import pytest

CHECKS = []


def pytest_addoption(parser):
    parser.addoption("--contract-report", required=True)


@pytest.fixture(autouse=True)
def offline_contract_boundary(monkeypatch, tmp_path_factory):
    import requests

    from pma.store import Store

    original = Store.__init__
    allowed = tmp_path_factory.getbasetemp().resolve()
    def isolated(self, path, *args, **kwargs):
        if not Path(path).resolve().is_relative_to(allowed):
            raise AssertionError("CONTRACT_PERSONAL_DATABASE_REJECTED")
        original(self, path, *args, **kwargs)
    def no_network(*args, **kwargs):
        raise AssertionError("CONTRACT_REAL_MODEL_OR_NETWORK_REJECTED")
    monkeypatch.setattr(Store, "__init__", isolated)
    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", no_network)


def pytest_runtest_logreport(report):
    if report.when == "call" or report.when in {"setup", "teardown"} and report.outcome != "passed":
        CHECKS.append({"id": report.nodeid, "phase": report.when, "outcome": report.outcome,
                       "duration_seconds": report.duration,
                       "failure": str(report.longrepr)[:3000] if report.failed else None})


def pytest_sessionfinish(session, exitstatus):
    from .runner import snapshot

    Path(session.config.getoption("--contract-report")).write_text(
        json.dumps({"scope":"offline_functional_no_real_models", "source_snapshot":snapshot(),
                    "exit_code": int(exitstatus), "checks": CHECKS}, ensure_ascii=False, indent=2), "utf-8")
