"""Test-only fake application adapters; no live provider or production state."""

import json
from pathlib import Path
import sys
import types

sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication
from pipeline.assistant import AssistantConfig, AssistantSession
from pipeline.providers import ChatCompletion
from pipeline.task_profiles import TASK_DOCUMENT_ANNOTATION, TaskProfile, TaskProfiles


class FakeAnnotationProvider:
    name = "Ollama"

    def __init__(self):
        self.calls = []
        self.probes = 0
        self.response = {"proposals": []}
        self.hook = None

    def complete(self, messages, *, model=None, options=None, stream=False):
        self.calls.append({"messages": tuple(dict(item) for item in messages),
                           "model": model, "options": dict(options or {})})
        if self.hook is not None:
            return self.hook()
        return ChatCompletion(json.dumps(self.response), "stop")

    def list_models(self):
        self.probes += 1
        raise AssertionError("no model probe")

    def probe_health(self):
        self.probes += 1
        raise AssertionError("no provider probe")


def make_application(provider=None):
    provider = provider if provider is not None else FakeAnnotationProvider()
    profiles = TaskProfiles({TASK_DOCUMENT_ANNOTATION: TaskProfile(
        TASK_DOCUMENT_ANNOTATION, provider="ollama", resource_profile="background",
        generation_options={"temperature": 0.0}, max_output_tokens=256,
    )})
    config = AssistantConfig("fixture-model", Path("persona/default.md"),
                             Path("config/assistant_policy.md"), "personal", 4, 0,
                             "off", "off", {}, profiles)
    session = AssistantSession(config, "Fixture persona", policy="Fixture policy",
                               provider=provider, memory_loader=lambda **_kwargs: [])
    def forbidden_write(*_args, **_kwargs):
        raise AssertionError("no canonical proposal write")
    return AssistantApplication(session, proposal_creator=forbidden_write), session, provider


def proposal_response():
    return {"proposals": [{
        "store": True, "subject": "Fixture person", "memory_type": "preference",
        "summary": "Prefers tea", "details": None,
        "importance": 0.5, "confidence": 0.9, "retention": "long_term",
    }]}


def multi_chunk_text():
    return "## First\n\n" + "Alpha. " * 220 + "\n\n## Second\n\n" + "Beta. " * 220
