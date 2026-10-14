"""Conservative partial scoring. Never equate keyword checks with semantic accuracy."""

from collections import Counter


def value(item, path):
    for key in path.split("."):
        if not isinstance(item, dict):
            return None
        item = item.get(key)
    return item


def normalized(text):
    if text is None:
        return None
    return str(text).replace(" ", "").rstrip(".")


def prf(tp, predicted, expected):
    p = tp / predicted if predicted else None
    r = tp / expected if expected else None
    return dict(
        tp=tp,
        predicted=predicted,
        expected=expected,
        precision=p,
        recall=r,
        f1=2 * p * r / (p + r) if p is not None and r is not None and p + r else 0.0,
    )


def score_extraction(case, result):
    gold = case["gold_events"]
    events = result["events"]
    matched, used, uncertain = {}, set(), []
    for pi, event in enumerate(events):
        candidates = []
        for gi, g in enumerate(gold):
            support = any(
                e.get("record") == g["record"] and e["start"] <= g["start"] and e["end"] >= g["end"]
                for e in event["evidence"]
            )
            if support and normalized(event["predicate"]) in {
                normalized(a) for a in g["predicate"]
            }:
                candidates.append(gi)
        available = [g for g in candidates if g not in used]
        if len(available) == 1:
            matched[pi] = available[0]
            used.add(available[0])
        else:
            uncertain.append(dict(event=pi, reason="duplicate_or_unaligned", candidates=candidates))
    fields = []
    for pi, gi in matched.items():
        for key, expected in gold[gi]["fields"].items():
            actual = value(events[pi], key)
            equal = (
                actual == expected
                if isinstance(expected, list)
                else normalized(actual) == normalized(expected)
            )
            fields.append(
                dict(
                    event=pi,
                    field=key,
                    expected=expected,
                    actual=actual,
                    correct=equal,
                    wrong_resolution=expected is None and actual is not None,
                    unnecessary_abstention=expected is not None and actual is None,
                )
            )
    wanted = {(r["source"], r["target"], r["type"]) for r in case["gold_relations"]}
    predicted = [
        (matched.get(r["source"], -1), matched.get(r["target"], -1), r["type"])
        for r in result["relations"]
    ]
    relation_tp = len(wanted & set(predicted))
    question_gold = {(i, f) for i, g in enumerate(gold) for f in g.get("ambiguous_fields", [])}
    question_predicted = {(matched.get(q["event"], -1), q["field"]) for q in result["questions"]}
    return dict(
        alignment=matched,
        event_lower_bound=prf(len(matched), len(events), len(gold)),
        unmatched_gold=[i for i in range(len(gold)) if i not in used],
        review_queue=uncertain,
        fields=fields,
        relation_specified_checks=prf(relation_tp, len(predicted), len(wanted)),
        relation_by_type={
            kind: prf(
                len({r for r in wanted & set(predicted) if r[2] == kind}),
                sum(r[2] == kind for r in predicted),
                sum(r[2] == kind for r in wanted),
            )
            for kind in {r[2] for r in wanted | set(predicted)}
        },
        clarification_checks=prf(
            len(question_gold & question_predicted), len(question_predicted), len(question_gold)
        ),
        over_split_candidates=sum(bool(q["candidates"]) for q in uncertain),
        duplicate_relations=sum(n - 1 for n in Counter(predicted).values()),
        semantic_precision=None,
        semantic_recall=None,
        note="Alias/span matches are partial lower-bound checks. Unaligned events and unlisted relations require review; gold is not an exhaustive ontology.",
    )


def score_answer(question, response, retrieved):
    items = response.get("items", [])
    text = " ".join(i["text"] for i in items)
    ids = {r["id"] for r in retrieved}
    citations = [c for i in items for c in i["citations"]]
    supported = {e.get("record") for r in retrieved for e in r.get("evidence", [])}
    wanted = set(question["supporting_records"])
    return dict(
        status=response.get("status"),
        expected_mode=question["mode"],
        lexical_check=any(t in text for t in question["contains_any"])
        if question["contains_any"]
        else None,
        appropriate_abstention=(response.get("status") == "insufficient_evidence" and not items)
        if question["mode"] == "abstain"
        else None,
        citation_ids_valid=all(c in ids for c in citations),
        evidence_recall=len(wanted & supported) / len(wanted) if wanted else None,
        irrelevant_record_fraction=len(supported - wanted) / len(supported)
        if wanted and supported
        else None,
        semantic_verdict=None,
        citation_entailment=None,
        review_required=True,
    )


def apply_reviews(entries, reviews):
    """Only attributed human/externally reviewed decisions enter semantic metrics."""
    by_id = {e["run_id"]: e for e in entries}
    seen = set()
    for review in reviews:
        key = (review["run_id"], review["question"])
        if key in seen or review["run_id"] not in by_id:
            raise ValueError("INVALID_OR_DUPLICATE_REVIEW")
        seen.add(key)
        if not review.get("reviewer", "").strip() or not review.get("rationale", "").strip():
            raise ValueError("REVIEW_ATTRIBUTION_REQUIRED")
        if review["verdict"] not in {
            "correct",
            "partial",
            "incorrect",
            "appropriate_abstention",
            "excessive_abstention",
        }:
            raise ValueError("INVALID_REVIEW_VERDICT")
        entry = by_id[review["run_id"]]
        if entry.get("result_hash") != review.get("result_hash"):
            raise ValueError("STALE_REVIEW")
        questions = entry.get("answers", [])
        if not 0 <= review["question"] < len(questions):
            raise ValueError("INVALID_REVIEW_QUESTION")
        target = questions[review["question"]]["assessment"]
        target.update(
            semantic_verdict=review["verdict"],
            review_required=False,
            reviewer=review["reviewer"],
            rationale=review["rationale"],
        )
