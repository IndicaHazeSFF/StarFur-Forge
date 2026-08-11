"""Temporary-fixture retrieval evaluation; never reads production memory/indexes."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pipeline import db
from pipeline.retrieval import (
    DeterministicMemoryRetriever,
    HybridMemoryRetriever,
    SemanticMemoryRetriever,
)


FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
FIXTURE_EMBEDDING_MODEL = "nomic-embed-text"
RETRIEVAL_EXPECTATIONS = frozenset({"lexical", "semantic", "no_match"})
DEFAULT_SEMANTIC_MIN_SIMILARITY_SWEEP = (0.0, 0.44, 0.46, 0.47, 0.48, 0.50, 0.55)
DEFAULT_SEMANTIC_MIN_MARGIN_SWEEP = (0.0, 0.005, 0.01, 0.02, 0.05, 0.10)


def load_cases(path=FIXTURE_ROOT / "retrieval_cases.json"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Retrieval fixture must be a list")
    required = {"name", "query", "expected_keys", "irrelevant_keys", "domain", "limit"}
    for case in data:
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError("Invalid retrieval case")
        if not isinstance(case["limit"], int) or case["limit"] <= 0:
            raise ValueError("Invalid retrieval case")
        if not isinstance(case["expected_keys"], list) or not isinstance(case["irrelevant_keys"], list):
            raise ValueError("Invalid retrieval keys")
        expectation = case.get("expectation", "no_match" if not case["expected_keys"] else "lexical")
        if expectation not in RETRIEVAL_EXPECTATIONS:
            raise ValueError("Invalid retrieval expectation")
        if (expectation == "no_match") != (not case["expected_keys"]):
            raise ValueError("No-match cases must not have expected keys")
        case["expectation"] = expectation
    return data


def load_memories(path=FIXTURE_ROOT / "retrieval_memories.json"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Retrieval memories fixture must be a list")
    return data


def build_ollama_fixture_embedder(model=FIXTURE_EMBEDDING_MODEL):
    """Return a fixed-model embedder for explicit fixture evaluation only."""
    try:
        import ollama
    except ImportError as error:
        raise RuntimeError("Ollama Python support is required for semantic fixture evaluation") from error

    def embed(text):
        response = ollama.embed(model=model, input=text)
        embeddings = response.get("embeddings") if isinstance(response, dict) else getattr(response, "embeddings", None)
        if not isinstance(embeddings, list) or not embeddings or not isinstance(embeddings[0], list):
            raise RuntimeError("Fixture embedding provider returned no embedding")
        return embeddings[0]

    return embed


class FixtureChromaAdapter:
    """A temporary, fixture-only Chroma collection with explicit cleanup."""

    def __init__(self, embed_query, embedding_model=FIXTURE_EMBEDDING_MODEL, chroma_client_factory=None):
        self.embed_query = embed_query
        self.embedding_model = embedding_model
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        if chroma_client_factory is None:
            try:
                import chromadb
            except ImportError as error:
                self.temp.cleanup()
                raise RuntimeError("chromadb is required for semantic fixture evaluation") from error
            chroma_client_factory = chromadb.PersistentClient
        self.client = chroma_client_factory(path=self.temp.name)
        self.collection = self.client.get_or_create_collection("retrieval_eval_fixture")

    def ingest(self, memories, *, min_similarity=None, min_similarity_margin=None):
        documents = [
            " ".join(str(item.get(key) or "") for key in ("summary", "details")).strip()
            for item in memories
        ]
        self.collection.add(
            ids=[item["key"] for item in memories],
            documents=documents,
            metadatas=[{"domain": item.get("domain", "personal")} for item in memories],
            embeddings=[self.embed_query(document) for document in documents],
        )
        return SemanticMemoryRetriever(
            self.collection,
            self.embed_query,
            {item["key"]: item for item in memories},
            min_similarity=min_similarity,
            min_similarity_margin=min_similarity_margin,
        )

    def close(self):
        self.temp.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _seed_fixture_memories(memories):
    key_to_id = {}
    fixture_rows = []
    for item in memories:
        memory_id = db.create_assistant_memory(
            item["subject"],
            item["memory_type"],
            item["summary"],
            details=item.get("details"),
            importance=item.get("importance", 0.5),
            confidence=item.get("confidence", 0.5),
            retention=item.get("retention", "long_term"),
            domain=item.get("domain", "personal"),
        )
        key_to_id[item["key"]] = memory_id
        fixture_rows.append({**item, "id": memory_id})
    return key_to_id, fixture_rows


def _normalize_semantic_min_similarity(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("semantic minimum similarity must be numeric") from error
    if not 0.0 <= value <= 1.0:
        raise ValueError("semantic minimum similarity must be between 0.0 and 1.0")
    return value


def _normalize_semantic_min_similarity_margin(value):
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("semantic minimum similarity margin must be numeric") from error
    if not 0.0 <= value <= 1.0:
        raise ValueError("semantic minimum similarity margin must be between 0.0 and 1.0")
    return value


def _evaluate_cases(retriever, cases, key_to_id):
    top1 = top3 = irrelevant = 0
    tier_totals = {
        expectation: {"cases": 0, "top1": 0, "top3": 0, "passed": 0}
        for expectation in RETRIEVAL_EXPECTATIONS
    }
    failures = []
    repeat = True
    recall_total = precision_total = 0.0
    measured_cases = []
    for case in cases:
        expected = {key_to_id[key] for key in case["expected_keys"]}
        irrelevant_keys = {key_to_id[key] for key in case["irrelevant_keys"]}
        first_diagnostics = {}
        second_diagnostics = {}
        first = retriever.retrieve(
            case["query"], domain=case["domain"], limit=case["limit"], diagnostics=first_diagnostics
        )
        second = retriever.retrieve(
            case["query"], domain=case["domain"], limit=case["limit"], diagnostics=second_diagnostics
        )
        ids = [item["memory"]["id"] for item in first]
        repeat &= ids == [item["memory"]["id"] for item in second]
        if ids and ids[0] in expected:
            top1 += 1
            tier_totals[case["expectation"]]["top1"] += 1
        if set(ids) & expected:
            top3 += 1
            tier_totals[case["expectation"]]["top3"] += 1
        tier_totals[case["expectation"]]["cases"] += 1
        relevant = set(ids) & expected
        case_passed = (not expected and not ids) or bool(relevant)
        if case_passed:
            tier_totals[case["expectation"]]["passed"] += 1
        recall_total += len(relevant) / len(expected) if expected else (1.0 if not ids else 0.0)
        precision_total += len(relevant) / len(ids) if ids else (1.0 if not expected else 0.0)
        irrelevant += sum(memory_id in irrelevant_keys or memory_id not in expected for memory_id in ids)
        measured_cases.append({
            "name": case["name"],
            "expectation": case["expectation"],
            "expected": sorted(expected),
            "returned": ids,
            "pass": case_passed,
            "retrieval": [
                {
                    "id": item["memory"]["id"],
                    "score": item["score"],
                    "reasons": list(item.get("reasons", [])),
                }
                for item in first
            ],
            "acceptance": first_diagnostics.get("semantic_acceptance"),
        })
        if (expected and (not ids or ids[0] not in expected)) or (not expected and ids):
            failures.append({"name": case["name"], "expected": sorted(expected), "returned": ids})

    total = len(cases) or 1
    expectation_metrics = {
        expectation: {
            "cases": values["cases"],
            "pass_rate": values["passed"] / values["cases"] if values["cases"] else None,
            "top1_hit_rate": values["top1"] / values["cases"] if values["cases"] else None,
            "top3_hit_rate": values["top3"] / values["cases"] if values["cases"] else None,
        }
        for expectation, values in sorted(tier_totals.items())
    }
    return {
        "cases": len(cases),
        "top1_hit_rate": top1 / total,
        "top3_hit_rate": top3 / total,
        "recall_at_k": recall_total / total,
        "precision_at_k": precision_total / total,
        "irrelevant_result_count": irrelevant,
        "repeatability": repeat,
        "expectation_metrics": expectation_metrics,
        "results": measured_cases,
        "failures": failures,
    }


def run_benchmark(
    cases=None,
    memories=None,
    strategy="deterministic",
    *,
    embed_query=None,
    semantic_retriever=None,
    fixture_adapter_factory=FixtureChromaAdapter,
    semantic_min_similarity=None,
    semantic_min_similarity_margin=None,
):
    """Run one temporary-fixture strategy; semantic use is explicit and opt-in."""
    if strategy not in {"deterministic", "semantic", "hybrid"}:
        raise ValueError("Unknown retrieval strategy")
    if strategy in {"semantic", "hybrid"} and embed_query is None and semantic_retriever is None:
        raise RuntimeError("Semantic benchmark requires an explicitly supplied fixture embedder or retriever")
    semantic_min_similarity = _normalize_semantic_min_similarity(semantic_min_similarity)
    semantic_min_similarity_margin = _normalize_semantic_min_similarity_margin(semantic_min_similarity_margin)
    if (semantic_min_similarity is not None or semantic_min_similarity_margin is not None) and semantic_retriever is not None:
        raise ValueError("semantic acceptance policy requires a fixture adapter, not an injected retriever")
    cases = load_cases() if cases is None else cases
    memories = load_memories() if memories is None else memories
    old_db_path = db.DB_PATH
    database_temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db.DB_PATH = Path(database_temp.name) / "retrieval.sqlite"
    adapter = None
    try:
        key_to_id, fixture_rows = _seed_fixture_memories(memories)
        deterministic = DeterministicMemoryRetriever()
        if strategy == "deterministic":
            retriever = deterministic
        else:
            if semantic_retriever is None:
                adapter = fixture_adapter_factory(embed_query)
                semantic_retriever = adapter.ingest(
                    fixture_rows,
                    min_similarity=semantic_min_similarity,
                    min_similarity_margin=semantic_min_similarity_margin,
                )
            retriever = semantic_retriever if strategy == "semantic" else HybridMemoryRetriever(deterministic, semantic_retriever)
        result = _evaluate_cases(retriever, cases, key_to_id)
        return {
            "benchmark_version": "retrieval-v3",
            "strategy": strategy,
            "semantic_min_similarity": semantic_min_similarity,
            "semantic_min_similarity_margin": semantic_min_similarity_margin,
            "started_at": datetime.now(timezone.utc).isoformat(),
            **result,
        }
    finally:
        if adapter is not None:
            adapter.close()
        db.DB_PATH = old_db_path
        database_temp.cleanup()


def compare_fixture_strategies(embed_query, cases=None, memories=None):
    """Run deterministic, semantic, and hybrid comparisons with temporary state only."""
    return {
        strategy: run_benchmark(cases, memories, strategy, embed_query=embed_query)
        for strategy in ("deterministic", "semantic", "hybrid")
    }


class _CachedEmbedder:
    """Avoid repeat local embedding calls while a calibration sweep reuses fixtures."""

    def __init__(self, embed_query):
        self.embed_query = embed_query
        self.cache = {}

    def __call__(self, text):
        if text not in self.cache:
            self.cache[text] = self.embed_query(text)
        return self.cache[text]


def sweep_semantic_min_similarity(
    embed_query,
    *,
    strategy="semantic",
    candidates=DEFAULT_SEMANTIC_MIN_SIMILARITY_SWEEP,
    cases=None,
    memories=None,
    fixture_adapter_factory=FixtureChromaAdapter,
):
    """Measure threshold tradeoffs without choosing a production policy."""
    if strategy not in {"semantic", "hybrid"}:
        raise ValueError("Semantic similarity sweep requires semantic or hybrid strategy")
    cached_embedder = _CachedEmbedder(embed_query)
    rows = []
    for candidate in candidates:
        minimum = _normalize_semantic_min_similarity(candidate)
        result = run_benchmark(
            cases,
            memories,
            strategy,
            embed_query=cached_embedder,
            fixture_adapter_factory=fixture_adapter_factory,
            semantic_min_similarity=minimum,
        )
        rows.append({
            "min_similarity": minimum,
            "top1_hit_rate": result["top1_hit_rate"],
            "semantic_top1_hit_rate": result["expectation_metrics"]["semantic"]["top1_hit_rate"],
            "no_match_pass_rate": result["expectation_metrics"]["no_match"]["pass_rate"],
            "irrelevant_result_count": result["irrelevant_result_count"],
        })
    return {
        "benchmark_version": "retrieval-v3",
        "strategy": strategy,
        "candidates": rows,
    }


def sweep_semantic_min_similarity_margin(
    embed_query,
    *,
    min_similarity,
    strategy="semantic",
    candidates=DEFAULT_SEMANTIC_MIN_MARGIN_SWEEP,
    cases=None,
    memories=None,
    fixture_adapter_factory=FixtureChromaAdapter,
):
    """Measure one-result ambiguity-guard tradeoffs for a fixed cutoff."""
    if strategy not in {"semantic", "hybrid"}:
        raise ValueError("Semantic margin sweep requires semantic or hybrid strategy")
    min_similarity = _normalize_semantic_min_similarity(min_similarity)
    if min_similarity is None:
        raise ValueError("Semantic margin sweep requires a minimum similarity")
    cached_embedder = _CachedEmbedder(embed_query)
    rows = []
    for candidate in candidates:
        margin = _normalize_semantic_min_similarity_margin(candidate)
        result = run_benchmark(
            cases,
            memories,
            strategy,
            embed_query=cached_embedder,
            fixture_adapter_factory=fixture_adapter_factory,
            semantic_min_similarity=min_similarity,
            semantic_min_similarity_margin=margin,
        )
        rows.append({
            "min_similarity_margin": margin,
            "top1_hit_rate": result["top1_hit_rate"],
            "semantic_top1_hit_rate": result["expectation_metrics"]["semantic"]["top1_hit_rate"],
            "no_match_pass_rate": result["expectation_metrics"]["no_match"]["pass_rate"],
            "irrelevant_result_count": result["irrelevant_result_count"],
        })
    return {
        "benchmark_version": "retrieval-v3",
        "strategy": strategy,
        "min_similarity": min_similarity,
        "candidates": rows,
    }


__all__ = [
    "FIXTURE_EMBEDDING_MODEL",
    "FixtureChromaAdapter",
    "build_ollama_fixture_embedder",
    "compare_fixture_strategies",
    "load_cases",
    "load_memories",
    "run_benchmark",
    "sweep_semantic_min_similarity",
    "sweep_semantic_min_similarity_margin",
]
