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
        diagnostics: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        """Return bounded result records with memory, score, and reasons."""


class DeterministicMemoryRetriever:
    """Production default: existing SQLite ranking and association behavior."""

    def retrieve(self, query, *, domain=None, limit=8, timings=None, diagnostics=None):
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

    def retrieve(self, query, *, domain=None, limit=8, timings=None, diagnostics=None):
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

    def __init__(
        self,
        collection,
        embed_query,
        memories_by_id=None,
        *,
        min_similarity=None,
        min_similarity_margin=None,
    ):
        if min_similarity is not None and not 0.0 <= float(min_similarity) <= 1.0:
            raise ValueError("min_similarity must be between 0.0 and 1.0")
        if min_similarity_margin is not None and not 0.0 <= float(min_similarity_margin) <= 1.0:
            raise ValueError("min_similarity_margin must be between 0.0 and 1.0")
        self.collection = collection
        self.embed_query = embed_query
        self.memories_by_id = memories_by_id or {}
        self.min_similarity = None if min_similarity is None else float(min_similarity)
        self.min_similarity_margin = (
            None if min_similarity_margin is None else float(min_similarity_margin)
        )

    def retrieve(self, query, *, domain=None, limit=8, timings=None, diagnostics=None):
        # Margin acceptance needs one additional candidate to assess ambiguity.
        query_limit = max(limit + 1, 2) if self.min_similarity_margin is not None else limit
        result = self.collection.query(
            query_embeddings=[self.embed_query(query)],
            n_results=query_limit,
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
            if self.min_similarity is not None and similarity < self.min_similarity:
                continue
            output.append({
                "memory": memory,
                "score": round(similarity, 6),
                "semantic_score": round(similarity, 6),
                "reasons": [f"semantic similarity: {similarity:.3f}"],
            })
        output.sort(key=lambda item: (-item["score"], str(item["memory"]["id"])))
        if self.min_similarity_margin is not None:
            if not output:
                acceptance = {
                    "accepted": False,
                    "min_similarity": self.min_similarity,
                    "min_similarity_margin": self.min_similarity_margin,
                    "reason": "semantic rejection: no candidate cleared minimum similarity",
                }
                if diagnostics is not None:
                    diagnostics["semantic_acceptance"] = acceptance
                if timings is not None:
                    timings.setdefault("association_ms", 0.0)
                return []
            acceptance = {
                "accepted": True,
                "min_similarity": self.min_similarity,
                "min_similarity_margin": self.min_similarity_margin,
            }
            if len(output) > 1:
                margin = output[0]["score"] - output[1]["score"]
                acceptance.update({
                    "top_similarity": output[0]["score"],
                    "runner_up_similarity": output[1]["score"],
                    "observed_margin": round(margin, 6),
                })
                if margin < self.min_similarity_margin:
                    acceptance.update({
                        "accepted": False,
                        "reason": (
                            "semantic ambiguity rejected: "
                            f"top {output[0]['score']:.3f} vs runner-up {output[1]['score']:.3f}; "
                            f"margin {margin:.3f} is below required {self.min_similarity_margin:.3f}"
                        ),
                    })
                    if diagnostics is not None:
                        diagnostics["semantic_acceptance"] = acceptance
                    if timings is not None:
                        timings.setdefault("association_ms", 0.0)
                    return []
            acceptance["reason"] = (
                "semantic top result accepted"
                if len(output) < 2
                else (
                    f"semantic margin {acceptance['observed_margin']:.3f} meets "
                    f"required {self.min_similarity_margin:.3f}"
                )
            )
            if diagnostics is not None:
                diagnostics["semantic_acceptance"] = acceptance
            output = output[:1]
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

    def retrieve(self, query, *, domain=None, limit=8, timings=None, diagnostics=None):
        combined = {}
        # Keep older injected deterministic test/retriever implementations valid.
        for item in self.deterministic.retrieve(query, domain=domain, limit=limit * 2):
            memory_id = item["memory"]["id"]
            combined.setdefault(memory_id, {}).update(item)
            combined[memory_id]["deterministic_score"] = item["score"]
        semantic_diagnostics = {} if diagnostics is not None else None
        for item in self.semantic.retrieve(
            query,
            domain=domain,
            limit=limit * 2,
            diagnostics=semantic_diagnostics,
        ):
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
        if diagnostics is not None and semantic_diagnostics and "semantic_acceptance" in semantic_diagnostics:
            diagnostics["semantic_acceptance"] = semantic_diagnostics["semantic_acceptance"]
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
