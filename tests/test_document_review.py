from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.document_intake import extract_document_memory_candidates, prepare_document
from pipeline.document_review import (
    DocumentReviewError,
    DocumentReviewStore,
    candidate_public_id,
    review_candidate_public_payload,
    review_public_payload,
)


class DocumentReviewStoreTests(unittest.TestCase):
    def _document_and_candidate(self, text="Roger prefers tea."):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.md"
            path.write_text(text, encoding="utf-8")
            document = prepare_document(path, domain="personal")
        candidates = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [{
            "store": True,
            "subject": "Roger",
            "memory_type": "preference",
            "summary": "Roger prefers tea.",
            "details": None,
            "importance": 0.6,
            "confidence": 0.9,
            "retention": "long_term",
        }]})
        return document, candidates

    def test_review_session_returns_only_original_server_candidate(self):
        document, candidates = self._document_and_candidate()
        store = DocumentReviewStore()
        session = store.create(document, candidates)

        selected = store.get_candidate(session.review_id, "C-001")
        payload = review_public_payload(session)

        self.assertIs(selected, candidates[0])
        self.assertEqual(payload["id"], session.review_id)
        self.assertEqual(payload["candidate_count"], 1)
        self.assertNotIn("observation_text", payload)
        self.assertEqual(store.get_document(session.review_id), document)
        self.assertEqual(candidate_public_id(0), "C-001")

    def test_missing_expired_and_invalid_candidate_ids_are_rejected(self):
        now = [datetime(2026, 8, 6, tzinfo=UTC)]
        store = DocumentReviewStore(ttl_seconds=10, clock=lambda: now[0])
        document, candidates = self._document_and_candidate()
        session = store.create(document, candidates)

        with self.assertRaisesRegex(DocumentReviewError, "candidate_id must"):
            store.get_candidate(session.review_id, "1")
        with self.assertRaisesRegex(DocumentReviewError, "candidate not found"):
            store.get_candidate(session.review_id, "C-002")
        now[0] += timedelta(seconds=11)
        with self.assertRaisesRegex(DocumentReviewError, "not found or expired"):
            store.get_candidate(session.review_id, "C-001")

    def test_batch_selection_is_ordered_and_validated_before_handoff(self):
        document, candidates = self._document_and_candidate()
        store = DocumentReviewStore()
        session = store.create(document, candidates)

        selected = store.get_candidates(session.review_id, ["C-001"])
        self.assertEqual(selected, (("C-001", candidates[0]),))

        with self.assertRaisesRegex(DocumentReviewError, "duplicates"):
            store.get_candidates(session.review_id, ["C-001", "c-001"])
        with self.assertRaisesRegex(DocumentReviewError, "candidate not found"):
            store.get_candidates(session.review_id, ["C-001", "C-002"])

    def test_mismatched_candidate_provenance_cannot_enter_review(self):
        first_document, first_candidates = self._document_and_candidate("Roger prefers tea.")
        _, second_candidates = self._document_and_candidate("Roger prefers coffee.")

        with self.assertRaisesRegex(DocumentReviewError, "does not match"):
            DocumentReviewStore().create(first_document, second_candidates)
        self.assertEqual(first_candidates[0].proposal["domain"], "personal")

    def test_review_status_is_ephemeral_and_rejection_blocks_handoff(self):
        document, candidates = self._document_and_candidate()
        store = DocumentReviewStore()
        session = store.create(document, candidates)

        review, entries = store.get_review(session.review_id)
        self.assertIs(review, session)
        candidate_id, status, candidate = entries[0]
        self.assertEqual((candidate_id, status), ("C-001", "pending"))
        public = review_candidate_public_payload(candidate_id, status, candidate)
        self.assertNotIn("observation_text", str(public))

        self.assertEqual(store.reject_candidates(session.review_id, ["C-001"]), ("C-001",))
        self.assertEqual(store.get_review(session.review_id)[1][0][1], "rejected")
        with self.assertRaisesRegex(DocumentReviewError, "dismissed"):
            store.get_candidate(session.review_id, "C-001")

    def test_handed_off_status_keeps_idempotent_candidate_available(self):
        document, candidates = self._document_and_candidate()
        store = DocumentReviewStore()
        session = store.create(document, candidates)

        store.mark_handed_off(session.review_id, ["C-001"])
        self.assertEqual(store.get_review(session.review_id)[1][0][1], "handed_off")
        self.assertIs(store.get_candidate(session.review_id, "C-001"), candidates[0])


if __name__ == "__main__":
    unittest.main()
