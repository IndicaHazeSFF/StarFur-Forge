import tempfile, shutil
import unittest
from pathlib import Path
from pipeline import db
from pipeline.reset import CONFIRMATION, factory_reset, factory_restore, list_backups
class FakeChroma:
 def __init__(self): self.deleted=[]
 def get_collection(self,name): return self
 def get(self,include=None): return {"ids":[],"documents":[],"metadatas":[],"embeddings":[]}
 def delete_collection(self,name): self.deleted.append(name)
class MissingCollectionChroma(FakeChroma):
 def get_collection(self,name): raise RuntimeError("Collection [starfur_canon] does not exist")
 def delete_collection(self,name): raise RuntimeError("Collection [starfur_canon] does not exist")

class ResetTests(unittest.TestCase):
 def test_confirmation_and_scoped_reset_with_backup(self):
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
   old=db.DB_PATH; db.DB_PATH=Path(td)/"db.sqlite"; db.create_assistant_memory("User","preference","Blue mug"); result=factory_reset(db.DB_PATH,scope="assistant-and-semantic",confirmation=CONFIRMATION,chroma_client=FakeChroma(),backup_dir=Path(td)/"backups",allow_production=True); self.assertTrue(Path(result["backup"]).exists()); self.assertEqual(db.list_assistant_memories(),[]); db.DB_PATH=old
 def test_absent_chroma_collection_is_treated_as_empty(self):
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
   old=db.DB_PATH; db.DB_PATH=Path(td)/"db.sqlite"; db.create_assistant_memory("User","preference","Blue mug")
   result=factory_reset(db.DB_PATH,scope="assistant-and-semantic",confirmation=CONFIRMATION,chroma_client=MissingCollectionChroma(),backup_dir=Path(td)/"backups",allow_production=True)
   self.assertTrue((Path(result["backup"])/"chroma.json").exists()); self.assertEqual(db.list_assistant_memories(),[]); db.DB_PATH=old

 def test_restore_lists_and_safety_backs_up_current(self):
  with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
   old=db.DB_PATH; db.DB_PATH=Path(td)/"db.sqlite"; db.create_assistant_memory("User","preference","Current"); root=Path(td)/"backup"; source=root/"20260730-0431"; source.mkdir(parents=True); src=Path(td)/"src.sqlite"; db.DB_PATH=src; db.create_assistant_memory("User","preference","Restored"); shutil.copy2(src,source/"starfur.db"); db.DB_PATH=Path(td)/"db.sqlite"; self.assertEqual(list_backups(root),[source]); result=factory_restore(db.DB_PATH,source,confirmation="StarFur Factory Restore",allow_production=True,backup_root=root); self.assertTrue(Path(result["safety_backup"]).exists()); self.assertEqual(db.list_assistant_memories()[0]["summary"],"Restored"); db.DB_PATH=old
if __name__ == "__main__": unittest.main()
