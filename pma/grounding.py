"""Extractive answers for supported constraints; open questions require model verification."""

import re
from decimal import Decimal

from .diagnostics import Reason, Stage
from .facts import COLORS, distance_values
from .validation_diagnostics import check, compatible_evidence, observed_validation


@observed_validation(Stage.GROUNDING_CHECK)
def claims_supported(items, evidence, plan=None):
    """Reject checkable invented attributes even when the model verifier says yes."""
    by_id = {r["id"]: r for r in evidence}
    for item in items:
        cited = [by_id[c] for c in item["citations"] if c in by_id]
        if plan and re.search(r"누가|누구|준\s*사람|주는\s*사람", plan.get("question", "")):
            # A second-person quotation without a stated addressee cannot certify
            # a named actor. Keep it searchable, but don't promote it to a role fact.
            if cited and all(
                {"unresolved_quoted_addressee", "actor_needs_context"}
                & set(r.get("fact", {}).get("review_reasons", []))
                for r in cited
            ):
                check("role", False, cited, Reason.PERSON_MISMATCH)
                return False
        if plan and any(not compatible_evidence(r, plan) for r in cited):
            return False
        distances = {Decimal(n) for r in cited for n in r.get("fact", {}).get("distance_m", [])}
        if not set(distance_values(item["text"])) <= distances:
            check("quantity", False, cited or None, Reason.QUANTITY_MISMATCH)
            return False
        check("quantity", True, cited or None)
        colors = {v for k, v in COLORS.items() if k in item["text"]}
        supported_colors = {
            v
            for r in cited
            for k, v in COLORS.items()
            if any(k in e["quote"] for e in r["evidence"])
        }
        if not colors <= supported_colors:
            check("color", False, cited or None, Reason.UNSUPPORTED_ATTRIBUTES)
            return False
        check("color", True, cited or None)
    return True


def grounded_response(found, *, semantic_current=False):
    plan, rows = found.get("query_plan", {}), found["results"]
    kind, rel = plan.get("kind"), plan.get("relation")
    if rel in {"give", "receive"} and kind not in {"compare", "change"}:
        directions = {(r["fact"].get("actor"), r["fact"].get("recipient")) for r in rows}
        if len(directions) > 1:
            return None
    if plan.get("execution_check") or any(
        r["fact"].get("review_reasons")
        or (
            r["fact"]["relation"] in {"give", "receive"}
            and r["fact"]["state"] != "observed"
            and kind != "compare"
        )
        for r in rows
    ):
        return None
    if any(
        hint["value"] != row["fact"].get(role)
        for role, hint in plan.get("role_hints", {}).items()
        for row in rows
    ):
        return None
    if kind == "why" or (kind == "current" and semantic_current):
        return None
    if kind == "change":
        changes = [r for r in rows if r["fact"]["relation"] == "prefer"]
        if not any(link["kind"] == "preference_change" for link in found["connections"]):
            return {
                "status": "answered",
                "items": [
                    {
                        "text": "이 기록만으로 취향이 바뀌었다고 판단할 수 없습니다. 희망과 실제 행동은 별개의 사실입니다.",
                        "citations": [r["id"] for r in rows],
                    }
                ],
            }
        rows = changes
    if kind == "current":
        preferences = [r for r in rows if r["fact"]["relation"] == "prefer"]
        if preferences:
            # Do not promote recording order to event order; unknown time remains visible.
            rows = preferences
    if kind == "compare":
        wishes = [
            r for r in rows if r["fact"]["relation"] == "desire" and r["fact"]["state"] == "desire"
        ]
        gifts = [
            r for r in rows if r["fact"]["relation"] == "give" and r["fact"]["state"] == "observed"
        ]
        if wishes and gifts:
            w, g = wishes[0], gifts[0]
            active = [
                link
                for link in found["connections"]
                if link["kind"] == "desire_action" and {w["id"], g["id"]} == set(link["citations"])
            ]
            if not active:
                return {
                    "status": "answered",
                    "items": [
                        {
                            "text": "희망과 실제 선물 기록은 있지만, 두 기록의 연결이 확인되지 않아 같은 선물 사건으로 단정하지 않습니다.",
                            "citations": [w["id"], g["id"]],
                        }
                    ],
                }
            if (
                w["fact"]["actor"] == g["fact"]["recipient"]
                and w["fact"]["object_key"] == g["fact"]["object_key"]
                and w["fact"]["colors"]
                and g["fact"]["colors"]
            ):
                comparison = (
                    "색상이 같습니다."
                    if w["fact"]["colors"] == g["fact"]["colors"]
                    else "색상이 다릅니다."
                )
                return {
                    "status": "answered",
                    "items": [
                        {
                            "text": f"원한 것은 {', '.join(w['fact']['colors'])} {w['fact']['object_key']}, 준 것은 {', '.join(g['fact']['colors'])} {g['fact']['object_key']}으로 {comparison} 같은 이름의 인물을 기준으로 대조했습니다.",
                            "citations": [w["id"], g["id"]],
                        }
                    ],
                }
    if rel == "other" and kind not in {"when", "current", "change", "activities"}:
        return None
    items = []
    for row in rows:
        t = row["time"]
        day = t.get("start")
        if day:
            prefix = f"사건 시점 {day}" + (f" ~ {t['end']}" if t.get("end") else "")
        else:
            prefix = "정확한 사건 날짜는 기록에서 확인되지 않습니다"
        text = row["content"]
        if row["fact"]["relation"] == "give" and row["fact"]["state"] == "observed":
            actor = row["fact"].get("actor")
            recipient = row["fact"].get("recipient")
            text = (
                f"주는 사람: {'사용자' if actor == 'self' else actor or '불명'} · 받는 사람: {'사용자' if recipient == 'self' else recipient or '불명'} — "
                + text
            )
        if row["fact"]["state"] == "planned" and not plan.get("planned"):
            text += " — 계획·결정 기록이며 실행 완료를 확인한 기록은 아닙니다."
        if day or kind in {"when", "current", "change"}:
            text = prefix + ": " + text
        if kind in {"current", "change"}:
            text += " (각 시점의 기록이며, 현재 상태를 단정하지 않습니다.)"
        items.append({"text": text, "citations": [row["id"]]})
    return {"status": "answered" if items else "insufficient_evidence", "items": items}
