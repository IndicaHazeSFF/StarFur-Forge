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
 def test_question_scaffolding_and_vocative_do_not_select_noise(self):
  gpu=db.create_assistant_memory("User","personal_fact","Desktop graphics card",details="The user has an NVIDIA RTX 4070 graphics card.",importance=.9,confidence=1)
  db.create_assistant_memory("User","personal_fact","Nozzle size correction",details="The user uses a 0.8 mm graphics nozzle.",importance=1,confidence=1)
  db.create_assistant_memory("Murr","relationship_context","Friend plays Fortnite",details="Murr plays a card game with the user.",importance=.8,confidence=.9)
  result=db.retrieve_assistant_memories("What graphics card do I have, Murr?",limit=5)
  self.assertEqual([item["memory"]["id"] for item in result],[gpu])
  self.assertEqual(result[0]["reasons"],["2 meaningful keyword overlap"])
 def test_stronger_multi_term_match_excludes_weak_single_term_noise(self):
  gpu=db.create_assistant_memory("User","personal_fact","Desktop graphics card",details="The user has an NVIDIA RTX 4070 graphics card.",importance=.9,confidence=1)
  db.create_assistant_memory("User","personal_fact","Graphics project",details="The user is making art for a game.",importance=1,confidence=1)
  result=db.retrieve_assistant_memories("What graphics card GPU do I have?",limit=5)
  self.assertEqual([item["memory"]["id"] for item in result],[gpu])
 def test_single_meaningful_term_recall_is_not_filtered(self):
  glasses=db.create_assistant_memory("User","personal_fact","New blue glasses",importance=.8,confidence=.9)
  cleaning=db.create_assistant_memory("User","personal_fact","Glasses cleaning routine",importance=.5,confidence=.5)
  result=db.retrieve_assistant_memories("glasses", limit=5)
  self.assertEqual([item["memory"]["id"] for item in result],[glasses, cleaning])
 def test_meaningful_single_term_recall_and_empty_meaningful_query(self):
  glasses=db.create_assistant_memory("User","personal_fact","New blue glasses",importance=.8,confidence=.9)
  self.assertEqual(db.retrieve_assistant_memories("What did I say about my glasses?")[0]["memory"]["id"],glasses)
  self.assertEqual(db.retrieve_assistant_memories("How are you?"),[])
 def test_deterministic_empty_limit_and_explain(self):
  db.create_assistant_memory("User","preference","Blue mug",importance=.5,confidence=.5)
  self.assertEqual(db.retrieve_assistant_memories("unrelated"),[])
  first=db.explain_assistant_memory_retrieval("blue mug"); second=db.explain_assistant_memory_retrieval("blue mug")
  self.assertEqual(first,second); self.assertEqual(len(first["selected"]),1)

if __name__ == "__main__": unittest.main()


