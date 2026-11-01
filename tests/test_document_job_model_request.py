"""Pure request contracts; no service or production-state access."""

from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from pipeline.document_job_locality import LocalAnnotationTarget, evaluate_annotation_locality
from pipeline.document_job_model_request import ModelListingRequest, ModelListingRequestError


class ModelListingRequestTests(unittest.TestCase):
    def setUp(self):
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start()
        self.addCleanup(guard.stop)
        self.target = LocalAnnotationTarget("http://127.0.0.1:11434")

    def test_fingerprint_is_deterministic_and_exactly_target_model_bound(self):
        value = ModelListingRequest(self.target, "fixture:1")
        self.assertRegex(value.fingerprint, r"\A[0-9a-f]{64}\Z")
        self.assertEqual(value.fingerprint, ModelListingRequest(self.target, "fixture:1").fingerprint)
        for target, model in ((self.target, "fixture:2"), (self.target, "Fixture:1"),
                              (LocalAnnotationTarget("http://[::1]:11434"), "fixture:1"),
                              (LocalAnnotationTarget("http://127.0.0.1:11435"), "fixture:1")):
            self.assertNotEqual(value.fingerprint, ModelListingRequest(target, model).fingerprint)

    def test_immutable_and_redacted(self):
        value = ModelListingRequest(self.target, "fixture:1")
        for name, replacement in (("model", "other"), ("target", None)):
            with self.assertRaises(FrozenInstanceError):
                setattr(value, name, replacement)
        self.assertNotIn("fixture:1", repr(value))
        self.assertNotIn("127.0.0.1", repr(value))

    def test_invalid_input_types_bounds_and_cloud_labels_deny_content_free(self):
        for target, model in ((None, "ok"), ("http://127.0.0.1:11434", "ok"),
                              (self.target, None), (self.target, False), (self.target, ""),
                              (self.target, "x" * 129), (self.target, "a cloud"),
                              (self.target, "a:CLOUD"), (self.target, "cloud/a"),
                              (self.target, "\ud800")):
            with self.subTest(model=repr(model)), self.assertRaises(ModelListingRequestError) as error:
                ModelListingRequest(target, model)
            self.assertEqual(str(error.exception), "model listing request is invalid")
        self.assertEqual(len(ModelListingRequest(self.target, "x" * 128).model), 128)

    def test_request_is_not_locality_authority_or_an_observation(self):
        value = ModelListingRequest(self.target, "fixture:1")
        self.assertEqual(set(value.__dataclass_fields__), {"target", "model"})
        self.assertEqual(evaluate_annotation_locality(self.target, value.model).status, "denied")
        with self.assertRaises(ValueError):
            evaluate_annotation_locality(self.target, value.model, value)
