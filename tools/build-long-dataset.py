"""Build the isolated development dataset from JSON in the handoff. No model calls.

Usage: python -B tools/build-long-dataset.py --zip <handoff.zip>
Only this dataset's explicitly named generated files are written. Archive code is
never imported or executed. Existing dataset versions and upstream ZIP stay intact.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import zipfile

VERSION = "pma-long-v1.0.1"
UPSTREAM = "evaluation/data/long_input_v1/"
PROFILES = {
    "smoke": (8, "짧은 대조군", "8개 의미 계열의 짧은 원문"),
    "core": (24, "길이·위치 비교", "3000자 × 앞·중간·끝, 8개 의미 계열"),
    "sentence": (8, "긴 단일 문장", "600·1800자, 4개 의미 계열, 목표는 끝에 위치"),
    "boundary": (6, "가져오기 경계", "3999·4000·4001·7999·8000·8001자; 분할 계획만 제공"),
    "dependency": (4, "원거리 근거 연결", "8500자, 떨어진 두 근거를 함께 확인"),
    "stress": (6, "장문 부하", "12000·24000자 × 앞·중간·끝; 조건부 계획 계열 한정"),
}
FAMILIES = {
    "roles": "행위자·수신자 역할", "negation": "부정", "conditional_plan": "조건부 계획",
    "correction": "정정", "identity": "동명이인 분리", "quoted_time": "인용 속 상대 시간",
    "unknown_actor": "행위자 미상", "cause_unknown": "원인 미상", "import_boundary": "가져오기 경계",
    "distant_correction": "원거리 정정", "distant_actor": "원거리 역할 참조",
    "distant_cause": "원거리 원인", "distant_conflict": "원거리 충돌",
}


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode("utf-8")).hexdigest()


def utf16_offset(text, codepoint_offset):
    return len(text[:codepoint_offset].encode("utf-16-le")) // 2


def import_plan(text):
    """Plan-only copy of upstream's documented 4000-codepoint/newline algorithm."""
    start, regions = 0, []
    while start < len(text):
        end = min(start + 4000, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + 2000, end)
            if boundary >= 0:
                end = boundary + 1
        if text[start:end].strip():
            regions.append({"start": start, "end": end, "utf16_start": utf16_offset(text, start),
                            "utf16_end": utf16_offset(text, end), "sha256": sha(text[start:end])})
        start = end
    return regions


def build(zip_path, root):
    dest = root / "datasets" / VERSION
    dest.mkdir(parents=True, exist_ok=True)
    preserved = {}
    with zipfile.ZipFile(zip_path) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC validation failed")
        # Literal allowlist: do not extract arbitrary paths or execute archive scripts.
        for name in ("inputs.json", "annotations.json", "manifest.json"):
            preserved["upstream/" + name] = archive.read(UPSTREAM + name)
    original_inputs = json.loads(preserved["upstream/inputs.json"])
    original_annotations = json.loads(preserved["upstream/annotations.json"])
    upstream_manifest = json.loads(preserved["upstream/manifest.json"])
    for name, expected in upstream_manifest["files"].items():
        assert sha(preserved["upstream/" + name]) == expected, name
    assert len(original_inputs) == len(original_annotations) == 56
    assert len({x["id"] for x in original_inputs}) == 56
    assert [x["id"] for x in original_inputs] == [x["id"] for x in original_annotations]
    for item, annotation in zip(original_inputs, original_annotations):
        assert annotation["input"] == {k: item[k] for k in ("text", "reference_time", "entry_mode")}
        assert annotation["metadata"]["characters"] == len(item["text"])
        assert annotation["metadata"]["sha256"] == sha(item["text"])
        for e in annotation["gold"]["evidence"]:
            assert item["text"][e["start"]:e["end"]] == e["quote"]

    inputs, annotations = copy.deepcopy(original_inputs), copy.deepcopy(original_annotations)
    index = next(i for i, x in enumerate(inputs) if x["id"] == "LI-import-4001")
    item, annotation = inputs[index], annotations[index]
    assert len(item["text"]) == 4013
    quote = annotation["gold"]["evidence"][0]["quote"]
    corrected = item["text"][:4001 - len(quote)] + quote
    item["text"] = annotation["input"]["text"] = corrected
    annotation["metadata"].update(characters=len(corrected), utf8_bytes=len(corrected.encode("utf-8")), sha256=sha(corrected))
    annotation["gold"]["evidence"] = [{"start": 4001 - len(quote), "end": 4001, "quote": quote}]

    sources, contexts, questions, plans = [], [], [], []
    for item, a in zip(inputs, annotations):
        key = sha(item["id"])[:16]
        sid, cid, owner = "LIS-" + key, "LIC-" + key, "fixture-" + key
        ref = {"source_id": sid, "revision": 1}
        evidence, facts = [], []
        for i, e in enumerate(a["gold"]["evidence"], 1):
            span = {**ref, "start": utf16_offset(item["text"], e["start"]),
                    "end": utf16_offset(item["text"], e["end"]), "quote": e["quote"]}
            evidence.append(span)
            facts.append({"id": sid + "-E" + str(i), "kind": "annotated_target_evidence_region",
                          "statement": e["quote"], "evidence": [span], "qualifiers": {}})
        sources.append({"id": sid, "revision": 1, "family_id": a["family"], "split": "development",
            "text": item["text"],
            "metadata": {"owner_id": owner, "owner_is_author": False, "created_at": None,
                "created_at_status": "NOT_PROVIDED", "document_reference_time": item["reference_time"],
                "time_zone": "+09:00", "channel": "synthetic_fixture"},
            "provenance": {"upstream_case_id": item["id"], "entry_mode": item["entry_mode"],
                "synthetic_only": True, "profile": a["profile"], "pair_group": a["pair_group"],
                "position": a["position"], "model_tokens": None},
            "gold": {"review_status": "AUTHOR_DRAFT", "coverage_scope": a["gold"]["coverage"],
                "facts": facts, "highlights": [], "structured_expectations": a["gold"]["structured_expectations"],
                "forbidden_inferences": a["gold"]["forbidden_inferences"]}})
        contexts.append({"id": cid, "family_id": a["family"], "split": "development", "now": item["reference_time"],
            "actor_id": owner, "setup": {"initial_sources": [ref], "steps": [], "history_visibility": "active_only"},
            "expected_state": {"active_sources": [ref], "accessible_sources": [ref]}, "conversation": [],
            "input_policy": {"auto_save": False, "search_scope": "actor_accessible_active_sources_only", "input_path": "raw_original_v1"},
            "required_observations": ["retrieved_source_revisions", "answer_claims", "citation_spans"]})
        questions.append({"id": item["id"] + ":Q1", "revision": 1, "display_case_id": item["id"],
            "family_id": a["family"], "split": "development", "context_id": cid, "text": a["gold"]["question"],
            "question_type": a["axis"], "profile": a["profile"], "pair_group": a["pair_group"],
            "position": a["position"], "variables": [], "variant": None,
            "gold": {"review_status": "AUTHOR_DRAFT", "label_status": a["label_status"],
                "expected_action": None, "reference_answer": None,
                "annotation_status": {"expected_action": "NOT_ANNOTATED", "reference_answer": "NOT_ANNOTATED"},
                "required_claims": a["gold"]["required_meanings"], "forbidden_claims": a["gold"]["forbidden_inferences"],
                "structured_expectations": a["gold"]["structured_expectations"],
                "evidence_groups": [{"id": item["id"] + ":G" + str(i), "any_of_fact_ids": [f["id"]]} for i, f in enumerate(facts, 1)],
                "answer_policy": "semantic review required; no automatic semantic PASS",
                "citation_policy": "all annotated target evidence groups required",
                "judging": a["gold"]["grading"], "coverage": a["gold"]["coverage"]},
            "required_observations": ["citation_spans", "answer_claims"]})
        regions = import_plan(item["text"])
        plans.append({"case_id": item["id"], "source_id": sid, "entry_mode": item["entry_mode"],
            "status": "PLAN_ONLY_NOT_EXECUTED", "algorithm": "upstream-4000-codepoints-newline-v1",
            "regions": regions,
            "evidence_regions": [{"start": e["start"], "end": e["end"],
                "overlaps_chunks": [i + 1 for i, c in enumerate(regions) if e["start"] < c["end"] and c["start"] < e["end"]]}
                for e in a["gold"]["evidence"]]})

    def write_json(name, value):
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    for name, raw in preserved.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    write_json("inputs.json", inputs)
    write_json("annotations.json", annotations)
    write_json("sources.json", {"schema_version": "pma-source-1", "dataset_version": VERSION,
        "offset_convention": "UTF-16 code units, zero-based half-open [start,end)", "records": sources, "relations": []})
    write_json("contexts.json", {"schema_version": "pma-context-1", "dataset_version": VERSION, "contexts": contexts})
    write_json("questions.json", {"schema_version": "pma-question-1", "dataset_version": VERSION, "questions": questions})
    write_json("coverage.json", {"variables": [], "mapping_status": "NOT_MAPPED_TO_MAIN_SUITE_489_VARIABLES",
        "profiles": [{"id": key, "count": count, "label": label, "description": desc} for key, (count, label, desc) in PROFILES.items()]})
    write_json("import_plans.json", {"schema_version": "pma-import-plan-1", "status": "PLAN_ONLY_NOT_EXECUTED", "cases": plans})
    files = ["inputs.json", "annotations.json", "sources.json", "contexts.json", "questions.json", "coverage.json", "import_plans.json", "lib.mjs", "README.md", *preserved]
    manifest = {"schema_version": "pma-long-dataset-1", "dataset_version": VERSION,
        "title": "장문 개발셋 v1.0.1", "synthetic_only": True, "model_execution": False, "independent_gold": False,
        "execution_input_path": "raw_original_v1", "default_profile": "smoke", "profiles": {k: v[0] for k, v in PROFILES.items()},
        "counts": {"families": len(FAMILIES), "sources": 56, "contexts": 56, "questions": 56,
            "source_facts": sum(len(s["gold"]["facts"]) for s in sources), "target_evidence_regions": 60,
            "source_relations": 0, "upstream_variables": 0, "draft_linked_variables": 0},
        "families": [{"id": k, "title": v, "split": "development", "review_status": "AUTHOR_DRAFT", "variables": []} for k, v in FAMILIES.items()],
        "partition": {"development": [q["id"] for q in questions], "final": []},
        "provenance": {"zip_filename": zip_path.name, "zip_sha256": sha(zip_path.read_bytes()),
            "upstream_version": upstream_manifest["version"], "upstream_files": upstream_manifest["files"],
            "builder_sha256": sha(Path(__file__).read_bytes()), "adapter_version": "pma-long-adapter-v1",
            "corrections": [{"case_id": "LI-import-4001", "old_characters": 4013, "new_characters": 4001,
                "reason": "negative suffix length in upstream generator; moved intact target to [3973,4001)",
                "old_sha256": original_annotations[index]["metadata"]["sha256"], "new_sha256": annotation["metadata"]["sha256"]}]},
        "limits": ["개발용 정답 초안이며 최종 평가셋이 아님", "같은 pair_group의 길이·위치 변형은 독립 표본이 아님",
            "목표 근거 구간 60개는 문서 전체 의미 사실 주석이 아님", "사례당 원문 1개: 원문 순위 성능으로 해석하지 않음",
            "reference_time은 문서 해석 기준이며 저장 시각·작성자 정보는 미제공",
            "대표 답변 문장과 기대 행동은 미주석; 필수 의미·금지 주장·구조 기대값만 보존",
            "실제 토큰수 미측정; 길이가 토큰 예산 이내임을 보장하지 않음",
            "현재 앱 실행은 원문 전체 경로; 4000자 가져오기 분할은 계획이며 실행 아님",
            "기존 추출 지침은 created_at 기준; 문서 기준시각 적용은 프롬프트 어댑터 검토 필요"],
        "integrity": [{"file": name, "sha256": sha((dest / name).read_bytes())} for name in files]}
    write_json("manifest.json", manifest)
    print(json.dumps({"dataset": VERSION, "path": str(dest), "cases": len(inputs), "target_evidence_regions": 60, "model_calls": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    build(args.zip, args.root)
