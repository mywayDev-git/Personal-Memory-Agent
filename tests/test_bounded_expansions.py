from types import SimpleNamespace

import pytest

from pma.models import LocalModels, NO_EXPANSION_SCHEMA, UNDERSTANDING_SCHEMA
from pma.search_expressions import GROUPS, TRANSLATIONS, expansion_possible, correspondence
from pma.settings import AppSettings


@pytest.mark.parametrize("group", [*GROUPS.values(), *TRANSLATIONS])
def test_every_reviewed_correspondence_remains_eligible(group):
    for before in group:
        for question in (before, "내 " + before + " 기록", before.upper(), "　" + before.replace(" ", "   ") + "은?"):
            assert expansion_possible(question)
        for after in group:
            if correspondence(before, after):
                assert expansion_possible("과거 " + before + " 사건")


def test_only_impossible_expansions_get_empty_schema():
    model = LocalModels.__new__(LocalModels)
    model.settings = AppSettings(bounded_expansions=True)
    seen = []
    model.structured = lambda prompt, data, schema: seen.append(schema) or {"intent": "recall"}
    model.understand("민수에게 무엇을 선물했어?", "2026-10-21")
    assert seen[-1] is NO_EXPANSION_SCHEMA
    assert seen[-1]["properties"]["expansions"]["maxItems"] == 0
    model.understand("쿠버네티스 배포 기록", "2026-10-21")
    assert seen[-1] is UNDERSTANDING_SCHEMA
    assert UNDERSTANDING_SCHEMA["properties"]["expansions"]["maxItems"] == 4


def test_unconfigured_default_preserves_original_schema():
    model = LocalModels.__new__(LocalModels)
    model.settings = AppSettings()
    model.structured = lambda prompt, data, schema: {"same_schema": schema is UNDERSTANDING_SCHEMA}
    assert model.understand("민수에게 선물했어?", "2026-10-21")["same_schema"]
