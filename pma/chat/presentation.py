"""Deterministic presentation of already verified claims; never invent source data."""

import re


def presentation(response):
    items = response.get("items", [])
    types = {
        "paragraph": "text",
        "list": "evidence_group",
        "timeline": "event_timeline",
        "entity": "text",
        "table": "evidence_comparison",
    }
    blocks = []
    for block in response.get("blocks", []):
        if not isinstance(block, dict):
            continue
        if not isinstance(block.get("item_indices"), list):
            continue
        indices = [
            i for i in block.get("item_indices", []) if type(i) is int and 0 <= i < len(items)
        ]
        blocks.append({"type": types.get(block.get("type"), "text"), "item_indices": indices})
    if response.get("status") == "needs_clarification":
        blocks = [{"type": "clarification_choices", "item_indices": list(range(len(items)))}]
    elif any(re.search(r"상충|서로\s*다른\s*기록|기록.{0,12}충돌", i["text"]) for i in items):
        blocks = [{"type": "evidence_comparison", "item_indices": list(range(len(items)))}]
    elif any(
        re.search(r"확인할 수 없|알 수 없|명시.{0,8}않|기록.{0,8}없", i["text"]) for i in items
    ):
        # Only mark an explicitly stated limit; never infer missing personal facts.
        blocks = [{"type": "claim_coverage", "item_indices": list(range(len(items)))}]
    return blocks or [{"type": "text", "item_indices": list(range(len(items)))}]
