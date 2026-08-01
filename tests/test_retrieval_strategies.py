import unittest
from pipeline.retrieval import DeterministicMemoryRetriever, SemanticMemoryRetriever, HybridMemoryRetriever

class FakeCollection:
 def query(self, **kwargs): return {"ids":[["1"]],"distances":[[.1]]}
class StrategyTests(unittest.TestCase):
 def test_semantic_and_hybrid_shapes(self):
  memory={"id":1,"summary":"glasses"}; semantic=SemanticMemoryRetriever(FakeCollection(),lambda q:[1.0],{"1":memory}); result=semantic.retrieve("glasses")
  self.assertEqual(result[0]["memory"],memory); self.assertTrue(any("semantic similarity" in reason for reason in result[0]["reasons"]))
  hybrid=HybridMemoryRetriever(type("D",(),{"retrieve":lambda self,*a,**k:[{"memory":memory,"score":.5,"reasons":["token"]}]})(),semantic); self.assertEqual(hybrid.retrieve("glasses")[0]["memory"],memory)
if __name__ == "__main__": unittest.main()
