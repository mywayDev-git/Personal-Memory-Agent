"""Extractive answers for supported constraints; open questions require model verification."""

from decimal import Decimal

from .facts import COLORS, compatible, distance_values


def claims_supported(items, evidence, plan=None):
    """Reject checkable invented attributes even when the model verifier says yes."""
    by_id = {r["id"]: r for r in evidence}
    for item in items:
        cited = [by_id[c] for c in item["citations"] if c in by_id]
        if plan and any(not compatible(r["fact"], plan) for r in cited):
            return False
        distances = {Decimal(n) for r in cited for n in r.get("fact", {}).get("distance_m", [])}
        if not set(distance_values(item["text"])) <= distances:
            return False
        colors = {v for k, v in COLORS.items() if k in item["text"]}
        supported_colors = {
            v
            for r in cited
            for k, v in COLORS.items()
            if any(k in e["quote"] for e in r["evidence"])
        }
        if not colors <= supported_colors:
            return False
    return True


def grounded_response(found):
    plan, rows = found.get("query_plan", {}), found["results"]
    kind, rel = plan.get("kind"), plan.get("relation")
    if kind == "why":
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
        wishes = [r for r in rows if r["fact"]["relation"] == "desire"]
        gifts = [r for r in rows if r["fact"]["relation"] == "give"]
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
        if row["fact"]["relation"] == "give":
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
