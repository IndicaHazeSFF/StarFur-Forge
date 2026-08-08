from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.chunker import chunk_markdown, chunk_text
from pipeline.document_intake import (
    DOCUMENT_ANNOTATION_SOURCE,
    DocumentAnnotationError,
    DocumentIntakeError,
    EXTERNAL_UPLOAD_SOURCE,
    extract_document_memory_candidates,
    extract_document_memory_candidates_resilient,
    prepare_document,
    prepare_document_text,
)


class DocumentIntakeTests(unittest.TestCase):
    def _write(self, directory, name, content, *, encoding="utf-8"):
        path = Path(directory) / name
        path.write_text(content, encoding=encoding)
        return path

    def test_prepares_markdown_with_stable_external_provenance(self):
        markdown = """---
title: Test upload
---

# First

Alpha paragraph.

## Second

Beta paragraph.
"""
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "notes.md", markdown)
            first = prepare_document(path, domain="personal")
            second = prepare_document(path, domain="personal")

        self.assertEqual(first.source_id, second.source_id)
        self.assertTrue(first.source_id.startswith("external:"))
        self.assertEqual(first.source_name, "notes.md")
        self.assertEqual(first.source_kind, EXTERNAL_UPLOAD_SOURCE)
        self.assertEqual(first.domain, "personal")
        self.assertEqual(len(first.chunks), 1)
        chunk = first.chunks[0]
        self.assertEqual(chunk.source_id, first.source_id)
        self.assertEqual(chunk.source_kind, EXTERNAL_UPLOAD_SOURCE)
        self.assertEqual(chunk.chunk_id, f"{first.source_id}:scene:0:chunk:0")
        self.assertEqual(chunk.frontmatter, {"title": "Test upload"})
        self.assertIn("Alpha paragraph.", chunk.text)
        self.assertIn("Beta paragraph.", chunk.text)

    def test_identical_content_has_same_identity_without_path_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            first = self._write(directory, "first.txt", "same content")
            second = self._write(directory, "second.txt", "same content")
            prepared_first = prepare_document(first)
            prepared_second = prepare_document(second)

        self.assertEqual(prepared_first.source_id, prepared_second.source_id)
        self.assertEqual(prepared_first.source_name, "first.txt")
        self.assertEqual(prepared_second.source_name, "second.txt")

    def test_rejects_unsupported_oversized_binary_and_invalid_utf8_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            directory_path = Path(directory)
            unsupported = self._write(directory, "notes.pdf", "not really a PDF")
            oversized = self._write(directory, "large.txt", "12345")
            binary = directory_path / "binary.txt"
            binary.write_bytes(b"hello\x00world")
            invalid_utf8 = directory_path / "invalid.md"
            invalid_utf8.write_bytes(b"\xff\xfe")

            with self.assertRaisesRegex(DocumentIntakeError, "Unsupported"):
                prepare_document(unsupported)
            with self.assertRaisesRegex(DocumentIntakeError, "exceeds"):
                prepare_document(oversized, max_bytes=4)
            with self.assertRaisesRegex(DocumentIntakeError, "NUL"):
                prepare_document(binary)
            with self.assertRaisesRegex(DocumentIntakeError, "UTF-8"):
                prepare_document(invalid_utf8)

    def test_domain_and_chunk_parameters_use_existing_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "notes.txt", "One. Two. Three.")
            prepared = prepare_document(path, domain="project:starfur", max_chars=8)
            self.assertEqual(prepared.domain, "project:starfur")
            self.assertGreaterEqual(len(prepared.chunks), 2)
            with self.assertRaisesRegex(ValueError, "Invalid memory domain"):
                prepare_document(path, domain="not a domain")
            with self.assertRaisesRegex(ValueError, "max_bytes"):
                prepare_document(path, max_bytes=0)


    def test_extracts_validated_non_persistent_candidates_with_engine_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            document = prepare_document(
                self._write(directory, "project.md", "I am building StarFur Forge."),
                domain="project:starfur",
            )
            calls = []

            def annotator(chunk):
                calls.append(chunk)
                return {"proposals": [{
                    "store": True,
                    "subject": "StarFur Forge",
                    "memory_type": "project_context",
                    "summary": "StarFur Forge is being built.",
                    "details": None,
                    "importance": 0.8,
                    "confidence": 0.9,
                    "retention": "long_term",
                }]}

            candidates = extract_document_memory_candidates(document, annotator)

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.proposal["domain"], "project:starfur")
        self.assertEqual(candidate.proposal["source"], DOCUMENT_ANNOTATION_SOURCE)
        self.assertEqual(candidate.source_reference, f"{document.chunks[0].chunk_id}:candidate:0")
        self.assertEqual(candidate.observation_text, document.chunks[0].text)

    def test_candidates_from_one_chunk_have_stable_distinct_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            document = prepare_document(self._write(directory, "notes.md", "Two project facts."))
            candidates = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [
                {"store": True, "subject": "StarFur", "memory_type": "project_context", "summary": "First fact.", "details": None, "importance": 0.5, "confidence": 0.8, "retention": "short_term"},
                {"store": True, "subject": "StarFur", "memory_type": "project_context", "summary": "Second fact.", "details": None, "importance": 0.5, "confidence": 0.8, "retention": "short_term"},
            ]})
        self.assertEqual(
            [candidate.source_reference for candidate in candidates],
            [f"{document.chunks[0].chunk_id}:candidate:0", f"{document.chunks[0].chunk_id}:candidate:1"],
        )
    def test_document_candidates_reject_untrusted_fields_and_omit_store_false(self):
        with tempfile.TemporaryDirectory() as directory:
            document = prepare_document(self._write(directory, "notes.md", "An observation."))

            def no_store(_chunk):
                return [{
                    "store": False, "subject": "User", "memory_type": "personal_fact",
                    "summary": "Not retained.", "importance": 0.1,
                    "confidence": 0.1, "retention": "session",
                }]

            self.assertEqual(extract_document_memory_candidates(document, no_store), ())

            def tries_to_select_domain(_chunk):
                return [{
                    "store": True, "subject": "User", "memory_type": "personal_fact",
                    "summary": "Bad boundary.", "importance": 0.5,
                    "confidence": 0.5, "retention": "long_term", "domain": "personal",
                }]

            with self.assertRaisesRegex(DocumentAnnotationError, "unknown fields"):
                extract_document_memory_candidates(document, tries_to_select_domain)

    def test_in_memory_chunking_matches_file_chunking(self):
        markdown = "# Heading\n\nFirst paragraph.\n\nSecond paragraph."
        with tempfile.TemporaryDirectory() as directory:
            path = self._write(directory, "notes.md", markdown)
            self.assertEqual(chunk_text(markdown), chunk_markdown(path))

    def test_resilient_extraction_retries_bad_chunks_and_continues(self):
        document = prepare_document_text(
            "# First\n\nFirst chunk.\n\n# Second\n\nSecond chunk.",
            "notes.md", max_chars=20,
        )
        self.assertGreaterEqual(len(document.chunks), 2)
        calls = []

        def annotator(chunk):
            calls.append(chunk.chunk_index)
            if chunk.chunk_index == 0:
                return {"proposals": "invalid"}
            return {"proposals": [{
                "store": True, "subject": "Roger", "memory_type": "personal_fact",
                "summary": "Second chunk is valid.", "details": None,
                "importance": 0.5, "confidence": 0.8, "retention": "short_term",
            }]}

        result = extract_document_memory_candidates_resilient(document, annotator, max_attempts=3)

        self.assertEqual(calls.count(0), 3)
        self.assertIn(1, calls)
        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertEqual(result.failures[0].chunk_index, 0)
        self.assertEqual(result.failures[0].attempts, 3)
if __name__ == "__main__":
    unittest.main()
