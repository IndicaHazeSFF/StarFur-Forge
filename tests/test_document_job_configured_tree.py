"""Config decode integrated with synthetic anchored measurement; no readiness."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_document_job_config_file import config_fixture, MODEL_BYTES
from pipeline.document_job_manifest import ROOT_MEDIA
from pipeline.document_job_artifact_tree import inspect_model_tree_config, measure_model_tree, ArtifactTreeError
from pipeline.document_job_config_file import read_model_config


@unittest.skipUnless(os.name == "posix", "POSIX handles required")
class ConfiguredTreeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.anchor = Path(temp.name)
        self.blobs = self.anchor / "models/blobs"; self.blobs.mkdir(parents=True)
        self.directory = self.anchor / "models/manifests/registry.ollama.ai/library/test"
        self.directory.mkdir(parents=True)
        self.raw, self.manifest = config_fixture(); self.write_fixture()
        self.fd = os.open(self.anchor, os.O_RDONLY | os.O_DIRECTORY); self.addCleanup(os.close, self.fd)
        guard = patch("socket.socket", side_effect=AssertionError("no network"))
        guard.start(); self.addCleanup(guard.stop)

    def write_fixture(self):
        def blob(item): return dict(mediaType=item.media_type, digest=item.digest, size=item.size)
        for descriptor, data in ((self.manifest.config,self.raw),(self.manifest.layers[0],MODEL_BYTES)):
            (self.blobs / descriptor.digest.replace(":", "-")).write_bytes(data)
        (self.directory / "v1").write_text(json.dumps(dict(schemaVersion=2,mediaType=ROOT_MEDIA,
            config=blob(self.manifest.config),layers=[blob(self.manifest.layers[0])])), encoding="utf-8")

    def run_tree(self, function=inspect_model_tree_config, **changes):
        args = dict(expected_uid=os.getuid(), max_bytes=1000, timeout_seconds=2); args.update(changes)
        return function(self.fd,("models",),"test:v1",**args)

    def test_explicit_config_inspection_and_legacy_measurement(self):
        parsed, hashes, metadata = self.run_tree()
        self.assertEqual(metadata.raw_bytes_sha256, parsed.config.digest[7:])
        self.assertEqual(len(hashes),2); self.assertEqual(len(self.run_tree(measure_model_tree)),2)
        self.assertFalse(hasattr(metadata,"local_execution_verified"))

    def test_hash_correct_remote_config_denies_only_explicit_inspection(self):
        self.raw,self.manifest=config_fixture({"remote_host":""}); self.write_fixture()
        self.assertEqual(len(self.run_tree(measure_model_tree)),2)
        with self.assertRaises(ArtifactTreeError): self.run_tree()

    def test_identical_config_replacement_during_work_denies(self):
        calls=[]
        def replaced(*args,**kw):
            value=read_model_config(*args,**kw); calls.append(1)
            if len(calls)==1:
                path=self.blobs/self.manifest.config.digest.replace(":","-")
                path.rename(self.blobs/"old"); path.write_bytes(self.raw)
            return value
        with patch("pipeline.document_job_artifact_tree.read_model_config",side_effect=replaced):
            with self.assertRaises(ArtifactTreeError): self.run_tree()

    def test_budget_and_post_config_deadline_denials(self):
        with patch("pipeline.document_job_artifact_tree.read_model_config",side_effect=AssertionError("no config read")):
            with self.assertRaises(ArtifactTreeError): self.run_tree(max_bytes=1)
        clock=[0]
        def slow(*args,**kw):
            value=read_model_config(*args,**kw); clock[0]=3; return value
        with patch("pipeline.document_job_artifact_tree.read_model_config",side_effect=slow):
            with self.assertRaises(ArtifactTreeError): self.run_tree(_clock=lambda:clock[0])
