from pathlib import Path
import tempfile
import unittest
from pipeline import db

class AssistantProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "db.sqlite"
    def tearDown(self):
        db.DB_PATH = self.old
        self.temp.cleanup()
    def test_pending_approval_links_both_records(self):
        proposal = {"subject":"Roger","memory_type":"goal","summary":"Build StarFur","details":"Long term project","importance":0.8,"confidence":0.9,"retention":"long_term","source":"assistant_turn_proposal"}
        proposal_id = db.create_assistant_memory_proposal(proposal)
        self.assertEqual(db.list_assistant_memory_proposals()[0]["status"], "pending")
        memory = db.approve_assistant_memory_proposal(proposal_id)
        self.assertEqual(memory["source_proposal_id"], proposal_id)
        stored = db.get_assistant_memory_proposal(proposal_id)
        self.assertEqual(stored["status"], "approved")
        self.assertEqual(stored["approved_memory_id"], memory["id"])
        repeated = db.approve_assistant_memory_proposal(proposal_id)
        self.assertEqual(repeated["id"], memory["id"])
    def test_approval_links_all_evidence_and_memory_inspection_reads_it(self):
        proposal = {"subject":"Roger","memory_type":"preference","summary":"Likes rice","details":"","importance":0.7,"confidence":0.8,"retention":"long_term"}
        result = db.upsert_assistant_memory_proposal(proposal, observation_text="I like jasmine rice")
        memory = db.approve_assistant_memory_proposal(result["proposal_id"])
        inspected = db.inspect_assistant_memory(memory["id"])
        self.assertEqual(len(inspected["evidence"]), 1)
        self.assertEqual(inspected["evidence"][0]["memory_id"], memory["id"])
        self.assertEqual(inspected["evidence"][0]["proposal_id"], result["proposal_id"])

    def test_rejection_preserves_proposal_without_memory(self):
        proposal_id = db.create_assistant_memory_proposal({"subject":"Roger","memory_type":"goal","summary":"Reject me","details":"","importance":0.5,"confidence":0.5,"retention":"session"})
        db.reject_assistant_memory_proposal(proposal_id)
        self.assertEqual(db.get_assistant_memory_proposal(proposal_id)["status"], "rejected")
        self.assertEqual(db.list_assistant_memories(), [])

    def test_explicit_visibility_scope_survives_review_and_approval(self):
        proposal_id = db.create_assistant_memory_proposal({
            "subject": "Story", "memory_type": "experience", "summary": "Met the captain",
            "details": "Adventure scene", "importance": 0.5, "confidence": 0.5,
            "retention": "long_term", "visibility_scope": "roleplay",
        })
        proposal = db.get_assistant_memory_proposal(proposal_id)
        self.assertEqual("roleplay", proposal["visibility_scope"])
        memory = db.approve_assistant_memory_proposal(proposal_id)
        self.assertEqual("roleplay", memory["visibility_scope"])

    def test_pending_proposal_scope_can_be_edited_but_approved_proposal_cannot(self):
        proposal_id = db.create_assistant_memory_proposal({
            "subject": "Story", "memory_type": "experience", "summary": "Found a map",
            "details": "Adventure scene", "importance": 0.5, "confidence": 0.5,
            "retention": "long_term",
        })
        edited = db.update_assistant_memory_proposal_visibility_scope(proposal_id, "roleplay")
        self.assertEqual("roleplay", edited["visibility_scope"])
        db.approve_assistant_memory_proposal(proposal_id)
        with self.assertRaises(ValueError):
            db.update_assistant_memory_proposal_visibility_scope(proposal_id, None)

if __name__ == "__main__":
    unittest.main()
