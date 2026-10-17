"""Offline validation ledger and review report. Never treats a verifier as ground truth."""

import argparse
import csv
import hashlib
import html
import json
from collections import Counter
from pathlib import Path
from statistics import median

from evaluation.query_paired import ARMS
from evaluation.query_paired_selective import selection_reasons
from evaluation.query_tree import coverage, digest
from evaluation.query_tree_run import read, write
from evaluation.validation_trace import inspect_trace


def freeze_holdout(development, out, identity, cases):
    """A dataset/source gets one held-out run. Resume is allowed; retuning is not."""
    if development is None:
        raise ValueError("HOLDOUT_REQUIRES_FROZEN_DEVELOPMENT")
    prior = read(development / "manifest.json")
    for key in ("files", "settings", "models", "suite", "arms"):
        if prior.get(key) != identity.get(key):
            raise ValueError("HOLDOUT_CONFIGURATION_CHANGED:" + key)
    if prior.get("validation", {}).get("split") != "development":
        raise ValueError("NOT_A_DEVELOPMENT_RUN")
    if prior["validation"]["memory_source"] != identity["validation"]["memory_source"]:
        raise ValueError("MEMORY_SOURCE_CHANGED")
    expected = {c["id"] for c in cases if c["split"] == "development"}
    completed = {
        e["case"]
        for p in (development / "results").glob("*.json")
        if (e := read(p)).get("status") == "complete" and set(e["arms"]) == set(ARMS)
    }
    if not expected <= completed:
        raise ValueError("DEVELOPMENT_INCOMPLETE")
    protocol_path = out.parent / f"holdout-protocol-{digest(cases)}.json"
    protocol = {key: identity[key] for key in ("files", "settings", "models", "suite", "arms")}
    if protocol_path.exists():
        if read(protocol_path) != protocol:
            raise ValueError("HOLDOUT_PROTOCOL_CHANGED_USE_NEW_DATASET")
    else:
        with protocol_path.open("x", encoding="utf-8") as stream:
            json.dump(protocol, stream, ensure_ascii=False, indent=2)
    key = digest([cases, identity["validation"]["memory_source"]])
    ledger = out.parent / f"holdout-{key}.json"
    value = dict(
        run=str(out.resolve()),
        identity=digest(identity),
        development=str(development.resolve()),
        policy="one run; incomplete cases resumable",
    )
    if ledger.exists():
        if read(ledger) != value:
            raise ValueError("HOLDOUT_ALREADY_CONSUMED_USE_NEW_DATASET")
    else:
        # Exclusive create prevents two differently named runs consuming the same holdout.
        with ledger.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)


def mechanical(entry):
    errors = []
    records = entry.get("records", [])
    frozen = entry.get("frozen_memories", [])
    if len(records) != len(frozen):
        errors.append("record_memory_count")
    for ri, memories in enumerate(frozen):
        for mi, memory in enumerate(memories):
            spans = memory.get("_evidence_spans")
            if not spans:
                errors.append(f"missing_original_offsets:{ri}:{mi}")
                continue
            if [e["quote"] for e in spans] != [e["quote"] for e in memory["evidence"]]:
                errors.append(f"quote_mapping:{ri}:{mi}")
            for s in spans:
                if (
                    ri >= len(records)
                    or not 0 <= s["start"] < s["end"] <= len(records[ri]["text"])
                    or records[ri]["text"][s["start"] : s["end"]] != s["quote"]
                ):
                    errors.append(f"source_offset:{ri}:{mi}")
    for label, arm in entry.get("arms", {}).items():
        for node in arm.get("direct_selected", arm.get("selected", [])):
            ri = node["record_no"]
            source = records[ri]["text"]
            for s in node["evidence"]:
                if (
                    not 0 <= s["start"] < s["end"] <= len(source)
                    or source[s["start"] : s["end"]] != s["quote"]
                ):
                    errors.append(f"replay_offset:{label}:{node['id']}")
            if not any(
                m["content"] == node["content"]
                and [e["quote"] for e in m["evidence"]] == [e["quote"] for e in node["evidence"]]
                for m in frozen[ri]
            ):
                errors.append(f"replay_memory_mapping:{label}:{node['id']}")
        if "direct_selected" in arm and entry.get("gold"):
            if (
                coverage(arm["direct_selected"], entry["gold"])["hits"]
                != arm["metrics"]["selected"]["hits"]
            ):
                errors.append(f"direct_metric:{label}")
    return errors


def review_item(stage, case, payload, arm=None, field=None):
    key = digest([stage, case, arm, field, payload])
    return dict(
        id=key,
        stage=stage,
        case=case,
        arm=arm,
        field=field,
        payload=payload,
        judgment="needs_review",
        reason="",
        reviewer="",
    )


def checked_reviews(path):
    result = {}
    for r in read(path) if path.exists() else []:
        if r["id"] in result:
            raise ValueError("DUPLICATE_REVIEW")
        if r["id"] != digest([r["stage"], r["case"], r.get("arm"), r.get("field"), r["payload"]]):
            raise ValueError("REVIEW_PAYLOAD_CHANGED")
        if r.get("judgment") not in {
            "needs_review",
            "correct",
            "wrong",
            "unclear",
            "appropriate_abstention",
            "excessive_abstention",
        }:
            raise ValueError("INVALID_REVIEW_JUDGMENT")
        if r["judgment"] != "needs_review" and (not r.get("reason") or not r.get("reviewer")):
            raise ValueError("REVIEW_REQUIRES_REASON_AND_REVIEWER")
        if r["stage"] == "retrieval_constraints" and r["judgment"] not in {
            "needs_review",
            "unclear",
        }:
            fields = {c["field"] for c in r["payload"]["constraints"]}
            for key in ("direct_conditions", "delivered_conditions"):
                states = r.get(key, {})
                if set(states) != fields or any(
                    v not in {"satisfied", "missing", "contradictory"} for v in states.values()
                ):
                    raise ValueError("REVIEW_REQUIRES_CONDITION_STATES")
        result[r["id"]] = r
    return result


def audit(run_dir, data, destination):
    cases = {c["id"]: c for c in read(data)}
    manifest = read(run_dir / "manifest.json")
    declared_data = manifest.get("validation", {}).get("data")
    if declared_data is None:
        declared_data = next(
            (
                p
                for p in manifest.get("files", {})
                if p.startswith("data/") and p.endswith("_cases.json")
            ),
            data.as_posix(),
        )
    data_hash = manifest.get("files", {}).get(Path(declared_data).as_posix())
    if data_hash and hashlib.sha256(data.read_bytes()).hexdigest() != data_hash:
        raise ValueError("EVALUATION_DATA_CHANGED")
    expected = set(manifest.get("validation", {}).get("case_ids", cases))
    reviews = checked_reviews(run_dir / "validation-reviews.json")
    queue, errors, details, pairs, excluded, failures = [], [], [], [], [], []
    answer_comparisons, pending_answers = [], []
    entries = [read(p) for p in sorted((run_dir / "results").glob("*.json"))]
    complete = []
    for entry in entries:
        case = cases[entry["case"]]
        if entry.get("status") != "complete" or set(entry["arms"]) != set(ARMS):
            failures.append(dict(case=entry["case"], error=entry.get("detail", entry.get("error"))))
            continue
        complete.append(entry)
        errors.extend(
            dict(case=entry["case"], stage="mechanical", error=e) for e in mechanical(entry)
        )
        if entry["excluded"]:
            excluded.append(
                dict(
                    case=entry["case"],
                    reason=case.get(
                        "exclusion_reason",
                        case.get("gold_note", "legacy exclusion; see source fixture"),
                    ),
                )
            )
            continue
        spec = case.get("validation", {})
        for ri, memories in enumerate(entry["frozen_memories"]):
            for mi, memory in enumerate(memories):
                queue.append(
                    review_item(
                        "memory_support",
                        case["id"],
                        dict(
                            record=ri,
                            memory_index=mi,
                            memory=memory,
                            source=entry["records"][ri]["text"],
                            rubric="Exact quotes alone do not prove semantic support. Check roles, polarity, dates, scope and context.",
                        ),
                    )
                )
        for constraint in spec.get("constraints", []):
            queue.append(
                review_item(
                    "decomposition",
                    case["id"],
                    dict(
                        question=entry["question"],
                        expected=constraint,
                        analysis=entry["analysis"],
                        rubric="Judge semantic role/meaning, not spelling equality. A fallback omits the required field.",
                    ),
                    field=constraint["field"],
                )
            )
        if spec:
            queue.append(
                review_item(
                    "decomposition",
                    case["id"],
                    dict(
                        question=entry["question"],
                        expected=spec["constraints"],
                        analysis=entry["analysis"],
                        rubric="Check the entire parse, including extra/wrong roles, missing negation or modality, action and relation endpoints.",
                    ),
                    field="__overall__",
                )
            )
        selective = run_dir / "selective_answers" / f"{case['id']}--{entry['scale']}.json"
        added = {}
        if selective.exists():
            extra = read(selective)
            original = run_dir / "results" / selective.name
            if extra["result_sha256"] != hashlib.sha256(original.read_bytes()).hexdigest():
                raise ValueError("STALE_SELECTIVE_ANSWERS")
            added = extra["arms"]
        for label in ARMS:
            arm = entry["arms"][label]
            answer_value = added.get(label, arm)
            response = answer_value.get("response")
            trace = answer_value.get("answer_trace", [])
            reused = bool(
                answer_value.get("reused_existing")
                or answer_value.get("reused_within_case")
                or arm.get("answer_reused_from")
            )
            row = dict(
                case=case["id"],
                group=case.get("group"),
                category=case["category"],
                arm=label,
                mandatory=spec.get("mandatory", False),
                direct_all=arm["metrics"]["selected"]["all_required"],
                delivered_all=arm["metrics"]["delivered"]["all_required"],
                direct_precision=arm["metrics"]["selected"]["precision"],
                search_seconds=arm["search_with_analysis_seconds"],
                answer_seconds=answer_value.get("seconds", arm.get("answer_seconds"))
                if response and not reused
                else None,
                answer_reused=reused,
                answer_status=response.get("status") if response else "not_run",
                answer_judgment="not_run" if response is None else "needs_review",
                reason_observed="processing_error"
                if any(t["stage"] == "error" for t in trace)
                else "validator_rejected"
                if any(t["stage"] == "verify" and not t["supported"] for t in trace)
                else "unspecified"
                if response and response["status"] != "answered"
                else None,
            )
            if response is not None:
                item = review_item(
                    "answer",
                    case["id"],
                    dict(
                        question=entry["question"],
                        expected=case.get("expected"),
                        answerability=spec.get("answerability", "legacy_source_review"),
                        time_basis=spec.get("time_basis"),
                        expected_reason=spec.get("expected_reason"),
                        expected_clarification=spec.get("clarification"),
                        response=response,
                        trace=trace,
                        sources=entry["records"],
                        delivered=arm["selected"],
                        rubric="Check source truth, requested date basis, justified deferral and explanation. A successful model verifier is not a correct answer label.",
                    ),
                    arm=label,
                )
                queue.append(item)
                row["answer_judgment"] = reviews.get(item["id"], item)["judgment"]
            constraint_item = review_item(
                "retrieval_constraints",
                case["id"],
                dict(
                    question=entry["question"],
                    constraints=spec.get("constraints", []),
                    direct=arm.get("direct_selected", []),
                    delivered=arm["selected"],
                    rubric="Annotate satisfied, missing and contradictory conditions separately in reason; never count mere surrounding-context coverage as direct support.",
                ),
                arm=label,
            )
            queue.append(constraint_item)
            constraint_review = reviews.get(constraint_item["id"], constraint_item)
            row["constraint_judgment"] = constraint_review["judgment"]
            for key in ("direct_conditions", "delivered_conditions"):
                states = constraint_review.get(key)
                row[key + "_missing"] = (
                    sum(v == "missing" for v in states.values()) if states is not None else None
                )
                row[key + "_contradictory"] = (
                    sum(v == "contradictory" for v in states.values())
                    if states is not None
                    else None
                )
            details.append(row)
        for method in "VMGH":
            a, b = (entry["arms"][method + flag] for flag in "01")
            reasons = selection_reasons(entry, method)
            if reasons:
                compared = {}
                for flag in "01":
                    label = method + flag
                    result = added.get(label, entry["arms"][label])
                    if "response" not in result:
                        pending_answers.append(dict(case=case["id"], arm=label))
                    compared[label] = dict(
                        response=result.get("response"), trace=result.get("answer_trace")
                    )
                answer_comparisons.append(
                    dict(
                        case=case["id"],
                        method=method,
                        question=entry["question"],
                        expected=case.get("expected"),
                        reasons=reasons,
                        answers=compared,
                    )
                )
            for stage in ("selected", "delivered"):
                left, right = (
                    a["metrics"][stage]["all_required"],
                    b["metrics"][stage]["all_required"],
                )
                pairs.append(
                    dict(
                        case=case["id"],
                        method=method,
                        stage=stage,
                        outcome="same" if left == right else "improved" if right else "worsened",
                        selection_reasons=selection_reasons(entry, method),
                    )
                )
    queue = [reviews.get(q["id"], q) for q in queue]
    active_ids = {q["id"] for q in queue}
    if set(reviews) - active_ids:
        raise ValueError("STALE_OR_UNRELATED_REVIEWS")
    summaries = []
    for label in ARMS:
        rows = [r for r in details if r["arm"] == label]
        answered = [r for r in rows if r["answer_status"] != "not_run"]
        judged = [r for r in answered if r["answer_judgment"] not in {"needs_review", "unclear"}]
        accepted = [r for r in judged if r["answer_status"] == "answered"]
        wrong = sum(r["answer_judgment"] == "wrong" for r in accepted)
        summaries.append(
            dict(
                arm=label,
                cases=len(rows),
                direct_all=sum(bool(r["direct_all"]) for r in rows),
                delivered_all=sum(bool(r["delivered_all"]) for r in rows),
                generated_answers=len(answered),
                reviewed_answers=len(judged),
                answer_accuracy=sum(
                    r["answer_judgment"] in {"correct", "appropriate_abstention"} for r in judged
                )
                / len(judged)
                if judged
                else None,
                wrong_accepted=wrong,
                accepted_reviewed=len(accepted),
                wrong_acceptance_rate=wrong / len(accepted) if accepted else None,
                excessive_abstentions=sum(
                    r["answer_judgment"] == "excessive_abstention" for r in judged
                ),
                constraint_reviewed=sum(
                    r["constraint_judgment"] not in {"needs_review", "unclear"} for r in rows
                ),
                direct_contradiction_cases=sum(
                    bool(r["direct_conditions_contradictory"]) for r in rows
                ),
                direct_missing_condition_cases=sum(
                    bool(r["direct_conditions_missing"]) for r in rows
                ),
                search_median_seconds=median([r["search_seconds"] for r in rows]) if rows else None,
                answer_median_seconds=median(
                    [r["answer_seconds"] for r in answered if r["answer_seconds"] is not None]
                )
                if any(r["answer_seconds"] is not None for r in answered)
                else None,
            )
        )
    stages = {}
    for row in summaries:
        denominator = row["constraint_reviewed"]
        row["direct_contradiction_rate"] = (
            row["direct_contradiction_cases"] / denominator if denominator else None
        )
        row["direct_missing_condition_rate"] = (
            row["direct_missing_condition_cases"] / denominator if denominator else None
        )
    for stage in ("memory_support", "decomposition", "retrieval_constraints", "answer"):
        items = [q for q in queue if q["stage"] == stage]
        counts = Counter(q["judgment"] for q in items)
        reviewed = sum(v for k, v in counts.items() if k not in {"needs_review", "unclear"})
        stages[stage] = dict(
            total=len(items),
            judgments=dict(counts),
            reviewed=reviewed,
            accuracy=counts["correct"] / reviewed if reviewed else None,
        )
    for label, overall in (("field", False), ("whole_parse", True)):
        items = [
            q
            for q in queue
            if q["stage"] == "decomposition"
            and (q.get("field") == "__overall__") == overall
            and q["judgment"] not in {"needs_review", "unclear"}
        ]
        stages["decomposition"][label + "_reviewed"] = len(items)
        stages["decomposition"][label + "_accuracy"] = (
            sum(q["judgment"] == "correct" for q in items) / len(items) if items else None
        )
    missing = sorted(expected - {e["case"] for e in entries})
    unresolved = any(q["judgment"] in {"needs_review", "unclear"} for q in queue)
    mandatory_failures = [
        r
        for r in details
        if r["mandatory"] and r["answer_judgment"] in {"wrong", "excessive_abstention"}
    ]
    trace_files = list((run_dir / "extractions").glob("*.trace.json"))
    trace_checks = [dict(file=str(p), **inspect_trace(read(p))) for p in trace_files]
    source = manifest.get("validation", {}).get("memory_source", "legacy_extracted")
    required_records = {digest(r) for e in complete for r in e.get("records", [])}
    traced_records = {digest(read(p)["record"]) for p in trace_files}
    pending_traces = len(required_records - traced_records) if source != "reference" else 0
    trace_unresolved = pending_traces or any(c["unresolved"] for c in trace_checks)
    errors.extend(
        dict(stage="extraction_transform", file=c["file"], error=e)
        for c in trace_checks
        for e in c["errors"]
    )
    model_calls = [c for e in entries for c in e.get("calls", [])]
    prior_attempts = [read(p) for p in (run_dir / "attempts").glob("*.json")]
    model_calls += [c for e in prior_attempts for c in e.get("calls", [])]
    model_calls += [
        c for p in (run_dir / "selective_answers").glob("*.json") for c in read(p).get("calls", [])
    ]
    summary = dict(
        suite="memory-validation-v1",
        expected=len(expected),
        saved=len(entries),
        complete=len(complete),
        missing=missing,
        failures=failures,
        excluded=excluded,
        mechanical_errors=errors,
        trace_files=len(trace_files),
        trace_checks=trace_checks,
        trace_attribution="not_applicable_reference"
        if source == "reference"
        else "unresolved: intermediate extraction evidence unavailable"
        if trace_unresolved
        else "available",
        pending_record_traces=pending_traces,
        source=source,
        decomposition_attempts=sum("analysis" in e for e in entries),
        decomposition_failures=sum(
            e.get("analysis", {}).get("status") == "fallback" for e in entries
        ),
        stages=stages,
        arms=summaries,
        mandatory_failures=mandatory_failures,
        pending_changed_answers=pending_answers,
        gate="failed"
        if errors or mandatory_failures
        else "incomplete"
        if missing or failures or unresolved or pending_answers or trace_unresolved or not details
        else "passed",
        model_calls=len(model_calls),
        model_call_seconds=sum(c["seconds"] for c in model_calls),
        prior_failed_attempts=len(prior_attempts),
        model_call_errors=sum(c["status"] != "ok" for c in model_calls),
        limitations=[
            "Changed-answer subset is not overall accuracy.",
            "Shared scenario templates; distinct event groups are not a natural-user distribution.",
            "Reference memories are a fixture-author-reviewed upper bound, not production performance.",
            "Current graph is lexical event expansion, not structural graph matching.",
            "Unreviewed semantics remain unknown, never pass by default.",
        ],
    )
    destination.mkdir(parents=True, exist_ok=True)
    inputs = [
        run_dir / "manifest.json",
        data,
        *sorted((run_dir / "results").glob("*.json")),
        *sorted((run_dir / "selective_answers").glob("*.json")),
        *trace_files,
    ]
    if (run_dir / "validation-reviews.json").exists():
        inputs.append(run_dir / "validation-reviews.json")
    write(
        destination / "report-source-manifest.json",
        dict(
            inputs={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            report_code={
                str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (
                    Path(__file__),
                    Path("evaluation/validation_trace.py"),
                    Path("evaluation/query_paired_selective.py"),
                )
            },
        ),
    )
    write(destination / "validation-summary.json", summary)
    write(destination / "review-queue.json", queue)
    write(destination / "paired-changes.json", pairs)
    write(destination / "answer-comparisons.json", answer_comparisons)
    write(
        destination / "deferrals.json",
        [r for r in details if r["answer_status"] not in {"answered", "not_run"}],
    )
    write(destination / "stage-errors.json", errors + failures)
    with (destination / "conditions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        if details:
            writer = csv.DictWriter(stream, fieldnames=list(details[0]))
            writer.writeheader()
            writer.writerows(details)
    body = "<html lang='ko'><meta charset='utf-8'><title>기억 검색 검증</title><style>body{font:16px system-ui;margin:32px;max-width:1300px}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #aaa}pre{white-space:pre-wrap}</style>"
    body += "<h1>기억 검색·질문 분해 검증</h1><p>판정: " + summary["gate"] + "</p>"
    body += "<p>직접 근거와 주변 문맥 포함 근거를 분리합니다. 미검토 답변은 정답으로 세지 않습니다.</p><table><tr>"
    columns = [
        "arm",
        "cases",
        "direct_all",
        "delivered_all",
        "generated_answers",
        "reviewed_answers",
        "wrong_accepted",
        "search_median_seconds",
        "answer_median_seconds",
    ]
    body += "".join(f"<th>{c}</th>" for c in columns) + "</tr>"
    for row in summaries:
        body += "<tr>" + "".join(f"<td>{html.escape(str(row[c]))}</td>" for c in columns) + "</tr>"
    body += "</table><h2>변경 사례 답변 비교</h2>"
    for item in answer_comparisons:
        body += (
            "<details><summary>"
            + html.escape(item["case"] + " / " + item["method"] + " / " + item["question"])
            + "</summary><pre>"
            + html.escape(json.dumps(item, ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    body += (
        "<h2>단계별 결과와 한계</h2><pre>"
        + html.escape(json.dumps(summary, ensure_ascii=False, indent=2))
        + "</pre></html>"
    )
    (destination / "validation-report.html").write_text(body, encoding="utf-8")
    return summary


def compare_sources(left_dir, right_dir, destination):
    """Same source/questions and retrieval implementation; vary extraction only."""
    left_manifest, right_manifest = (
        read(left_dir / "manifest.json"),
        read(right_dir / "manifest.json"),
    )
    for key in ("files", "settings", "models", "suite", "arms"):
        if left_manifest.get(key) != right_manifest.get(key):
            raise ValueError("SOURCE_COMPARISON_CONFIGURATION_CHANGED:" + key)
    left_source = left_manifest["validation"]["memory_source"]
    right_source = right_manifest["validation"]["memory_source"]
    if {left_source, right_source} != {"extracted", "reference"}:
        raise ValueError("SOURCE_COMPARISON_REQUIRES_RAW_AND_REFERENCE")
    indices = []
    for directory in (left_dir, right_dir):
        indices.append(
            {
                e["case"]: e
                for p in (directory / "results").glob("*.json")
                if (e := read(p)).get("status") == "complete"
            }
        )
    rows = []
    for case in sorted(indices[0].keys() & indices[1].keys()):
        left, right = indices[0][case], indices[1][case]
        if left["question"] != right["question"] or left["records"] != right["records"]:
            raise ValueError("SOURCE_COMPARISON_INPUT_CHANGED")
        for label in ARMS:
            for stage in ("selected", "delivered"):
                a, b = (e["arms"][label]["metrics"][stage]["all_required"] for e in (left, right))
                rows.append(
                    dict(
                        case=case,
                        arm=label,
                        stage=stage,
                        left_source=left_source,
                        right_source=right_source,
                        left_all=a,
                        right_all=b,
                        outcome="same" if a == b else "right_improved" if b else "right_worsened",
                    )
                )
    destination.mkdir(parents=True, exist_ok=True)
    write(
        destination / "extraction-comparison.json",
        dict(
            matched_questions=len(indices[0].keys() & indices[1].keys()),
            left_only=sorted(indices[0].keys() - indices[1].keys()),
            right_only=sorted(indices[1].keys() - indices[0].keys()),
            rows=rows,
            interpretation="Fixture-author-reviewed reference; not production accuracy.",
        ),
    )
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data", type=Path, default=Path("data/memory_validation_cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare-run", type=Path)
    args = parser.parse_args()
    result = audit(args.run_dir, args.data, args.output)
    if args.compare_run:
        compare_sources(args.run_dir, args.compare_run, args.output)
    print(
        json.dumps(
            {k: result[k] for k in ("expected", "complete", "gate", "trace_attribution")},
            ensure_ascii=False,
        )
    )
