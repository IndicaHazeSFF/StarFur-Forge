import json
import sys
import re
import threading
import time
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.application import AssistantApplication, ConversationNotFoundError, create_assistant_application
from pipeline.document_intake import DocumentAnnotationExecution, prepare_document_text
from pipeline.persona_registry import PersonaRegistry, load_persona_package
from pipeline.provider_registry import ChatProviderRegistration, ChatProviderRegistry
from pipeline.research_disclosure import ResearchProviderTarget
from pipeline.research_provider import LocalResearchClaimProvider, LocalResearchRelationshipProvider
from pipeline.sandbox_execution_status import SandboxExecutionStatus
from pipeline.system_metrics import SystemMetricsSnapshot
from pipeline.task_profiles import TaskProfile, TaskProfiles
from pipeline.tool_web_connector import WebDecodedChunk, WebFetchSupervisor, WebTransportResponse
from pipeline.tool_web_native import (
    NativeWebResolver,
    NativeWebToolRuntime,
    SessionWebPrerequisiteStore,
    SessionWebQuarantineStore,
)
from pipeline.tool_web_response import WebResponseMetadata
from pipeline.tool_web_search import SessionWebSearchArtifactStore, WebSearchCandidate
from pipeline.tool_web_search_connector import WebSearchResponse, WebSearchSupervisor
from pipeline.tool_web_search_preflight import (
    WEB_SEARCH_PREFLIGHT_POLICY_REVISION, WebSearchServicePrerequisite,
)
from pipeline.tool_web_search_runtime import (
    LocalWebSearchRuntime, SessionWebSearchPrerequisiteStore,
)


class FakeConfig:
    chat_model = "fake:latest"
    persona_path = Path("persona.md")
    policy_path = Path("policy.md")


class FakeSession:
    def __init__(self, config=None, *args, **kwargs):
        self.config = config or FakeConfig()
        self.active_model = "fake:latest"
        self.stream = False
        self.stream_writer = None
        self.calls = []
        self.messages = []
        self.last_memory_ids = []
        self.pending_bulk_approval = None

    def respond(self, text):
        self.calls.append((text, self.stream))
        self.messages.append({"role": "user", "content": text})
        if self.stream and self.stream_writer:
            self.stream_writer("chunk")
        return "answer"

    def context_stats(self):
        return "stats"


class ResearchSession(FakeSession):
    def __init__(self, *, malformed=False, two_claims=False):
        super().__init__()
        self.research_calls = []
        self.relationship_calls = []
        self.malformed = malformed
        self.two_claims = two_claims

    def local_research_claim_provider(self):
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")

        def complete(messages, model, schema):
            self.research_calls.append((messages, model, schema))
            if self.malformed:
                return {"message": {"content": "not json"}}
            packet = json.loads(messages[1]["content"].split("\n", 1)[1])
            claims = [{
                "claim_id": "RC-001",
                "statement": "The fixture is bounded public text.",
                "source_ids": [packet["sources"][0]["source_id"]],
                "confidence": 0.9,
            }]
            if self.two_claims:
                claims.append({
                    "claim_id": "RC-002",
                    "statement": "The fixture has an exact digest binding.",
                    "source_ids": [packet["sources"][0]["source_id"]],
                    "confidence": 0.8,
                })
            return {"message": {"content": json.dumps({
                "schema_version": 1,
                "packet_sha256": packet["packet_sha256"],
                "claims": claims,
            })}}

        return LocalResearchClaimProvider(target, complete)

    def local_research_relationship_provider(self):
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")

        def complete(messages, model, schema):
            self.relationship_calls.append((messages, model, schema))
            review = json.loads(messages[1]["content"].split("\n", 1)[1])
            return {"message": {"content": json.dumps({
                "schema_version": 1,
                "review_id": review["review_id"],
                "packet_sha256": review["packet_sha256"],
                "relationships": [{
                    "relationship_id": "RL-001",
                    "left_claim_id": "RC-001",
                    "right_claim_id": "RC-002",
                    "relation": "related_only",
                    "confidence": 0.8,
                }],
            })}}

        return LocalResearchRelationshipProvider(target, complete)


class FailingSession(FakeSession):
    def respond(self, text):
        self.calls.append((text, self.stream))
        raise RuntimeError("expected failure")


class BlockingSession(FakeSession):
    def __init__(self, started, release, config=None):
        super().__init__(config=config)
        self.started = started
        self.release = release

    def respond(self, text):
        self.calls.append((text, self.stream))
        self.started.set()
        if not self.release.wait(2):
            raise RuntimeError("test response was not released")
        self.messages.append({"role": "user", "content": text})
        return "answer"


class SequentialBlockingSession(FakeSession):
    def __init__(self, started_events, release_events, config=None):
        super().__init__(config=config)
        self.started_events = started_events
        self.release_events = release_events
        self._call_lock = threading.Lock()

    def respond(self, text):
        with self._call_lock:
            index = len(self.calls)
            self.calls.append((text, self.stream))
        self.started_events[index].set()
        if not self.release_events[index].wait(2):
            raise RuntimeError("test response was not released")
        self.messages.append({"role": "user", "content": text})
        return "answer"


class HealthyProvider:
    name = "healthy fake"

    def __init__(self):
        self.probe_calls = 0

    def probe_health(self):
        self.probe_calls += 1
        return {"models": [{"name": "one"}, {"name": "two"}]}


class UnavailableProvider:
    name = "unavailable fake"

    def probe_health(self):
        raise RuntimeError("provider is offline")


class FakeWebTransport:
    available = True

    def fetch(self, request, cancellation):
        body = b"bounded public fixture"
        return WebTransportResponse(
            1,
            request.invocation_id,
            request.binding_fingerprint,
            request.worker_generation,
            request.selected_address,
            WebResponseMetadata(1, 200, "text/plain", "identity", len(body)),
            (WebDecodedChunk(body, len(body)),),
        )

    def request_cancel(self, request):
        return None


class AssistantApplicationTests(unittest.TestCase):
    def test_tool_namespace_is_reserved_and_shared_chat_cannot_control_it(self):
        session = ResearchSession()
        app = AssistantApplication(session)

        result = app.respond("tool approve TI-forged")

        self.assertIn("unavailable through shared chat/API", result)
        self.assertEqual([], session.calls)

    def test_malformed_local_tool_command_never_reaches_model_generation(self):
        session = FakeSession()
        app = AssistantApplication(session)

        result = app.respond("tool approve yes please", trusted_local_control=True)

        self.assertIn("Unknown or malformed local tool command", result)
        self.assertEqual([], session.calls)

    def test_local_tool_authority_is_isolated_and_lost_with_session_eviction(self):
        sessions = []

        def factory():
            created = FakeSession()
            sessions.append(created)
            return created

        app = AssistantApplication(FakeSession(), session_factory=factory, max_conversations=1)
        created = app.respond(
            'tool propose sandbox.run {"task_kind":"python_tests","objective":"one",'
            '"files":[{"path":"main.py","content":"pass"}]}',
            conversation_id="tool-a", trusted_local_control=True,
        )
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)

        other = app.respond("tool list", conversation_id="tool-b", trusted_local_control=True)
        recreated = app.respond(
            f"tool status {request_id}", conversation_id="tool-a", trusted_local_control=True,
        )

        self.assertIn("No local tool requests", other)
        self.assertIn("not found in this local session", recreated)
        self.assertEqual(3, len(sessions))

    def test_trusted_local_cli_can_preview_grant_and_approve_inert_request(self):
        session = FakeSession()
        app = AssistantApplication(session)
        command = (
            'tool propose sandbox.run {"task_kind":"python_tests",'
            '"objective":"Run a harmless fixture.",'
            '"files":[{"path":"main.py","content":"print(1)"}]}'
        )

        created = app.respond(command, trusted_local_control=True)
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)
        preview = app.respond(f"tool preview {request_id}", trusted_local_control=True)
        granted = app.respond(f"tool grant {request_id}", trusted_local_control=True)
        approved = app.respond(f"tool approve {request_id}", trusted_local_control=True)
        status = app.respond(f"tool status {request_id}", trusted_local_control=True)

        self.assertIn("No files were created", created)
        self.assertIn("main.py", preview)
        self.assertNotIn("print(1)", preview)
        self.assertIn("explicit approval is still required", granted)
        self.assertIn("Execution remains disabled", approved)
        self.assertIn("[approved]", status)
        self.assertEqual([], session.calls)

    def test_trusted_local_web_fetch_requires_inert_proposal_then_exact_preparation(self):
        resolver_calls = []

        def runtime_factory():
            resolver = NativeWebResolver(
                getaddrinfo=lambda *args: resolver_calls.append(args) or [
                    (2, 1, 6, "", ("93.184.216.34", 443)),
                ],
                clock=time.time,
            )
            prerequisites = SessionWebPrerequisiteStore(resolver)
            quarantine = SessionWebQuarantineStore()
            supervisor = WebFetchSupervisor(
                prerequisites, FakeWebTransport(), quarantine, clock=time.time,
            )
            return NativeWebToolRuntime(prerequisites, quarantine, supervisor)

        session = FakeSession()
        app = AssistantApplication(session, local_web_runtime_factory=runtime_factory)
        created = app.respond(
            'tool propose web.fetch {"url":"https://example.com/reference"}',
            trusted_local_control=True,
        )
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)
        self.assertEqual([], resolver_calls)
        self.assertIn("No DNS lookup", created)
        self.assertIn("Exact public URL", app.respond(
            f"tool preview {request_id}", trusted_local_control=True,
        ))
        app.respond(f"tool grant {request_id}", trusted_local_control=True)
        app.respond(f"tool approve {request_id}", trusted_local_control=True)
        prepared = app.respond(f"tool prepare {request_id}", trusted_local_control=True)
        self.assertEqual(1, len(resolver_calls))
        self.assertIn("URL-only disclosure evidence", prepared)

        completed = app.respond(f"tool execute {request_id}", trusted_local_control=True)
        artifact_ref = re.search(r"TF-[A-Za-z0-9_-]+", completed).group(0)
        artifact = app.respond(f"tool artifact {artifact_ref}", trusted_local_control=True)
        self.assertIn("untrusted_external", artifact)
        self.assertIn("Source media: text/plain", artifact)
        self.assertIn("Prepared media: text/plain", artifact)
        self.assertIn("bounded public fixture", artifact)
        self.assertEqual([], session.calls)

        fast = app.respond(
            "tool fetch https://example.com/fast", trusted_local_control=True,
        )
        fast_artifact = re.search(r"TF-[A-Za-z0-9_-]+", fast)
        self.assertIsNotNone(fast_artifact, fast)
        self.assertIn("Explicit local fast fetch confirmed for https://example.com/fast", fast)
        self.assertIn("Inspect any returned artifact explicitly", fast)
        self.assertEqual(2, len(resolver_calls))
        self.assertEqual([], session.calls)

    def test_trusted_local_web_search_requires_injected_runtime_and_exact_preparation(self):
        adapter_calls = []

        class FakeSearchAdapter:
            available = True
            service_id = "fixture.search"

            def search(self, request, cancellation):
                adapter_calls.append(request)
                return WebSearchResponse(
                    1, request.invocation_id, request.binding_fingerprint,
                    request.worker_generation, request.service_id, request.query_sha256,
                    (WebSearchCandidate(1, "https://example.com/result", "Fixture result"),),
                )

            def request_cancel(self, request):
                return None

        def runtime_factory():
            prerequisites = SessionWebSearchPrerequisiteStore(
                service_id="fixture.search", deployment="local", maximum_results=4,
            )
            quarantine = SessionWebSearchArtifactStore(ref_factory=lambda: "TF-search_fixture")

            def observation(service_ref):
                now = time.time()
                return WebSearchServicePrerequisite(
                    1, service_ref, "fixture.search", "local", 4, True,
                    now, now + 60.0, WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
                )

            supervisor = WebSearchSupervisor(
                prerequisites, FakeSearchAdapter(), quarantine, clock=time.time,
            )
            return LocalWebSearchRuntime(
                prerequisites, quarantine, supervisor, observation,
            )

        session = FakeSession()
        app = AssistantApplication(
            session, local_web_search_runtime_factory=runtime_factory,
        )
        created = app.respond(
            'tool propose web.search {"query":"Please research the current price of an RTX 4070."}',
            trusted_local_control=True,
        )
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)
        self.assertIn("No provider probe or search request", created)
        self.assertEqual([], adapter_calls)
        preview = app.respond(f"tool preview {request_id}", trusted_local_control=True)
        self.assertIn("Public query is intentionally withheld", preview)
        self.assertNotIn("RTX 4070", preview)
        app.respond(f"tool grant {request_id}", trusted_local_control=True)
        app.respond(f"tool approve {request_id}", trusted_local_control=True)
        prepared = app.respond(f"tool prepare {request_id}", trusted_local_control=True)
        self.assertIn("search-service and public-query disclosure", prepared)
        self.assertEqual([], adapter_calls)
        completed = app.respond(f"tool execute {request_id}", trusted_local_control=True)
        match = re.search(r"TF-search_[A-Za-z0-9_-]+", completed)
        self.assertIsNotNone(match, completed)
        artifact_ref = match.group(0)
        inspected = app.respond(
            f"tool search artifact {artifact_ref}", trusted_local_control=True,
        )
        self.assertIn("Fixture result", inspected)
        self.assertIn("untrusted_discovery", inspected)
        self.assertEqual(1, len(adapter_calls))
        self.assertEqual([], session.calls)

        fast = app.respond(
            "tool search Please research the current public price of an RTX 4070.",
            trusted_local_control=True,
        )
        self.assertIn("Explicit local fast web search confirmed", fast)
        self.assertIn("Inspect any returned discovery links explicitly", fast)
        self.assertNotIn("RTX 4070", fast)
        self.assertEqual(2, len(adapter_calls))

    def test_trusted_local_search_selection_creates_inert_exact_fetch_proposal(self):
        resolver_calls = []
        adapter_calls = []
        search_artifact_serial = [0]

        class FakeSearchAdapter:
            available = True
            service_id = "fixture.search"

            def search(self, request, cancellation):
                adapter_calls.append(request)
                return WebSearchResponse(
                    1, request.invocation_id, request.binding_fingerprint,
                    request.worker_generation, request.service_id, request.query_sha256,
                    (WebSearchCandidate(1, "https://example.com/result", "Fixture result"),),
                )

            def request_cancel(self, request):
                return None

        def fetch_runtime_factory():
            resolver = NativeWebResolver(
                getaddrinfo=lambda *args: resolver_calls.append(args) or [
                    (2, 1, 6, "", ("93.184.216.34", 443)),
                ],
                clock=time.time,
            )
            prerequisites = SessionWebPrerequisiteStore(resolver)
            quarantine = SessionWebQuarantineStore()
            return NativeWebToolRuntime(
                prerequisites,
                quarantine,
                WebFetchSupervisor(prerequisites, FakeWebTransport(), quarantine, clock=time.time),
            )

        def search_runtime_factory():
            prerequisites = SessionWebSearchPrerequisiteStore(
                service_id="fixture.search", deployment="local", maximum_results=4,
            )
            def artifact_ref():
                search_artifact_serial[0] += 1
                return f"TF-search_fixture{search_artifact_serial[0]}"

            quarantine = SessionWebSearchArtifactStore(ref_factory=artifact_ref)

            def observation(service_ref):
                now = time.time()
                return WebSearchServicePrerequisite(
                    1, service_ref, "fixture.search", "local", 4, True,
                    now, now + 60.0, WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
                )

            supervisor = WebSearchSupervisor(
                prerequisites, FakeSearchAdapter(), quarantine, clock=time.time,
            )
            return LocalWebSearchRuntime(prerequisites, quarantine, supervisor, observation)

        session = ResearchSession()
        app = AssistantApplication(
            session,
            local_web_runtime_factory=fetch_runtime_factory,
            local_web_search_runtime_factory=search_runtime_factory,
        )
        search_created = app.respond(
            'tool propose web.search {"query":"Please research the current price of an RTX 4070."}',
            trusted_local_control=True,
        )
        search_id = re.search(r"TI-[A-Za-z0-9_-]+", search_created).group(0)
        app.respond(f"tool grant {search_id}", trusted_local_control=True)
        app.respond(f"tool approve {search_id}", trusted_local_control=True)
        app.respond(f"tool prepare {search_id}", trusted_local_control=True)
        search_completed = app.respond(f"tool execute {search_id}", trusted_local_control=True)
        artifact_ref = re.search(r"TF-search_[A-Za-z0-9_-]+", search_completed).group(0)

        selected = app.respond(
            f"tool search select {artifact_ref} 1", trusted_local_control=True,
        )
        fetch_id = re.search(r"TI-[A-Za-z0-9_-]+", selected).group(0)
        self.assertIn("Selected untrusted discovery link 1", selected)
        self.assertIn("No DNS lookup or network request occurred", selected)
        self.assertEqual([], resolver_calls)
        self.assertEqual(1, len(adapter_calls))
        preview = app.respond(f"tool preview {fetch_id}", trusted_local_control=True)
        self.assertIn("https://example.com/result", preview)

        app.respond(f"tool grant {fetch_id}", trusted_local_control=True)
        app.respond(f"tool approve {fetch_id}", trusted_local_control=True)
        prepared = app.respond(f"tool prepare {fetch_id}", trusted_local_control=True)
        self.assertIn("URL-only disclosure evidence", prepared)
        self.assertEqual(1, len(resolver_calls))
        completed = app.respond(f"tool execute {fetch_id}", trusted_local_control=True)
        self.assertIn("quarantined artifact", completed)

        fast = app.respond(
            f"tool search fetch {artifact_ref} 1", trusted_local_control=True,
        )
        self.assertIn("Explicit local fast fetch confirmed for selected discovery link 1", fast)
        self.assertIn("quarantined artifact", fast)
        self.assertIn("Inspect any returned artifact explicitly", fast)
        self.assertEqual(2, len(resolver_calls))

        selected_research = app.respond(
            f"tool research selected {artifact_ref} 1: What does the fixture contain?",
            trusted_local_control=True,
        )
        self.assertIn("Explicit local selected-link research confirmed", selected_research)
        self.assertIn("quarantined artifact", selected_research)
        self.assertIn("Research claim proposals (untrusted; not a final answer)", selected_research)
        self.assertEqual(3, len(resolver_calls))
        self.assertEqual(1, len(session.research_calls))
        searched_research = app.respond(
            "tool research search Please research the current fixture fact 1: What does the fixture contain?",
            trusted_local_control=True,
        )
        self.assertIn("Explicit local fast search-to-research confirmed for selected discovery link 1", searched_research)
        self.assertIn("Research claim proposals (untrusted; not a final answer)", searched_research)
        self.assertNotIn("current fixture fact", searched_research)
        self.assertEqual(2, len(adapter_calls))
        self.assertEqual(4, len(resolver_calls))
        self.assertEqual(2, len(session.research_calls))
        self.assertIn(
            "rank was not found",
            app.respond(f"tool search select {artifact_ref} 2", trusted_local_control=True),
        )
        self.assertEqual([], session.calls)

    def test_explicit_local_search_does_not_require_research_magic_words(self):
        adapter_calls = []

        class FakeSearchAdapter:
            available = True
            service_id = "fixture.search"

            def search(self, request, cancellation):
                adapter_calls.append(request)
                return WebSearchResponse(
                    1, request.invocation_id, request.binding_fingerprint,
                    request.worker_generation, request.service_id, request.query_sha256,
                    (WebSearchCandidate(1, "https://example.com/result", "Fixture result"),),
                )

            def request_cancel(self, request):
                return None

        def search_runtime_factory():
            prerequisites = SessionWebSearchPrerequisiteStore(
                service_id="fixture.search", deployment="local", maximum_results=4,
            )
            quarantine = SessionWebSearchArtifactStore(ref_factory=lambda: "TF-search_wording")

            def observation(service_ref):
                now = time.time()
                return WebSearchServicePrerequisite(
                    1, service_ref, "fixture.search", "local", 4, True,
                    now, now + 60.0, WEB_SEARCH_PREFLIGHT_POLICY_REVISION,
                )

            supervisor = WebSearchSupervisor(
                prerequisites, FakeSearchAdapter(), quarantine, clock=time.time,
            )
            return LocalWebSearchRuntime(prerequisites, quarantine, supervisor, observation)

        app = AssistantApplication(
            FakeSession(), local_web_search_runtime_factory=search_runtime_factory,
        )
        result = app.respond("tool search Example Domain", trusted_local_control=True)
        self.assertIn("Explicit local fast web search confirmed", result)
        self.assertEqual(1, len(adapter_calls))

    def test_trusted_local_research_proposes_cited_claims_without_publishing_state(self):
        def runtime_factory():
            resolver = NativeWebResolver(
                getaddrinfo=lambda *_args: [(2, 1, 6, "", ("93.184.216.34", 443))],
                clock=time.time,
            )
            prerequisites = SessionWebPrerequisiteStore(resolver)
            quarantine = SessionWebQuarantineStore()
            return NativeWebToolRuntime(
                prerequisites,
                quarantine,
                WebFetchSupervisor(prerequisites, FakeWebTransport(), quarantine, clock=time.time),
            )

        session = ResearchSession()
        app = AssistantApplication(session, local_web_runtime_factory=runtime_factory)
        created = app.respond(
            'tool propose web.fetch {"url":"https://example.com/reference"}',
            trusted_local_control=True,
        )
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)
        app.respond(f"tool grant {request_id}", trusted_local_control=True)
        app.respond(f"tool approve {request_id}", trusted_local_control=True)
        app.respond(f"tool prepare {request_id}", trusted_local_control=True)
        completed = app.respond(f"tool execute {request_id}", trusted_local_control=True)
        artifact_ref = re.search(r"TF-[A-Za-z0-9_-]+", completed).group(0)

        result = app.respond(
            f"tool research {artifact_ref}: What does the fixture contain?",
            trusted_local_control=True,
        )

        self.assertIn("Research claim proposals (untrusted; not a final answer)", result)
        review_id = re.search(r"RR-[0-9a-f]{24}", result).group(0)
        self.assertIn("RC-001 [confidence 0.90]", result)
        self.assertIn("Cites: RS-", result)
        self.assertIn("Citation diversity: single_source", result)
        self.assertIn("(fetched ", result)
        self.assertIn("no final answer, memory, learning, adventure, or canonical state", result)
        self.assertEqual(1, len(session.research_calls))
        self.assertEqual([], session.calls)
        listed = app.respond("tool research list", trusted_local_control=True)
        inspected = app.respond(f"tool research inspect {review_id}", trusted_local_control=True)
        brief = app.respond(f"tool research brief {review_id}", trusted_local_control=True)
        answer = app.respond(f"tool research answer {review_id}", trusted_local_control=True)
        bound_answer = app.respond(
            f"tool research answer {review_id}: What does the fixture contain?",
            trusted_local_control=True,
        )
        mismatched_answer = app.respond(
            f"tool research answer {review_id}: What is a different question?",
            trusted_local_control=True,
        )
        self.assertIn(review_id, listed)
        self.assertIn("Read-only review record", inspected)
        self.assertIn("RC-001 [confidence 0.90]", inspected)
        self.assertIn("Citation diversity: single_source", inspected)
        self.assertIn("(fetched ", inspected)
        self.assertIn("Source-backed research brief", brief)
        self.assertIn("unverified; not a final answer", brief)
        self.assertIn("https://example.com/reference", brief)
        self.assertIn("Research answer (source-backed, unverified)", answer)
        self.assertIn("No model was called for this answer", answer)
        self.assertIn("Question binding: exact reviewed question match", bound_answer)
        self.assertIn("does not match this review", mismatched_answer)
        self.assertNotIn("What does the fixture contain?", mismatched_answer)

    def test_trusted_local_relationship_review_is_session_local_and_nonpublishing(self):
        def runtime_factory():
            resolver = NativeWebResolver(
                getaddrinfo=lambda *_args: [(2, 1, 6, "", ("93.184.216.34", 443))],
                clock=time.time,
            )
            prerequisites = SessionWebPrerequisiteStore(resolver)
            quarantine = SessionWebQuarantineStore()
            return NativeWebToolRuntime(
                prerequisites,
                quarantine,
                WebFetchSupervisor(prerequisites, FakeWebTransport(), quarantine, clock=time.time),
            )

        session = ResearchSession(two_claims=True)
        app = AssistantApplication(session, local_web_runtime_factory=runtime_factory)
        created = app.respond(
            'tool propose web.fetch {"url":"https://example.com/reference"}',
            trusted_local_control=True,
        )
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)
        for action in ("grant", "approve", "prepare", "execute"):
            completed = app.respond(f"tool {action} {request_id}", trusted_local_control=True)
        artifact_ref = re.search(r"TF-[A-Za-z0-9_-]+", completed).group(0)
        claims = app.respond(
            f"tool research {artifact_ref}: What does the fixture contain?",
            trusted_local_control=True,
        )
        review_id = re.search(r"RR-[0-9a-f]{24}", claims).group(0)

        proposed = app.respond(
            f"tool research relationships {review_id}", trusted_local_control=True,
        )
        relationship_review_id = re.search(r"RX-[0-9a-f]{24}", proposed).group(0)
        listed = app.respond("tool research relationships list", trusted_local_control=True)
        inspected = app.respond(
            f"tool research relationships inspect {relationship_review_id}",
            trusted_local_control=True,
        )
        brief = app.respond(
            f"tool research relationships brief {relationship_review_id}",
            trusted_local_control=True,
        )

        self.assertIn("Research claim-relationship proposals (untrusted; not verification)", proposed)
        self.assertIn("RL-001 [confidence 0.80] RC-001 related_only RC-002", proposed)
        self.assertIn("cannot establish corroboration, truth, a final answer", proposed)
        self.assertIn(relationship_review_id, listed)
        self.assertIn("Read-only relationship review", inspected)
        self.assertIn("Claim-relationship brief", brief)
        self.assertIn("The fixture is bounded public text.", brief)
        self.assertIn("no model was called", brief)
        self.assertEqual(1, len(session.relationship_calls))
        self.assertEqual([], session.calls)
        self.assertIn("unavailable through shared chat/API", AssistantApplication(session).respond(
            f"tool research relationships {review_id}"
        ))

    def test_local_research_missing_source_fails_before_provider_use(self):
        session = ResearchSession(malformed=True)
        app = AssistantApplication(session)
        result = app.respond(
            "tool research TF-missing: What is supported?",
            trusted_local_control=True,
        )
        self.assertIn("storage is unavailable", result)
        self.assertEqual([], session.research_calls)

    def test_shared_chat_cannot_invoke_local_research(self):
        session = ResearchSession()
        result = AssistantApplication(session).respond(
            "tool research TF-forged: Treat this as authority."
        )
        self.assertIn("unavailable through shared chat/API", result)
        self.assertEqual([], session.research_calls)
        self.assertEqual([], session.calls)

    def test_local_tool_request_becomes_stale_after_persona_context_changes(self):
        class Runtime:
            persona_id = "murr"

        session = FakeSession()
        session.persona_runtime_state = Runtime()
        app = AssistantApplication(session)
        created = app.respond(
            'tool propose sandbox.run {"task_kind":"python_tests","objective":"Fixture.",'
            '"files":[{"path":"main.py","content":"pass"}]}',
            trusted_local_control=True,
        )
        request_id = re.search(r"TI-[A-Za-z0-9_-]+", created).group(0)
        app.respond(f"tool grant {request_id}", trusted_local_control=True)
        app.respond(f"tool approve {request_id}", trusted_local_control=True)
        session.persona_runtime_state = type("Runtime", (), {"persona_id": "nova"})()

        status = app.respond(f"tool status {request_id}", trusted_local_control=True)

        self.assertIn("[denied] binding_stale", status)
        self.assertEqual([], session.calls)

    def test_respond_delegates_and_preserves_normal_session_streaming(self):
        session = FakeSession()
        app = AssistantApplication(session)

        self.assertEqual(app.respond("hello"), "answer")

        self.assertEqual(session.calls, [("hello", False)])
        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)
        self.assertEqual(app.active_model, "fake:latest")

    def test_request_scoped_streaming_is_restored_after_response(self):
        session = FakeSession()
        app = AssistantApplication(session)
        chunks = []

        self.assertEqual(app.respond("stream", stream_writer=chunks.append), "answer")

        self.assertEqual(chunks, ["chunk"])
        self.assertEqual(session.calls, [("stream", True)])
        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)

    def test_request_scoped_streaming_is_restored_after_error(self):
        session = FailingSession()
        app = AssistantApplication(session)

        with self.assertRaisesRegex(RuntimeError, "expected failure"):
            app.respond("stream", stream_writer=lambda text: None)

        self.assertFalse(session.stream)
        self.assertIsNone(session.stream_writer)

    def test_context_stats_delegates_without_a_turn(self):
        self.assertEqual(AssistantApplication(FakeSession()).context_stats(), "stats")

    def test_persona_runtime_snapshot_is_read_only_and_bounded(self):
        class Runtime:
            def public_dict(self):
                return {"persona_id": "murr", "storage": "restart_ephemeral"}

        session = FakeSession()
        session.persona_runtime_state = Runtime()
        app = AssistantApplication(session)

        result = app.persona_runtime_snapshot()

        self.assertEqual(result, {
            "object": "starfur.persona_runtime",
            "available": True,
            "persona": {"persona_id": "murr", "storage": "restart_ephemeral"},
        })
        self.assertEqual(session.calls, [])

    def test_persona_runtime_snapshot_is_compatible_with_legacy_sessions(self):
        session = FakeSession()
        app = AssistantApplication(session)

        self.assertEqual(app.persona_runtime_snapshot(), {
            "object": "starfur.persona_runtime", "available": False, "persona": None,
        })

    def test_read_only_snapshots_do_not_create_an_unknown_conversation(self):
        sessions = []

        def factory():
            session = FakeSession()
            sessions.append(session)
            return session

        app = AssistantApplication(FakeSession(), session_factory=factory)
        with self.assertRaises(ConversationNotFoundError):
            app.persona_runtime_snapshot(conversation_id="missing-snapshot")
        with self.assertRaises(ConversationNotFoundError):
            app.resident_snapshot(conversation_id="missing-snapshot")
        self.assertEqual(sessions, [])

    def test_resident_snapshot_is_read_only_and_summary_only(self):
        class Runtime:
            def public_dict(self):
                return {"persona_id": "murr", "display_name": "Murr", "static_identity": "hidden"}

        class Lifecycle:
            def public_dict(self):
                return {"state": "idle", "error": "hidden", "transition_count": 2}

        class Adventure:
            def public_dict(self):
                return {
                    "mounted": True, "title": "Quiet Ember", "participant_count": 2,
                    "hidden_resource": "ammo", "participant_identity": "Murr",
                }

        class Roleplay:
            def public_dict(self):
                return {"active": True, "title": "Quiet Ember", "storage": "session_ephemeral"}

        class Turn:
            active = True
            drafts = (object(), object())

        class Inbox:
            active = True
            batch = type("Batch", (), {"candidates": (object(),)})()

        session = FakeSession()
        session.persona_runtime_state = Runtime()
        session.provider = type("Provider", (), {"name": "fake"})()
        session.provider_lifecycle = Lifecycle()
        session.adventure_session = Adventure()
        session.roleplay_state = Roleplay()
        session.adventure_turn = Turn()
        session.adventure_turn_candidate_inbox = Inbox()
        session.adventure_turn_mutation_candidate_inbox = Inbox()
        class Metrics:
            def snapshot(self):
                return SystemMetricsSnapshot("partial", platform_name="test", cpu_logical_cores=4)

        app = AssistantApplication(session, system_metrics_provider=Metrics())

        result = app.resident_snapshot()

        self.assertEqual(result["object"], "starfur.resident_snapshot")
        self.assertEqual(result["conversation"]["id"], "default")
        self.assertEqual(result["activity"], "reviewing_candidates")
        self.assertEqual(result["adventure_turn"], {"active": True, "staged_count": 2})
        self.assertEqual(result["routing"], {
            "configured_task_count": 1, "routable_task_count": 1,
            "unavailable_task_count": 0, "storage": "session_ephemeral",
        })
        self.assertEqual(result["focus_mode"], {
            "enabled": False, "storage": "session_ephemeral",
        })
        self.assertEqual(result["sandbox_execution"], {
            "schema_version": 1, "configured": False,
            "host_status": "unprobed", "supervisor_status": "unprobed",
            "execution_status": "disabled", "reason": "not_configured",
            "storage": "presentation_ephemeral",
        })
        self.assertEqual(result["tool_activity"], {
            "schema_version": 1, "total_count": 0,
            "pending_review_count": 0, "approved_count": 0,
            "queued_count": 0, "running_count": 0,
            "terminal_count": 0, "storage": "session_ephemeral",
        })
        self.assertEqual(result["candidate_inbox"]["ordinary_count"], 1)
        self.assertEqual(result["presentation"]["animation_slot"], "resident.murr.reviewing")
        self.assertEqual(result["system_metrics"]["cpu"]["logical_cores"], 4)
        self.assertNotIn("static_identity", result["persona"])
        self.assertNotIn("error", result["lifecycle"])
        self.assertNotIn("hidden_resource", result["adventure"])
        self.assertEqual(2, result["adventure"]["participant_count"])
        self.assertNotIn("participant_identity", result["adventure"])
        self.assertEqual(session.calls, [])

    def test_resident_snapshot_exposes_aggregate_tool_status_for_exact_session(self):
        app = AssistantApplication(FakeSession())
        result = app.respond(
            'tool propose sandbox.run {"task_kind":"python_tests",'
            '"objective":"Count only.","files":[{"path":"fixture.py",'
            '"content":"print(1)"}]}',
            trusted_local_control=True,
        )
        self.assertIn("Registered inert tool proposal", result)

        snapshot = app.resident_snapshot()

        self.assertEqual(1, snapshot["tool_activity"]["total_count"])
        self.assertEqual(1, snapshot["tool_activity"]["pending_review_count"])
        rendered = repr(snapshot["tool_activity"])
        self.assertNotIn("TI-", rendered)
        self.assertNotIn("fixture.py", rendered)
        self.assertNotIn("Count only", rendered)

    def test_resident_snapshot_exposes_only_focus_mode_boolean(self):
        session = FakeSession()
        session.focus_mode_enabled = True

        snapshot = AssistantApplication(session).resident_snapshot()

        self.assertEqual(snapshot["focus_mode"], {
            "enabled": True, "storage": "session_ephemeral",
        })
        self.assertEqual(session.calls, [])

    def test_resident_snapshot_uses_only_injected_passive_sandbox_status(self):
        class PassiveStatus:
            def __init__(self):
                self.calls = 0

            def snapshot(self):
                self.calls += 1
                return SandboxExecutionStatus(
                    1, True, "unsupported", "unavailable", "unavailable",
                    "host_unsupported",
                )

        source = PassiveStatus()
        session = FakeSession()
        result = AssistantApplication(
            session, sandbox_status_provider=source,
        ).resident_snapshot()

        self.assertEqual(1, source.calls)
        self.assertEqual("host_unsupported", result["sandbox_execution"]["reason"])
        self.assertNotIn("backend_id", result["sandbox_execution"])
        self.assertEqual(session.calls, [])

    def test_resident_snapshot_contains_status_source_failure(self):
        class FailingStatus:
            def snapshot(self):
                raise RuntimeError("C:/private/service/key")

        result = AssistantApplication(
            FakeSession(), sandbox_status_provider=FailingStatus(),
        ).resident_snapshot()
        self.assertEqual("observation_failed", result["sandbox_execution"]["reason"])
        self.assertNotIn("private", repr(result))

    def test_application_isolates_ephemeral_state_per_conversation(self):
        default = FakeSession()
        created = []

        def make_session():
            session = FakeSession()
            created.append(session)
            return session

        app = AssistantApplication(default, session_factory=make_session, max_conversations=2)
        app.respond("first turn", conversation_id="chat-a")
        app.respond("second turn", conversation_id="chat-b")
        app.respond("another a turn", conversation_id="chat-a")

        session_a, session_b = created
        session_a.active_model = "model-a"
        session_a.last_memory_ids = ["M-001"]
        session_a.pending_bulk_approval = {"proposal": "P-001"}

        self.assertEqual(default.calls, [])
        self.assertEqual([call[0] for call in session_a.calls], ["first turn", "another a turn"])
        self.assertEqual([call[0] for call in session_b.calls], ["second turn"])
        self.assertEqual(session_b.active_model, "fake:latest")
        self.assertEqual(session_b.last_memory_ids, [])
        self.assertIsNone(session_b.pending_bulk_approval)
        self.assertEqual(app.active_model_for("chat-a"), "model-a")
        self.assertEqual(app.active_model_for("chat-b"), "fake:latest")

    def test_application_evicts_only_bounded_nondefault_conversations(self):
        default = FakeSession()
        created = []

        def make_session():
            session = FakeSession()
            created.append(session)
            return session

        app = AssistantApplication(default, session_factory=make_session, max_conversations=1)
        app.respond("one", conversation_id="chat-one")
        app.respond("two", conversation_id="chat-two")
        app.respond("one again", conversation_id="chat-one")

        self.assertEqual(len(created), 3)
        self.assertEqual(default.calls, [])
        self.assertEqual([call[0] for call in created[-1].calls], ["one again"])

    def test_independent_conversations_do_not_wait_on_each_others_response(self):
        starts = [threading.Event(), threading.Event()]
        releases = [threading.Event(), threading.Event()]
        created = []

        def make_session():
            session = BlockingSession(starts[len(created)], releases[len(created)])
            created.append(session)
            return session

        app = AssistantApplication(FakeSession(), session_factory=make_session)
        first = threading.Thread(target=app.respond, args=("first",), kwargs={"conversation_id": "chat-a"})
        second = threading.Thread(target=app.respond, args=("second",), kwargs={"conversation_id": "chat-b"})
        first.start()
        self.assertTrue(starts[0].wait(0.5))
        second.start()
        try:
            self.assertTrue(starts[1].wait(0.5))
        finally:
            for release in releases:
                release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())

    def test_new_busy_conversation_is_pinned_before_lru_eviction(self):
        """A capacity overflow must not evict the just-created live session."""
        starts = [threading.Event(), threading.Event()]
        releases = [threading.Event(), threading.Event()]
        created = []
        failures = []

        def make_session():
            session = BlockingSession(starts[len(created)], releases[len(created)])
            created.append(session)
            return session

        app = AssistantApplication(
            FakeSession(), session_factory=make_session, max_conversations=1,
        )

        def respond(text, conversation_id):
            try:
                app.respond(text, conversation_id=conversation_id)
            except Exception as error:  # Thread failures must be asserted below.
                failures.append(error)

        first = threading.Thread(target=respond, args=("first", "chat-a"))
        second = threading.Thread(target=respond, args=("second", "chat-b"))
        first.start()
        self.assertTrue(starts[0].wait(0.5))
        second.start()
        try:
            self.assertTrue(starts[1].wait(0.5))
        finally:
            for release in releases:
                release.set()
            first.join(2)
            second.join(2)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([], failures)
        self.assertEqual([("first", False)], created[0].calls)
        self.assertEqual([("second", False)], created[1].calls)

    def test_same_conversation_remains_serialized_while_response_is_active(self):
        started = [threading.Event(), threading.Event()]
        releases = [threading.Event(), threading.Event()]
        created = []

        def make_session():
            session = SequentialBlockingSession(started, releases)
            created.append(session)
            return session

        app = AssistantApplication(FakeSession(), session_factory=make_session)
        first = threading.Thread(target=app.respond, args=("first",), kwargs={"conversation_id": "chat-a"})
        second = threading.Thread(target=app.respond, args=("second",), kwargs={"conversation_id": "chat-a"})
        first.start()
        self.assertTrue(started[0].wait(0.5))
        second.start()
        try:
            self.assertFalse(started[1].wait(0.15))
            releases[0].set()
            self.assertTrue(started[1].wait(0.5))
        finally:
            for release in releases:
                release.set()
            first.join(2)
            second.join(2)
        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual([call[0] for call in created[0].calls], ["first", "second"])

    def test_application_rejects_invalid_conversation_identifiers(self):
        app = AssistantApplication(FakeSession(), session_factory=FakeSession)

        with self.assertRaisesRegex(ValueError, "Conversation identifier"):
            app.respond("hello", conversation_id="not/a/session")

    def test_document_annotation_is_serialized_review_only_and_injectable(self):
        session = FakeSession()

        class RecordingLifecycle:
            def __init__(self):
                self.events = []

            def begin_generation(self, *, stream, model):
                self.events.append(("begin", stream, model))

            def finish(self):
                self.events.append(("finish",))

            def fail(self, error):
                self.events.append(("fail", str(error)))

        lifecycle = RecordingLifecycle()
        session.provider_lifecycle = lifecycle
        app = AssistantApplication(session)
        document = prepare_document_text(
            "Roger prefers tea.", "notes.md", domain="personal",
        )
        seen = []

        def annotator(chunk):
            seen.append(chunk.chunk_id)
            return {"proposals": [{
                "store": True,
                "subject": "Roger",
                "memory_type": "preference",
                "summary": "Roger prefers tea.",
                "details": None,
                "importance": 0.6,
                "confidence": 0.9,
                "retention": "long_term",
            }]}

        annotation = app.annotate_document(document, annotator=annotator)
        candidates = annotation.candidates

        self.assertEqual(seen, [document.chunks[0].chunk_id])
        self.assertEqual(candidates[0].proposal["source"], "external_document_annotation")
        self.assertEqual(session.calls, [])
        self.assertEqual(lifecycle.events, [("begin", False, "fake:latest"), ("finish",)])

    def test_document_annotation_adds_elapsed_time_to_bounded_execution_accounting(self):
        class TimedAnnotator:
            def __call__(self, _chunk):
                return {"proposals": []}

            def execution_summary(self):
                return DocumentAnnotationExecution("phi4-mini:latest", 1, "qwen3:8b", 0)

        app = AssistantApplication(FakeSession())
        document = prepare_document_text("No durable facts.", "notes.md", domain="personal")
        with patch("pipeline.application.perf_counter", side_effect=(10.0, 11.25)):
            result = app.annotate_document(document, annotator=TimedAnnotator())
        self.assertEqual("phi4-mini:latest", result.execution.primary_model)
        self.assertEqual(1250.0, result.execution.elapsed_ms)

    def test_document_proposal_handoff_uses_existing_writer_with_original_provenance(self):
        writes = []

        def proposal_creator(proposal, *, domain, source_reference, observation_text):
            writes.append({
                "proposal": proposal,
                "domain": domain,
                "source_reference": source_reference,
                "observation_text": observation_text,
            })
            return {"proposal_id": 41, "action": "created", "evidence_count": 1}

        app = AssistantApplication(FakeSession(), proposal_creator=proposal_creator)
        document = prepare_document_text("Roger prefers tea.", "notes.md", domain="personal")
        candidate = app.annotate_document(document, annotator=lambda _chunk: {"proposals": [{
            "store": True,
            "subject": "Roger",
            "memory_type": "preference",
            "summary": "Roger prefers tea.",
            "details": None,
            "importance": 0.6,
            "confidence": 0.9,
            "retention": "long_term",
        }]}).candidates[0]

        result = app.create_document_pending_proposal(candidate)

        self.assertEqual(result["proposal_id"], 41)
        self.assertEqual(writes[0]["domain"], "personal")
        self.assertRegex(
            writes[0]["source_reference"],
            rf"^{candidate.chunk_id}:candidate:[0-9a-f]{{64}}$",
        )
        self.assertEqual(writes[0]["observation_text"], "Roger prefers tea.")
        self.assertEqual(writes[0]["proposal"]["source"], "external_document_annotation")
    def test_runtime_diagnostics_are_bounded_and_do_not_probe_provider(self):
        session = FakeSession()
        app = AssistantApplication(session)
        snapshot = app.runtime_diagnostics()
        self.assertEqual(snapshot["status"], "provider_unavailable")
        self.assertEqual(snapshot["provider"]["health"], "not_probed")
        self.assertFalse(snapshot["provider"]["probe_performed"])
        self.assertEqual(snapshot["model"]["active"], "fake:latest")
        self.assertIsNone(snapshot["latest_turn"])
        self.assertTrue(snapshot["capabilities"]["ids"])
        self.assertIsNone(snapshot["lifecycle"])
        self.assertEqual("unavailable", snapshot["routing"]["provider"]["status"])
        self.assertEqual("unavailable", snapshot["routing"]["tasks"]["assistant_chat"]["status"])

    def test_runtime_diagnostics_include_passive_provider_route_preview(self):
        session = FakeSession()
        session.provider = HealthyProvider()
        app = AssistantApplication(session)

        snapshot = app.runtime_diagnostics()

        self.assertEqual("unprobed", snapshot["routing"]["provider"]["status"])
        chat = snapshot["routing"]["tasks"]["assistant_chat"]
        self.assertEqual("routable", chat["status"])
        self.assertEqual("unprobed", chat["candidates"][0]["provider_status"])

    def test_runtime_diagnostics_route_preview_exposes_bounded_budgets_only(self):
        class BudgetConfig(FakeConfig):
            task_profiles = TaskProfiles({"assistant_chat": TaskProfile(
                "assistant_chat",
                provider="ollama",
                model="qwen3:8b",
                context_size=4096,
                max_output_tokens=512,
            )})

        session = FakeSession(config=BudgetConfig())
        snapshot = AssistantApplication(session).runtime_diagnostics()
        candidate = snapshot["routing"]["tasks"]["assistant_chat"]["candidates"][0]

        self.assertEqual(4096, candidate["context_size"])
        self.assertEqual(512, candidate["max_output_tokens"])
        self.assertEqual("qwen3:8b", candidate["model"])
        self.assertNotIn("prompt", candidate)
        self.assertNotIn("messages", candidate)
        self.assertNotIn("provider_payload", candidate)

    def test_resident_snapshot_exposes_only_aggregate_passive_route_readiness(self):
        class OllamaNamedProvider:
            name = "ollama"

            def __init__(self):
                self.probe_calls = 0

            def probe_health(self):
                self.probe_calls += 1
                return {"models": [{"name": "one"}]}

        class RoutedConfig(FakeConfig):
            task_profiles = TaskProfiles({
                "assistant_chat": TaskProfile("assistant_chat", provider="ollama", model="qwen3:8b"),
                "vision": TaskProfile("vision", provider="ollama", model="vision:latest"),
            })

        session = FakeSession(config=RoutedConfig())
        session.provider = OllamaNamedProvider()
        result = AssistantApplication(session).resident_snapshot()

        self.assertEqual(result["routing"], {
            "configured_task_count": 2,
            "routable_task_count": 1,
            "unavailable_task_count": 1,
            "storage": "session_ephemeral",
        })
        self.assertEqual(session.provider.probe_calls, 0)
        self.assertNotIn("tasks", result["routing"])

    def test_runtime_diagnostics_expose_only_bounded_completed_turn_route_trace(self):
        session = FakeSession()
        session.last_turn_diagnostics = {
            "turn_status": "completed", "completed": True,
            "model": "qwen3:8b", "provider": "Ollama",
            "response_characters": 12, "response_latency_ms": 24.0,
            "time_to_first_token_ms": None, "proposal_outcome": "skipped",
            "task_routes": [{
                "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
                "provider": "ollama", "model": "qwen3:8b",
                "fallback_used": False, "outcome": "submitted",
            }],
        }
        snapshot = AssistantApplication(session).runtime_diagnostics()

        self.assertEqual([{
            "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
            "provider": "ollama", "model": "qwen3:8b",
            "fallback_used": False, "outcome": "submitted",
        }], snapshot["latest_turn"]["task_routes"])

    def test_runtime_diagnostics_drop_malformed_or_unbounded_turn_route_trace_data(self):
        session = FakeSession()
        session.last_turn_diagnostics = {
            "task_routes": [
                {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "qwen3:8b", "fallback_used": False, "outcome": "submitted"},
                {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "x" * 257, "fallback_used": False, "outcome": "submitted", "raw_provider_output": "must not leak"},
                {"requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat", "provider": "ollama", "model": "qwen3:8b", "fallback_used": "no", "outcome": "submitted"},
            ],
        }
        snapshot = AssistantApplication(session).runtime_diagnostics()

        self.assertEqual(1, len(snapshot["latest_turn"]["task_routes"]))

    def test_runtime_diagnostics_preserve_closed_completed_route_outcome(self):
        session = FakeSession()
        session.last_turn_diagnostics = {
            "task_routes": [{
                "requested_task_id": "assistant_chat", "selected_task_id": "assistant_chat",
                "provider": "ollama", "model": "qwen3:8b", "fallback_used": False,
                "outcome": "completed",
            }],
        }
        snapshot = AssistantApplication(session).runtime_diagnostics()
        self.assertEqual("completed", snapshot["latest_turn"]["task_routes"][0]["outcome"])
        self.assertNotIn("raw_provider_output", snapshot["latest_turn"]["task_routes"][0])

    def test_explicit_provider_probe_records_only_bounded_health_metadata(self):
        session = FakeSession()
        provider = HealthyProvider()
        session.provider = provider
        app = AssistantApplication(session)

        before = app.runtime_diagnostics()
        snapshot = app.runtime_diagnostics(probe_provider=True)

        self.assertEqual(provider.probe_calls, 1)
        self.assertEqual(before["provider"]["health"], "not_probed")
        self.assertEqual(snapshot["provider"]["name"], "healthy fake")
        self.assertEqual(snapshot["provider"]["health"], "healthy")
        self.assertTrue(snapshot["provider"]["probe_performed"])
        self.assertEqual(snapshot["provider"]["model_count"], 2)
        self.assertIsNotNone(snapshot["provider"]["checked_at"])
        self.assertIsNone(snapshot["provider"]["error"])
        self.assertEqual(session.calls, [])

    def test_explicit_provider_probe_reports_unavailability_without_generating(self):
        session = FakeSession()
        session.provider = UnavailableProvider()
        app = AssistantApplication(session)

        snapshot = app.runtime_diagnostics(probe_provider=True)

        self.assertEqual(snapshot["provider"]["health"], "unavailable")
        self.assertTrue(snapshot["provider"]["probe_performed"])
        self.assertEqual(snapshot["provider"]["error"], "provider is offline")
        self.assertEqual(session.calls, [])
    def test_application_attaches_one_core_manifest_when_session_supports_it(self):
        class ManifestAwareSession(FakeSession):
            def set_capability_manifest(self, manifest):
                self.received_manifest = manifest

        session = ManifestAwareSession()
        app = AssistantApplication(session)

        self.assertIs(session.received_manifest, app.capability_manifest)
        self.assertIsNotNone(app.capability_manifest.get("assistant.memory.proposals"))
    def test_factory_centralizes_standard_session_dependencies(self):
        config = FakeConfig()
        captured = {}

        def session_factory(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return FakeSession(*args, **kwargs)

        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_persona", return_value="persona"
        ), patch("pipeline.application.load_policy", return_value="policy"):
            app = create_assistant_application(
                "custom.json",
                stream=True,
                stream_writer=lambda text: None,
                debug_level="verbose",
                session_factory=session_factory,
            )

        self.assertIsInstance(app, AssistantApplication)
        self.assertEqual(captured["args"], (config, "persona"))
        self.assertEqual(captured["kwargs"]["policy"], "policy")
        self.assertTrue(captured["kwargs"]["stream"])
        self.assertEqual(captured["kwargs"]["debug_level"], "verbose")
        self.assertIsNotNone(captured["kwargs"]["proposal_creator"])

    def test_factory_passes_opt_in_registered_provider_adapters_without_changing_default_setup(self):
        config = FakeConfig()
        primary = type("PrimaryProvider", (), {
            "name": "primary",
            "complete": lambda self, *args, **kwargs: {"message": {"content": "ok"}},
            "list_models": lambda self: {"models": []},
            "probe_health": lambda self: {"models": []},
        })()
        registry = ChatProviderRegistry({
            "primary": ChatProviderRegistration("primary", primary),
        })
        captured = {}

        def session_factory(*args, **kwargs):
            captured["kwargs"] = kwargs
            return FakeSession(*args, **kwargs)

        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_persona", return_value="persona"
        ), patch("pipeline.application.load_policy", return_value="policy"):
            create_assistant_application(
                "custom.json", session_factory=session_factory,
                provider=primary, provider_registry=registry,
            )

        self.assertIs(primary, captured["kwargs"]["provider"])
        self.assertIs(registry, captured["kwargs"]["provider_registry"])

    def test_factory_opt_in_composes_one_cross_process_provider_gate(self):
        config = FakeConfig()
        provider = type("PrimaryProvider", (), {
            "name": "primary",
            "complete": lambda self, *args, **kwargs: {"message": {"content": "ok"}},
            "list_models": lambda self: {"models": []},
            "probe_health": lambda self: {"models": []},
        })()
        registry = ChatProviderRegistry({
            "primary": ChatProviderRegistration("primary", provider),
        })

        class GateSession(FakeSession):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.chat_provider_registry = kwargs["provider_registry"]

        with tempfile.TemporaryDirectory() as directory, patch(
            "pipeline.application.load_config", return_value=config,
        ), patch(
            "pipeline.application.load_persona", return_value="persona",
        ), patch("pipeline.application.load_policy", return_value="policy"):
            root = Path(directory).resolve()
            first = create_assistant_application(
                "custom.json", session_factory=GateSession,
                provider=provider, provider_registry=registry,
                provider_process_gate_root=root,
            )
            second = create_assistant_application(
                "custom.json", session_factory=GateSession,
                provider=provider, provider_registry=registry,
                provider_process_gate_root=root,
            )
            admitted = first._workload_gate.try_acquire("primary", 1)
            self.assertEqual("admitted", admitted.status)
            self.assertEqual(
                "deferred", second._workload_gate.try_acquire("primary", 1).status,
            )
            self.assertTrue(first._workload_gate.release(admitted.lease))

    def test_factory_rejects_a_provider_registry_without_a_selected_active_provider(self):
        with self.assertRaisesRegex(ValueError, "explicit active provider"):
            create_assistant_application(provider_registry=ChatProviderRegistry())

    def test_factory_explicitly_selects_tavily_without_affecting_default_setup(self):
        from pipeline.tool_web_search_tavily_native import create_tavily_web_search_runtime

        runtime = create_tavily_web_search_runtime(getenv=lambda name: None)
        with patch(
            "pipeline.tool_web_search_tavily_native.create_tavily_web_search_runtime",
            return_value=runtime,
        ) as builder:
            app = create_assistant_application(
                session_factory=FakeSession,
                enable_tavily_web_search=True,
            )

        builder.assert_called_once_with()
        self.assertIs(
            runtime,
            app._sessions["default"].local_web_search_runtime,
        )

    def test_factory_rejects_multiple_hosted_search_providers(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            create_assistant_application(
                enable_brave_web_search=True,
                enable_tavily_web_search=True,
            )

    def test_standard_factory_resolves_only_the_declared_builtin_murr_idle_slot(self):
        app = create_assistant_application(session_factory=FakeSession)

        asset = app.persona_asset_resolver.resolve("murr", "idle")
        self.assertIsNotNone(asset)
        self.assertTrue(asset.is_file())
        self.assertIsNone(app.persona_asset_resolver.resolve("nova", "idle"))

    def test_factory_preserves_builtin_murr_art_for_a_pre_manifest_stock_config(self):
        config = FakeConfig()
        config.persona_registry = PersonaRegistry((load_persona_package(
            None, persona_id="murr", display_name="Murr",
        ),))
        config.active_persona_id = "murr"

        with patch("pipeline.application.load_config", return_value=config), patch(
            "pipeline.application.load_policy", return_value="policy"
        ):
            app = create_assistant_application("legacy-config.json", session_factory=FakeSession)

        self.assertTrue(app.persona_asset_resolver.resolve("murr", "idle").is_file())


if __name__ == "__main__":
    unittest.main()
