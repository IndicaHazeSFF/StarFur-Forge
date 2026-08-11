from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.retrieval import DeterministicMemoryRetriever, SemanticMemoryRetriever, HybridMemoryRetriever

class FakeCollection:
 def __init__(self, ids=(("1",),), distances=((.1,),)): self.ids=ids; self.distances=distances
 def query(self, **kwargs): return {"ids":[list(self.ids[0])],"distances":[list(self.distances[0])]}
class StrategyTests(unittest.TestCase):
 def test_semantic_and_hybrid_shapes(self):
  memory={"id":1,"summary":"glasses"}; semantic=SemanticMemoryRetriever(FakeCollection(),lambda q:[1.0],{"1":memory}); result=semantic.retrieve("glasses")
  self.assertEqual(result[0]["memory"],memory); self.assertTrue(any("semantic similarity" in reason for reason in result[0]["reasons"]))
  hybrid=HybridMemoryRetriever(type("D",(),{"retrieve":lambda self,*a,**k:[{"memory":memory,"score":.5,"reasons":["token"]}]})(),semantic); self.assertEqual(hybrid.retrieve("glasses")[0]["memory"],memory)
 def test_semantic_minimum_similarity_filters_low_confidence_results(self):
  memory={"id":1,"summary":"glasses"}; semantic=SemanticMemoryRetriever(FakeCollection(),lambda q:[1.0],{"1":memory},min_similarity=.95,min_similarity_margin=.01)
  diagnostics={}
  self.assertEqual(semantic.retrieve("glasses",diagnostics=diagnostics),[])
  self.assertEqual(diagnostics["semantic_acceptance"]["reason"],"semantic rejection: no candidate cleared minimum similarity")
  with self.assertRaises(ValueError): SemanticMemoryRetriever(FakeCollection(),lambda q:[1.0],min_similarity=1.1)
 def test_semantic_margin_rejects_near_ties_and_explains_why(self):
  memories={"1":{"id":1,"summary":"glasses"},"2":{"id":2,"summary":"gpu"}}
  semantic=SemanticMemoryRetriever(FakeCollection((("1","2"),),((1.0,1.01),)),lambda q:[1.0],memories,min_similarity_margin=.01)
  diagnostics={}
  self.assertEqual(semantic.retrieve("question",limit=1,diagnostics=diagnostics),[])
  self.assertFalse(diagnostics["semantic_acceptance"]["accepted"])
  self.assertIn("ambiguity rejected",diagnostics["semantic_acceptance"]["reason"])
 def test_semantic_margin_returns_only_clear_top_result(self):
  memories={"1":{"id":1,"summary":"glasses"},"2":{"id":2,"summary":"gpu"}}
  semantic=SemanticMemoryRetriever(FakeCollection((("1","2"),),((.1,1.0),)),lambda q:[1.0],memories,min_similarity_margin=.05)
  diagnostics={}
  result=semantic.retrieve("question",limit=3,diagnostics=diagnostics)
  self.assertEqual([item["memory"]["id"] for item in result],[1])
  self.assertTrue(diagnostics["semantic_acceptance"]["accepted"])
  self.assertIn("meets",diagnostics["semantic_acceptance"]["reason"])
  with self.assertRaises(ValueError): SemanticMemoryRetriever(FakeCollection(),lambda q:[1.0],min_similarity_margin=1.1)
if __name__ == "__main__": unittest.main()
