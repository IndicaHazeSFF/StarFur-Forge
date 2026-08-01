import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import db
from pipeline.assistant import AssistantConfig, AssistantSession


class BulkApprovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.old_db = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "assistant.sqlite"

    def tearDown(self):
        db.DB_PATH = self.old_db
        self.temp.cleanup()

    def config(self):
        return AssistantConfig("test", Path("persona/default.md"), Path("config/assistant_policy.md"), "personal", 6, 3, "off", "off")

    def proposal(self, summary, *, domain="personal", confidence=0.9):
        return db.create_assistant_memory_proposal({
            "subject": "Roger",
            "memory_type": "preference",
            "summary": summary,
            "details": "",
            "importance": 0.8,
            "confidence": confidence,
            "retention": "long_term",
            "source": "test",
        }, domain=domain)

    def session(self):
        return AssistantSession(
            self.config(), "Persona", chat=lambda **kwargs: (_ for _ in ()).throw(AssertionError("model must not run")),
            memory_loader=lambda **kwargs: [], policy="Policy",
        )

    def test_preview_requires_exact_second_confirmation_and_approves_pending_only(self):
        first = self.proposal("Likes tea")
        second = self.proposal("Likes coffee", confidence=0.4)
        session = self.session()
        preview = session.respond("proposal approve all")
        self.assertIn("Pending proposals in domain personal", preview)
        self.assertIn("P-", preview)
        self.assertIn("low confidence", preview)
        self.assertIn('Type "approve all" to continue', preview)
        self.assertEqual(db.list_assistant_memories(), [])
        self.assertEqual(session.respond("approve All"), "Bulk approval cancelled.")
        self.assertEqual(db.list_assistant_memories(), [])
        session.respond("proposal approve all")
        result = session.respond("approve all")
        self.assertIn("Approved 2 proposal(s).", result)
        self.assertEqual(len(db.list_assistant_memories()), 2)
        self.assertEqual(db.get_assistant_memory_proposal(first)["status"], "approved")
        self.assertEqual(db.get_assistant_memory_proposal(second)["status"], "approved")

    def test_preview_is_domain_scoped_and_empty_is_safe(self):
        personal = self.proposal("Personal fact")
        other = self.proposal("Other project fact", domain="project:demo")
        session = self.session()
        preview = session.respond("proposal approve all")
        self.assertIn("Personal fact", preview or "")
        self.assertNotIn("Other project fact", preview or "")
        session.respond("approve all")
        self.assertEqual(db.get_assistant_memory_proposal(personal)["status"], "approved")
        self.assertEqual(db.get_assistant_memory_proposal(other, domain="project:demo")["status"], "pending")
        self.assertEqual(len(db.list_assistant_memories(domain="personal")), 1)
        self.assertEqual(session.respond("proposal approve all"), "No pending assistant proposals.")


if __name__ == "__main__":
    unittest.main()
