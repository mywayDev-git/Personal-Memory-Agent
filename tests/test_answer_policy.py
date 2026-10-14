from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_answer_review import Gateway, fixture

from pma.models import LocalModels
from pma.service import Service
from pma.settings import AppSettings


def test_experimental_policy_is_opt_in(monkeypatch):
    monkeypatch.delenv("PMA_ANSWER_VALIDATION", raising=False)
    assert AppSettings().answer_validation is False
    assert AppSettings.from_env().answer_validation is False
    monkeypatch.setenv("PMA_ANSWER_VALIDATION", "1")
    assert AppSettings.from_env().answer_validation is True


def test_default_gateway_keeps_legacy_answer_and_boolean_verifier(settings):
    models = LocalModels(settings)
    found, response, _ = fixture()
    seen = []

    def structured(prompt, data, schema, **kwargs):
        seen.append(data)
        if "original_question" in data:
            return {"reason": "원문 일치", "verdict": "supported_answer"}
        return response

    def forbidden(*args):
        raise AssertionError("default policy must not call experimental reviewer")

    models.structured = structured
    models.review = forbidden
    models.answer("어디?", found["results"])
    assert "reference_time" in seen[0]["evidence"][0]
    assert "time_context" not in seen[0]["evidence"][0]
    assert models.verify("어디?", found["results"], response["items"]) is True


def test_enabled_gateway_uses_answer_time_context(settings):
    models = LocalModels(replace(settings, answer_validation=True))
    found, response, _ = fixture()
    seen = []

    def structured(prompt, data, schema, **kwargs):
        seen.append(data)
        return response

    models.structured = structured
    models.answer("어디?", found["results"])
    assert "time_context" in seen[0]["evidence"][0]
    assert "reference_time" not in seen[0]["evidence"][0]


@pytest.mark.parametrize("enabled", [False, True])
def test_service_routes_only_opted_in_policy(settings, enabled):
    gateway = Gateway()
    gateway.found.update(status="ok", connections=[])
    store = SimpleNamespace(assert_generation=lambda generation: None)
    service = Service(store, gateway, replace(settings, answer_validation=enabled))
    service._search = lambda *args: (1, gateway.found)
    response = service.answer("민수는 지금 어디에 살아?")
    assert response["status"] == "answered"
    assert len(gateway.calls) == (2 if enabled else 0)
    if not enabled:
        assert "현재 상태를 단정하지 않습니다" in response["items"][0]["text"]
