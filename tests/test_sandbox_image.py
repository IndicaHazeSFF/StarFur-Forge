from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.sandbox_image import (
    SandboxImageEvidence,
    SandboxImageRequirement,
    evaluate_image_compatibility,
)


SHA = "a" * 64


def requirement(**changes):
    values = {
        "schema_version": 1,
        "image_id": "starfur-python",
        "image_revision": "image-v1",
        "guest_family": "linux",
        "guest_generation": 2,
        "architecture": "x86_64",
        "image_format": "vhdx",
        "content_sha256": SHA,
        "toolchain_revision": "python-v1",
        "signature_policy": "required",
        "signer_id": "starfur-release-v1",
        "license_policy_revision": "licenses-v1",
        "patch_policy_revision": "patches-v1",
    }
    values.update(changes)
    return SandboxImageRequirement(**values)


def evidence(**changes):
    values = {
        "schema_version": 1,
        "image_id": "starfur-python",
        "image_revision": "image-v1",
        "guest_family": "linux",
        "guest_generation": 2,
        "architecture": "x86_64",
        "image_format": "vhdx",
        "observed_content_sha256": SHA,
        "toolchain_revision": "python-v1",
        "signer_id": "starfur-release-v1",
        "license_policy_revision": "licenses-v1",
        "patch_policy_revision": "patches-v1",
        "integrity_status": "verified",
        "signature_status": "verified",
        "license_status": "approved",
        "patch_status": "current",
        "verifier_revision": "verifier-v1",
        "observed_at_epoch": 100.0,
        "expires_at_epoch": 200.0,
    }
    values.update(changes)
    return SandboxImageEvidence(**values)


class SandboxImageTests(unittest.TestCase):
    def test_matching_supplied_evidence_is_only_compatible(self):
        with patch("builtins.open", side_effect=AssertionError("must not open image")):
            result = evaluate_image_compatibility(requirement(), evidence(), now_epoch=150.0)
        self.assertTrue(result.compatible)
        self.assertEqual("compatible", result.status)
        self.assertNotIn("ready", repr(result.public_dict()).casefold())

    def test_unconfigured_missing_invalid_and_stale_evidence_deny(self):
        self.assertEqual(
            "image_unconfigured",
            evaluate_image_compatibility(None, None, now_epoch=150.0).reason,
        )
        self.assertEqual(
            "evidence_missing",
            evaluate_image_compatibility(requirement(), None, now_epoch=150.0).reason,
        )
        self.assertEqual(
            "evidence_invalid",
            evaluate_image_compatibility(requirement(), {}, now_epoch=150.0).reason,
        )
        self.assertEqual(
            "evidence_stale",
            evaluate_image_compatibility(requirement(), evidence(), now_epoch=200.0).reason,
        )

    def test_every_security_dimension_fails_closed(self):
        cases = (
            (evidence(observed_content_sha256="b" * 64), "binding_mismatch"),
            (evidence(integrity_status="failed"), "integrity_unverified"),
            (evidence(signature_status="unverified"), "signature_unverified"),
            (evidence(license_status="unapproved"), "license_unapproved"),
            (evidence(patch_status="stale"), "patch_status_unacceptable"),
        )
        for supplied, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(
                    reason,
                    evaluate_image_compatibility(requirement(), supplied, now_epoch=150.0).reason,
                )

    def test_requirement_is_strict_immutable_and_requires_signature(self):
        value = requirement()
        with self.assertRaises(FrozenInstanceError):
            value.image_revision = "changed"
        with self.assertRaisesRegex(ValueError, "signature policy"):
            requirement(signature_policy="optional")
        with self.assertRaisesRegex(ValueError, "guest profile"):
            requirement(guest_generation=1)
        with self.assertRaisesRegex(ValueError, "content_sha256"):
            requirement(content_sha256="not-a-digest")

    def test_evidence_lifetime_and_status_vocabulary_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "lifetime"):
            evidence(expires_at_epoch=4000.1)
        with self.assertRaisesRegex(ValueError, "signature status"):
            evidence(signature_status="trusted")
        with self.assertRaisesRegex(ValueError, "patch status"):
            evidence(patch_status="probably-current")

    def test_public_result_omits_image_and_signer_identity(self):
        result = evaluate_image_compatibility(requirement(), evidence(), now_epoch=150.0)
        public = repr(result.public_dict()).casefold()
        for forbidden in ("image_id", "sha256", "signer", "license", "path", "source"):
            self.assertNotIn(forbidden, public)


if __name__ == "__main__":
    unittest.main()
