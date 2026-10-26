"""Ten bound-runtime/store integration gates; no live provider or real state."""

from dataclasses import replace
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tests.document_job_fixtures import (
    FakeAnnotationProvider, make_application, multi_chunk_text, proposal_response,
)
from pipeline.document_job_runtime import AnnotationJobRuntimeError, annotation_runtime_fingerprint
from pipeline.document_job_processor import AnnotationJobProcessor
from pipeline.document_job_store import AnnotationJobStore
from pipeline.providers import ChatCompletion, DisabledChatProvider
from pipeline.task_profiles import (
    TASK_ASSISTANT_CHAT, TASK_DOCUMENT_ANNOTATION, TASK_DOCUMENT_ANNOTATION_FALLBACK,
    TaskProfile, TaskProfiles,
)


class AnnotationRuntimeContracts(unittest.TestCase):
    def test_only_effective_annotation_routes_enter_fingerprint(self):
        primary = TaskProfile(TASK_DOCUMENT_ANNOTATION, provider="ollama", model="fixed", max_output_tokens=256)
        profiles = TaskProfiles({primary.task_id: primary})
        first = annotation_runtime_fingerprint(profiles, default_model="a", provider_id="Ollama")
        profiles.profiles[TASK_ASSISTANT_CHAT] = TaskProfile(TASK_ASSISTANT_CHAT, model="unrelated")
        self.assertEqual(first, annotation_runtime_fingerprint(profiles, default_model="b", provider_id="ollama"))
        primary.generation_options["temperature"] = 0.1
        self.assertNotEqual(first, annotation_runtime_fingerprint(profiles, default_model="a", provider_id="ollama"))

    def test_invalid_profile_and_fallback_metadata_fail_with_closed_message(self):
        for profile in (
            TaskProfile(TASK_DOCUMENT_ANNOTATION, fallback_task=TASK_ASSISTANT_CHAT),
            TaskProfile(TASK_DOCUMENT_ANNOTATION, fallback_task=TASK_DOCUMENT_ANNOTATION_FALLBACK),
            TaskProfile(TASK_DOCUMENT_ANNOTATION, provider="different"),
            TaskProfile(TASK_DOCUMENT_ANNOTATION, generation_options={"temperature": float("inf")}),
        ):
            with self.assertRaises(AnnotationJobRuntimeError) as error:
                annotation_runtime_fingerprint(TaskProfiles({profile.task_id: profile}),
                                               default_model="private-model", provider_id="ollama")
            self.assertNotIn("private-model", str(error.exception))


@unittest.skipUnless(os.name == "posix", "private store awaits native Windows support")
class AnnotationRuntimeSmokes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "jobs"
        self.root.mkdir(mode=0o700)
        self.now = datetime.now(UTC)
        self.store = AnnotationJobStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.app, self.session, self.provider = make_application()
        self.provider.response = proposal_response()
        self.job = self.store.submit(multi_chunk_text(), "fixture.md")
        self.document = self.store.read_source(self.job.job_id)
        self.assertGreater(len(self.document.chunks), 1)
        for target in ("pipeline.db.connect", "socket.socket"):
            guard = mock.patch(target, side_effect=AssertionError("no database/network"))
            guard.start()
            self.addCleanup(guard.stop)

    def processor(self):
        runtime = self.app.bind_annotation_job_runtime()
        return AnnotationJobProcessor(self.store, runtime), runtime

    def record(self):
        return json.loads((self.root / (self.job.job_id + ".json")).read_bytes())

    def profile(self, **changes):
        old = self.session.config.task_profiles.get(TASK_DOCUMENT_ANNOTATION)
        profiles = dict(self.session.config.task_profiles.profiles)
        profiles[TASK_DOCUMENT_ANNOTATION] = replace(old, **changes)
        self.session.config = replace(self.session.config, task_profiles=TaskProfiles(profiles))

    def test_01_binding_capture_is_passive_and_opaque(self):
        before = self.record()
        self.session.focus_mode_set(True)
        runtime = self.app.bind_annotation_job_runtime()
        self.assertNotIn("fixture-model", repr(runtime))
        self.assertNotIn("ollama", repr(runtime).lower())
        self.assertEqual(self.record(), before)
        self.assertEqual(self.provider.calls, [])
        self.assertEqual(self.provider.probes, 0)

    def test_02_bound_chunk_keeps_original_profile_and_checkpoint_provenance(self):
        processor, _ = self.processor()
        run = processor.start(self.job.job_id)
        self.assertEqual(processor.step(run).status, "checkpointed")
        self.assertEqual(self.provider.calls[0]["model"], "fixture-model")
        self.assertEqual(self.provider.calls[0]["options"]["num_predict"], 256)
        record = self.record()
        self.assertEqual(record["checkpoints"][0]["chunk_id"], self.document.chunks[0].chunk_id)
        self.assertEqual(len(record["checkpoints"]), 1)
        self.assertIsNone(record["result"])
        self.assertEqual(self.app._workload_gate.active_count("ollama"), 0)

    def test_03_active_model_drift_fences_attempt_without_provider_replay(self):
        processor, _ = self.processor()
        run = processor.start(self.job.job_id)
        self.session.active_model = "changed-model"
        outcome = processor.step(run)
        self.assertEqual((outcome.status, outcome.reason), ("failed", "runtime_binding_changed"))
        self.assertEqual(self.record()["state"], "interrupted")
        self.assertEqual(self.record()["checkpoints"], [])
        self.assertEqual(self.provider.calls, [])

    def test_04_mutable_options_and_budget_drift_are_detected_before_call(self):
        runtime = self.app.bind_annotation_job_runtime()
        profile = self.session.config.task_profiles.get(TASK_DOCUMENT_ANNOTATION)
        profile.generation_options["temperature"] = 0.5
        with self.assertRaises(AnnotationJobRuntimeError):
            runtime.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        for changes in ({"max_output_tokens": 512}, {"context_size": 2048},
                        {"model_thinking": False}, {"max_concurrent_requests": 2},
                        {"model_keep_alive_seconds": 0}, {"resource_profile": "interactive"}):
            runtime = self.app.bind_annotation_job_runtime()
            self.profile(**changes)
            with self.assertRaises(AnnotationJobRuntimeError):
                runtime.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        self.assertEqual(self.provider.calls, [])

    def test_05_fallback_profile_changes_cannot_hide_behind_same_primary(self):
        self.profile(fallback_task=TASK_DOCUMENT_ANNOTATION_FALLBACK)
        profiles = self.session.config.task_profiles.profiles
        profiles[TASK_DOCUMENT_ANNOTATION_FALLBACK] = TaskProfile(
            TASK_DOCUMENT_ANNOTATION_FALLBACK, provider="ollama", model="fallback-a", max_output_tokens=256)
        runtime = self.app.bind_annotation_job_runtime()
        profiles[TASK_DOCUMENT_ANNOTATION_FALLBACK] = replace(profiles[TASK_DOCUMENT_ANNOTATION_FALLBACK], model="fallback-b")
        with self.assertRaises(AnnotationJobRuntimeError):
            runtime.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        self.assertEqual(self.provider.calls, [])

    def test_06_same_label_provider_replacement_and_disabled_provider_refuse(self):
        runtime = self.app.bind_annotation_job_runtime()
        replacement = FakeAnnotationProvider()
        self.session.provider = replacement
        with self.assertRaises(AnnotationJobRuntimeError):
            runtime.annotate_document_chunk(self.document, self.document.chunks[0].chunk_id)
        self.session.provider = DisabledChatProvider()
        with self.assertRaises(AnnotationJobRuntimeError):
            self.app.bind_annotation_job_runtime()
        self.assertEqual(replacement.calls, [])
        self.assertEqual(self.provider.calls, [])

    def test_07_focus_and_capacity_are_rechecked_without_invalidating_binding(self):
        processor, _ = self.processor()
        run = processor.start(self.job.job_id)
        self.session.focus_mode_set(True)
        self.assertEqual(processor.step(run).reason, "focus_mode")
        self.session.focus_mode_set(False)
        lease = self.app._workload_gate.try_acquire("ollama", 1).lease
        try:
            self.assertEqual(processor.step(run).reason, "provider_capacity_busy")
            self.assertEqual(self.provider.calls, [])
        finally:
            self.app._workload_gate.release(lease)
        self.assertEqual(processor.step(run).status, "checkpointed")
        self.assertEqual(len(self.provider.calls), 1)

    def test_08_reentrant_config_change_discards_late_output_and_releases_capacity(self):
        processor, _ = self.processor()
        run = processor.start(self.job.job_id)
        def change_during_call():
            self.profile(max_output_tokens=512)
            return ChatCompletion(json.dumps(proposal_response()), "stop")
        self.provider.hook = change_during_call
        outcome = processor.step(run)
        self.assertEqual(outcome.reason, "runtime_binding_changed")
        self.assertEqual(self.record()["checkpoints"], [])
        self.assertEqual(self.record()["state"], "interrupted")
        self.assertEqual(self.app._workload_gate.active_count("ollama"), 0)
        self.assertEqual(len(self.provider.calls), 1)

    def test_09_explicit_new_attempt_rebinds_without_redoing_saved_chunks(self):
        processor, _ = self.processor()
        run = processor.start(self.job.job_id)
        self.assertEqual(processor.step(run).status, "checkpointed")
        saved = self.record()["checkpoints"][0]
        self.session.active_model = "fresh-model"
        self.assertEqual(processor.step(run).reason, "runtime_binding_changed")
        self.store.resume(self.job.job_id)  # trusted explicit intent, never automatic
        fresh, _ = self.processor()
        run = fresh.start(self.job.job_id)
        for _ in self.document.chunks[1:]:
            self.assertEqual(fresh.step(run).status, "checkpointed")
        self.assertEqual(fresh.finish(run).status, "completed")
        self.assertEqual(self.record()["checkpoints"][0], saved)
        self.assertEqual(len(self.provider.calls), len(self.document.chunks))
        self.assertEqual(self.provider.calls[-1]["model"], "fresh-model")
        self.assertEqual(self.store.status(self.job.job_id).metadata.expires_at, self.job.metadata.expires_at)

    def test_10_ctrl_c_through_bound_runtime_preserves_prior_work(self):
        processor, _ = self.processor()
        run = processor.start(self.job.job_id)
        self.assertEqual(processor.step(run).status, "checkpointed")
        saved = self.record()["checkpoints"]
        def interrupted():
            raise KeyboardInterrupt
        self.provider.hook = interrupted
        with self.assertRaises(KeyboardInterrupt):
            processor.step(run)
        self.assertEqual(self.record()["checkpoints"], saved)
        self.assertEqual(self.record()["state"], "interrupted")
        self.assertIsNone(self.record()["result"])
        self.assertEqual(self.app._workload_gate.active_count("ollama"), 0)


if __name__ == "__main__":
    unittest.main()
