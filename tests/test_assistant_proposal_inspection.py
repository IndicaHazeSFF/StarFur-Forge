import tempfile
import unittest
from pathlib import Path
from pipeline import db

class ProposalInspectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.old=db.DB_PATH; db.DB_PATH=Path(self.tmp.name)/"db.sqlite"
    def tearDown(self): db.DB_PATH=self.old; self.tmp.cleanup()
    def test_inspection_returns_oldest_evidence_and_is_read_only(self):
        p={"subject":"Roger","memory_type":"preference","summary":"Likes rice","details":"","importance":.7,"confidence":.8,"retention":"long_term"}
        first=db.upsert_assistant_memory_proposal(p,observation_text="I like rice")
        with db.transaction() as c:
            c.execute("INSERT INTO assistant_memory_proposal_evidence (proposal_id, source, source_reference, evidence_hash, raw_excerpt) VALUES (?,?,?,?,?)", (first["proposal_id"], "manual", "turn-2", "hash-2", "Second observation")); c.commit()
        before=db.get_assistant_memory_proposal(first["proposal_id"])
        result=db.inspect_assistant_memory_proposal(first["proposal_id"])
        self.assertEqual(result["proposal"]["id"],first["proposal_id"]); self.assertEqual(len(result["evidence"]),2)
        self.assertLessEqual(result["evidence"][0]["id"],result["evidence"][1]["id"]); self.assertEqual(db.get_assistant_memory_proposal(first["proposal_id"])["evidence_count"],before["evidence_count"])
    def test_domain_isolation_and_legacy(self):
        p={"subject":"R","memory_type":"goal","summary":"Build it","details":"","importance":.5,"confidence":.5,"retention":"long_term"}
        with db.transaction() as c:
            c.execute("INSERT INTO assistant_memory_proposals (domain,subject,memory_type,summary,details,importance,confidence,retention,source) VALUES (?,?,?,?,?,?,?,?,?)",("personal","R","goal","Legacy","",.5,.5,"long_term","manual")); c.commit()
        row=db.list_assistant_memory_proposals()[0]; self.assertIsNone(db.inspect_assistant_memory_proposal(row["id"],domain="project:starfur")); self.assertEqual(db.inspect_assistant_memory_proposal(row["id"])["proposal"]["proposal_key"],None)
if __name__ == "__main__": unittest.main()


