"""Synthetic manifest contracts; no actual sockets, model files or services."""
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from pipeline.document_job_manifest import (
    CONFIG_MEDIA, MODEL_MEDIA, ROOT_MEDIA, MAX_BLOB_BYTES, MAX_MANIFEST_BYTES,
    MAX_TOTAL_BYTES, ManifestBlobDescriptor, ManifestDecodeError, decode_model_manifest,
)


def blob(media, digit, size=1):
    return dict(mediaType=media, digest="sha256:" + digit * 64, size=size)


def fixture():
    return dict(schemaVersion=2, mediaType=ROOT_MEDIA, config=blob(CONFIG_MEDIA, "a"), layers=[blob(MODEL_MEDIA, "b")])


def encode(value):
    return json.dumps(value).encode()


class ManifestTests(unittest.TestCase):
    def setUp(self):
        g = patch("socket.socket", side_effect=AssertionError("no network"))
        g.start(); self.addCleanup(g.stop)

    def deny(self, raw):
        with self.assertRaises(ManifestDecodeError) as error:
            decode_model_manifest(raw)
        self.assertEqual(str(error.exception), "model manifest is invalid")

    def test_valid_order_and_whitespace_hash_are_separate_from_descriptors(self):
        value = fixture(); value["layers"].append(blob("application/vnd.ollama.image.params", "c"))
        raw = encode(value); first = decode_model_manifest(raw); second = decode_model_manifest(raw + b"\n")
        self.assertEqual(first.raw_bytes_sha256, sha256(raw).hexdigest())
        self.assertNotEqual(first.raw_bytes_sha256, second.raw_bytes_sha256)
        self.assertEqual(first.layers, second.layers)
        self.assertEqual(first.layers[1].digest, "sha256:" + "c" * 64)
        self.assertEqual(first.declared_total, 3)

    def test_immutable_redacted_and_direct_construction_validated(self):
        value = decode_model_manifest(encode(fixture()))
        with self.assertRaises(FrozenInstanceError): value.declared_total = 9
        for obj in (value, value.config, value.layers[0]): self.assertNotIn("sha256", repr(obj))
        for fields in (dict(declared_total=True), dict(layers=list(value.layers)), dict(raw_bytes_sha256="bad"),
                       dict(config=value.layers[0]), dict(declared_total=99), dict(layers=(value.layers[0],)*2)):
            with self.assertRaises(ManifestDecodeError): replace(value, **fields)
        with self.assertRaises(ManifestDecodeError): ManifestBlobDescriptor(CONFIG_MEDIA, "sha256:"+"a"*64, 65537)

    def test_root_keys_schema_media_and_layer_counts(self):
        for key, item in (("schemaVersion", True), ("schemaVersion", 3), ("mediaType", "other"),
                          ("layers", []), ("layers", {}), ("layers", [blob(MODEL_MEDIA,"b")]*17), ("remote_host", "private")):
            value=fixture(); value[key]=item; self.deny(encode(value))
        value=fixture(); del value["config"]; self.deny(encode(value))

    def test_descriptor_fields_types_and_bounds(self):
        for key, item in (("from", "remote"), ("name", "private"), ("size", False), ("size", 0),
                          ("size", MAX_BLOB_BYTES+1), ("size", 1.5), ("digest", "sha256:"+"A"*64),
                          ("mediaType", "application/vnd.ollama.image.projector")):
            value=fixture(); value["layers"][0][key]=item; self.deny(encode(value))
        value=fixture(); value["config"]["size"]=65537; self.deny(encode(value))

    def test_unique_digests_exactly_one_model_and_aggregate_limit(self):
        for layers in ([blob("application/vnd.ollama.image.params","b")],
                       [blob(MODEL_MEDIA,"b"),blob(MODEL_MEDIA,"c")],
                       [blob(MODEL_MEDIA,"a")]):
            value=fixture(); value["layers"]=layers; self.deny(encode(value))
        value=fixture(); value["layers"]=[blob(MODEL_MEDIA,"b",MAX_BLOB_BYTES),blob("application/vnd.ollama.image.params","c",MAX_BLOB_BYTES)]
        self.deny(encode(value))
        value["layers"][1]["size"]-=1
        self.assertEqual(decode_model_manifest(encode(value)).declared_total,MAX_TOTAL_BYTES)

    def test_raw_byte_and_json_failures(self):
        for raw in (None, "{}", b"\xff", b"x"*(MAX_MANIFEST_BYTES+1), b'{"x":NaN}',
                    b'{"x":1,"x":2}', b"["*1500+b"]"*1500, encode(fixture())+b" {}"):
            self.deny(raw)
        raw=encode(fixture()); self.assertIsNotNone(decode_model_manifest(raw+b" "*(MAX_MANIFEST_BYTES-len(raw))))

    def test_output_never_contains_evidence_or_policy_authority(self):
        value=decode_model_manifest(encode(fixture()))
        self.assertEqual(set(value.__dataclass_fields__), {"raw_bytes_sha256","config","layers","declared_total"})
