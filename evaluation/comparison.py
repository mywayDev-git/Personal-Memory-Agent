"""Conservative comparison: unknown experimental conditions are not equal conditions."""

from .metrics import dashboard_metrics


def compare(repo, left_id, right_id):
    left, right = repo.get_run(left_id), repo.get_run(right_id)
    reasons = []
    if left["content_hash"] != right["content_hash"]:
        reasons.append("dataset_content_hash")
    for key in ("snapshot", "model", "embedding", "grading_version", "retrieval"):
        a, b = left["config"].get(key), right["config"].get(key)
        if a is None or b is None or a != b:
            reasons.append(key)
        elif key == "model" and isinstance(a, dict) and not a.get("model"):
            reasons.append("model identity unconfigured")
    if left["variant"] != right["variant"]:
        reasons.append("variant (ablation comparison not enabled)")
    if left["environment"] != right["environment"]:
        reasons.append("environment")
    if left["status"] != "completed" or right["status"] != "completed":
        reasons.append("incomplete_run")
    left_results = {result.case_id: result for result in repo.results(left_id)}
    right_results = {result.case_id: result for result in repo.results(right_id)}
    common = sorted(
        k
        for k in left_results.keys() & right_results.keys()
        if left_results[k].verdict in {"pass", "fail"}
        and right_results[k].verdict in {"pass", "fail"}
    )
    cases = [c for c in repo.cases(left["dataset_id"]) if c.id in common]
    lm = dashboard_metrics(cases, [left_results[k] for k in common])
    rm = dashboard_metrics(cases, [right_results[k] for k in common])
    deltas = {
        k: None
        if reasons or lm[k]["value"] is None or rm[k]["value"] is None
        else (rm[k]["value"] - lm[k]["value"]) * (1 if k == "p95_latency_ms" else 100)
        for k in lm
    }
    return dict(
        left=left,
        right=right,
        comparable=not reasons,
        reasons=reasons,
        common_case_count=len(common),
        metric_deltas=deltas,
        delta_units={"ratios": "percentage_points", "p95_latency_ms": "ms"},
        new_failures=[
            k
            for k in common
            if left_results[k].verdict == "pass" and right_results[k].verdict == "fail"
        ]
        if not reasons
        else [],
        resolved=[
            k
            for k in common
            if left_results[k].verdict == "fail" and right_results[k].verdict == "pass"
        ]
        if not reasons
        else [],
        persistent_failures=[
            k for k in common if left_results[k].verdict == right_results[k].verdict == "fail"
        ]
        if not reasons
        else [],
        excluded=sorted((left_results.keys() | right_results.keys()) - set(common)),
    )
