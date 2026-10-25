from copy import deepcopy
from dataclasses import replace
import unittest

from pipeline.document_intake import (
    DocumentAnnotationExecution, DocumentAnnotationFailure, DocumentAnnotationResult,
    extract_document_memory_candidates, prepare_document_text,
)
from pipeline.document_job_results import (
    AnnotationJobResultError, decode_annotation_job_result, encode_annotation_job_result,
    validate_chunk_checkpoint,
)


def fixture_document():
    return prepare_document_text("A fixture person prefers tea.", "fixture.md")


def fixture_result(document):
    candidates = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [{
        "store": True, "subject": "Fixture person", "memory_type": "preference",
        "summary": "Prefers tea", "details": "Test-owned observation",
        "importance": 0.5, "confidence": 0.9, "retention": "long_term",
    }]})
    return DocumentAnnotationResult(candidates, (), DocumentAnnotationExecution("fixture-model", 1))


class AnnotationJobResultCodecTests(unittest.TestCase):
    def setUp(self):
        self.document = fixture_document()
        self.result = fixture_result(self.document)

    def test_roundtrip_rederives_provenance_and_returns_detached_data(self):
        payload = encode_annotation_job_result(self.document, self.result)
        self.assertNotIn("observation_text", str(payload))
        restored = decode_annotation_job_result(self.document, payload)
        self.assertEqual(restored, self.result)
        payload["candidates"][0]["proposal"]["summary"] = "Changed"
        self.assertEqual(self.result.candidates[0].proposal["summary"], "Prefers tea")
        self.assertEqual(restored.candidates[0].proposal["summary"], "Prefers tea")

    def test_forged_candidate_source_chunk_reference_and_observation_deny(self):
        candidate = self.result.candidates[0]
        for changed in (replace(candidate, source_id="foreign"), replace(candidate, chunk_id="foreign"),
                        replace(candidate, source_reference="foreign"), replace(candidate, observation_text="foreign")):
            with self.assertRaises(AnnotationJobResultError):
                encode_annotation_job_result(self.document, replace(self.result, candidates=(changed,)))

    def test_closed_payload_unknown_fields_domain_and_authority_deny(self):
        original = encode_annotation_job_result(self.document, self.result)
        for field, value in (("domain", "project:foreign"), ("source", "assistant_chat"),
                             ("grant", True), ("confidence", float("nan")), ("subject", "x" * 129)):
            payload = deepcopy(original)
            payload["candidates"][0]["proposal"][field] = value
            with self.assertRaises(AnnotationJobResultError):
                decode_annotation_job_result(self.document, payload)
        for value in (True, 2, "1"):
            payload = {**original, "schema_version": value}
            with self.assertRaises(AnnotationJobResultError):
                decode_annotation_job_result(self.document, payload)

    def test_failed_and_empty_chunks_remain_distinct(self):
        chunk = self.document.chunks[0]
        failure = DocumentAnnotationFailure(chunk.chunk_id, chunk.scene_index, chunk.chunk_index, 3)
        failed = DocumentAnnotationResult((), (failure,))
        for result in (failed, DocumentAnnotationResult((), ())):
            payload = encode_annotation_job_result(self.document, result)
            self.assertEqual(validate_chunk_checkpoint(self.document, chunk.chunk_id, payload), result)
        with self.assertRaises(AnnotationJobResultError):
            encode_annotation_job_result(self.document, replace(self.result, failures=(failure,)))

    def test_duplicate_candidates_and_failure_coordinates_deny(self):
        with self.assertRaises(AnnotationJobResultError):
            encode_annotation_job_result(self.document, replace(self.result, candidates=self.result.candidates * 2))
        chunk = self.document.chunks[0]
        for failure in (DocumentAnnotationFailure(chunk.chunk_id, 999, chunk.chunk_index, 1),
                        DocumentAnnotationFailure(chunk.chunk_id, chunk.scene_index, chunk.chunk_index, True),
                        DocumentAnnotationFailure(chunk.chunk_id, chunk.scene_index, chunk.chunk_index, 4)):
            with self.assertRaises(AnnotationJobResultError):
                encode_annotation_job_result(self.document, DocumentAnnotationResult((), (failure,)))

    def test_execution_metadata_is_bounded_and_not_chunk_checkpoint_data(self):
        for execution in (DocumentAnnotationExecution("m", 1, elapsed_ms=float("inf")),
                          DocumentAnnotationExecution("m", 1, elapsed_ms=float("nan")),
                          DocumentAnnotationExecution("m", 1, fallback_attempts=1),
                          DocumentAnnotationExecution("m", 1, elapsed_ms=10 ** 500)):
            with self.assertRaises(AnnotationJobResultError):
                encode_annotation_job_result(self.document, replace(self.result, execution=execution))
        with self.assertRaises(AnnotationJobResultError):
            validate_chunk_checkpoint(self.document, self.document.chunks[0].chunk_id,
                                      encode_annotation_job_result(self.document, self.result))


if __name__ == "__main__":
    unittest.main()
