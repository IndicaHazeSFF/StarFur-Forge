from pathlib import Path
import tempfile
import unittest
from pipeline import db

class RetrievalTests(unittest.TestCase):
 def setUp(self): self.t=tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.old=db.DB_PATH; db.DB_PATH=Path(self.t.name)/"db.sqlite"
 def tearDown(self): db.DB_PATH=self.old; self.t.cleanup()
 def test_relevant_ranked(self):
  db.create_assistant_memory("User","personal_fact","New blue glasses",importance=.8,confidence=.9)
  db.create_assistant_memory("Work","personal_fact","McDonalds schedule",importance=1,confidence=1)
  result=db.retrieve_assistant_memories("What about my glasses?")
  self.assertEqual(result[0]["memory"]["summary"],"New blue glasses")
 def test_deterministic_empty_limit_and_explain(self):
  db.create_assistant_memory("User","preference","Blue mug",importance=.5,confidence=.5)
  self.assertEqual(db.retrieve_assistant_memories("unrelated"),[])
  first=db.explain_assistant_memory_retrieval("blue mug"); second=db.explain_assistant_memory_retrieval("blue mug")
  self.assertEqual(first,second); self.assertEqual(len(first["selected"]),1)

if __name__ == "__main__": unittest.main()
