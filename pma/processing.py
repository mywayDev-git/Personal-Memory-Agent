"""Resumable extraction; no partial memory publication."""

import hashlib
import json
import os

from scripts.memory_agent.accuracy import POLICY_VERSION, RULES
from scripts.memory_agent.diagnostics import ProcessingError
from scripts.memory_agent.pipeline import fingerprint
from scripts.memory_agent.provenance import sentences

from .errors import AppError

PROCESSING_VERSION = 3


def extract_record(service, job, context):
    model = service.models
    if not hasattr(model, "count_tokens"):
        return model.extract(job["text"], context)
    units = sentences(job["text"])
    identity = fingerprint(
        dict(
            version=PROCESSING_VERSION,
            accuracy_policy=POLICY_VERSION,
            accuracy_rules=RULES,
            prompt=model.prompt,
            schema=model.raw_schema,
            settings=vars(service.settings.llm),
            embedding=service.settings.embedding_key,
            generation_revision=os.getenv("PMA_GENERATION_REVISION", "unconfigured"),
        )
    )
    groups, group = [], []
    for unit in units:
        proposed = group + [unit]
        if group and (
            len(proposed) > 6 or model.count_tokens(" ".join(u["text"] for u in proposed)) > 600
        ):
            groups.append(group)
            group = []
        group.append(unit)
    if group:
        groups.append(group)
    all_memories, provenance, diagnostics, warnings = [], [], [], []
    completed = 0
    total = len(groups)

    def run(group, depth=0):
        nonlocal completed, total
        if service.stop_event.is_set():
            raise ProcessingError("PROCESSING_INTERRUPTED", "extract")
        key = fingerprint([identity, [(u["id"], u["start"], u["end"]) for u in group]])
        cached = service.store.chunk_get(job["revision_id"], key)
        if cached and "split" in cached:
            children = cached["split"]
            if len(group) == 1 and children[0][0]["id"] != group[0]["id"]:
                position = next(i for i, u in enumerate(units) if u["id"] == group[0]["id"])
                units[position : position + 1] = children[0] + children[1]
            total += 1
            for child in children:
                run(child, depth + 1)
            return
        service.processing_status = dict(
            service.processing_status,
            chunks_total=total,
            chunks_completed=completed,
            chunk=group[0]["id"],
        )
        if cached is None:
            first = next(i for i, u in enumerate(units) if u["id"] == group[0]["id"])
            last = next(i for i, u in enumerate(units) if u["id"] == group[-1]["id"])
            before, after = units[max(0, first - 2) : first], units[last + 1 : last + 3]
            while before or after:
                if model.count_tokens(" ".join(u["text"] for u in before + after)) <= 300:
                    break
                if before:
                    before.pop(0)
                elif after:
                    after.pop()
            try:
                result, meta = model.extract(
                    job["text"], context, before + group + after, [u["id"] for u in group]
                )
                cached = dict(memories=result["memories"], metadata=meta)
                service.store.chunk_save(job, key, cached)
            except (ProcessingError, AppError) as exc:
                if isinstance(exc, AppError):
                    if exc.code != "CONTEXT_LIMIT":
                        raise
                    exc = ProcessingError(exc.code, "extract")
                exc.diagnostic.update(chunk=group[0]["id"], depth=depth)
                if exc.code not in {"MODEL_TRUNCATED", "CONTEXT_LIMIT"} or depth >= 4:
                    raise exc
                diagnostics.append(exc.diagnostic)
                if len(group) > 1:
                    middle = len(group) // 2
                    service.store.chunk_save(
                        job,
                        key,
                        {"split": [group[:middle], group[middle:]], "diagnostic": exc.diagnostic},
                    )
                    total += 1
                    run(group[:middle], depth + 1)
                    run(group[middle:], depth + 1)
                    return
                unit = group[0]
                text = unit["text"]
                middle = len(text) // 2
                cuts = [m for m in range(1, len(text)) if text[m - 1].isspace()]
                if not cuts:
                    raise
                cut = min(cuts, key=lambda n: abs(n - middle))
                left = dict(unit, id=unit["id"] + "a", end=unit["start"] + cut, text=text[:cut])
                right = dict(unit, id=unit["id"] + "b", start=unit["start"] + cut, text=text[cut:])
                units[first : first + 1] = [left, right]
                service.store.chunk_save(
                    job, key, {"split": [[left], [right]], "diagnostic": exc.diagnostic}
                )
                total += 1
                run([left], depth + 1)
                run([right], depth + 1)
                return
        if len(cached["memories"]) != len(cached["metadata"].get("provenance", [])):
            raise ProcessingError("CACHE_PROVENANCE_INVALID", "cache")
        diagnostics.extend(
            dict(item, chunk=group[0]["id"])
            for item in cached["metadata"].get("repair_attempts", [])
        )
        warnings.extend(
            dict(item, chunk=group[0]["id"]) for item in cached["metadata"].get("warnings", [])
        )
        for m, p in zip(cached["memories"], cached["metadata"].get("provenance", [])):
            signature = hashlib.sha256(
                json.dumps(
                    [{k: v for k, v in m.items() if k != "local_id"}, p["evidence"]],
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
            if signature not in seen:
                seen.add(signature)
                all_memories.append(m)
                provenance.append(p)
        completed += 1

    seen = set()
    for group in groups:
        run(group)
    for i, m in enumerate(all_memories):
        m["local_id"] = f"m{i + 1}"
    service.processing_status = dict(
        service.processing_status, chunks_total=total, chunks_completed=completed
    )
    return {"memories": all_memories}, dict(
        processing_version=PROCESSING_VERSION,
        provenance=provenance,
        chunks_completed=completed,
        chunks_total=total,
        recovered_diagnostics=diagnostics,
        warnings=warnings,
        settings_hash=identity,
    )
