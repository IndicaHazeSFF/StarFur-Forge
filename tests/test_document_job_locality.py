"""Pure private-job locality policy contracts; never touch a provider/network."""

from dataclasses import replace
import os
import unittest
from unittest import mock

from pipeline.document_job_locality import (
    ANNOTATION_LOCALITY_POLICY, AnnotationLocalityDecision, AnnotationLocalityError,
    AnnotationLocalityEvidence, LocalAnnotationTarget, evaluate_annotation_locality,
)


class AnnotationLocalityContracts(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "socket.getaddrinfo"):
            guard = mock.patch(target, side_effect=AssertionError("no network/discovery"))
            guard.start()
            self.addCleanup(guard.stop)
        self.target = LocalAnnotationTarget("http://127.0.0.1:11434")
        self.evidence = AnnotationLocalityEvidence(
            self.target.fingerprint, "fixture-model", "a" * 64, True, True, True)

    def test_numeric_loopback_targets_only_without_normalization_or_dns(self):
        self.assertNotEqual(self.target.fingerprint, LocalAnnotationTarget("http://[::1]:11434").fingerprint)
        for endpoint in ("http://localhost:11434", "http://192.168.1.1:11434", "http://172.20.0.1:11434",
                         "https://ollama.com:443", "http://8.8.8.8:11434", "http://0.0.0.0:11434",
                         "http://127.0.0.2:11434", "http://[::ffff:127.0.0.1]:11434",
                         "http://2130706433:11434", "http://127.1:11434", "http://127.0.0.1:011434",
                         "http://127.0.0.1:11434/", "http://127.0.0.1:11434?x=1",
                         "http://u:p@127.0.0.1:11434", "http://127.0.0.1:11434#x",
                         "http://127.0.0.1:0", "http://127.0.0.1:65536", "http://127.0.0.1",
                         " http://127.0.0.1:11434", "http://127.0.0.1:11434\n"):
            with self.subTest(endpoint=endpoint), self.assertRaises(AnnotationLocalityError):
                LocalAnnotationTarget(endpoint)

    def test_endpoint_or_environment_presence_is_never_execution_evidence(self):
        with mock.patch.dict(os.environ, {"OLLAMA_HOST": self.target.endpoint, "OLLAMA_NO_CLOUD": "1"}):
            self.assertEqual(evaluate_annotation_locality(self.target, "fixture-model").reason, "locality_unverified")
        self.assertEqual(evaluate_annotation_locality(self.target, "fixture-model", self.evidence).status, "eligible")

    def test_every_verification_dimension_is_required(self):
        for changes, reason in (({"model_digest": None}, "local_artifact_unverified"),
                                ({"local_execution_verified": False}, "local_execution_unverified"),
                                ({"server_cloud_disabled": False}, "cloud_relay_not_disabled"),
                                ({"direct_transport_verified": False}, "direct_transport_unverified")):
            self.assertEqual(evaluate_annotation_locality(self.target, "fixture-model",
                             replace(self.evidence, **changes)).reason, reason)

    def test_evidence_is_exact_target_model_and_policy_bound(self):
        other = LocalAnnotationTarget("http://127.0.0.1:11435")
        self.assertEqual(evaluate_annotation_locality(other, "fixture-model", self.evidence).reason, "target_mismatch")
        self.assertEqual(evaluate_annotation_locality(self.target, "other-model", self.evidence).reason, "model_mismatch")
        for changes in ({"policy_revision": "allow-cloud"}, {"model_digest": "invalid"},
                        {"local_execution_verified": 1}, {"target_fingerprint": "x"}, {"model": "bad model"}):
            with self.assertRaises(AnnotationLocalityError):
                replace(self.evidence, **changes)

    def test_cloud_model_labels_deny_even_with_declarations(self):
        for model in ("model:cloud", "model-cloud", "provider/cloud/model", "model:Cloud"):
            evidence = replace(self.evidence, model=model)
            self.assertEqual(evaluate_annotation_locality(self.target, model, evidence).reason, "cloud_model_forbidden")
        # A friendly alias is still denied with no independently checked evidence.
        self.assertEqual(evaluate_annotation_locality(self.target, "friendly-local-name").status, "denied")

    def test_untrusted_dicts_and_unknown_outcomes_cannot_supply_policy(self):
        with self.assertRaises(AnnotationLocalityError):
            evaluate_annotation_locality(self.target, "fixture-model", {"local_execution_verified": True})
        with self.assertRaises(AnnotationLocalityError):
            AnnotationLocalityDecision("eligible", "user-says-local")
        self.assertNotIn("fixture-model", repr(self.evidence))
        self.assertNotIn("127.0.0.1", repr(self.target))
        self.assertEqual(self.evidence.policy_revision, ANNOTATION_LOCALITY_POLICY)


if __name__ == "__main__":
    unittest.main()
