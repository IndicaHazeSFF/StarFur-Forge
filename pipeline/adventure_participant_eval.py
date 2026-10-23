"""Provider-free participant lifecycle fixtures in test-owned workspaces only.

Exercises the real session command boundary with injected synthetic completions.
Reports closed outcomes/counts, not fixture prose, prompts, IDs, or host paths.
This is a regression benchmark, not a live-model quality or stop guarantee.
"""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from pipeline.adventure_events import AdventureEventLog
from pipeline.adventure_initiative import AdventureParticipant, AdventureParticipantRoster, PersonaInitiativePolicy
from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_transcript import AdventureTranscriptLog
from pipeline.assistant import AssistantSession, GenerationInterrupted
from pipeline.persona import Persona
from pipeline.persona_registry import PersonaPackage
from pipeline.persona_state import PersonaState
from pipeline.provider_workload_gate import ProviderWorkloadGate
from pipeline.providers import ChatCompletion

BENCHMARK_VERSION = "adventure-participant-lifecycle-v2"
_TURN_TEXT = "Synthetic crew pauses beside a synthetic hatch."
_SUMMARY = "Suggest inspecting the synthetic key."
_GENERATE = f"adventure participant action generate murr player_turn: {_TURN_TEXT}"
# name, expected outcome, calls, candidates, transcript records, events, pacing
_CASES = (
    ("review_only", "reviewed", 1, 1, 0, 0, 0),
    ("no_action", "no_action", 1, 0, 0, 0, 0),
    ("record_once", "recorded_once", 1, 1, 2, 0, 1),
    ("pacing", "policy_denied_then_eligible", 2, 1, 2, 0, 0),
    ("interruption", "interrupted_then_recovered", 3, 1, 0, 0, 0),
    ("stale_origin", "stale_rejected", 1, 0, 0, 1, 0),
    ("invalid_envelope", "invalid_rejected", 1, 0, 0, 0, 0),
    ("binding_required", "binding_denied", 0, 0, 0, 0, 0),
    ("binding_ended", "binding_completion_rejected", 1, 0, 0, 0, 0),
    ("binding_replaced", "binding_completion_rejected", 1, 0, 0, 0, 0),
    ("binding_recovery", "binding_recovered", 2, 1, 0, 0, 0),
)
FIXTURE_FINGERPRINT = hashlib.sha256(json.dumps(
    {"version": BENCHMARK_VERSION, "cases": _CASES, "turn": _TURN_TEXT, "summary": _SUMMARY},
    sort_keys=True, separators=(",", ":"),
).encode("utf-8")).hexdigest()


class _FixtureProvider:
    name = "participant-fixture"

    def __init__(self):
        self.calls = 0
        self.mode = "candidate"
        self.after_call = None

    def complete(self, messages, **kwargs):
        self.calls += 1
        if self.mode == "interrupt":
            raise KeyboardInterrupt()
        if self.after_call is not None:
            self.after_call()
        candidates = [] if self.mode == "empty" else [{
            "participant_id": "murr", "action": "suggest", "summary": _SUMMARY, "confidence": 0.8,
        }]
        payload = {"schema_version": 1, "candidates": candidates}
        if self.mode == "invalid":
            payload["authority"] = True
        return ChatCompletion(json.dumps(payload), finish_reason="stop")

    def list_models(self):
        raise AssertionError("fixture must not probe models")

    def probe_health(self):
        raise AssertionError("fixture must not probe provider health")


def _fixture(root: Path):
    registry = AdventureRegistry(root, now=lambda: datetime(2026, 10, 11, tzinfo=UTC))
    record = registry.create("Participant Fixture")
    registry.configure_participant_roster(record, AdventureParticipantRoster(record.adventure_id, (
        AdventureParticipant("murr", "Murr", "persona", f"adventure:{record.adventure_id}:participant:murr",
            initiative_policy=PersonaInitiativePolicy(enabled=True, allowed_triggers=("player_turn",),
                allowed_actions=("suggest",), cooldown_turns=1, max_actions_per_turn=1)),
    )))
    provider = _FixtureProvider()
    writes = []

    def unexpected_memory_write(*args, **kwargs):
        writes.append(True)
        raise AssertionError("participant fixture must not write assistant memory")

    config = SimpleNamespace(chat_model="fixture", domain="personal", max_session_messages=4,
        max_memories=2, memory_policy="off", debug_level="off")
    persona = PersonaPackage("murr", "Murr", Persona("Synthetic persona."),
        PersonaState("murr", "Murr", "Synthetic persona."))
    session = AssistantSession(config, persona, provider=provider, policy="Synthetic policy.",
        adventure_registry=registry, memory_loader=lambda **kwargs: [],
        memory_creator=unexpected_memory_write, proposal_creator=unexpected_memory_write)
    session._provider_workload_gate = ProviderWorkloadGate({"participant-fixture": 1})
    session.respond("adventure begin Participant Fixture")
    session.respond("adventure turn begin")
    return session, provider, writes, AdventureEventLog(registry, record), AdventureTranscriptLog(registry, record)


def _candidate_count(session):
    result = session.last_adventure_participant_action_generation
    if isinstance(result, dict) and result.get("status") == "completed":
        return len(result["proposal"].batch.candidates)
    return 0


def _run_case(root: Path, spec: tuple) -> dict[str, object]:
    name, outcome, calls, candidates, transcripts, events, pacing = spec
    session, provider, writes, log, transcript = _fixture(root)
    checks = []
    if name == "no_action":
        provider.mode = "empty"
    elif name == "invalid_envelope":
        provider.mode = "invalid"
    elif name == "stale_origin":
        provider.after_call = lambda: log.append("discovery", "Synthetic intervening event.")
    elif name == "binding_required":
        session.respond("roleplay end")
    elif name in {"binding_ended", "binding_recovery"}:
        provider.after_call = session.roleplay_end
    elif name == "binding_replaced":
        def replace_binding():
            session.respond("roleplay end")
            session.respond("adventure turn abort")
            session.respond("adventure begin Participant Fixture")
            session.respond("adventure turn begin")
        provider.after_call = replace_binding
    session.respond(_GENERATE)
    if name == "review_only":
        checks.append("TP-001" in session.respond("adventure participant actions"))
    elif name == "no_action":
        checks.append("no participant action was proposed" in session.respond("adventure participant actions"))
        checks.append("not found" in session.respond("adventure participant action record TP-001"))
    elif name in {"record_once", "pacing"}:
        checks.append("transcript pair" in session.respond("adventure participant action record TP-001"))
        checks.append("already recorded" in session.respond("adventure participant action record TP-001"))
        pair = transcript.records()
        checks.append(len(pair) == 2 and pair[0].role == "user" and pair[0].text == _TURN_TEXT
            and pair[1].role == "narrator" and pair[1].text == f"Murr suggests: {_SUMMARY}")
        if name == "pacing":
            session.respond(_GENERATE)
            checks.append(provider.calls == 1 and
                session.last_adventure_participant_action_generation.get("reason") == "policy_ineligible")
            session.respond("adventure turn abort")
            session.respond("adventure turn begin")
            session.respond(_GENERATE)
    elif name == "interruption":
        checks.append(_candidate_count(session) == 1)
        provider.mode = "interrupt"
        interrupted = False
        try:
            session.respond(_GENERATE)
        except GenerationInterrupted:
            interrupted = True
        checks.append(interrupted and session.last_adventure_participant_action_generation is None)
        checks.append(not transcript.records() and not log.events() and not session.adventure_turn.drafts)
        provider.mode = "candidate"
        session.respond(_GENERATE)  # Also proves the fixture capacity lease was released.
    elif name in {"stale_origin", "invalid_envelope"}:
        expected_reason = "stale_authoritative_origin" if name == "stale_origin" else "candidate_envelope_invalid"
        checks.append(session.last_adventure_participant_action_generation.get("reason") == expected_reason)
        checks.append("No untrusted" in session.respond("adventure participant actions"))
        checks.append("No untrusted" in session.respond("adventure participant action record TP-001"))
    elif name in {"binding_required", "binding_ended", "binding_replaced", "binding_recovery"}:
        expected_reason = "story_session_binding_required" if name == "binding_required" else "story_session_binding_stale"
        checks.append(session.last_adventure_participant_action_generation == {
            "status": "failed", "reason": expected_reason,
        })
        checks.append("No untrusted" in session.respond("adventure participant actions"))
        checks.append("No untrusted" in session.respond("adventure participant action record TP-001"))
        checks.append(not transcript.records() and not log.events() and not writes)
        if name == "binding_recovery":
            provider.after_call = None
            session.respond("adventure turn abort")
            session.respond("adventure begin Participant Fixture")
            session.respond("adventure turn begin")
            session.respond(_GENERATE)
            checks.append(_candidate_count(session) == 1)
    checks.append(not session.proposals and not session.messages and not writes)
    preserved = all(checks)
    result = {
        "name": name, "kind": "adventure_participant_lifecycle",
        "expected_outcome": outcome, "actual_outcome": outcome if preserved else "unexpected",
        "expected_provider_calls": calls, "actual_provider_calls": provider.calls,
        "expected_candidates": candidates, "actual_candidates": _candidate_count(session),
        "expected_transcript_records": transcripts, "actual_transcript_records": len(transcript.records()),
        "expected_events": events, "actual_events": len(log.events()),
        "expected_staged": 0, "actual_staged": len(session.adventure_turn.drafts),
        "expected_pacing_count": pacing, "actual_pacing_count": session._participant_action_counters("murr")[1],
        "invariants_preserved": preserved,
    }
    result["pass"] = preserved and all(result[f"expected_{field}"] == result[f"actual_{field}"]
        for field in ("outcome", "provider_calls", "candidates", "transcript_records", "events", "staged", "pacing_count"))
    return result


def _run_once() -> list[dict[str, object]]:
    with TemporaryDirectory() as directory:
        return [_run_case(Path(directory) / spec[0], spec) for spec in _CASES]


def run_adventure_participant_benchmark() -> dict[str, object]:
    """Run the frozen fixture twice; compare sanitized results, not generated IDs."""
    first, second = _run_once(), _run_once()
    return {"benchmark_version": BENCHMARK_VERSION, "fixture_fingerprint": FIXTURE_FINGERPRINT,
        "repeatability": first == second,
        "participant_lifecycle_pass_rate": sum(case["pass"] for case in first) / len(first),
        "results": first}


def format_adventure_participant_result(result: dict[str, object]) -> str:
    lines = ["Adventure Participant Lifecycle Evaluation", "------------------------------------------",
        f"Benchmark:          {result['benchmark_version']}", f"Cases:              {len(result['results'])}",
        f"Lifecycle checks:   {result['participant_lifecycle_pass_rate']:.1%}",
        f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}",
        "Provider-free fixtures; not a live-model quality or verified-stop result."]
    failures = [case["name"] for case in result["results"] if not case["pass"]]
    if failures:
        lines.append("Failed cases: " + ", ".join(failures))
    return "\n".join(lines)


__all__ = ["BENCHMARK_VERSION", "FIXTURE_FINGERPRINT", "run_adventure_participant_benchmark",
    "format_adventure_participant_result"]
