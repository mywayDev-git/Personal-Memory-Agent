"""Offline contract checks: never launch a real model or the official suite."""

import json
import threading
import time
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from evaluation import latency_recheck
from evaluation.latency_variants import OPTIONS, configured
from evaluation.response_latency import reset_experiment_slot
from pma.chat.automatic import NEXT, structured
from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings
from scripts.memory_agent.llm_client import chat, post_json, request_budget


def test_current_baseline_preserves_stop_default_and_separates_switches():
    base = AppSettings(request_reuse=True, request_token_cache=True, selection_batch_size=8,
                       chat_presentation="plain", compact_search_planning=True)
    current = configured(base)
    assert current.source_stop_drafts is True
    assert current.request_reuse is False
    assert current.selection_reuse is False
    assert current.explicit_context_shortcut is False
    assert current.selection_batch_size == 4
    assert current.chat_presentation == "reviewed"
    for name, changes in OPTIONS.items():
        candidate = configured(base, [name])
        assert candidate == replace(current, **changes)
    with pytest.raises(ValueError):
        configured(base, ["prefix_off", "prefix_on"])


@pytest.mark.parametrize("explicit,legacy,expected", [(True, False, 1), (False, True, 2), (None, True, 1)])
def test_selection_cache_is_independent_of_context_shortcut(explicit, legacy, expected):
    model = LocalModels.__new__(LocalModels)
    model.settings = AppSettings(selection_reuse=explicit, request_reuse=legacy,
                                 explicit_context_shortcut=False)
    calls = []
    def answer(*args, **kwargs):
        calls.append(1)
        return {"items": [{"id": "a", "category": "direct_answer", "quote": "공부를 접었다."}]}
    model.structured = answer
    evidence = [{"id": "a", "revision_id": "v1", "source_text": "공부를 접었다.",
                 "evidence": [{"quote": "공부를 접었다."}]}]
    with request_budget(30):
        model.select_explained("공부 기록", evidence)
        model.select_explained("공부 기록", evidence)
    assert len(calls) == expected


def test_compact_planning_keeps_semantic_warnings_all_sources_and_input_immutable():
    seen = []
    engine = SimpleNamespace(service=SimpleNamespace(settings=AppSettings(compact_search_planning=True)),
                             models=SimpleNamespace(count_tokens=lambda text: 1,
                                structured=lambda p, d, s, **kw: seen.append(deepcopy(d)) or {"query": ""}))
    data = {"question": "회사 동료 민수의 직업은?", "history": [],
            "filters": {"person": "민수"}, "searches": [{"query_plan": {"a": 1}, "query": "민수"}],
            "evidence": [{"source_text": "회사 동료 민수는 교사다.", "score": 1,
                          "search_explanation": {"query_correction": {"before": "민쑤", "after": "민수"},
                                                 "warning": "unverified"}}]}
    original = deepcopy(data)
    assert structured(engine, "policy", data, NEXT) == {"query": ""}
    assert data == original
    assert "query_plan" not in seen[0]["searches"][0]
    assert "score" not in seen[0]["evidence"][0]
    assert seen[0]["evidence"][0]["search_explanation"] == data["evidence"][0]["search_explanation"]
    assert seen[0]["evidence"][0]["source_text"] == data["evidence"][0]["source_text"]
    assert seen[0]["filters"] == data["filters"]


class Transport:
    def __init__(self, payload):
        self.payload, self.bodies = payload, []
    def post(self, endpoint, **kw):
        self.bodies.append(kw["json"])
        return SimpleNamespace(status_code=200, json=lambda: self.payload)


@pytest.mark.parametrize("policy", [None, False, True])
def test_prefix_policy_does_not_change_messages_or_bypass_model(policy):
    session = Transport({"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})
    messages = [{"role": "system", "content": "policy"}, {"role": "user", "content": "untrusted"}]
    chat(session, "http://127.0.0.1:18581/v1/chat/completions", messages, cache_prompt=policy)
    assert session.bodies[0]["messages"] == messages
    assert ("cache_prompt" in session.bodies[0]) == (policy is not None)
    if policy is not None:
        assert session.bodies[0]["cache_prompt"] is policy


def test_cache_metrics_are_numeric_allowlist_only():
    session = Transport({"timings": {"cache_n": 9, "prompt_ms": 2.5, "predicted_ms": float("nan"),
                                     "prompt": "secret", "source_text": "secret"},
                         "usage": {"prompt_tokens_details": {"cached_tokens": 9, "text": "secret"}}})
    with request_budget(10) as budget:
        post_json(session, "http://127.0.0.1:18581/v1/chat/completions", {}, 2)
    assert budget.calls[0]["timings"] == {"cache_n": 9, "prompt_ms": 2.5}
    assert budget.calls[0]["cached_prompt_tokens"] == 9
    assert "secret" not in json.dumps(budget.calls)


def test_slot_reset_keeps_transport_query_policy_and_disables_redirects(monkeypatch):
    from contextlib import nullcontext

    from scripts.memory_agent import llm_client
    calls = []
    transport = SimpleNamespace(post=lambda endpoint, **kw: calls.append((endpoint, kw))
                                or SimpleNamespace(status_code=200))
    monkeypatch.setattr(llm_client, "local_session", lambda: nullcontext(transport))
    reset_experiment_slot(18581)
    assert calls == [("http://127.0.0.1:18581/slots/0", {
        "params": {"action": "erase"}, "json": {}, "timeout": 30, "allow_redirects": False})]
    with pytest.raises(ValueError):
        llm_client.validate_endpoint("http://127.0.0.1:18581/slots/0?action=erase")


def test_fair_scheduling_yields_to_waiting_background_after_two_foregrounds():
    service = Service(None, None, AppSettings(fair_model_scheduling=True))
    order, errors = [], []
    service.foreground_streak = 2
    service.gate.acquire()
    def run(name, background):
        try:
            with service.model_slot(wait=2, background=background):
                order.append(name)
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=run, args=("foreground", False)),
               threading.Thread(target=run, args=("background", True))]
    for t in threads:
        t.start()
    deadline = time.monotonic() + 1
    while service.background_waiters != 1 and time.monotonic() < deadline:
        time.sleep(.001)
    with service.slot_condition:
        service.gate.release()
        service.slot_condition.notify_all()
    for t in threads:
        t.join(3)
    assert not errors
    assert order == ["background", "foreground"]
    assert service.foreground_waiters == service.background_waiters == 0
    assert not service.gate.locked()


def test_plan_does_not_create_output_or_spawn_and_uses_current_baseline(monkeypatch, capsys):
    monkeypatch.setattr(latency_recheck.subprocess, "run", lambda *a, **k: pytest.fail("spawn"))
    assert latency_recheck.main(["--name", "offline-plan-only", "--candidates", "token_cache"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["status"] == "PLANNED"
    assert plan["main_evaluation"] == "NOT_RUN"
    assert plan["samples"] == 5
    assert plan["threads"] == 4 and plan["embedding_batch"] == 4096
    command = plan["trials"][0]["command"]
    assert command[command.index("--variants") + 1:command.index("--candidate-options")] == ["current", "candidate"]
    assert "--fixed-anchor" in command and "--reset-prompt-cache" in command
    assert not latency_recheck.output_path("offline-plan-only").exists()


@pytest.mark.parametrize("error,status", [(KeyboardInterrupt, "INTERRUPTED"), (OSError, "ERROR")])
def test_interruption_and_spawn_failure_leave_honest_records_without_payload(tmp_path, monkeypatch, error, status):
    monkeypatch.setattr(latency_recheck, "OUTPUT_ROOT", tmp_path)
    def fail(*a, **kw):
        raise error("private exception payload")
    monkeypatch.setattr(latency_recheck.subprocess, "run", fail)
    with pytest.raises(error):
        latency_recheck.main(["--execute", "--name", "interrupted", "--candidates", "token_cache", "batch8"])
    raw = (tmp_path / "interrupted/verification.json").read_text("utf-8")
    data = json.loads(raw)
    assert data["status"] == status
    assert data["trials"][0]["status"] == status
    assert data["trials"][1]["status"] == "NOT_RUN"
    assert "private exception payload" not in raw


@pytest.mark.parametrize("name", ["../escape", "/tmp", "a/b", "a b", ""])
def test_output_is_strictly_isolated(name):
    with pytest.raises(ValueError):
        latency_recheck.output_path(name)


def document():
    return {"execution_completed": True, "source_unchanged": True, "evaluator_unchanged": True,
            "configuration": {"cases": ["stopped"]}, "runs": [
                {"variant": variant, "case": "stopped", "sample": n, "seconds": seconds,
                 "quality": {"passed": True}, "warmup": False}
                for variant, seconds in [("current", 10), ("candidate", 7)] for n in range(1, 21)]}


def test_timing_gate_never_implies_semantic_approval_or_default_change():
    report = latency_recheck.assessment(document(), required_samples=20)
    assert report["timing_gate_passed"]
    assert report["semantic_review"] == "PENDING_REVIEW"
    assert report["default_change_allowed"] is False
    assert report["application_wide_claim"] is False


@pytest.mark.parametrize("damage", ["wrong", "missing", "error", "changed_source", "duplicate"])
def test_bad_or_incomplete_trials_cannot_pass(damage):
    data = document()
    if damage == "wrong":
        data["runs"][-1]["quality"]["passed"] = False
    elif damage == "missing":
        data["runs"].pop()
    elif damage == "error":
        data["runs"][-1]["error_code"] = "TIMEOUT"
    elif damage == "changed_source":
        data["source_unchanged"] = False
    else:
        data["runs"][-1]["sample"] = 1
    assert not latency_recheck.assessment(data, required_samples=20)["timing_gate_passed"]
