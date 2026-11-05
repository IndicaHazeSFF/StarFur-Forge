"""Pure synthetic config bytes; no filesystem, provider or network."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch

from pipeline.document_job_manifest import ParsedModelManifest, ManifestBlobDescriptor, CONFIG_MEDIA, MODEL_MEDIA
from pipeline.document_job_config import decode_model_config, ModelConfigError


def fixture():
    return dict(model_format="gguf", model_family="qwen3", model_families=["qwen3"],
                model_type="8.2B", file_type="Q4_K_M", architecture="amd64", os="linux",
                rootfs=dict(type="layers", diff_ids=["sha256:"+"b"*64]))


def bind(raw):
    config = ManifestBlobDescriptor(CONFIG_MEDIA, "sha256:"+sha256(raw).hexdigest(), len(raw))
    model = ManifestBlobDescriptor(MODEL_MEDIA, "sha256:"+"b"*64, 1)
    return ParsedModelManifest("a"*64, config, (model,), config.size+model.size)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket", "builtins.open"):
            guard = patch(target, side_effect=AssertionError("no I/O"))
            guard.start(); self.addCleanup(guard.stop)

    def deny_raw(self, raw):
        with self.assertRaises(ModelConfigError) as error: decode_model_config(raw, bind(raw))
        self.assertEqual(str(error.exception), "model config is invalid")

    def deny(self, value): self.deny_raw(json.dumps(value).encode())

    def test_valid_immutable_redacted_metadata(self):
        raw = json.dumps(fixture()).encode(); result = decode_model_config(raw, bind(raw))
        self.assertEqual(result.family, "qwen3")
        self.assertEqual(result.raw_bytes_sha256, sha256(raw).hexdigest())
        self.assertNotIn("qwen3", repr(result))
        self.assertFalse(hasattr(result, "local_execution_verified"))
        with self.assertRaises(FrozenInstanceError): result.family = "other"
        with self.assertRaises(ModelConfigError): replace(result, families=("other",))

    def test_hash_size_and_layer_binding(self):
        raw = json.dumps(fixture()).encode(); manifest = bind(raw)
        for wrong in (raw+b" ", raw.replace(b"8.2B", b"9.2B")):
            with self.assertRaises(ModelConfigError): decode_model_config(wrong, manifest)
        v = fixture(); v["rootfs"]["diff_ids"] = ["sha256:"+"c"*64]; self.deny(v)
        v = fixture(); v["rootfs"]["diff_ids"] *= 2; self.deny(v)

    def test_remote_draft_and_optional_extensions_deny_even_empty(self):
        for key in ("remote_host", "remote_model", "draft", "renderer", "parser", "requires",
                    "capabilities", "context_length", "embedding_length", "base_name", "unknown"):
            for value in ("", None, {}, [], "https://example.com"):
                v = fixture(); v[key] = value; self.deny(v)

    def test_strict_required_fields_and_labels(self):
        for key in fixture():
            v = fixture(); del v[key]; self.deny(v)
        for key in ("model_format", "architecture", "os", "model_family", "model_type", "file_type"):
            for value in (None, True, [], {}, "", "x"*65, "bad/path", "\ud800"):
                v = fixture(); v[key] = value; self.deny(v)
        for families in ([], None, "qwen3", ["other"], ["qwen3"]*2, ["qwen3", 1]):
            v = fixture(); v["model_families"] = families; self.deny(v)

    def test_json_encoding_duplicates_nonfinite_and_recursion(self):
        for raw in (b"{}", b"\xff\xff", b"[]", b'{"a":1,"a":2}', b'{"a":NaN}',
                    b"["*1100+b"0"+b"]"*1100, json.dumps(fixture()).encode()+b"{}"):
            self.deny_raw(raw)
        raw = b"x"*65537
        with self.assertRaises(ModelConfigError): decode_model_config(raw, bind(b"{}"))

    def test_rootfs_schema_and_direct_output_validation(self):
        for root in (None, [], {"type":"layers", "diff_ids":[]},
                     {"type":"layers", "diff_ids":["sha256:"+"b"*64], "extra":1}):
            v = fixture(); v["rootfs"] = root; self.deny(v)
        raw = json.dumps(fixture()).encode(); result = decode_model_config(raw, bind(raw))
        with self.assertRaises(ModelConfigError): replace(result, layer_digests=("bad",))
