"""Synthetic disk-manifest -> descriptor-set measurement acceptance fence."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch

from pipeline.document_job_manifest import ROOT_MEDIA, CONFIG_MEDIA, MODEL_MEDIA
from pipeline.document_job_manifest_file import read_manifest_file
from pipeline.document_job_blob_measurement import measure_blob_set, BlobMeasurementError


@unittest.skipUnless(os.name == "posix", "POSIX handles required")
class ArtifactFlowTests(unittest.TestCase):
    def test_manifest_to_measured_blobs_and_missing_member_denial(self):
        with tempfile.TemporaryDirectory() as temp, patch("socket.socket", side_effect=AssertionError("no network")):
            root = Path(temp); blobs = root / "blobs"; manifests = root / "manifests"
            blobs.mkdir(mode=0o700); manifests.mkdir(mode=0o700)
            entries = []
            for media, data in ((CONFIG_MEDIA, b"uninterpreted synthetic config"), (MODEL_MEDIA, b"synthetic model")):
                digest = sha256(data).hexdigest()
                (blobs / ("sha256-"+digest)).write_bytes(data)
                entries.append(dict(mediaType=media, digest="sha256:"+digest, size=len(data)))
            payload = dict(schemaVersion=2, mediaType=ROOT_MEDIA, config=entries[0], layers=[entries[1]])
            raw = json.dumps(payload).encode(); (manifests / "tag").write_bytes(raw)
            m = os.open(manifests, os.O_RDONLY | os.O_DIRECTORY)
            try:
                b = os.open(blobs, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    parsed = read_manifest_file(m, "tag", expected_uid=os.getuid(), timeout_seconds=2)
                    hashes = measure_blob_set(b, parsed, expected_uid=os.getuid(), max_bytes=1000, timeout_seconds=2)
                    self.assertEqual(hashes, tuple(e["digest"][7:] for e in entries))
                    self.assertEqual(parsed.raw_bytes_sha256, sha256(raw).hexdigest())
                    # Measured config bytes are deliberately not treated as
                    # parsed local-only config, readiness or authority.
                    self.assertFalse(hasattr(parsed, "local_execution_verified"))
                    (blobs / entries[1]["digest"].replace(":", "-")).unlink()
                    with self.assertRaises(BlobMeasurementError):
                        measure_blob_set(b, parsed, expected_uid=os.getuid(), max_bytes=1000, timeout_seconds=2)
                finally: os.close(b)
            finally: os.close(m)
