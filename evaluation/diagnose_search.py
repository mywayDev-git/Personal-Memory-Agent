"""Offline, conservative analysis of private v1 search traces. No model or DB access.

Run python -m evaluation.diagnose_search --help. Bindings explicitly associate
evaluation case IDs and gold IDs with a request's pseudonyms; never join by order.
"""

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

STAGES = (
    "snapshot",
    "structure_filter",
    "vector_retrieval",
    "keyword_retrieval",
    "retrieval_union",
    "rank_fusion",
    "evidence_selection",
)
ACTIVE = {"included", "selected"}


def load_cases(data):
    """Adapt existing search fixtures, scenario supporting indices, and dashboard groups.

    relevant is an annotated record set, not a claim that every record is necessary.
    Explicit gold_groups encode required groups with alternative memories per group.
    """
    cases = []
    parents = data if isinstance(data, list) else [data]
    for parent in parents:
        questions = parent.get("questions", [parent] if "question" in parent else [])
        for index, question in enumerate(questions):
            cid = question.get("id") or f"{parent.get('id', 'case')}.{index}"
            unit = "memory"
            groups = question.get("gold_groups")
            if groups:
                gold = list(groups.values())
            elif "gold_memory_ids" in question:
                gold = [[i] for i in question["gold_memory_ids"]]
            else:
                unit = "record"
                ids = question.get(
                    "gold_record_ids",
                    question.get("relevant", question.get("supporting_records", [])),
                )
                gold = [[str(i)] for i in ids]
            if any(
                not isinstance(g, list) or not g or any(not isinstance(i, str) or not i for i in g)
                for g in gold
            ):
                raise ValueError("Invalid gold evidence groups")
            cases.append(
                {
                    "id": str(cid),
                    "unit": unit,
                    "gold": gold,
                    "has_expected": bool(
                        question.get("expected")
                        or question.get("expected_answer")
                        or parent.get("expected")
                    ),
                    "gold_semantics": "required_groups" if groups else "annotated_set",
                }
            )
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Duplicate case IDs; use an explicit dataset-specific case ID")
    return cases


def capture_binding(trace, case_id, *, memory_ids=(), records=None, **labels):
    """Explicit evaluation-only export. Call after trace completion.

    records maps fixture aliases/indices to actual stored record IDs. Unknown IDs
    remain null. This sidecar contains IDs, so keep it separate from default logs.
    """
    return {
        case_id: {
            "trace_id": trace.trace_id,
            "memory_refs": {i: trace.lookup_ref("memory", i) for i in memory_ids},
            "record_refs": {
                str(alias): trace.lookup_ref("record", rid)
                for alias, rid in (records or {}).items()
            },
            **{
                key: value
                for key, value in labels.items()
                if key in {"answer_correct", "answerable", "expected_verified"}
                and type(value) is bool
            },
        }
    }


def read_events(path):
    events = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
                if (
                    not isinstance(event, dict)
                    or event.get("schema_version") != "pma.search_trace.v1"
                    or not isinstance(event.get("trace_id"), str)
                ):
                    raise ValueError
            except ValueError, TypeError:
                raise ValueError(f"Invalid trace event at line {number}") from None
            events.append(event)
    return events


def _candidates(event, k=None):
    if event is None or event.get("status") in {"not_executed", "error"}:
        return None
    if not isinstance(event.get("candidates"), list):
        return None
    rows = [c for c in event.get("candidates", []) if c.get("status") in ACTIVE]
    if k is not None:
        rows = sorted(rows, key=lambda c: c.get("rank", math.inf))[:k]
    return {c["memory_ref"] for c in rows if c.get("memory_ref")}


def _recall(groups, found):
    return None if found is None else sum(bool(g & found) for g in groups) / len(groups)


def _case(case, binding, events, k):
    result = {
        "case_id": case["id"],
        "unit": case["unit"],
        "trace_id": binding.get("trace_id"),
        "stage_recall": {s: None for s in STAGES},
        "evidence_recall": None,
        "recall_at_k": {
            s: None
            for s in ("vector_retrieval", "keyword_retrieval", "retrieval_union", "rank_fusion")
        },
        "complete_evidence_recall": None,
        "loss_stage": "unknown",
        "evaluation_unavailable_reason": None,
        "filter_exclusions": {},
        "gold_exclusions": [],
        "evidence_present_answer_failed": None,
        "evidence_present_no_answer": None,
        "unnecessary_clarification": None,
        "suspected_unnecessary_clarification": False,
        "insufficient_evidence_abstention": False,
        "stage_counts": {},
        "stage_durations_ms": {},
        "total_duration_ms": None,
        "final_status": None,
    }
    by_stage = defaultdict(list)
    for event in events:
        by_stage[event["stage"]].append(event)
    for stage, rows in by_stage.items():
        result["stage_counts"][stage] = [
            {"input_count": e.get("input_count"), "output_count": e.get("output_count")}
            for e in rows
            if "input_count" in e or "output_count" in e
        ]
        result["stage_durations_ms"][stage] = [
            e["duration_ms"]
            for e in rows
            if type(e.get("duration_ms")) in (int, float)
            and math.isfinite(e["duration_ms"])
            and e["duration_ms"] >= 0
        ]
    final = by_stage.get("final_decision", [{}])[-1]
    http = by_stage.get("http_request", [{}])[-1]
    result["final_status"] = final.get("status")
    result["total_duration_ms"] = http.get("duration_ms", final.get("duration_ms"))
    result["insufficient_evidence_abstention"] = (
        final.get("status") == "abstention" and final.get("reason") == "insufficient_evidence"
    )
    structural = by_stage.get("structure_filter", [{}])[-1]
    result["filter_exclusions"] = dict(
        Counter(
            c.get("reason", "unknown")
            for c in structural.get("candidates", [])
            if c.get("status") == "excluded"
        )
    )

    def unavailable(reason):
        result["evaluation_unavailable_reason"] = reason
        return result

    if not case["gold"]:
        return unavailable("no_gold_evidence")
    if not binding or not events:
        return unavailable("trace_binding_missing")
    if any(e.get("truncated") or e.get("recording_failed") for e in events):
        return unavailable("trace_incomplete")
    sequences = [e.get("event_sequence") for e in events]
    if sequences != list(range(1, len(events) + 1)) or len(by_stage.get("final_decision", [])) != 1:
        return unavailable("trace_incomplete_or_multiple_requests")
    unit = case["unit"]
    mapping = binding.get(f"{unit}_refs", {})
    prefix = f"{unit}-{binding['trace_id']}-"
    if any(
        not isinstance(mapping.get(i), str) or not mapping[i].startswith(prefix)
        for g in case["gold"]
        for i in g
    ):
        return unavailable("gold_id_mapping_missing")
    groups = [{mapping[i] for i in group} for group in case["gold"]]
    observed_refs = {c.get(f"{unit}_ref") for e in events for c in e.get("candidates", [])}
    observed_refs.update(
        ref
        for e in events
        for key in ("evidence_refs", "model_selected_refs", "citation_refs", "record_refs")
        for ref in (e.get(key) or [])
    )
    if any(ref not in observed_refs for group in groups for ref in group):
        return unavailable("gold_mapping_not_observed")
    links = {}
    for e in by_stage.get("snapshot", []):
        for c in e.get("candidates", []):
            if c.get("memory_ref") and c.get("record_ref"):
                if c["memory_ref"] in links and links[c["memory_ref"]] != c["record_ref"]:
                    return unavailable("ambiguous_source_mapping")
                links[c["memory_ref"]] = c["record_ref"]

    candidates = {
        s: _candidates(by_stage.get(s, [None])[-1]) for s in STAGES if s != "retrieval_union"
    }
    ranked = {
        s: _candidates(by_stage.get(s, [None])[-1], k)
        for s in ("vector_retrieval", "keyword_retrieval", "rank_fusion")
    }
    ranked["retrieval_union"] = (
        None
        if ranked["vector_retrieval"] is None or ranked["keyword_retrieval"] is None
        else ranked["vector_retrieval"] | ranked["keyword_retrieval"]
    )
    vector, keyword = candidates["vector_retrieval"], candidates["keyword_retrieval"]
    candidates["retrieval_union"] = None if vector is None or keyword is None else vector | keyword
    # Empty structural output establishes no downstream evidence; do not turn
    # a missing/failed retrieval event into zero when viable candidates remain.
    if candidates["structure_filter"] == set():
        candidates["rank_fusion"] = set()
        candidates["evidence_selection"] = set()
    elif candidates["rank_fusion"] == set():
        candidates["evidence_selection"] = set()
    if unit == "record":
        if any(
            ref not in links for refs in candidates.values() if refs is not None for ref in refs
        ):
            return unavailable("record_memory_mapping_missing")
        if any(ref not in set(links.values()) for group in groups for ref in group):
            return unavailable("record_memory_mapping_missing")
        candidates = {
            s: None if ids is None else {links[i] for i in ids} for s, ids in candidates.items()
        }
        ranked = {s: None if ids is None else {links[i] for i in ids} for s, ids in ranked.items()}
    result["recall_at_k"] = {s: _recall(groups, ids) for s, ids in ranked.items()}
    result["stage_recall"] = {s: _recall(groups, candidates.get(s)) for s in STAGES}
    result["evidence_recall"] = result["stage_recall"]["evidence_selection"]
    if result["evidence_recall"] is None:
        return unavailable("final_evidence_not_observed")
    complete = result["evidence_recall"] == 1
    result["complete_evidence_recall"] = int(complete)
    # Retrieval is a branch, not a destructive step: fusion may add structural candidates.
    pipeline = ["snapshot", "structure_filter", "rank_fusion", "evidence_selection"]
    losses = []
    for group in groups:
        if group & candidates["evidence_selection"]:
            continue
        stage_loss = "unknown"
        for index, stage in enumerate(pipeline):
            found = candidates[stage]
            later = [candidates[s] for s in pipeline[index + 1 :]]
            if (
                found is not None
                and not group & found
                and all(v is not None and not group & v for v in later)
            ):
                stage_loss = stage
                break
        losses.append(stage_loss)
    result["loss_stage"] = (
        "none"
        if complete
        else "unknown"
        if "unknown" in losses
        else min(losses, key=pipeline.index)
    )
    gold_refs = set.union(*groups)
    for c in structural.get("candidates", []):
        ref = c.get("memory_ref") if unit == "memory" else links.get(c.get("memory_ref"))
        if c.get("status") == "excluded" and ref in gold_refs:
            result["gold_exclusions"].append(
                {"reason": c.get("reason", "unknown"), "evidence_ref": ref}
            )
    status = final.get("status")
    correct = binding.get("answer_correct")
    result["evidence_present_no_answer"] = complete and status in {"abstention", "error"}
    if not complete:
        result["evidence_present_answer_failed"] = False
    elif type(correct) is bool:
        result["evidence_present_answer_failed"] = not correct
    elif status == "error":
        result["evidence_present_answer_failed"] = True
    elif (
        status == "abstention"
        and case.get("has_expected")
        and binding.get("expected_verified") is True
        and type(binding.get("answerable")) is bool
    ):
        result["evidence_present_answer_failed"] = binding["answerable"]
    result["suspected_unnecessary_clarification"] = complete and status == "clarification"
    if (
        status == "clarification"
        and complete
        and case.get("has_expected")
        and binding.get("expected_verified") is True
        and type(binding.get("answerable")) is bool
    ):
        result["unnecessary_clarification"] = binding["answerable"]
    return result


def analyze(events, cases, bindings=None, k=20):
    if type(k) is not int or k < 1:
        raise ValueError("k must be positive")
    bindings = bindings or {}
    grouped = defaultdict(list)
    for event in events:
        grouped[event["trace_id"]].append(event)
    used = [b.get("trace_id") for b in bindings.values() if b.get("trace_id")]
    if len(set(used)) != len(used):
        raise ValueError("One trace must not be assigned to multiple evaluation cases")
    results = [
        _case(
            c,
            bindings.get(c["id"], {}),
            grouped.get(bindings.get(c["id"], {}).get("trace_id"), []),
            k,
        )
        for c in cases
    ]
    available = [r for r in results if r["evidence_recall"] is not None]
    stage_recall = {}
    for stage in STAGES:
        values = [r["stage_recall"][stage] for r in results if r["stage_recall"][stage] is not None]
        stage_recall[stage] = {"mean": mean(values) if values else None, "evaluated": len(values)}
    at_k = {}
    for stage in ("vector_retrieval", "keyword_retrieval", "retrieval_union", "rank_fusion"):
        values = [r["recall_at_k"][stage] for r in results if r["recall_at_k"][stage] is not None]
        at_k[stage] = {"mean": mean(values) if values else None, "evaluated": len(values)}
    losses = Counter(
        r["loss_stage"] for r in available if r["loss_stage"] not in {"none", "unknown"}
    )
    priorities = [
        {"stage": stage, "observed_cases": count} for stage, count in losses.most_common(5)
    ]
    failed = sum(r["evidence_present_answer_failed"] is True for r in available)
    if failed:
        priorities.append({"stage": "answer_validation_or_generation", "observed_cases": failed})
    priorities = sorted(priorities, key=lambda r: -r["observed_cases"])[:5]
    exclusions = Counter()
    durations = defaultdict(list)
    for result in results:
        exclusions.update(result["filter_exclusions"])
        for stage, values in result["stage_durations_ms"].items():
            durations[stage].extend(values)
    totals = [
        r["total_duration_ms"]
        for r in results
        if type(r["total_duration_ms"]) in (int, float) and math.isfinite(r["total_duration_ms"])
    ]
    summary = {
        "total_questions": len(cases),
        "evaluable_questions": len(available),
        "recall_k": k,
        "stage_recall": stage_recall,
        "recall_at_k": at_k,
        "evidence_recall": mean(r["evidence_recall"] for r in available) if available else None,
        "complete_evidence_recall": mean(r["complete_evidence_recall"] for r in available)
        if available
        else None,
        "loss_stage_counts": dict(losses),
        "priorities": priorities,
        "filter_exclusions": dict(exclusions),
        "total_duration_ms": {"mean": mean(totals) if totals else None, "measured": len(totals)},
        "stage_duration_ms": {
            stage: {"mean": mean(values), "measured": len(values)}
            for stage, values in durations.items()
            if values
        },
        "unavailable_reasons": dict(
            Counter(
                r["evaluation_unavailable_reason"]
                for r in results
                if r["evaluation_unavailable_reason"]
            )
        ),
        "evidence_present_answer_failed": failed,
        "evidence_present_no_answer": sum(r["evidence_present_no_answer"] is True for r in results),
        "suspected_unnecessary_clarifications": sum(
            r["suspected_unnecessary_clarification"] for r in results
        ),
        "confirmed_unnecessary_clarifications": sum(
            r["unnecessary_clarification"] is True for r in results
        ),
        "semantic_accuracy": None,
        "limitations": [
            "Offline trace analysis; no live LLM evaluation was performed.",
            "Annotated-set completeness is not proof of sufficient or necessary evidence.",
            "Missing mappings, incomplete traces, and unexecuted stages are not retrieval failures.",
            "Durations may nest; do not add stage durations to estimate total latency.",
            "Priorities are observed case counts, not estimated accuracy improvements.",
        ],
    }
    return summary, results


def write_report(output, summary, cases):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for name, data in (("diagnostic_summary.json", summary), ("diagnostic_cases.json", cases)):
        (output / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    lines = [
        "# 검색 진단 보고서",
        "",
        f"실행 유형: {summary.get('mode', '입력 Trace의 모델 실행 유형 미확인')}. 실제 제품 정확도로 해석하지 마세요.",
        "",
        f"평가 질문 {summary['total_questions']}개, 근거 평가 가능 {summary['evaluable_questions']}개.",
        "",
        "| 단계 | Recall | 평가 수 |",
        "|---|---:|---:|",
    ]
    for stage, metric in summary["stage_recall"].items():
        lines.append(f"| {stage} | {metric['mean']} | {metric['evaluated']} |")
    lines += [
        "",
        f"## Recall@{summary['recall_k']} (분기별 K, 합집합은 최대 2K)",
        "",
        json.dumps(summary["recall_at_k"], ensure_ascii=False),
    ]
    lines += [
        "",
        "## 근거·필터·시간 요약",
        "",
        f"Evidence Recall: {summary['evidence_recall']}; Complete Evidence Recall: {summary['complete_evidence_recall']}",
        "",
        "필터별 제외 건수: " + json.dumps(summary["filter_exclusions"], ensure_ascii=False),
        "",
        "전체 응답 시간(ms): " + json.dumps(summary["total_duration_ms"], ensure_ascii=False),
        "",
        "단계 시간(ms, 중첩되어 합산 불가): "
        + json.dumps(summary["stage_duration_ms"], ensure_ascii=False),
    ]
    lines += [
        "",
        "## 최초 손실 단계",
        "",
        json.dumps(summary["loss_stage_counts"], ensure_ascii=False),
        "",
        "## 수정 우선순위 (최대 5개)",
        "",
    ]
    lines += [
        f"- {p['stage']}: 관찰 사례 {p['observed_cases']}개" for p in summary["priorities"]
    ] or ["근거가 부족하여 우선순위를 산출하지 않았습니다."]
    for title, selected in (
        (
            "정답 라벨 근거 제외 사례 — 오제외 의심, 정책 검토 필요",
            [r["case_id"] for r in cases if r["gold_exclusions"]],
        ),
        (
            "근거가 있었지만 답변 실패",
            [r["case_id"] for r in cases if r["evidence_present_answer_failed"]],
        ),
        (
            "불필요한 재질문 의심",
            [r["case_id"] for r in cases if r["suspected_unnecessary_clarification"]],
        ),
    ):
        lines += ["", f"## {title}", "", json.dumps(selected, ensure_ascii=False)]
    lines += [
        "",
        "## 평가 불가 이유",
        "",
        json.dumps(summary["unavailable_reasons"], ensure_ascii=False),
        "",
        "## 한계",
        "",
    ]
    lines += [f"- {limit}" for limit in summary["limitations"]]
    (output / "diagnostic_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--bindings", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--k", type=int, default=20)
    args = parser.parse_args()
    cases = load_cases(json.loads(args.dataset.read_text(encoding="utf-8")))
    bindings = json.loads(args.bindings.read_text(encoding="utf-8")) if args.bindings else {}
    summary, results = analyze(read_events(args.trace), cases, bindings, args.k)
    write_report(args.output, summary, results)
    print(
        json.dumps(
            {
                "total_questions": summary["total_questions"],
                "evaluable_questions": summary["evaluable_questions"],
            }
        )
    )


if __name__ == "__main__":
    main()
