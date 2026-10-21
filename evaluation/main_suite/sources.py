"""Synthetic input sources for browsing, independent of personal storage and inference."""

from copy import deepcopy

from evaluation.schema import content_hash

SOURCE_VERSION = "main-source-v1"


def source_id(text, version, owner):
    return "test-" + content_hash([text, version, owner])[:24]


def test_sources(cases):
    sources = {}
    for case in cases:
        records = []
        for record in case["records"]:
            records.append((record["text"], record.get("version", 1), record.get("owner", "user-a"), record["id"], "기록 입력"))
            if record.get("initial_text") and record["initial_text"] != record["text"]:
                records.append((record["initial_text"], max(1, record.get("version", 2)-1), record.get("owner", "user-a"), record["id"], "수정 전 원문"))
        for index, step in enumerate(case["steps"]):
            if step["action"] in {"capture", "assert_no_capture"}:
                previous = next((s for s in reversed(case["steps"][:index]) if s["action"] == "chat"), None)
                if previous:
                    kind = "저장 요청 대화" if step["action"] == "capture" else "비저장 요청 대화"
                    records.append((previous["question"], 1, "user-a", f"chat-{index}", kind))
        for text, version, owner, record_id, kind in records:
            sid = source_id(text, version, owner)
            source = sources.setdefault(sid, {"id": sid, "text": text, "version": version,
                                             "owner": owner, "kinds": [], "cases": []})
            if kind not in source["kinds"]:
                source["kinds"].append(kind)
            reference = {"case_id": case["id"], "record_id": record_id, "kind": kind,
                         "question": case["question"], "variant": case["variant"], "split": case["split"],
                         "variables": case["variables"]}
            if reference not in source["cases"]:
                source["cases"].append(reference)
    return list(sources.values())


def register_sources(cases):
    """Freeze the existing synthetic sentences as the input source dataset."""
    sources = test_sources(cases)
    for case in cases:
        for record in case["records"]:
            record["source_id"] = source_id(record["text"], record.get("version", 1), record.get("owner", "user-a"))
            if record.get("initial_text") and record["initial_text"] != record["text"]:
                record["initial_source_id"] = source_id(record["initial_text"], max(1, record.get("version", 2)-1), record.get("owner", "user-a"))
        for index, step in enumerate(case["steps"]):
            if step["action"] in {"capture", "assert_no_capture"}:
                previous = next((s for s in reversed(case["steps"][:index]) if s["action"] == "chat"), None)
                if previous:
                    previous["source_id"] = source_id(previous["question"], 1, "user-a")
    return {"version": SOURCE_VERSION, "title": "메인 테스트 원문 데이터",
            "provenance": "질문별 검색 검사를 위해 작성한 기존 합성 문장을 원문 데이터로 확정",
            "synthetic_only": True, "records": sources}


def source_dataset():
    from .catalog import read
    data = read("source_records.json")
    if data.get("version") != SOURCE_VERSION or not data.get("synthetic_only"):
        raise ValueError("F-SOURCE:INVALID_DATASET")
    ids = set()
    for source in data["records"]:
        if source["id"] != source_id(source["text"], source["version"], source["owner"]) or source["id"] in ids:
            raise ValueError("F-SOURCE:INVALID_SOURCE_ID")
        ids.add(source["id"])
    return data


def resolve_sources(case, dataset=None):
    """Resolve real evaluation inputs from the registered corpus, with no model calls."""
    case = deepcopy(case)
    linked = any(r.get("source_id") for r in case["records"]) or any(s.get("source_id") for s in case["steps"])
    if not linked:
        return case
    indexed = {s["id"]: s for s in (dataset or source_dataset())["records"]}

    def resolve(sid, expected, version, owner):
        source = indexed.get(sid)
        if not source or (source["text"], source["version"], source["owner"]) != (expected, version, owner):
            raise ValueError("F-SOURCE:CASE_SOURCE_MISMATCH")
        return source["text"]

    for record in case["records"]:
        if record.get("source_id"):
            record["text"] = resolve(record["source_id"], record["text"], record.get("version", 1), record.get("owner", "user-a"))
        if record.get("initial_source_id"):
            record["initial_text"] = resolve(record["initial_source_id"], record["initial_text"], max(1, record.get("version", 2)-1), record.get("owner", "user-a"))
    for step in case["steps"]:
        if step.get("source_id"):
            step["question"] = resolve(step["source_id"], step["question"], 1, "user-a")
    return case
