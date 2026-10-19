"""Conservative exact comparison. Similarity alone cannot prove equivalence."""

import re


def normalized(content):
    return re.sub(r"\s+", " ", content).strip()


def compare(content, rows):
    result = []
    for row in rows:
        old = row["content"]
        if normalized(content) == normalized(old):
            relation = "exact_duplicate"
        else:
            # Flag overlap for human comparison, never assert contradiction from overlap.
            words = set(re.findall(r"\w+", content))
            previous = set(re.findall(r"\w+", old))
            compact, old_compact = re.sub(r"\W", "", content), re.sub(r"\W", "", old)
            grams = {compact[i : i + 2] for i in range(len(compact) - 1)}
            old_grams = {old_compact[i : i + 2] for i in range(len(old_compact) - 1)}
            overlap = grams & old_grams
            if len(words & previous) < 2 and (
                len(overlap) < 3 or len(overlap) / max(1, len(grams | old_grams)) < 0.15
            ):
                continue
            relation = "needs_review"
        result.append(
            {
                "memory_id": row["memory_id"],
                "content": old,
                "record_version": row["record_version"],
                "relation": relation,
            }
        )
    return result
