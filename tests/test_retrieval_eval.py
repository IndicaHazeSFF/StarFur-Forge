import json
import tempfile
import unittest
from pathlib import Path
from pipeline.retrieval_eval import load_cases, run_benchmark

class RetrievalEvalTests(unittest.TestCase):
 def test_checked_in_benchmark_runs(self):
  result=run_benchmark(); self.assertEqual(result["cases"],15); self.assertTrue(result["repeatability"]); self.assertGreaterEqual(result["top3_hit_rate"], result["top1_hit_rate"])
 def test_malformed_fixture_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   path=Path(td)/"bad.json"; path.write_text(json.dumps({"not":"a list"}))
   with self.assertRaises(ValueError): load_cases(path)
if __name__ == "__main__": unittest.main()
