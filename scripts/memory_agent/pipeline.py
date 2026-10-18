"""Shared extraction contract for CLI, evaluation and the local application."""

import copy
import hashlib
import json

from jsonschema import Draft202012Validator, FormatChecker

from .accuracy import (
    RULES,
    align_evidence,
    relation_issues,
    remove_duplicate_target,
    restore_explicit_companion,
    restore_transfer_participants,
)
from .diagnostics import ProcessingError
from .exceptions import SchemaValidationError
from .extractor import extract_memories
from .postprocess import build_final_result
from .provenance import normalize_time, sentences
from .validator import schema_errors, validate_extraction, validate_final_result


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def process_text(
    source_text,
    source_context,
    *,
    prompt,
    output_schema,
    final_schema,
    session,
    settings,
    source_units=None,
    target_ids=None,
    _repair_attempt=False,
):
    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("EMPTY_SOURCE")
    if schema_errors(build_final_result({"memories": []}, source_context), final_schema):
        raise SchemaValidationError("INVALID_SOURCE_CONTEXT")
    if source_units is None:
        source_units = sentences(source_text)
        target_ids = [u["id"] for u in source_units]
    prompt += RULES if RULES not in prompt else ""
    request_schema = copy.deepcopy(output_schema)
    time_properties = request_schema["$defs"]["time"]["properties"]
    time_properties["start"] = {"type": "null"}
    time_properties["end"] = {"type": "null"}
    time_properties["precision"] = {"enum": ["relative", "unknown"]}
    time_properties["certainty"] = {"const": "uncertain"}
    request_text = source_text
    if source_units is not None:
        request_schema["$defs"]["evidence_item"] = {
            "type": "object",
            "additionalProperties": False,
            "required": ["sentence_id"],
            "properties": {"sentence_id": {"type": "string", "enum": list(target_ids)}},
        }
        request_text = json.dumps(
            {"target_ids": target_ids, "sentences": source_units}, ensure_ascii=False
        )
        prompt += "\n이번 요청은 인용문을 다시 쓰지 않는다. evidence에는 quote 대신 sentence_id만 넣는다. target_ids 문장의 사실만 추출한다. 나머지 문장은 문맥용이다. time은 근거 문장의 시간 범위만 적용하고 기록 시각을 사건 시각으로 복사하지 않는다. 요일만 있는 약속은 날짜를 추측하지 않는다. 받은 사람은 내가 아니라 X라는 문장에서 사용자가 받은 것으로 추출하지 않는다."
    extraction, metadata, latency = extract_memories(
        session=session,
        endpoint=settings.endpoint,
        model=settings.model,
        prompt=prompt,
        source_text=request_text,
        source_context=source_context,
        timeout=settings.timeout,
        max_tokens=settings.max_tokens,
        temperature=settings.temperature,
        seed=settings.seed,
        top_p=settings.top_p,
        output_schema=request_schema,
    )
    if source_units is not None:
        by_id = {u["id"]: u for u in source_units}
        annotations = []
        warnings = []
        for index, memory in enumerate(extraction.get("memories", [])):
            ids = [e.get("sentence_id") for e in memory.get("evidence", [])]
            if not ids or any(i not in by_id or i not in target_ids for i in ids):
                raise ProcessingError(
                    "EVIDENCE_MISMATCH", "evidence", field=f"memories[{index}].evidence"
                )
            units = [by_id[i] for i in dict.fromkeys(ids)]
            memory["evidence"] = [{"quote": u["text"]} for u in units]
            # Apply only after required fields are structurally valid; temporal
            # fields will be replaced by normalization below.
            shape = copy.deepcopy(memory)
            shape["time"] = dict(
                raw=None, start=None, end=None, precision="unknown", certainty="uncertain"
            )
            if not validate_extraction({"memories": [shape]}, output_schema):
                aligned = align_evidence(
                    memory,
                    {
                        "selected": units,
                        "allowed": [u for u in source_units if u["id"] in target_ids],
                    },
                )
                if aligned:
                    warnings.append(
                        dict(
                            code="EVIDENCE_REALIGNED",
                            memory_index=index,
                            original_ids=ids,
                            replacement_ids=[u["id"] for u in aligned],
                        )
                    )
                    units = aligned
                    memory["evidence"] = [{"quote": u["text"]} for u in units]
            temporal = normalize_time(memory, units, source_context.get("reference_time"))
            annotations.append(
                dict(
                    time_validation=temporal,
                    evidence=[{"start": u["start"], "end": u["end"]} for u in units],
                )
            )
        metadata["provenance"] = annotations
        metadata["warnings"] = warnings
    if validate_extraction(extraction, output_schema):
        issues = [
            {"path": list(e.absolute_path), "rule": e.validator}
            for e in Draft202012Validator(
                output_schema, format_checker=FormatChecker()
            ).iter_errors(extraction)
        ]
        diagnostic = dict(code="INVALID_EXTRACTION_SCHEMA", stage="schema", issues=issues[:20])
        if source_units is not None and not _repair_attempt:
            # Retry generation once using the original source and safe field diagnostics.
            # Never coerce a guessed value into the required type.
            try:
                repaired, repair_meta = process_text(
                    source_text,
                    source_context,
                    prompt=prompt
                    + "\n이전 출력이 필드 검증에 실패했다. 원문으로 다시 추출하고 스키마의 타입을 지켜라. 모르는 값은 스키마가 허용하는 unknown 표현을 사용하고 사실을 만들지 마라. 검증 결과: "
                    + json.dumps(diagnostic, ensure_ascii=False),
                    output_schema=output_schema,
                    final_schema=final_schema,
                    session=session,
                    settings=settings,
                    source_units=source_units,
                    target_ids=target_ids,
                    _repair_attempt=True,
                )
            except ProcessingError as exc:
                exc.diagnostic["previous_attempts"] = [diagnostic]
                raise
            repair_meta["repair_attempts"] = [diagnostic]
            repair_meta["latency_seconds"] += latency
            return repaired, repair_meta
        raise ProcessingError("INVALID_EXTRACTION_SCHEMA", "schema", issues=issues[:20])
    for i, memory in enumerate(extraction["memories"]):
        metadata["warnings"].extend(
            dict(w, memory_index=i) for w in remove_duplicate_target(memory)
        )
        metadata["warnings"].extend(
            dict(w, memory_index=i) for w in restore_explicit_companion(memory)
        )
        metadata["warnings"].extend(
            dict(w, memory_index=i) for w in restore_transfer_participants(memory)
        )
    violations = [
        dict(memory_index=i, **issue)
        for i, memory in enumerate(extraction["memories"])
        for issue in relation_issues(memory)
    ]
    if violations and not _repair_attempt:
        repaired, repair_meta = process_text(
            source_text,
            source_context,
            prompt=prompt
            + "\n관계 검사에서 오류가 발견됐다. 원문을 다시 확인해 실제 주체와 행동 대상을 보존하라. "
            "동행 관계에 장소나 시간을 넣지 말고 확실하지 않은 target은 null로 둬라. 검사: "
            + json.dumps(violations, ensure_ascii=False),
            output_schema=output_schema,
            final_schema=final_schema,
            session=session,
            settings=settings,
            source_units=source_units,
            target_ids=target_ids,
            _repair_attempt=True,
        )
        repair_meta.setdefault("repair_attempts", []).append(
            dict(code="RELATION_REPAIR", stage="relation", issues=violations)
        )
        repair_meta["latency_seconds"] += latency
        return repaired, repair_meta
    if violations:
        core = [issue for issue in violations if issue["field"] != "target"]
        if core:
            raise ProcessingError("RELATION_VALIDATION_FAILED", "relation", issues=core)
        for i in sorted({issue["memory_index"] for issue in violations}):
            extraction["memories"][i]["target"] = None
            metadata["warnings"].append(
                dict(
                    code="TARGET_ABSTAINED",
                    memory_index=i,
                    issues=[v for v in violations if v["memory_index"] == i],
                )
            )
            metadata["warnings"].extend(
                dict(w, memory_index=i)
                for w in restore_transfer_participants(extraction["memories"][i])
            )
    for i, annotation in enumerate(metadata.get("provenance", [])):
        annotation["relation_validation"] = dict(
            status="abstained"
            if any(
                w["code"] == "TARGET_ABSTAINED" and w["memory_index"] == i
                for w in metadata["warnings"]
            )
            else "grounded_from_source"
            if any(
                w["code"] == "TARGET_GROUNDED_FROM_SOURCE" and w["memory_index"] == i
                for w in metadata["warnings"]
            )
            else "no_detected_violation",
            scope="explicit_transfer_and_companion_arguments",
        )
    result = build_final_result(extraction, source_context)
    report = validate_final_result(result, final_schema, source_text)
    if not report["valid"]:
        raise ProcessingError(
            "EVIDENCE_MISMATCH" if not report["evidence_valid"] else "INVALID_FINAL_SCHEMA",
            "evidence" if not report["evidence_valid"] else "schema",
        )
    metadata.update(
        latency_seconds=latency,
        memory_count=len(result["memories"]),
        output_schema_valid=True,
        final_schema_valid=True,
        evidence_valid=True,
        prompt_hash=fingerprint(prompt),
        schema_hash=fingerprint(output_schema),
        settings_hash=fingerprint(vars(settings)),
    )
    return result, metadata
