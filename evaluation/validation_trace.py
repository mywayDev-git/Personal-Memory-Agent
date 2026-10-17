"""Evaluation-only instrumentation. Never imported by production modules."""

import copy
from contextlib import ExitStack
from unittest.mock import patch

from pma.store import Store
from scripts.memory_agent import llm_client
from scripts.memory_agent.exceptions import ExtractionError
from scripts.memory_agent.extractor import extract_json


class ExtractionTrace:
    def __init__(self, models):
        self.models = models
        self.events = []
        self.stack = ExitStack()

    def __enter__(self):
        original_request = llm_client.post_json
        original_extract = self.models.extract
        original_save = Store.chunk_save
        original_publish = Store.publish

        def request(session, endpoint, body, timeout):
            generation = "messages" in body
            event = dict(stage="model_request", body=copy.deepcopy(body), status="pending")
            if generation:
                self.events.append(event)
            try:
                result = original_request(session, endpoint, body, timeout)
                if generation:
                    event.update(status="complete", response=copy.deepcopy(result))
                return result
            except Exception as exc:
                event.update(status="failed", error=type(exc).__name__)
                raise

        def extract(text, context, source_units=None, target_ids=None):
            event = dict(
                stage="sentence_mapping",
                source_units=copy.deepcopy(source_units),
                target_ids=copy.deepcopy(target_ids),
                status="pending",
            )
            self.events.append(event)
            begin = len(self.events)
            try:
                result = original_extract(text, context, source_units, target_ids)
                event.update(status="complete", restored=copy.deepcopy(result))
                generations = [
                    e
                    for e in self.events[begin:]
                    if e["stage"] == "model_request" and e["status"] == "complete"
                ]
                if generations:
                    try:
                        event["raw_memories"] = extract_json(
                            generations[-1]["response"]["choices"][0]["message"]["content"]
                        )["memories"]
                    except KeyError, IndexError, ValueError, TypeError, ExtractionError:
                        event["raw_mapping"] = "unavailable"
                return result
            except Exception as exc:
                event.update(status="failed", error=type(exc).__name__)
                raise

        def save(store, job, key, payload):
            result = original_save(store, job, key, payload)
            self.events.append(dict(stage="chunk_cache", key=key, payload=copy.deepcopy(payload)))
            return result

        def publish(store, job, memories, vectors, model_key, metadata):
            event = dict(
                stage="deduplicated_publish",
                memories=copy.deepcopy(memories),
                metadata=copy.deepcopy(metadata),
                status="pending",
            )
            self.events.append(event)
            result = original_publish(store, job, memories, vectors, model_key, metadata)
            event.update(status="complete" if result else "stale_job")
            return result

        self.stack.enter_context(patch("scripts.memory_agent.llm_client.post_json", request))
        self.stack.enter_context(patch.object(self.models, "extract", extract))
        self.stack.enter_context(patch.object(Store, "chunk_save", save))
        self.stack.enter_context(patch.object(Store, "publish", publish))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


def inspect_trace(value):
    """Check mechanical transformations, not semantic entailment."""
    text, errors, unresolved = value["record"]["text"], [], []
    cached = []
    for index, event in enumerate(value["events"]):
        stage = event["stage"]
        if stage == "attempt":
            cached = []
        elif stage == "sentence_mapping":
            units = {u["id"]: u for u in event.get("source_units") or []}
            for u in units.values():
                if text[u["start"] : u["end"]] != u["text"]:
                    errors.append("sentence_source_offset")
            if event.get("status") != "complete":
                continue
            extraction, metadata = event["restored"]
            memories, provenance = extraction["memories"], metadata.get("provenance", [])
            if len(memories) != len(provenance):
                errors.append("restored_provenance_count")
                continue
            for m, p in zip(memories, provenance, strict=True):
                if len(m["evidence"]) != len(p["evidence"]):
                    errors.append("restored_evidence_count")
                    continue
                for e, s in zip(m["evidence"], p["evidence"], strict=True):
                    if text[s["start"] : s["end"]] != e["quote"]:
                        errors.append("restored_source_offset")
            raw = event.get("raw_memories")
            if raw is None:
                # Earlier traces stored the raw wire response in the following event.
                for following in value["events"][index + 1 :]:
                    if following["stage"] in {
                        "sentence_mapping",
                        "deduplicated_publish",
                        "attempt",
                    }:
                        break
                    if (
                        following["stage"] == "model_request"
                        and following.get("status") == "complete"
                    ):
                        try:
                            raw = extract_json(
                                following["response"]["choices"][0]["message"]["content"]
                            )["memories"]
                        except KeyError, IndexError, TypeError, ValueError, ExtractionError:
                            raw = None
            if raw is None:
                unresolved.append("raw_sentence_id_mapping")
            elif len(raw) != len(memories):
                errors.append("raw_restored_count")
            else:
                for original, restored in zip(raw, memories, strict=True):
                    ids = list(dict.fromkeys(e.get("sentence_id") for e in original["evidence"]))
                    if any(i not in units or i not in event["target_ids"] for i in ids):
                        errors.append("raw_sentence_id")
                    elif [units[i]["text"] for i in ids] != [
                        e["quote"] for e in restored["evidence"]
                    ]:
                        errors.append("raw_restored_quote_mapping")
        elif stage == "chunk_cache" and "memories" in event["payload"]:
            p = event["payload"]
            if len(p["memories"]) != len(p["metadata"].get("provenance", [])):
                errors.append("cache_provenance_count")
            else:
                cached.extend(zip(p["memories"], p["metadata"]["provenance"], strict=True))
        elif stage == "deduplicated_publish" and event.get("status") == "complete":
            from evaluation.query_tree import digest

            def identity(m, p):
                return digest([{k: v for k, v in m.items() if k != "local_id"}, p["evidence"]])

            expected = list(dict.fromkeys(identity(m, p) for m, p in cached))
            provenance = event["metadata"].get("provenance", [])
            if len(event["memories"]) != len(provenance):
                errors.append("publish_provenance_count")
            elif expected != [
                identity(m, p) for m, p in zip(event["memories"], provenance, strict=True)
            ]:
                errors.append("cache_dedup_publish_mapping")
    return dict(errors=errors, unresolved=sorted(set(unresolved)), events=len(value["events"]))
