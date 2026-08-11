import json
import tempfile
import unittest
from pathlib import Path
from pipeline.retrieval_eval import load_cases, run_benchmark, sweep_semantic_min_similarity, sweep_semantic_min_similarity_margin


class FakeSemanticRetriever:
 def __init__(self, rows, min_similarity=None, min_similarity_margin=None): self.rows={row["key"]:row for row in rows}; self.min_similarity=min_similarity; self.min_similarity_margin=min_similarity_margin
 def retrieve(self, query, *, domain=None, limit=8, timings=None, diagnostics=None):
  lowered=query.casefold()
  key = (
   "personal.glasses" if any(term in lowered for term in ("glasses", "spectacles", "see better")) else
   "personal.work_schedule" if any(term in lowered for term in ("working", "shifts")) else
   "personal.gpu" if any(term in lowered for term in ("gpu", "graphics hardware", "main pc", "computer component", "computers")) else
   None
  )
  memory=self.rows.get(key)
  if self.min_similarity is not None and self.min_similarity > .9: memory=None
  if self.min_similarity_margin is not None:
   if diagnostics is not None: diagnostics["semantic_acceptance"]={"accepted":self.min_similarity_margin < .5,"reason":"semantic top result accepted" if self.min_similarity_margin < .5 else "semantic ambiguity rejected: fixture tie"}
   if self.min_similarity_margin >= .5: memory=None
  return [] if memory is None or (domain and memory["domain"] != domain) else [{"memory":memory,"score":0.9,"reasons":["semantic similarity: 0.900"]}]


class FakeFixtureAdapter:
 instances=[]
 def __init__(self, embed_query): self.embed_query=embed_query; self.rows=[]; self.closed=False; self.__class__.instances.append(self)
 def ingest(self, rows, *, min_similarity=None, min_similarity_margin=None): self.rows=rows; return FakeSemanticRetriever(rows,min_similarity,min_similarity_margin)
 def close(self): self.closed=True

class RetrievalEvalTests(unittest.TestCase):
 def test_checked_in_benchmark_runs(self):
  result=run_benchmark(); self.assertEqual(result["cases"],15); self.assertTrue(result["repeatability"]); self.assertGreaterEqual(result["top3_hit_rate"], result["top1_hit_rate"]); self.assertEqual(result["benchmark_version"], "retrieval-v3"); self.assertEqual(len(result["results"]), result["cases"]); self.assertGreaterEqual(result["recall_at_k"], 0.0); self.assertGreaterEqual(result["precision_at_k"], 0.0); self.assertEqual(result["expectation_metrics"]["lexical"]["top1_hit_rate"], 1.0); self.assertEqual(result["expectation_metrics"]["semantic"]["top1_hit_rate"], 0.0); self.assertEqual(result["expectation_metrics"]["no_match"]["pass_rate"], 1.0)
 def test_malformed_fixture_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"bad.json"; path.write_text(json.dumps({"not":"a list"}))
   with self.assertRaises(ValueError): load_cases(path)
 def test_missing_or_invalid_expectation_is_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"bad.json"; path.write_text(json.dumps([{"name":"bad","query":"x","expected_keys":[],"irrelevant_keys":[],"domain":"personal","limit":1,"expectation":"magic"}]))
   with self.assertRaises(ValueError): load_cases(path)
 def test_legacy_fixture_defaults_to_safe_lexical_or_no_match_tiers(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"legacy.json"; path.write_text(json.dumps([{"name":"match","query":"gpu","expected_keys":["personal.gpu"],"irrelevant_keys":[],"domain":"personal","limit":1},{"name":"none","query":"garden","expected_keys":[],"irrelevant_keys":[],"domain":"personal","limit":1}]))
   cases=load_cases(path)
  self.assertEqual([case["expectation"] for case in cases], ["lexical", "no_match"])
 def test_semantic_and_hybrid_benchmarks_are_fixture_only_and_injected(self):
  FakeFixtureAdapter.instances=[]
  semantic=run_benchmark(strategy="semantic", embed_query=lambda text:[1.0], fixture_adapter_factory=FakeFixtureAdapter)
  hybrid=run_benchmark(strategy="hybrid", embed_query=lambda text:[1.0], fixture_adapter_factory=FakeFixtureAdapter)
  self.assertEqual(semantic["benchmark_version"], "retrieval-v3")
  self.assertEqual(semantic["expectation_metrics"]["semantic"]["top1_hit_rate"], 1.0)
  self.assertEqual(hybrid["expectation_metrics"]["semantic"]["top1_hit_rate"], 1.0)
  self.assertTrue(all(adapter.closed and all(isinstance(row["id"], int) for row in adapter.rows) for adapter in FakeFixtureAdapter.instances))
 def test_semantic_strategy_requires_explicit_fixture_dependency(self):
  with self.assertRaises(RuntimeError): run_benchmark(strategy="semantic")
 def test_semantic_minimum_requires_fixture_adapter_and_is_validated(self):
  with self.assertRaises(ValueError): run_benchmark(strategy="semantic", semantic_retriever=FakeSemanticRetriever([]), semantic_min_similarity=.5)
  with self.assertRaises(ValueError): run_benchmark(strategy="semantic", semantic_retriever=FakeSemanticRetriever([]), semantic_min_similarity_margin=.5)
  with self.assertRaises(ValueError): run_benchmark(strategy="semantic", embed_query=lambda text:[1.0], semantic_min_similarity=1.1)
 def test_similarity_sweep_reports_fixture_only_tradeoffs(self):
  sweep=sweep_semantic_min_similarity(lambda text:[1.0], candidates=(0.0,.95), fixture_adapter_factory=FakeFixtureAdapter)
  self.assertEqual([row["min_similarity"] for row in sweep["candidates"]],[0.0,.95])
  self.assertGreater(sweep["candidates"][0]["semantic_top1_hit_rate"], sweep["candidates"][1]["semantic_top1_hit_rate"])
 def test_margin_sweep_requires_cutoff_and_reports_tradeoffs(self):
  with self.assertRaises(ValueError): sweep_semantic_min_similarity_margin(lambda text:[1.0], min_similarity=None, fixture_adapter_factory=FakeFixtureAdapter)
  sweep=sweep_semantic_min_similarity_margin(lambda text:[1.0], min_similarity=.47, candidates=(0.0,.5), fixture_adapter_factory=FakeFixtureAdapter)
  self.assertEqual([row["min_similarity_margin"] for row in sweep["candidates"]],[0.0,.5])
  self.assertGreater(sweep["candidates"][0]["semantic_top1_hit_rate"], sweep["candidates"][1]["semantic_top1_hit_rate"])
if __name__ == "__main__": unittest.main()
