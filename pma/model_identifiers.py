"""Optional call-local aliases for opaque evidence IDs; original validation remains."""

from functools import wraps

from scripts.memory_agent.performance import count
from scripts.memory_agent.validator import schema_errors


def identifiers(data):
    ids = []
    for key in ("evidence", "source_records"):
        rows = data.get(key, [])
        if isinstance(rows, list):
            ids.extend(row["id"] for row in rows if isinstance(row, dict)
                       and isinstance(row.get("id"), str))
    ids = list(dict.fromkeys(ids))
    long_ids = [identifier for identifier in ids if len(identifier) > 8]
    prefix = "S"
    while any(prefix + str(i) in ids for i in range(len(long_ids))):
        prefix += "S"
    return {identifier: prefix + str(i) for i, identifier in enumerate(long_ids)}


def references(value, mapping, key=None):
    # Never rewrite free text, source quotes, person names, dates or reasons.
    if isinstance(value, dict):
        return {name: references(child, mapping, name) for name, child in value.items()}
    if isinstance(value, list):
        return [references(child, mapping, key) for child in value]
    if isinstance(value, str) and key in {"id", "citations", "ids", "evidence_id"}:
        return mapping.get(value, value)
    return value


def schema_references(value, mapping):
    if isinstance(value, list):
        return [schema_references(child, mapping) for child in value]
    if isinstance(value, dict):
        return {key: [mapping.get(item, item) if isinstance(item, str) else item for item in child]
                if key == "enum" and isinstance(child, list) else schema_references(child, mapping)
                for key, child in value.items()}
    return value


def compact_identifiers(function):
    @wraps(function)
    def wrapped(self, prompt, data, schema, *args, **kwargs):
        if not getattr(self.settings, "compact_model_ids", False):
            return function(self, prompt, data, schema, *args, **kwargs)
        mapping = identifiers(data)
        if not mapping:
            return function(self, prompt, data, schema, *args, **kwargs)
        result = function(self, prompt, references(data, mapping),
                          schema_references(schema, mapping), *args, **kwargs)
        restored = references(result, {alias: original for original, alias in mapping.items()})
        if schema_errors(restored, schema):
            raise ValueError("INVALID_RESTORED_MODEL_REFERENCES")
        count("compact_identifier_calls")
        return restored
    return wrapped
