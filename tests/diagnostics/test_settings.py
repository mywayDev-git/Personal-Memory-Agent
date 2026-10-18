"""Prompt 3: startup configuration only; no automatic service instrumentation yet."""

from dataclasses import FrozenInstanceError, fields, replace

import pytest

from pma.diagnostics import Stage, record_event, start_trace
from pma.settings import AppSettings


@pytest.mark.parametrize("value", ["", "true", "yes", "2", " 1 "])
def test_only_literal_one_enables_diagnostics(monkeypatch, value):
    monkeypatch.setenv("PMA_DIAGNOSTICS", value)
    assert AppSettings.from_env().diagnostics is False


def test_direct_constructor_stays_off_even_when_environment_enabled(monkeypatch):
    monkeypatch.setenv("PMA_DIAGNOSTICS", "1")
    monkeypatch.setenv("PMA_DIAGNOSTICS_PATH", "unused.jsonl")
    assert AppSettings().diagnostics is False
    assert AppSettings().diagnostics_path is None


@pytest.mark.parametrize("path", [None, ""])
def test_no_path_uses_memory_only(monkeypatch, tmp_path, path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PMA_DIAGNOSTICS", "1")
    if path is None:
        monkeypatch.delenv("PMA_DIAGNOSTICS_PATH", raising=False)
    else:
        monkeypatch.setenv("PMA_DIAGNOSTICS_PATH", path)
    configured = AppSettings.from_env()
    assert configured.diagnostics is True
    assert configured.diagnostics_path is None
    with start_trace(enabled=configured.diagnostics, path=configured.diagnostics_path) as trace:
        record_event(Stage.FINAL_DECISION, status="answer")
    assert trace.events and not trace.storage_failed
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["directory", "missing_parent", "invalid"])
def test_unusable_path_does_not_break_configuration_or_processing(monkeypatch, tmp_path, kind):
    path = {
        "directory": str(tmp_path),
        "missing_parent": str(tmp_path / "missing" / "trace.jsonl"),
        "invalid": "invalid\0path",
    }[kind]
    monkeypatch.setenv("PMA_DIAGNOSTICS", "1")
    # Windows environment variables cannot contain NUL; simulate an invalid path
    # through the supported constructor override, not an invalid OS operation.
    monkeypatch.setenv("PMA_DIAGNOSTICS_PATH", str(tmp_path) if kind == "invalid" else path)
    configured = AppSettings.from_env()
    if kind == "invalid":
        configured = replace(configured, diagnostics_path=path)
    configured.validate()
    assert configured.diagnostics_path == path
    with start_trace(enabled=configured.diagnostics, path=configured.diagnostics_path) as trace:
        record_event(Stage.FINAL_DECISION, status="answer")
    assert trace.storage_failed
    assert list(tmp_path.iterdir()) == []


def test_environment_is_read_once_and_settings_are_immutable(monkeypatch, tmp_path):
    path = str(tmp_path / "trace.jsonl")
    monkeypatch.setenv("PMA_DIAGNOSTICS", "1")
    monkeypatch.setenv("PMA_DIAGNOSTICS_PATH", path)
    configured = AppSettings.from_env()
    monkeypatch.setenv("PMA_DIAGNOSTICS", "0")
    monkeypatch.setenv("PMA_DIAGNOSTICS_PATH", "different.jsonl")
    assert configured.diagnostics is True and configured.diagnostics_path == path
    with pytest.raises(FrozenInstanceError):
        configured.diagnostics = False
    assert not (tmp_path / "trace.jsonl").exists()


def test_existing_positional_constructor_and_model_configuration_preserved(settings):
    legacy_names = [
        "data_dir",
        "port",
        "embedding_endpoint",
        "embedding_model",
        "embedding_revision",
        "embedding_dimensions",
        "answer_validation",
        "evaluation_enabled",
        "evaluation_details",
        "context_tokens",
        "llm",
    ]
    reconstructed = AppSettings(*(getattr(settings, name) for name in legacy_names))
    assert reconstructed == settings
    enabled = replace(settings, diagnostics=True, diagnostics_path="relative-trace.jsonl")
    assert enabled.embedding_key == settings.embedding_key
    assert enabled.llm is settings.llm
    assert enabled.origin == settings.origin
    assert [f.name for f in fields(settings) if not f.kw_only] == legacy_names
    assert all(getattr(enabled, name) == getattr(settings, name) for name in legacy_names)
