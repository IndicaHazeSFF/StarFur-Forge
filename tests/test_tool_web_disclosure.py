from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_web_disclosure import (
    MAX_WEB_DISCLOSURE_BYTES,
    WebDisclosureIntent,
    evaluate_web_disclosure,
)


DIGEST = "a" * 64


class ToolWebDisclosureTests(unittest.TestCase):
    def test_no_data_and_core_classified_public_data_are_policy_permitted(self):
        empty = WebDisclosureIntent(1, "none", "none", 0, None)
        public = WebDisclosureIntent(1, "public", "user_supplied", 12, DIGEST)
        self.assertEqual("no_disclosure", evaluate_web_disclosure(empty).reason)
        self.assertEqual("public_disclosure", evaluate_web_disclosure(public).reason)
        self.assertTrue(evaluate_web_disclosure(public).permitted)

    def test_private_and_secret_data_have_no_initial_permission_path(self):
        private = WebDisclosureIntent(1, "private", "private_resource", 12, DIGEST)
        secret = WebDisclosureIntent(1, "secret", "secret_store", 12, DIGEST)
        self.assertEqual("private_disclosure_unsupported", evaluate_web_disclosure(private).reason)
        self.assertEqual("secret_disclosure_forbidden", evaluate_web_disclosure(secret).reason)
        self.assertFalse(evaluate_web_disclosure(private).permitted)
        self.assertFalse(evaluate_web_disclosure(secret).permitted)

    def test_empty_and_content_metadata_must_be_consistent(self):
        invalid = (
            ("none", "none", 1, None),
            ("none", "user_supplied", 0, None),
            ("public", "none", 1, DIGEST),
            ("public", "user_supplied", 0, DIGEST),
            ("public", "user_supplied", 1, None),
            ("public", "user_supplied", 1, "A" * 64),
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                WebDisclosureIntent(1, *values)

    def test_sensitive_source_kinds_cannot_be_downgraded(self):
        with self.assertRaisesRegex(ValueError, "private-resource"):
            WebDisclosureIntent(1, "public", "private_resource", 1, DIGEST)
        with self.assertRaisesRegex(ValueError, "secret-store"):
            WebDisclosureIntent(1, "private", "secret_store", 1, DIGEST)

    def test_byte_count_is_bounded_and_rejects_boolean(self):
        for count in (True, -1, MAX_WEB_DISCLOSURE_BYTES + 1):
            with self.subTest(count=count), self.assertRaises(ValueError):
                WebDisclosureIntent(1, "public", "core_public", count, DIGEST)

    def test_contracts_are_immutable_content_free_and_not_authority(self):
        intent = WebDisclosureIntent(1, "public", "core_public", 4, DIGEST)
        with self.assertRaises(FrozenInstanceError):
            intent.classification = "private"
        rendered = repr(intent).casefold()
        for forbidden in ("raw_content", "grant", "approval", "principal", "provider"):
            self.assertNotIn(forbidden, rendered)
        with self.assertRaises(TypeError):
            evaluate_web_disclosure({})


if __name__ == "__main__":
    unittest.main()
