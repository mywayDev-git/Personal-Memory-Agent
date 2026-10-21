from copy import deepcopy
from types import SimpleNamespace

import pytest

from pma.model_identifiers import compact_identifiers, identifiers, references


ID = "c61a2e39-f36b-4235-a356-93066a42f15e"
SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {
    "type": "array", "items": {"type": "object", "required": ["text", "citations"],
        "properties": {"text": {"type": "string"}, "citations": {"type": "array", "items": {"enum": [ID]}}}}}}}


def test_call_local_roundtrip_preserves_text_schema_inputs_and_original_ids():
    data = {"evidence": [{"id": ID, "source_text": ID, "quote": "S0", "content": "비 때문에 취소했다."}],
            "proposed_answer": {"items": [{"text": ID, "citations": [ID]}]}}
    original = deepcopy((data, SCHEMA))
    seen = []
    @compact_identifiers
    def call(self, prompt, payload, schema):
        seen.append((payload, schema))
        return {"items": [{"text": ID, "citations": [payload["evidence"][0]["id"]]}]}
    model = SimpleNamespace(settings=SimpleNamespace(compact_model_ids=True))
    assert call(model, "unchanged", data, SCHEMA) == {"items": [{"text": ID, "citations": [ID]}]}
    assert (data, SCHEMA) == original
    payload, schema = seen[0]
    assert payload["evidence"][0] == {"id": "S0", "source_text": ID, "quote": "S0", "content": "비 때문에 취소했다."}
    assert payload["proposed_answer"]["items"][0] == {"text": ID, "citations": ["S0"]}
    assert schema["properties"]["items"]["items"]["properties"]["citations"]["items"]["enum"] == ["S0"]


def test_unknown_and_cross_call_references_fail_original_validation():
    @compact_identifiers
    def call(self, prompt, data, schema):
        return {"items": [{"text": "unknown", "citations": ["S99"]}]}
    model = SimpleNamespace(settings=SimpleNamespace(compact_model_ids=True))
    with pytest.raises(ValueError, match="INVALID_RESTORED_MODEL_REFERENCES"):
        call(model, "p", {"source_records": [{"id": ID}]}, SCHEMA)


def test_identity_collision_duplicates_and_context_evidence_id():
    mapping = identifiers({"evidence": [{"id": "S0"}, {"id": ID}, {"id": ID}]})
    assert len(mapping) == 1
    assert not set(mapping) & set(mapping.values())
    assert references({"alternatives": [{"evidence_id": ID, "quote": ID}]}, mapping) == {
        "alternatives": [{"evidence_id": mapping[ID], "quote": ID}]}
    assert identifiers({"evidence": [{"id": "a"}, {"id": "S0"}]}) == {}


def test_disabled_or_no_sources_is_original_call_including_schema_identity():
    @compact_identifiers
    def call(self, prompt, data, schema):
        assert schema is SCHEMA
        return data
    model = SimpleNamespace(settings=SimpleNamespace(compact_model_ids=False))
    data = {"evidence": [{"id": ID}]}
    assert call(model, "p", data, SCHEMA) is data
    model.settings.compact_model_ids = True
    assert call(model, "p", {}, SCHEMA) == {}


def test_real_model_gateway_restores_ids_before_selection_validation(monkeypatch):
    import json
    from dataclasses import replace
    from pma import models
    from pma.settings import AppSettings
    gateway = models.LocalModels(replace(AppSettings(), compact_model_ids=True))
    monkeypatch.setattr(gateway, "budget", lambda *a, **k: None)
    requests = []
    def chat(session, endpoint, messages, **kwargs):
        payload = json.loads(messages[-1]["content"])
        requests.append((payload, kwargs["output_schema"]))
        return json.dumps({"ids": [payload["evidence"][0]["id"]]}), {}, 0
    monkeypatch.setattr(models, "chat", chat)
    assert gateway.select("무엇을 했어?", [{"id": ID, "source_text": "공부했다.", "content": "공부했다."}]) == [ID]
    assert requests[0][0]["evidence"][0]["id"] == "S0"
    assert requests[0][1]["properties"]["ids"]["items"]["enum"] == ["S0"]
