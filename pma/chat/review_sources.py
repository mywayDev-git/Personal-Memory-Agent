"""Server-owned complete source spans; models select identifiers, not invented quotes."""

from scripts.memory_agent.provenance import sentences


def source_catalog(evidence):
    catalog = {}
    rows = []
    for source_index, row in enumerate(evidence):
        text = row["source_text"]
        spans = []
        # Keep punctuation and the entire sentence, including negation and qualifiers.
        for sentence in sentences(text):
            quote = sentence["text"].strip()
            if not quote:
                continue
            span_id = f"s{source_index}:{len(spans)}"
            catalog[span_id] = {"id": row["id"], "quote": quote}
            spans.append({"span_id": span_id, "text": quote})
        if not spans and text.strip():
            span_id = f"s{source_index}:0"
            catalog[span_id] = {"id": row["id"], "quote": text}
            spans.append({"span_id": span_id, "text": text})
        rows.append({"id": row["id"], "source_context": text, "spans": spans})
    return rows, catalog
