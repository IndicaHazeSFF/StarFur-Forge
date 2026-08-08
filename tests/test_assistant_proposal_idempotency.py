from pathlib import Path
import tempfile
import unittest
from pipeline import db

class AssistantProposalIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.old = db.DB_PATH; db.DB_PATH = Path(self.temp.name) / "db.sqlite"
    def tearDown(self):
        db.DB_PATH = self.old; self.temp.cleanup()
    def test_equivalent_pending_proposals_reinforce(self):
        base = {"subject":"Roger","memory_type":"preference","summary":" My favorite game is Fortnite! ","details":"","importance":0.8,"confidence":0.8,"retention":"long_term"}
        first = db.upsert_assistant_memory_proposal(base)
        second = db.upsert_assistant_memory_proposal({**base, "summary":"my   favorite game is fortnite."})
        self.assertEqual(first["action"], "created"); self.assertEqual(second["action"], "reinforced"); self.assertEqual(first["proposal_id"], second["proposal_id"])
        row = db.get_assistant_memory_proposal(first["proposal_id"])
        self.assertEqual(row["evidence_count"], 2)
        self.assertGreater(row["confidence"], 0.8)
        self.assertEqual(len(db.list_assistant_memory_proposals()), 1)
    def test_distinct_subject_domain_and_type_do_not_merge(self):
        base = {"subject":"Roger","memory_type":"preference","summary":"Likes purple","details":"","importance":0.5,"confidence":0.5,"retention":"long_term"}
        a = db.upsert_assistant_memory_proposal(base)
        b = db.upsert_assistant_memory_proposal({**base, "subject":"Murr"})
        c = db.upsert_assistant_memory_proposal({**base, "memory_type":"personal_fact"})
        d = db.upsert_assistant_memory_proposal({**base}, domain="project:starfur")
        self.assertEqual(len({a["proposal_id"],b["proposal_id"],c["proposal_id"],d["proposal_id"]}), 4)
    def test_evidence_is_not_duplicated_for_same_source_event(self):
        base = {"subject":"Roger","memory_type":"goal","summary":"Build StarFur","details":"","importance":0.5,"confidence":0.5,"retention":"long_term"}
        a = db.upsert_assistant_memory_proposal(base, source_reference="turn-1")
        db.upsert_assistant_memory_proposal(base, source_reference="turn-1")
        with db.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM assistant_memory_proposal_evidence WHERE proposal_id = ?", (a["proposal_id"],)).fetchone()[0]
        self.assertEqual(count, 1)

    def test_observation_identity_survives_summary_paraphrase_and_is_idempotent(self):
        text = "I am building a two-dimensional memory system for Murr."
        base = {"subject":"Roger","memory_type":"project_context","summary":"Building memory for Murr","details":"first","importance":0.8,"confidence":0.8,"retention":"long_term"}
        first = db.upsert_assistant_memory_proposal(base, observation_text=text)
        second = db.upsert_assistant_memory_proposal({**base, "summary":"Creating a layered memory engine for Murr", "details":"later"}, observation_text=text)
        third = db.upsert_assistant_memory_proposal({**base, "summary":"Yet another paraphrase"}, observation_text=text)
        self.assertEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(second["action"], "duplicate_evidence")
        self.assertEqual(third["action"], "duplicate_evidence")
        row = db.get_assistant_memory_proposal(first["proposal_id"])
        self.assertEqual(row["evidence_count"], 1)
        self.assertEqual(row["summary"], base["summary"])

    def test_document_candidates_from_same_chunk_remain_distinct_and_repeat_idempotently(self):
        base = {"subject":"Stage 2","memory_type":"project_context","summary":"First capability","details":"","importance":0.7,"confidence":0.8,"retention":"long_term","source":"external_document_annotation"}
        observation = "One document chunk describing several capabilities."
        first = db.upsert_assistant_memory_proposal(base, source_reference="external:hash:chunk:0:candidate:0", observation_text=observation)
        second = db.upsert_assistant_memory_proposal({**base, "summary":"Second capability"}, source_reference="external:hash:chunk:0:candidate:1", observation_text=observation)
        repeated = db.upsert_assistant_memory_proposal(base, source_reference="external:hash:chunk:0:candidate:0", observation_text=observation)
        self.assertNotEqual(first["proposal_id"], second["proposal_id"])
        self.assertEqual(repeated["proposal_id"], first["proposal_id"])
        self.assertEqual(repeated["action"], "duplicate_evidence")
    def test_different_observations_remain_separate(self):
        base = {"subject":"Roger","memory_type":"preference","summary":"Likes cats","details":"","importance":0.5,"confidence":0.5,"retention":"long_term"}
        a = db.upsert_assistant_memory_proposal(base, observation_text="I like cats")
        b = db.upsert_assistant_memory_proposal(base, observation_text="I like dogs")
        self.assertNotEqual(a["proposal_id"], b["proposal_id"])

if __name__ == "__main__":
    unittest.main()
