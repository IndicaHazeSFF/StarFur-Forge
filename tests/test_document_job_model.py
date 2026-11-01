"""Pure local-model-listing contract tests; no service, filesystem, or network."""

import json
import socket
import unittest
from unittest import mock

from pipeline.document_job_model import (
    MAX_LOCAL_MODEL_LISTING_BYTES, DeclaredLocalModel, LocalModelInspectionError,
    inspect_ollama_local_model_listing,
)


def listing(*models):
    return json.dumps({"models": list(models)})


def model(name="qwen3:8b", digest="a" * 64, size=1):
    return {"name": name, "model": name, "digest": digest, "size": size, "details": {"format": "gguf"}}


class LocalModelListingContracts(unittest.TestCase):
    def setUp(self):
        guard = mock.patch.object(socket, "socket", side_effect=AssertionError("no network"))
        guard.start()
        self.addCleanup(guard.stop)

    def test_exact_gguf_listing_returns_bounded_declared_identity(self):
        result = inspect_ollama_local_model_listing(listing(model()), "qwen3:8b")
        self.assertEqual(result, DeclaredLocalModel("qwen3:8b", "a" * 64, 1, "gguf"))
        self.assertNotIn("qwen3:8b", repr(result))
        self.assertNotIn("a" * 64, repr(result))

    def test_selected_name_and_returned_model_must_be_exact_not_aliases(self):
        for changed in ({"name": "qwen3"}, {"model": "qwen3:8b-internal"}):
            item = model()
            item.update(changed)
            with self.subTest(changed=changed), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(listing(item), "qwen3:8b")

    def test_missing_duplicate_or_multiple_exact_matches_deny(self):
        for data in (listing(model("other")), listing(model(), model(digest="b" * 64))):
            with self.subTest(data=data), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(data, "qwen3:8b")

    def test_unknown_and_incomplete_shapes_fail_closed(self):
        cases = (
            '{"models": [], "extra": true}',
            listing({"name": "qwen3:8b", "model": "qwen3:8b", "digest": "a" * 64, "size": 1,
                     "details": {"format": "gguf", "unexpected": "qwen"}}),
            listing({"name": "qwen3:8b", "model": "qwen3:8b", "digest": "a" * 64, "size": 1,
                     "details": {}}),
        )
        for data in cases:
            with self.subTest(data=data), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(data, "qwen3:8b")

    def test_invalid_json_duplicate_keys_nonfinite_and_bounds_deny(self):
        cases = (
            '{"models":[],"models":[]}',
            '{"models":[{"name":"qwen3:8b","model":"qwen3:8b","digest":"' + "a" * 64
            + '","size":NaN,"details":{"format":"gguf"}}]}',
            b"x" * (MAX_LOCAL_MODEL_LISTING_BYTES + 1),
        )
        for data in cases:
            with self.subTest(data=type(data).__name__), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(data, "qwen3:8b")

    def test_declared_listing_never_becomes_execution_or_byte_proof(self):
        result = inspect_ollama_local_model_listing(listing(model()), "qwen3:8b")
        self.assertEqual(set(result.__dataclass_fields__), {"model", "digest", "byte_size", "format"})
        self.assertNotIn("verified", result.__dataclass_fields__)

    def test_documented_tags_metadata_is_accepted_but_not_retained(self):
        item = model()
        item["modified_at"] = "2025-05-10T08:06:48.639712648-07:00"
        item["details"].update(parent_model="", family="qwen2", families=["qwen2"],
                               parameter_size="8.0B", quantization_level="Q4_K_M")
        result = inspect_ollama_local_model_listing(listing(item), "qwen3:8b")
        self.assertEqual(result.digest, "a" * 64)
        self.assertNotIn("family", result.__dataclass_fields__)

    def test_encoding_and_deep_json_errors_are_content_free(self):
        for raw in ("\ud800", b"\xff", "[" * 1500 + "]" * 1500):
            with self.subTest(kind=type(raw).__name__), self.assertRaises(LocalModelInspectionError) as error:
                inspect_ollama_local_model_listing(raw, "qwen3:8b")
            self.assertEqual(str(error.exception), "local model listing is invalid")

    def test_optional_metadata_is_bounded_and_strictly_typed(self):
        for key, value in (("family", {}), ("families", "qwen"), ("families", ["q"] * 17),
                           ("families", [False]), ("quantization_level", "x" * 129)):
            item = model()
            item["details"][key] = value
            with self.subTest(key=key), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(listing(item), "qwen3:8b")

    def test_remote_metadata_is_not_silently_accepted(self):
        for key in ("remote_host", "remote_model"):
            item = model()
            item[key] = "remote.invalid"
            with self.subTest(key=key), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(listing(item), "qwen3:8b")

    def test_release_metadata_is_discarded_from_declared_identity(self):
        item = model()
        item["capabilities"] = ["completion", "tools", "thinking"]
        item["details"].update(context_length=32768, embedding_length=4096)
        self.assertEqual(inspect_ollama_local_model_listing(listing(item), "qwen3:8b"),
                         inspect_ollama_local_model_listing(listing(model()), "qwen3:8b"))

    def test_advisory_lengths_are_bounded_integers_not_authority(self):
        for field in ("context_length", "embedding_length"):
            for value in (False, -1, 1.5, "4096", None, 2 ** 31, {}):
                item = model()
                item["details"][field] = value
                with self.subTest(field=field, value=value), self.assertRaises(LocalModelInspectionError):
                    inspect_ollama_local_model_listing(listing(item), "qwen3:8b")
            for value in (0, 2 ** 31 - 1):
                item = model()
                item["details"][field] = value
                self.assertEqual(inspect_ollama_local_model_listing(listing(item), "qwen3:8b").digest, "a" * 64)

    def test_capability_labels_are_bounded_data(self):
        for value in (None, "completion", {}, [False], [["completion"]],
                      ["x"] * 17, ["x" * 65], ["\u00e9"], ["bad\nlabel"], [""]):
            item = model()
            item["capabilities"] = value
            with self.subTest(value=value), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(listing(item), "qwen3:8b")
        for value in ([], ["future_label"], ["x"] * 16):
            item = model()
            item["capabilities"] = value
            self.assertEqual(inspect_ollama_local_model_listing(listing(item), "qwen3:8b").format, "gguf")

    def test_release_metadata_does_not_hide_unknown_or_remote_fields(self):
        for key in ("remote_host", "remote_model", "verified", "consent"):
            item = model()
            item["capabilities"] = ["completion"]
            item[key] = True
            with self.subTest(key=key), self.assertRaises(LocalModelInspectionError):
                inspect_ollama_local_model_listing(listing(item), "qwen3:8b")
        unrelated = model("other")
        unrelated["capabilities"] = [False]
        with self.assertRaises(LocalModelInspectionError):
            inspect_ollama_local_model_listing(listing(model(), unrelated), "qwen3:8b")


if __name__ == "__main__":
    unittest.main()
