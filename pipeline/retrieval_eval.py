import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from pipeline.retrieval import DeterministicMemoryRetriever, SemanticMemoryRetriever, HybridMemoryRetriever
from pipeline import db

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

def load_cases(path=FIXTURE_ROOT / "retrieval_cases.json"):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,list): raise ValueError("Retrieval fixture must be a list")
    required={"name","query","expected_keys","irrelevant_keys","domain","limit"}
    for case in data:
        if not isinstance(case,dict) or not required.issubset(case) or not isinstance(case["limit"],int) or case["limit"]<=0: raise ValueError("Invalid retrieval case")
        if not isinstance(case["expected_keys"],list) or not isinstance(case["irrelevant_keys"],list): raise ValueError("Invalid retrieval keys")
    return data

def load_memories(path=FIXTURE_ROOT / "retrieval_memories.json"):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,list): raise ValueError("Retrieval memories fixture must be a list")
    return data

def run_benchmark(cases=None, memories=None, strategy="deterministic"):
    if strategy not in {"deterministic", "semantic", "hybrid"}:
        raise ValueError("Unknown retrieval strategy")
    if strategy != "deterministic":
        raise RuntimeError("Semantic benchmark requires an explicitly injected temporary Chroma retriever")
    cases = load_cases() if cases is None else cases
    memories = load_memories() if memories is None else memories
    old = db.DB_PATH
    temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
    db.DB_PATH = Path(temp.name) / "retrieval.sqlite"
    try:
        key_to_id = {}
        for item in memories:
            key_to_id[item["key"]] = db.create_assistant_memory(
                item["subject"], item["memory_type"], item["summary"],
                details=item.get("details"), importance=item.get("importance", .5),
                confidence=item.get("confidence", .5), retention=item.get("retention", "long_term"),
                domain=item.get("domain", "personal"),
            )
        top1 = top3 = irrelevant = 0
        failures = []
        repeat = True
        recall_total = precision_total = 0.0
        measured_cases = []
        for case in cases:
            expected = {key_to_id[k] for k in case["expected_keys"]}
            irrelevant_keys = {key_to_id[k] for k in case["irrelevant_keys"]}
            def retrieve(q):
                return db.retrieve_assistant_memories(q, domain=case["domain"], limit=case["limit"])
            first = retrieve(case["query"])
            second = retrieve(case["query"])
            ids = [x["memory"]["id"] for x in first]
            repeat &= ids == [x["memory"]["id"] for x in second]
            if ids and ids[0] in expected:
                top1 += 1
            if set(ids) & expected:
                top3 += 1
            relevant = set(ids) & expected
            recall_total += (len(relevant) / len(expected)) if expected else (1.0 if not ids else 0.0)
            precision_total += (len(relevant) / len(ids)) if ids else (1.0 if not expected else 0.0)
            irrelevant += sum(i in irrelevant_keys or i not in expected for i in ids)
            measured_cases.append({"name": case["name"], "expected": sorted(expected), "returned": ids, "pass": (not expected and not ids) or bool(relevant)})
            if (expected and (not ids or ids[0] not in expected)) or (not expected and ids):
                failures.append({"name": case["name"], "expected": sorted(expected), "returned": ids})
        total = len(cases) or 1
        return {
            "benchmark_version": "retrieval-v1", "strategy": strategy,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "cases": len(cases), "top1_hit_rate": top1 / total,
            "top3_hit_rate": top3 / total, "recall_at_k": recall_total / total,
            "precision_at_k": precision_total / total,
            "irrelevant_result_count": irrelevant, "repeatability": repeat,
            "results": measured_cases, "failures": failures,
        }
    finally:
        db.DB_PATH = old
        temp.cleanup()

class FixtureChromaAdapter:
    """Temporary Chroma collection for benchmark fixtures only."""
    def __init__(self, embed_query, embedding_model="nomic-embed-text"):
        self.embed_query = embed_query; self.embedding_model = embedding_model; self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        try:
            import chromadb
        except ImportError as error: self.temp.cleanup(); raise RuntimeError("chromadb is required for semantic fixture evaluation") from error
        self.client = chromadb.PersistentClient(path=self.temp.name)
        self.collection = self.client.get_or_create_collection("retrieval_eval_fixture")
    def ingest(self, memories):
        self.collection.add(ids=[item["key"] for item in memories], documents=[item["summary"] for item in memories], metadatas=[{"domain":item.get("domain","personal")} for item in memories], embeddings=[self.embed_query(item["summary"]) for item in memories])
        return SemanticMemoryRetriever(self.collection, self.embed_query, {item["key"]:item for item in memories})
    def close(self): self.temp.cleanup()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


def compare_fixture_strategies(embed_query, cases=None, memories=None):
    """Compare deterministic/semantic/hybrid using one temporary fixture collection."""
    cases=load_cases() if cases is None else cases; memories=load_memories() if memories is None else memories
    with FixtureChromaAdapter(embed_query) as adapter:
        semantic=adapter.ingest(memories); deterministic=DeterministicMemoryRetriever(); hybrid=HybridMemoryRetriever(deterministic, semantic)
        results={}
        for name,retriever in (("deterministic",deterministic),("semantic",semantic),("hybrid",hybrid)):
            results[name]=[]
            for case in cases:
                rows=retriever.retrieve(case["query"],domain=case["domain"],limit=case["limit"]); results[name].append([row["memory"]["id"] for row in rows])
        return results
