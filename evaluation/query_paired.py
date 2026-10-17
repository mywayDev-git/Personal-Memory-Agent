"""Eight paired retrieval arms; experimental event graph, not a production retriever."""

import copy
import re
from collections import defaultdict

import numpy as np

from evaluation.query_tree import query_texts
from pma.facts import name, relation

ARMS = [f"{method}{split}" for method in "VMGH" for split in (0, 1)]
LABELS = {
    "V": "벡터·키워드",
    "M": "핵심 사실별 다중 벡터",
    "G": "사건 그래프 단독",
    "H": "다중 벡터·사건 그래프 혼합",
}


def tokens(text):
    return {name(t) for t in re.findall(r"[\w]+", text.casefold()) if name(t)}


def parts(node):
    """Several representations of ONE grounded event; never split roles into bare vectors."""
    fact = node.get("fact") or {}
    subject = (node.get("subject") or {}).get("value", "")
    obj = (node.get("object") or {}).get("value", "")
    target = (node.get("target") or {}).get("value", "")
    triple = f"주체 {subject}, 행동 {node.get('predicate', '')}, 대상 {obj}, 상대 {target}"
    result = [node["content"], triple]
    for e in node["evidence"]:
        result.append(f"{triple}. 근거: {e['quote']}")
    when = fact.get("event_time") or {}
    if when.get("start"):
        result.append(f"{triple}. 사건 시점: {when['start']}. 상태: {fact.get('state', '')}")
    return list(dict.fromkeys(result))


class PairedIndex:
    def __init__(self, path, models, rows, records, cached_embed):
        self.embed = cached_embed
        self.nodes = {}
        self.membership = {}  # Same runner interface; this experiment has no topic tree.
        self.buckets = defaultdict(set)
        self.features = {}
        self.fragments = {}
        for row in rows:
            n = copy.deepcopy(row)
            n["node_kind"] = "memory"
            n["spans"] = [
                dict(record=n["record_no"], start=e["start"], end=e["end"]) for e in n["evidence"]
            ]
            self.nodes[n["id"]] = n
            f = n.get("fact") or {}
            features = {
                k: str(f.get(k) or "")
                for k in ("actor", "recipient", "relation", "object", "state")
            }
            self.features[n["id"]] = features
            # Shared labels are candidate links only, NOT proven person/event identity.
            for k in ("actor", "recipient", "object"):
                value = features[k]
                if value and value != "self":
                    bucket = ("object" if k == "object" else "person", value)
                    self.buckets[bucket].add(n["id"])
            self.fragments[n["id"]] = parts(n)
        self.ids = sorted(self.nodes, key=self.stable_key)
        self.vectors = {}
        self.vector_texts = {}
        # No vectors are constructed for the graph. Dense preparation is explicit/lazy.

    def close(self):
        pass

    def stable_key(self, key):
        n = self.nodes[key]
        return (n["record_no"], tuple((e["start"], e["end"]) for e in n["evidence"]), n["content"])

    def prepare_dense(self):
        for key in self.ids:
            self.vectors[key] = self.embed(self.fragments[key])
        self.vector_texts = {key: self.fragments[key] for key in self.ids}

    def dense(self, queries, multi):
        if self.ids and not self.vectors:
            self.prepare_dense()
        orders, trace = [], []
        for query in queries:
            q = self.embed([query])[0]
            scores = {
                k: float(np.max(self.vectors[k] @ q)) if multi else float(self.vectors[k][0] @ q)
                for k in self.ids
            }
            order = sorted(self.ids, key=lambda k: (-scores[k], self.stable_key(k)))[:20]
            lexical = {
                k: len(
                    tokens(query) & tokens(" ".join(e["quote"] for e in self.nodes[k]["evidence"]))
                )
                for k in self.ids
            }
            sparse = sorted(
                (k for k in self.ids if lexical[k]), key=lambda k: (-lexical[k], self.stable_key(k))
            )[:20]
            orders.extend([order, sparse])
            trace.append(
                dict(
                    query=query, dense=[dict(id=k, score=scores[k]) for k in order], lexical=sparse
                )
            )
        return orders, trace

    def graph(self, queries, analysis):
        orders, trace = [], []
        for query in queries:
            query_tokens = tokens(query)
            rel = relation(query)
            scores, matches = {}, {}
            for key in self.ids:
                f = self.features[key]
                matched = [
                    role
                    for role in ("actor", "recipient", "object")
                    if f[role] and (tokens(f[role]) & query_tokens)
                ]
                if rel != "other" and rel == f["relation"]:
                    matched.append("relation")
                # Decomposition can additionally distinguish explicitly labelled roles.
                role_hits = [
                    u["field"]
                    for u in analysis.get("units", [])
                    if u["field"] in {"actor", "recipient"}
                    and name(u["value"]) == f.get(u["field"])
                ]
                if matched or role_hits:
                    scores[key] = len(matched) + len(role_hits)
                    matches[key] = dict(matched=matched, role_hits=role_hits)
            seeds = sorted(scores, key=lambda k: (-scores[k], self.stable_key(k)))[:20]
            visited = set(seeds)
            frontier = seeds
            paths = []
            for hop in (1, 2):
                next_frontier = set()
                for bucket, members in sorted(self.buckets.items()):
                    parents = set(frontier) & members
                    if not parents:
                        continue
                    # Degree normalization limits high-frequency mention hubs.
                    contribution = max(scores[p] for p in parents) * 0.35 / len(members)
                    for child in sorted(members - visited, key=self.stable_key):
                        scores[child] = max(scores.get(child, 0), contribution)
                        next_frontier.add(child)
                        paths.append(
                            dict(
                                hop=hop,
                                parents=sorted(parents),
                                child=child,
                                bucket=list(bucket),
                                identity_verified=False,
                            )
                        )
                frontier = sorted(next_frontier, key=lambda k: (-scores[k], self.stable_key(k)))[
                    :40
                ]
                visited.update(frontier)
            order = sorted(visited, key=lambda k: (-scores[k], self.stable_key(k)))[:40]
            orders.append(order)
            trace.append(
                dict(
                    query=query,
                    seeds=seeds,
                    matches=matches,
                    paths=paths,
                    scores={k: scores[k] for k in order},
                )
            )
        return orders, trace

    def search(self, question, analysis, condition):
        method, decomposed = condition[0], condition[1] == "1"
        active = analysis if decomposed and analysis.get("status") == "ok" else {}
        queries = query_texts(question, active) if active else [question]
        orders, routes = [], {}
        if method in "VMH":
            dense_orders, routes["dense"] = self.dense(queries, multi=method != "V")
            orders.extend(dense_orders)
        if method in "GH":
            graph_orders, routes["graph"] = self.graph(queries, active)
            orders.extend(graph_orders)
        scores = defaultdict(float)
        for order in orders:
            for rank, key in enumerate(order, 1):
                scores[key] += 1 / (60 + rank)
        ranked = sorted(scores, key=lambda k: (-scores[k], self.stable_key(k)))
        selected = ranked[:8]
        return [copy.deepcopy(self.nodes[k]) for k in selected], dict(
            routes=routes,
            candidates=ranked[:40],
            selected=selected,
            queries=queries,
            decomposition_requested=decomposed,
            decomposition_applied=bool(active),
            fallback=decomposed and not active,
            ranked=[dict(id=k, score=scores[k]) for k in ranked],
        )
