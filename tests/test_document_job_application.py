"""Five fake-provider application admission/chunk integration smoke gates."""

from dataclasses import replace
import unittest
from unittest import mock

from tests.document_job_fixtures import make_application, multi_chunk_text, proposal_response
from pipeline.document_annotation import DocumentAnnotationDeferredError
from pipeline.document_intake import prepare_document_text
from pipeline.providers import DisabledChatProvider


class AnnotationJobApplicationSmokes(unittest.TestCase):
    def setUp(self):
        for target in ("pipeline.db.connect", "socket.socket"):
            guard = mock.patch(target, side_effect=AssertionError("no database/network"))
            guard.start()
            self.addCleanup(guard.stop)
        self.document = prepare_document_text(multi_chunk_text(), "fixture.md")
        self.assertGreater(len(self.document.chunks), 1)

    def test_01_exact_chunk_keeps_source_and_selected_profile(self):
        app, _session, provider = make_application()
        provider.response = proposal_response()
        chunk = self.document.chunks[1]
        result = app.annotate_document_chunk(self.document, chunk.chunk_id)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result.candidates[0].source_id, self.document.source_id)
        self.assertEqual(result.candidates[0].chunk_id, chunk.chunk_id)
        self.assertEqual(result.candidates[0].observation_text, chunk.text)
        self.assertIn(chunk.text, provider.calls[0]["messages"][1]["content"])
        self.assertEqual(provider.calls[0]["model"], "fixture-model")
        self.assertEqual(provider.calls[0]["options"]["num_predict"], 256)
        self.assertEqual(provider.probes, 0)

    def test_02_focus_mode_is_rechecked_between_chunks(self):
        app, session, provider = make_application()
        first, second = self.document.chunks[:2]
        app.annotate_document_chunk(self.document, first.chunk_id)
        session.focus_mode_set(True)
        with self.assertRaises(DocumentAnnotationDeferredError) as caught:
            app.annotate_document_chunk(self.document, second.chunk_id)
        self.assertEqual(caught.exception.reason, "focus_mode")
        self.assertEqual(len(provider.calls), 1)
        session.focus_mode_set(False)
        app.annotate_document_chunk(self.document, second.chunk_id)
        self.assertEqual(len(provider.calls), 2)

    def test_03_capacity_deferral_precedes_provider_and_recovers(self):
        app, _session, provider = make_application()
        gate = app._workload_gate
        held = gate.try_acquire("ollama", 1)
        with self.assertRaises(DocumentAnnotationDeferredError) as caught:
            app.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        self.assertEqual(caught.exception.reason, "provider_capacity_busy")
        self.assertEqual(provider.calls, [])
        self.assertTrue(gate.release(held.lease))
        app.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(gate.active_count("ollama"), 0)

    def test_04_disabled_provider_refuses_without_probe(self):
        app, _session, _provider = make_application(DisabledChatProvider())
        with self.assertRaises(DocumentAnnotationDeferredError) as caught:
            app.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        self.assertEqual(caught.exception.reason, "provider_unavailable")

    def test_05_invalid_or_ambiguous_chunk_binding_never_calls_provider(self):
        app, _session, provider = make_application()
        chunk = self.document.chunks[0]
        for document, identifier in (
            (self.document, "missing"), (self.document, "../outside"),
            (replace(self.document, chunks=(chunk, chunk)), chunk.chunk_id),
            (replace(self.document, chunks=(replace(chunk, source_id="foreign"),)), chunk.chunk_id),
            (replace(self.document, chunks=(replace(chunk, domain="project:foreign"),)), chunk.chunk_id),
            (replace(self.document, chunks=(None,)), chunk.chunk_id),
        ):
            with self.assertRaises(ValueError):
                app.annotate_document_chunk(document, identifier)
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
