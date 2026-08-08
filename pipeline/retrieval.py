"""Injectable assistant-memory retrieval strategies.

The production assistant uses ``DeterministicMemoryRetriever``.  Semantic and
hybrid implementations remain evaluation-only until deliberately injected;
this module never opens or rebuilds a production Chroma collection.
"""

from __future__ import annotations

from typing import Protocol

from pipeline import db


class MemoryRetriever(Protocol):
    """Read-only ranked assistant-memory retrieval boundary."""

    def retrieve(
        self,
        query: str,
        *,
        domain: str | None = None,
        limit: int = 8,
        timings: dict[str, float] | None = None,
    ) -> list[dict[str, object]]:
        """Return bounded result records with memory, score, and reasons."""


class DeterministicMemoryRetriever:
    """Production default: existing SQLite ranking and association behavior."""

    def retrieve(self, query, *, domain=None, limit=8, timings=None):
        return db.retrieve_assistant_memories(
            query,
            domain=domain or "personal",
            limit=limit,
            timings=timings,
        )


class MemoryLoaderRetriever:
    """Compatibility adapter for older custom ``memory_loader`` test hooks."""

    def __init__(self, memory_loader):
        self.memory_loader = memory_loader

    def retrieve(self, query, *, domain=None, limit=8, timings=None):
        memories = self.memory_loader(domain=domain or "personal", status="active", limit=limit)
        if timings is not None:
            timings.setdefault("retrieval_ms", 0.0)
            timings.setdefault("association_ms", 0.0)
        return [
            {
                "memory": memory,
                "score": None,
                "reasons": ["custom memory loader"],
            }
            for memory in memories
        ]


class SemanticMemoryRetriever:
    """Fixture/injected semantic retriever; never configured by production chat."""

    def __init__(self, collection, embed_query, memories_by_id=None):
        self.collection = collection
        self.embed_query = embed_query
        self.memories_by_id = memories_by_id or {}

    def retrieve(self, query, *, domain=None, limit=8, timings=None):
        result = self.collection.query(
            query_embeddings=[self.embed_query(query)],
            n_results=limit,
            where={"domain": domain} if domain else None,
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        output = []
        for index, key in enumerate(ids):
            memory = self.memories_by_id.get(key)
            if memory is None:
                continue
            similarity = 1.0 / (1.0 + float(distances[index])) if index < len(distances) else 0.0
            output.append({
                "memory": memory,
                "score": round(similarity, 6),
                "semantic_score": round(similarity, 6),
                "reasons": [f"semantic similarity: {similarity:.3f}"],
            })
        if timings is not None:
            timings.setdefault("association_ms", 0.0)
        return output


class HybridMemoryRetriever:
    """Transparent evaluation-only combination of injected retrieval strategies."""

    def __init__(self, deterministic, semantic, deterministic_weight=.6, semantic_weight=.4):
        self.deterministic = deterministic
        self.semantic = semantic
        self.deterministic_weight = deterministic_weight
        self.semantic_weight = semantic_weight

    def retrieve(self, query, *, domain=None, limit=8, timings=None):
        combined = {}
        for item in self.deterministic.retrieve(query, domain=domain, limit=limit * 2):
            memory_id = item["memory"]["id"]
            combined.setdefault(memory_id, {}).update(item)
            combined[memory_id]["deterministic_score"] = item["score"]
        for item in self.semantic.retrieve(query, domain=domain, limit=limit * 2):
            memory_id = item["memory"]["id"]
            combined.setdefault(memory_id, {}).update(item)
            combined[memory_id]["semantic_score"] = item["score"]
        max_d = max((item.get("deterministic_score", 0) for item in combined.values()), default=1) or 1
        max_s = max((item.get("semantic_score", 0) for item in combined.values()), default=1) or 1
        for item in combined.values():
            deterministic_score = item.get("deterministic_score", 0) / max_d
            semantic_score = item.get("semantic_score", 0) / max_s
            item["score"] = round(
                self.deterministic_weight * deterministic_score
                + self.semantic_weight * semantic_score,
                6,
            )
            item["reasons"] = item.get("reasons", []) + [
                f"hybrid deterministic: {deterministic_score:.3f}",
                f"hybrid semantic: {semantic_score:.3f}",
            ]
        if timings is not None:
            timings.setdefault("association_ms", 0.0)
        return sorted(
            combined.values(),
            key=lambda item: (-item["score"], -int(item["memory"]["id"])),
        )[:limit]


__all__ = [
    "DeterministicMemoryRetriever",
    "HybridMemoryRetriever",
    "MemoryLoaderRetriever",
    "MemoryRetriever",
    "SemanticMemoryRetriever",
]
