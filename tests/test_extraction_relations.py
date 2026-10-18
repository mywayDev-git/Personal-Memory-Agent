import copy
import json
from unittest.mock import patch

import pytest
from conftest import memory

from config.settings import Settings, paths
from scripts.memory_agent.accuracy import relation_issues
from scripts.memory_agent.diagnostics import ProcessingError
from scripts.memory_agent.pipeline import process_text
from scripts.memory_agent.provenance import normalize_time, sentences
from scripts.memory_agent.validator import load_schema


def ref(name):
    return dict(kind="self" if name == "사용자" else "entity", value=name, value_type="string")


def example(text, actor="사용자", obj="책", predicate="주다", target=None):
    m = memory(text)
    m.pop("local_id")
    m.update(
        memory_type="event", subject=ref(actor), object=ref(obj), predicate=predicate, target=target
    )
    return m


@pytest.mark.parametrize("value", ["도서관", "다음 주 금요일"])
def test_companion_place_and_time_rejected(value):
    text = f"{value}에서 민수와 공부했다." if value == "도서관" else f"{value}에 민수와 공부한다."
    m = example(text, target=dict(subject=ref("민수"), predicate="동반하다", object=ref(value)))
    assert relation_issues(m)[0]["code"] == "INVALID_COMPANION_ARGUMENT"


@pytest.mark.parametrize(
    "text,actor,obj,predicate",
    [
        ("지현이 나에게 책을 줬다.", "지현", "책", "주다"),
        ("나는 민수에게 책을 줬다.", "사용자", "책", "주다"),
        ("나는 지현에게서 책을 받았다.", "사용자", "책", "받다"),
        ("영수가 철수한테 노트북을 주었다.", "영수", "노트북", "주다"),
    ],
)
def test_explicit_transfer_preserved_and_wrong_actor_detected(text, actor, obj, predicate):
    m = example(text, actor, obj, predicate)
    assert relation_issues(m) == []
    m["subject"] = ref("없는사람")
    assert any(i["code"] == "TRANSFER_ACTOR_MISMATCH" for i in relation_issues(m))


@pytest.mark.parametrize(
    "text,predicate,actor,obj",
    [
        ("민수는 지현의 동생이다.", "동생이다", "민수", "지현"),
        ("연구실은 학교에 소속된다.", "소속된다", "연구실", "학교"),
        ("민수가 나에게 책을 줬다고 지현이 말했다.", "말하다", "지현", "민수의 말"),
        ("내일 민수에게 책을 줄 예정이다.", "주다", "사용자", "책"),
        ("민수와 지현이 서로 책을 교환했다.", "교환하다", "민수", "책"),
    ],
)
def test_unparsed_relationships_are_not_rewritten(text, predicate, actor, obj):
    m = example(text, actor, obj, predicate)
    before = copy.deepcopy(m)
    assert relation_issues(m) == []
    assert m == before


def run_pipeline(text, responses):
    calls = []

    def extract(**kwargs):
        calls.append(kwargs)
        return copy.deepcopy(responses[min(len(calls) - 1, len(responses) - 1)]), {}, 1.0

    with patch("scripts.memory_agent.pipeline.extract_memories", side_effect=extract):
        result, meta = process_text(
            text,
            dict(source_id="test", reference_time="2026-10-14T14:36:00+09:00", language="ko"),
            prompt="test",
            output_schema=load_schema(paths.output_schema),
            final_schema=load_schema(paths.final_schema),
            session=None,
            settings=Settings(),
        )
    return result, meta, calls


def generated(m, sentence="s0"):
    m = copy.deepcopy(m)
    m["evidence"] = [{"sentence_id": sentence}]
    return {"memories": [m]}


def test_repeated_bad_target_abstains_without_losing_event():
    text = "어제 민수와 지현과 도서관에서 과제를 마쳤다."
    m = example(
        text,
        obj="과제",
        predicate="마치다",
        target=dict(subject=ref("민수"), predicate="동반하다", object=ref("도서관")),
    )
    m["time"]["raw"] = "어제"
    result, meta, calls = run_pipeline(text, [generated(m)])
    assert len(calls) == 2
    assert result["memories"][0]["target"] is None
    assert result["memories"][0]["content"] == text
    assert result["memories"][0]["time"]["start"] == "2026-10-13"
    assert meta["warnings"][0]["code"] == "TARGET_ABSTAINED"
    assert meta["latency_seconds"] == 2
    assert meta["provenance"][0]["relation_validation"]["status"] == "abstained"


def test_valid_companion_survives_repair_and_schema_unchanged():
    text = "민수와 지현과 도서관에서 공부했다."
    bad = example(
        text,
        obj="공부",
        predicate="공부하다",
        target=dict(subject=ref("민수"), predicate="동반하다", object=ref("도서관")),
    )
    good = copy.deepcopy(bad)
    good["target"] = dict(subject=ref("사용자"), predicate="함께하다", object=ref("민수"))
    result, meta, calls = run_pipeline(text, [generated(bad), generated(good)])
    assert result["memories"][0]["target"] == good["target"]
    assert meta["warnings"] == []
    assert calls[0]["output_schema"]["$defs"]["time"]["properties"]["start"] == {"type": "null"}
    assert load_schema(paths.output_schema)["$defs"]["evidence_item"]["required"] == ["quote"]


def test_wrong_transfer_is_never_published():
    text = "지현이 나에게 책을 줬다."
    m = example(text, actor="사용자")
    with pytest.raises(ProcessingError, match="RELATION_VALIDATION_FAILED"):
        run_pipeline(text, [generated(m)])


def test_transfer_repair_preserves_real_giver():
    text = "지현이 나에게 책을 줬다."
    result, _, calls = run_pipeline(
        text, [generated(example(text)), generated(example(text, actor="지현"))]
    )
    assert len(calls) == 2
    assert result["memories"][0]["subject"]["value"] == "지현"


@pytest.mark.parametrize(
    "raw,start,end,precision",
    [
        ("다음 주 금요일", "2026-10-23", "2026-10-23", "day"),
        ("다음 주", "2026-10-19", "2026-10-25", "range"),
        ("지난달", "2026-09", "2026-09", "month"),
        ("작년", "2025", "2025", "year"),
    ],
)
def test_prior_relative_time_improvements_preserved(raw, start, end, precision):
    m = example(f"{raw}에 회의했다.")
    m["time"]["raw"] = raw
    normalize_time(m, sentences(m["content"]), "2026-10-14T14:36:00+09:00")
    assert (m["time"]["start"], m["time"]["end"], m["time"]["precision"]) == (start, end, precision)


def test_wrong_evidence_realigned_with_audit():
    text = "배경 설명을 읽었다. 오늘 지현과 카페에서 오해를 풀었다."
    m = example("지현과 카페에서 오해를 풀었다", obj="오해", predicate="풀다")
    m["time"]["raw"] = "오늘"
    result, meta, calls = run_pipeline(text, [generated(m)])
    assert len(calls) == 1
    assert result["memories"][0]["evidence"][0]["quote"].strip().startswith("오늘")
    assert result["memories"][0]["time"]["start"] == "2026-10-14"
    assert meta["warnings"][0]["code"] == "EVIDENCE_REALIGNED"


def test_wrong_raw_is_not_replaced_by_neighbor_date():
    m = example("오늘 회의했다.")
    m["time"]["raw"] = "어제"
    status = normalize_time(m, sentences(m["content"]), "2026-10-14T12:00:00+09:00")
    assert m["time"]["start"] is None
    assert status["rule"] == "unsupported_time_raw"


def test_no_private_text_in_relation_diagnostic():
    m = example("지현이 나에게 책을 줬다.")
    assert "지현" not in json.dumps(relation_issues(m), ensure_ascii=False)


def test_companion_keyword_does_not_reject_location_relation():
    m = example(
        "민수와 도서관에서 공부했다.",
        obj="공부",
        predicate="공부하다",
        target=dict(subject=ref("사용자"), predicate="함께 공부한 장소", object=ref("도서관")),
    )
    assert relation_issues(m) == []


def test_transfer_object_can_omit_modifier():
    m = example("나는 민수에게 빨간 책을 줬다.", obj="책")
    assert relation_issues(m) == []


@pytest.mark.parametrize("actor,verb,obj", [("사용자", "주다", "책"), ("사용자", "받다", "지현")])
def test_transfer_target_cannot_reverse_sender_or_replace_object(actor, verb, obj):
    m = example(
        "지현이 나에게 책을 줬다.",
        actor="지현",
        target=dict(subject=ref(actor), predicate=verb, object=ref(obj)),
    )
    assert any(issue["field"] == "target" for issue in relation_issues(m))
    result, meta, calls = run_pipeline(m["content"], [generated(m), generated(m)])
    assert len(calls) == 2
    assert result["memories"][0]["target"] is None
    assert any(w["code"] == "TARGET_ABSTAINED" for w in meta["warnings"])


def test_transfer_target_can_describe_receiver_perspective():
    m = example(
        "지현이 나에게 책을 줬다.",
        actor="지현",
        target=dict(subject=ref("사용자"), predicate="받다", object=ref("책")),
    )
    assert relation_issues(m) == []


def test_duplicate_target_removed_without_regeneration():
    m = example(
        "나는 민수에게 책을 줬다.",
        target=dict(subject=ref("사용자"), predicate="주다", object=ref("책")),
    )
    result, meta, calls = run_pipeline(m["content"], [generated(m)])
    assert len(calls) == 1
    assert result["memories"][0]["target"] is None
    assert meta["warnings"][0]["code"] == "TARGET_DUPLICATE_REMOVED"


def test_negative_transfer_must_preserve_polarity_and_object():
    m = example("나는 태호에게 선물을 주지 않았다.", obj="태호", predicate="주지 않았다")
    assert {i["code"] for i in relation_issues(m)} == {
        "TRANSFER_OBJECT_MISMATCH",
        "TRANSFER_STATE_MISMATCH",
    }
    m["object"] = ref("선물")
    m["assertion_polarity"] = "negated"
    assert relation_issues(m) == []


def test_simple_walk_cannot_use_companion_as_action_object():
    m = example("내일 서연과 공원에서 산책할 예정이다.", obj="서연", predicate="산책하다")
    m["time"]["raw"] = "내일"
    assert relation_issues(m) == [{"field": "object", "code": "COMPANION_AS_ACTION_OBJECT"}]


def test_companion_and_unselected_context_do_not_steal_evidence():
    from scripts.memory_agent.accuracy import align_evidence

    m = example("민수와 도서관에서 오해를 풀었다", obj="오해", predicate="풀다")
    allowed = sentences("배경 설명을 읽었다.")
    assert align_evidence(m, {"selected": allowed, "allowed": allowed}) is None
    repeated = sentences("민수와 도서관에서 오해를 풀었다. 민수와 도서관에서 오해를 풀었다.")
    assert align_evidence(m, {"selected": allowed, "allowed": repeated}) is None


@pytest.mark.parametrize("bad_actor", [False, True])
def test_relation_validation_reaches_store_without_partial_publication(
    store, settings, models, bad_actor
):
    from pma.service import Service

    text = "지현이 나에게 책을 줬다." if bad_actor else "민수와 지현과 도서관에서 공부했다."
    m = (
        example(text)
        if bad_actor
        else example(
            text,
            obj="공부",
            predicate="공부하다",
            target=dict(subject=ref("민수"), predicate="동반하다", object=ref("도서관")),
        )
    )
    models.prompt = "test"
    models.raw_schema = load_schema(paths.output_schema)
    models.count_tokens = lambda text: len(text)

    def extract(text, context, source_units, target_ids):
        return process_text(
            text,
            context,
            prompt=models.prompt,
            output_schema=models.raw_schema,
            final_schema=load_schema(paths.final_schema),
            session=None,
            settings=settings.llm,
            source_units=source_units,
            target_ids=target_ids,
        )

    models.extract = extract
    rid = store.create(text, None)["record_id"]
    with patch(
        "scripts.memory_agent.pipeline.extract_memories",
        side_effect=lambda **kw: (copy.deepcopy(generated(m)), {}, 1.0),
    ):
        Service(store, models, settings).run_one()
    record = store.get(rid)
    if bad_actor:
        assert record["status"] == "failed"
        assert record["error_code"] == "RELATION_VALIDATION_FAILED"
        assert not store.snapshot(settings.embedding_key)[1]
        assert record["text"] == text
    else:
        assert record["status"] == "ready"
        assert record["memories"][0]["target"] is None
        assert record["processing_details"]["warnings"][0]["code"] == "TARGET_ABSTAINED"


@pytest.mark.parametrize(
    "name,raw,content",
    [
        ("민수", "어제", "도서관에서 과제를 마쳤다"),
        ("하준", "오늘", "오늘 도서관에서 과제를 마쳤다"),
    ],
)
def test_actual_companion_omission_restored_from_source(name, raw, content):
    text = f"{raw} {name}와 도서관에서 과제를 마쳤다."
    m = example(
        content,
        obj="과제",
        predicate="마치다",
        target=dict(subject=ref(name), predicate="동반하다", object=ref("도서관")),
    )
    m["time"]["raw"] = raw
    result, meta, calls = run_pipeline(text, [generated(m)])
    restored = result["memories"][0]
    assert len(calls) == 1
    assert name in restored["content"]
    assert restored["target"] == dict(subject=ref("사용자"), predicate="함께하다", object=ref(name))
    assert {w["code"] for w in meta["warnings"]} == {
        "CONTENT_PARTICIPANT_RESTORED",
        "TARGET_GROUNDED_FROM_SOURCE",
    }


@pytest.mark.parametrize(
    "text",
    [
        "민수와 지현과 도서관에서 공부했다.",
        "민수와 도서관에서 공부하지 않았다.",
        "민수와 도서관에서 공부하고 운동했다.",
        '"민수와 도서관에서 공부했다"라고 지현이 말했다.',
        "민수와 도서관에서 아마 공부했을 것이다.",
    ],
)
def test_companion_recovery_refuses_ambiguous_or_negative_source(text):
    from scripts.memory_agent.accuracy import restore_explicit_companion

    m = example(text, obj="공부", predicate="공부하다")
    before = copy.deepcopy(m)
    assert restore_explicit_companion(m) == []
    assert m == before


@pytest.mark.parametrize(
    "source,actor,obj,verb,summary",
    [
        ("어제 지현이 나에게 책을 줬다.", "지현", "책", "주다", "지현이 책을 줬다"),
        ("나는 민수에게 펜을 줬다.", "사용자", "펜", "주다", "펜을 줬다"),
        ("나는 수진에게서 공책을 받았다.", "사용자", "공책", "받다", "공책을 받았다"),
    ],
)
def test_transfer_sender_and_recipient_survive_summary(source, actor, obj, verb, summary):
    m = example(summary, actor=actor, obj=obj, predicate=verb)
    if source.startswith("어제"):
        m["time"]["raw"] = "어제"
    result, meta, calls = run_pipeline(source, [generated(m)])
    assert len(calls) == 1
    assert result["memories"][0]["content"] == source.rstrip(".")
    assert meta["warnings"][0]["code"] == "TRANSFER_PARTICIPANTS_RESTORED"
