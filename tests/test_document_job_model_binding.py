"""Pure declaration binding never supplies locality evidence."""
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch
from pipeline.document_job_locality import LocalAnnotationTarget, evaluate_annotation_locality
from pipeline.document_job_model import DeclaredLocalModel
from pipeline.document_job_model_request import ModelListingRequest
from pipeline.document_job_model_binding import BoundModelDeclaration, ModelListingBindingError


class ModelListingBindingTests(unittest.TestCase):
    def setUp(self):
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start()
        self.addCleanup(guard.stop)
        self.target = LocalAnnotationTarget("http://127.0.0.1:11434")
        self.request = ModelListingRequest(self.target, "fixture")
        self.model = DeclaredLocalModel("fixture", "a" * 64, 1, "gguf")

    def test_exact_redacted_immutable_binding(self):
        value = BoundModelDeclaration(self.request, self.model, "a" * 64)
        self.assertEqual(value.request_fingerprint, self.request.fingerprint)
        self.assertEqual(value.declaration, self.model)
        self.assertEqual(value, BoundModelDeclaration(self.request, self.model, "a" * 64))
        self.assertNotIn("fixture", repr(value))
        self.assertNotIn("a" * 64, repr(value))
        with self.assertRaises(FrozenInstanceError):
            value.declaration = None

    def test_invalid_or_mismatching_identity_denies_content_free(self):
        for req, model, digest in ((None, self.model, "a" * 64), (self.request, None, "a" * 64),
                                   (self.request, self.model, False), (self.request, self.model, "a" * 63),
                                   (self.request, self.model, "A" * 64), (self.request, self.model, "b" * 64),
                                   (self.request, DeclaredLocalModel("other", "a" * 64, 1, "gguf"), "a" * 64)):
            with self.assertRaises(ModelListingBindingError) as error:
                BoundModelDeclaration(req, model, digest)
            self.assertEqual(str(error.exception), "model listing binding is invalid")

    def test_target_change_produces_distinct_binding(self):
        other = ModelListingRequest(LocalAnnotationTarget("http://[::1]:11434"), "fixture")
        self.assertNotEqual(BoundModelDeclaration(self.request, self.model, "a" * 64),
                            BoundModelDeclaration(other, self.model, "a" * 64))

    def test_no_fabricated_locality_evidence(self):
        value = BoundModelDeclaration(self.request, self.model, "a" * 64)
        self.assertEqual(set(value.__dataclass_fields__), {"request_fingerprint", "declaration"})
        self.assertEqual(evaluate_annotation_locality(self.target, "fixture").status, "denied")
        with self.assertRaises(ValueError):
            evaluate_annotation_locality(self.target, "fixture", value)
