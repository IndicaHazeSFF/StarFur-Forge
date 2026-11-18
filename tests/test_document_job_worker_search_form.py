"""Synthetic bytes only; recognition is never execution permission."""
from dataclasses import FrozenInstanceError
from hashlib import sha256
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import WorkerElfError, inspect_worker_elf
from pipeline.document_job_worker_elf_search import review_worker_elf_search
from pipeline.document_job_worker_search_form import WorkerSearchFormReview, review_worker_search_form
from tests.test_document_job_worker_elf_search import search_fixture


class WorkerSearchFormTests(unittest.TestCase):
    def test_exact_known_forms_only(self):
        for entries, form in (((), "no_search"), (((29, "$ORIGIN"),), "origin_runpath"),
                             (((29, "$ORIGIN:/build/llama-server-cpu/bin:"),), "origin_build_empty_runpath")):
            raw = search_fixture(entries)
            value = review_worker_search_form(raw)
            self.assertEqual((value.raw_sha256, value.form), (sha256(raw).hexdigest(), form))

    def test_mixed_recognition_does_not_change_old_classifier_or_strict_refusal(self):
        raw = search_fixture(((29, "$ORIGIN:/build/llama-server-cpu/bin:"),))
        self.assertEqual(review_worker_search_form(raw).form, "origin_build_empty_runpath")
        self.assertEqual(review_worker_elf_search(raw).category, "mixed_or_unsupported")
        with self.assertRaises(WorkerElfError): inspect_worker_elf(raw)

    def test_no_normalization_or_rpath_promotion(self):
        for tag, text in ((15, "$ORIGIN"), (15, "$ORIGIN:/build/llama-server-cpu/bin:"),
                          (29, "${ORIGIN}"), (29, "$ORIGIN:/build/llama-server-cpu/bin"),
                          (29, "$ORIGIN:/build/llama-server-cpu/bin::"),
                          (29, ":$ORIGIN:/build/llama-server-cpu/bin"),
                          (29, "$ORIGIN:/build/llama-server-cpu/bin/..:"), (29, "")):
            self.assertEqual(review_worker_search_form(search_fixture(((tag, text),))).form, "unsupported")

    def test_conflicting_and_duplicate_tags(self):
        raw = search_fixture(((15, "$ORIGIN"), (29, "$ORIGIN")))
        self.assertEqual(review_worker_search_form(raw).form, "unsupported")
        with self.assertRaises(WorkerElfError):
            review_worker_search_form(search_fixture(((29, "$ORIGIN"), (29, "$ORIGIN"))))

    def test_fingerprint_distinguishes_unsupported_paths_without_returning_them(self):
        a = review_worker_search_form(search_fixture(((29, "/private-a"),)))
        b = review_worker_search_form(search_fixture(((29, "/private-b"),)))
        self.assertNotEqual(a.search_fingerprint, b.search_fingerprint)
        self.assertNotIn("private", repr(a)); self.assertFalse(hasattr(a, "paths"))

    def test_inert_immutable_redacted_not_permission(self):
        raw = search_fixture()
        with patch("builtins.open", side_effect=AssertionError), patch("subprocess.Popen", side_effect=AssertionError):
            value = review_worker_search_form(raw)
        self.assertFalse(hasattr(value, "eligible_to_execute"))
        with self.assertRaises(FrozenInstanceError): value.form = "no_search"

    def test_malformed_input_and_constructed_values_refuse(self):
        for raw in (b"PRIVATE", bytearray(search_fixture()), None):
            with self.assertRaisesRegex(WorkerElfError, "^worker search-form review is unavailable$"):
                review_worker_search_form(raw)
        for args in (("a" * 64, "b" * 64, "safe"), ("PRIVATE", "b" * 64, "no_search")):
            with self.assertRaises(WorkerElfError): WorkerSearchFormReview(*args)
