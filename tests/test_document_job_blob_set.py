"""Whole-set budgets over disposable synthetic artifacts; no provider."""
import os
import tempfile
from pathlib import Path
from hashlib import sha256
import unittest
from unittest.mock import patch

from pipeline.document_job_manifest import ManifestBlobDescriptor, ParsedModelManifest, CONFIG_MEDIA, MODEL_MEDIA
from pipeline.document_job_blob_measurement import measure_blob, measure_blob_set, BlobMeasurementError


@unittest.skipUnless(os.name == "posix", "POSIX handles required")
class BlobSetTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, self.fd)
        self.descriptors = []
        for media, data in ((CONFIG_MEDIA, b"synthetic config"), (MODEL_MEDIA, b"synthetic weights")):
            digest = sha256(data).hexdigest()
            self.descriptors.append(ManifestBlobDescriptor(media, "sha256:"+digest, len(data)))
            (self.root / ("sha256-"+digest)).write_bytes(data)
        self.manifest = ParsedModelManifest("a"*64, self.descriptors[0],
                                           (self.descriptors[1],), sum(d.size for d in self.descriptors))
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start(); self.addCleanup(guard.stop)

    def run_set(self, **changes):
        args = dict(expected_uid=os.getuid(), max_bytes=self.manifest.declared_total, timeout_seconds=2)
        args.update(changes)
        return measure_blob_set(self.fd, self.manifest, **args)

    def test_ordered_hashes_and_original_handle_survives(self):
        self.assertEqual(self.run_set(), tuple(d.digest[7:] for d in self.descriptors))
        os.fstat(self.fd)

    def test_budget_denies_before_file_access(self):
        with patch("pipeline.document_job_blob_measurement.os.dup", side_effect=AssertionError("no open")):
            with self.assertRaises(BlobMeasurementError):
                self.run_set(max_bytes=self.manifest.declared_total-1)

    def test_changed_earlier_blob_after_later_measurement_denies(self):
        def changed(directory, descriptor, **args):
            result = measure_blob(directory, descriptor, **args)
            if descriptor == self.descriptors[1]:
                first = self.root / self.descriptors[0].digest.replace(":", "-")
                first.write_bytes(b"x"*self.descriptors[0].size)
            return result
        with patch("pipeline.document_job_blob_measurement.measure_blob", side_effect=changed):
            with self.assertRaises(BlobMeasurementError): self.run_set()

    def test_shared_deadline_is_not_reset_per_blob(self):
        clock = [0.0]
        calls = []
        def spent(directory, descriptor, **args):
            calls.append(args["timeout_seconds"])
            clock[0] += 1.25
            return descriptor.digest[7:]
        with patch("pipeline.document_job_blob_measurement.measure_blob", side_effect=spent):
            with self.assertRaises(BlobMeasurementError): self.run_set(_clock=lambda: clock[0])
        self.assertEqual(calls, [2, .75])

    def test_missing_or_linked_member_and_invalid_clock_deny(self):
        self.assertEqual(len(self.run_set()), 2)
        last = self.root / self.descriptors[1].digest.replace(":", "-")
        last.unlink(); last.symlink_to("missing")
        with self.assertRaises(BlobMeasurementError): self.run_set()
        with self.assertRaises(BlobMeasurementError): self.run_set(_clock=lambda: float("nan"))

    def test_interruption_closes_group_handle(self):
        with patch("pipeline.document_job_blob_measurement.measure_blob", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.run_set()
        os.fstat(self.fd)
