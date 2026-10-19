"""Source snapshots are derived on the server and checked again at approval."""

import hashlib
import json


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def message_snapshot(row, role, text):
    inputs = json.loads(row["request_input"] or "{}")
    return dict(
        message_id=row["id"],
        session_id=row["session_id"],
        source_type=role,
        text=text,
        fingerprint=digest(text),
        created_at=row["created_at"],
        reference_date=inputs.get("today"),
    )


def source_text(row, source_type):
    if source_type == "user_message":
        return row["question"]
    return "\n\n".join(i["text"] for i in json.loads(row["response"] or "{}").get("items", []))


def corpus_digest(rows):
    return digest(
        [
            {
                k: r.get(k)
                for k in (
                    "memory_id",
                    "record_id",
                    "record_version",
                    "content",
                    "memory_type",
                    "epistemic_status",
                    "project_scope",
                    "event_time",
                    "lifecycle_status",
                )
            }
            for r in sorted(rows, key=lambda r: r["memory_id"])
        ]
    )


def review_input(candidate):
    return digest(
        {
            k: candidate.get(k)
            for k in (
                "candidate_id",
                "candidate_version",
                "content",
                "memory_type",
                "epistemic_status",
                "project_scope",
                "event_time",
                "supersedes_memory_id",
                "expected_version",
            )
        }
    )
