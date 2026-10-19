"""Pre-optimization algorithms for synthetic DB benchmarks only.

Preserves the correlated capture scans, N+1 evidence reads, uncached keyword
normalization, and repeated vector normalization. Never used by the application.
"""

import json
from types import FunctionType

import numpy as np

from pma.diagnostics import Stage
from pma.facts import FACT_VERSION
from pma.models import normalized_vectors
from pma.search_explain import TOKEN, normalize
from pma.service import Service as CurrentService
from pma.store import Store as CurrentStore
from pma.store import _observe_read, _start_observation


def keyword_matches(row, terms, vocabulary, **ignored):
    matches = []
    for field, text in (("source_text", row["text"]), ("content", row["memory"]["content"])):
        tokens = list(TOKEN.finditer(text))
        for term in terms:
            exact = [match for match in tokens if match.group().casefold() == term["text"]]
            for match in exact:
                matches.append(
                    {
                        "term": term["text"],
                        "kind": "exact",
                        "field": field,
                        "start": match.start(),
                        "end": match.end(),
                        "quote": match.group(),
                    }
                )
            if not exact:
                for match in tokens:
                    if normalize(match.group(), vocabulary) == term["normalized"]:
                        matches.append(
                            {
                                "term": term["text"],
                                "kind": "normalized",
                                "field": field,
                                "start": match.start(),
                                "end": match.end(),
                                "quote": match.group(),
                            }
                        )
    return matches


class Store(CurrentStore):
    def snapshot(self, model_key, *, owner_id=None):
        observation = _start_observation()
        with self.connect() as db:
            generation = db.execute("SELECT generation FROM metadata WHERE id=1").fetchone()[0]
            rows = db.execute(
                "SELECT m.id,m.payload,e.vector,e.dimensions,v.record_id,v.version,v.text,v.reference_time,v.created_at,f.payload AS fact_payload FROM memories m JOIN embeddings e ON e.memory_id=m.id JOIN revisions v ON v.id=m.revision_id JOIN records r ON r.id=v.record_id LEFT JOIN facts f ON f.memory_id=m.id AND f.projection_version=? WHERE r.state='active' AND r.status='ready' AND r.version=v.version AND NOT EXISTS(SELECT 1 FROM captured_memories c WHERE c.record_id=r.id AND json_extract(c.payload,'$.record_version')=r.version AND json_extract(c.payload,'$.lifecycle_status')='archived') "
                "AND (? IS NULL OR NOT EXISTS(SELECT 1 FROM captured_memories c WHERE c.record_id=r.id AND c.owner_id<>?)) "
                "AND e.model_key=? ORDER BY v.id,m.local_id",
                (FACT_VERSION, owner_id, owner_id, model_key),
            ).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["memory"] = json.loads(item.pop("payload"))
                fact = item.pop("fact_payload")
                item["fact"] = json.loads(fact) if fact else None
                item["evidence"] = [
                    dict(e)
                    for e in db.execute(
                        "SELECT quote,start,end FROM evidence WHERE memory_id=? ORDER BY position",
                        (row["id"],),
                    )
                ]
                result.append(item)
        _observe_read(Stage.SNAPSHOT, observation, result)
        return generation, result


class Service(CurrentService):
    def _candidate_matrix(self, generation, candidates):
        matrix = np.stack([np.frombuffer(r["vector"], dtype="<f4") for r in candidates])
        return normalized_vectors(matrix, len(candidates), self.settings.embedding_dimensions)


# Give the reference search its own keyword matcher without mutating the real
# service module or maintaining a second copy of the entire search implementation.
_search = CurrentService._search
Service._search = FunctionType(_search.__code__,
    {**_search.__globals__, "keyword_matches": keyword_matches,
     "keyword_matches_batch": lambda rows, terms, vocabulary: [
         keyword_matches(row, terms, vocabulary) for row in rows]},
    _search.__name__, _search.__defaults__, _search.__closure__)
Service._search.__kwdefaults__ = _search.__kwdefaults__
