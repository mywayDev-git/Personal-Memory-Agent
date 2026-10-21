"""Shared extraction contract for CLI, evaluation and the local application."""

import copy
import hashlib
import json

from jsonschema import Draft202012Validator, FormatChecker

from .diagnostics import ProcessingError
from .exceptions import ExtractionError, SchemaValidationError
from .extractor import extract_memories
from .meaning import action_assertions, extraction_conflicts
from .postprocess import build_final_result
from .provenance import normalize_time
from .validator import schema_errors, validate_extraction, validate_final_result


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def decoder_schema(schema):
    """Express conditional value types as a tagged union for constrained decoders."""
    result = copy.deepcopy(schema)
    value = result.get('$defs', {}).get('value_ref')
    if not value or not value.get('allOf'):
        return result
    branches = []
    for tag, kind in [('string', 'string'), ('number', 'number'), ('boolean', 'boolean'),
                      ('date', 'string'), ('datetime', 'string'), ('none', 'null')]:
        branch = {k: copy.deepcopy(v) for k, v in value.items() if k != 'allOf'}
        branch['properties']['value_type'] = {'const': tag}
        branch['properties']['value'] = {'type': kind}
        if kind == 'string':
            branch['properties']['value']['minLength'] = 1
        if tag != 'none':
            branch['properties']['kind'] = {'enum': ['self', 'entity', 'literal']}
        branches.append(branch)
    result['$defs']['value_ref'] = {'oneOf': branches}
    return result


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
    request_schema = decoder_schema(output_schema)
    request_text = source_text
    if source_units is not None:
        request_schema = decoder_schema(output_schema)
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
    def repair(diagnostic, latency=0):
        if _repair_attempt:
            raise ProcessingError(diagnostic["code"], diagnostic["stage"], issues=diagnostic.get("issues", []))
        try:
            repaired, meta = process_text(
                source_text, source_context,
                prompt=prompt + "\n이전 출력이 검증에 실패했다. 원문과 스키마만 사용해 다시 추출하라. 타입과 필수 필드를 지켜라. "
                "value_type=number이면 value는 따옴표 없는 JSON 숫자이고, string/date/datetime이면 문자열이다. "
                "사건 날짜가 없으면 time.raw/start/end는 null, precision=unknown, certainty=uncertain이다. "
                "time.start/end는 문자열 또는 null이며 객체나 배열을 넣지 않는다. 숫자를 모르면 숫자를 만들어내지 않는다. "
                + json.dumps(diagnostic, ensure_ascii=False),
                output_schema=output_schema, final_schema=final_schema, session=session,
                settings=settings, source_units=source_units, target_ids=target_ids, _repair_attempt=True)
        except ProcessingError as exc:
            exc.diagnostic["previous_attempts"] = [diagnostic]
            raise
        meta.setdefault("repair_attempts", []).append(diagnostic)
        meta["latency_seconds"] += latency
        return repaired, meta

    try:
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
    except ExtractionError:
        return repair(dict(code="MODEL_INVALID_JSON", stage="parse"))
    # Validate before iterating memory/evidence objects or normalizing time.
    # A malformed list/object must yield a bounded repair, not an AttributeError.
    if schema_errors(extraction, request_schema):
        issues = [{"path": list(e.absolute_path), "rule": e.validator}
                  for e in Draft202012Validator(request_schema, format_checker=FormatChecker()).iter_errors(extraction)]
        return repair(dict(code="INVALID_EXTRACTION_SCHEMA", stage="schema", issues=issues[:20]), latency)
    if source_units is not None:
        by_id = {u["id"]: u for u in source_units}
        annotations = []
        for index, memory in enumerate(extraction.get("memories", [])):
            ids = [e.get("sentence_id") for e in memory.get("evidence", [])]
            if not ids or any(i not in by_id or i not in target_ids for i in ids):
                raise ProcessingError(
                    "EVIDENCE_MISMATCH", "evidence", field=f"memories[{index}].evidence"
                )
            units = [by_id[i] for i in dict.fromkeys(ids)]
            memory["evidence"] = [{"quote": u["text"]} for u in units]
            temporal = normalize_time(memory, units, source_context.get("reference_time"))
            annotations.append(
                dict(
                    time_validation=temporal,
                    evidence=[{"start": u["start"], "end": u["end"]} for u in units],
                )
            )
        metadata["provenance"] = annotations
    if validate_extraction(extraction, output_schema):
        issues = [
            {"path": list(e.absolute_path), "rule": e.validator}
            for e in Draft202012Validator(
                output_schema, format_checker=FormatChecker()
            ).iter_errors(extraction)
        ]
        diagnostic = dict(code="INVALID_EXTRACTION_SCHEMA", stage="schema", issues=issues[:20])
        if not _repair_attempt:
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
    conflicts = extraction_conflicts(extraction["memories"])
    if conflicts:
        diagnostic = dict(code="EXTRACTION_MEANING_MISMATCH", stage="meaning", issues=conflicts)
        if not _repair_attempt:
            repaired, repair_meta = process_text(
                source_text, source_context,
                prompt=prompt + "\n이전 추출의 content와 predicate가 원문의 동작을 반대로 표현했다. "
                "접었다/그만뒀다/중단했다를 시작했다로, 실패를 성공으로, 퇴사를 입사로, 판매를 구매로 바꾸지 마라. "
                "원문을 다시 읽고 content와 predicate를 일치시켜라. 불확실하면 추측하지 마라. "
                + json.dumps(diagnostic, ensure_ascii=False),
                output_schema=output_schema, final_schema=final_schema, session=session,
                settings=settings, source_units=source_units, target_ids=target_ids, _repair_attempt=True,
            )
            repair_meta.setdefault("repair_attempts", []).append(diagnostic)
            repair_meta["latency_seconds"] += latency
            return repaired, repair_meta
        # A model can repeat a fluent but opposite summary after repair. If its
        # predicate is explicitly supported, use the complete original quote as
        # the summary instead of publishing that paraphrase. Never repair an
        # unsupported predicate or invent an action/role through this fallback.
        for issue in conflicts:
            memory = extraction["memories"][issue["index"]]
            quote = "\n".join(e["quote"] for e in memory["evidence"])
            predicate = action_assertions(memory.get("predicate", ""))
            original = action_assertions(quote)
            if not predicate or any(not states <= original.get(family, set())
                                    for family, states in predicate.items()):
                raise ProcessingError("EXTRACTION_MEANING_MISMATCH", "meaning", issues=conflicts)
            memory["content"] = quote
        if extraction_conflicts(extraction["memories"]):
            raise ProcessingError("EXTRACTION_MEANING_MISMATCH", "meaning", issues=conflicts)
        metadata["summary_fallback"] = "verbatim_supported_predicate"
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
