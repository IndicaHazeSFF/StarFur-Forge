import sys
import tempfile
import types
import unittest
import json
from datetime import UTC, datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.adventure_registry import AdventureRegistry
from pipeline.adventure_events import AdventureEvent, AdventureEventLog
from pipeline.adventure_mutation import AdventureEventEnvelope, AdventureMutation, MUTATION_STATE_SET
from pipeline.adventure_resources import AdventureResourceCatalog, AdventureResourceDefinition
from pipeline.adventure_import import AdventureImportLog
from pipeline.assistant import AssistantSession
from pipeline.adventure_turn_candidates import parse_untrusted_adventure_turn_candidates
from pipeline.adventure_turn_coordinator import AdventureTurnCoordinator
from pipeline.adventure_turn_generation import AdventureTurnGenerationRequest, AdventureTurnGenerationResult
from pipeline.adventure_turn_mutation_coordinator import AdventureTurnMutationCoordinator
from pipeline.command_help import detect_command_help
from pipeline.document_intake import extract_document_memory_candidates, prepare_document_text


class AdventureCommandTests(unittest.TestCase):
    def _config(self):
        return type("Config", (), {
            "chat_model": "test-model", "domain": "personal", "max_session_messages": 4,
            "max_memories": 2, "memory_policy": "off", "debug_level": "off",
        })()

    def _session(
        self, root, calls, *, adventure_turn_coordinator=None,
        adventure_turn_mutation_coordinator=None, chat_response=None,
    ):
        registry = AdventureRegistry(root, now=lambda: datetime(2026, 8, 15, tzinfo=UTC))
        chat_response = chat_response or {"message": {"content": "unexpected"}}
        return AssistantSession(
            self._config(), "Persona", policy="Policy", adventure_registry=registry,
            chat=lambda **kwargs: calls.append(kwargs) or chat_response,
            memory_loader=lambda **kwargs: [],
            adventure_turn_coordinator=adventure_turn_coordinator,
            adventure_turn_mutation_coordinator=adventure_turn_mutation_coordinator,
        )

    class _CandidateProvider:
        def __init__(self, payload):
            self.payload = payload
            self.requests = []

        def propose(self, request):
            self.requests.append(request)
            return self.payload

    def test_commands_create_list_and_inspect_metadata_without_a_model_or_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertEqual("No adventure workspaces are registered.", session.respond("adventure list"))
            created = session.respond("adventure create Quiet Ember")
            self.assertIn("Created adventure workspace: Quiet Ember", created)
            self.assertIn("metadata-only", created)
            self.assertIn("Quiet Ember", session.respond("adventure list"))
            inspected = session.respond("adventure inspect quiet ember")
            self.assertIn("manifest only", inspected)
            self.assertEqual([], calls)
            self.assertEqual([], session.messages)
            self.assertEqual([], session.proposals)

    def test_duplicate_missing_and_invalid_commands_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertEqual("Usage: adventure create <title>", session.respond("adventure create"))
            self.assertEqual("Adventure workspace not found.", session.respond("adventure inspect missing"))
            session.respond("adventure create Quiet Ember")
            self.assertIn("was not created", session.respond("adventure create quiet ember"))
            self.assertEqual([], calls)

    def test_malformed_adventure_namespace_never_reaches_model_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record

            for command in (
                "adventure",
                "adventure status/",
                "adventure turn typo",
                "adventure state nonsense",
                "adventure relationship mutate Vespera trust: cautious",
                "adventure knowledge invent Vespera knows: the hatch is trapped",
                "adventure recordish discovery: This must not persist.",
            ):
                self.assertIn("Unknown or malformed adventure command", session.respond(command))

            self.assertEqual([], calls)
            self.assertEqual([], session.messages)
            self.assertEqual([], session.proposals)
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())

    def test_help_is_core_owned_and_explicit(self):
        help_payload = detect_command_help("How do I create an adventure?")
        self.assertIsNotNone(help_payload)
        self.assertIn("adventure create <title>", help_payload.render())

    def test_load_is_session_local_and_injects_only_metadata_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            self.assertIn("loaded: Quiet Ember", session.respond("adventure load Quiet Ember"))
            self.assertIn("0 authoritative event(s)", session.respond("adventure status"))
            self.assertEqual(session.respond("adventure status"), session.respond("What is loaded?"))
            self.assertEqual("unexpected", session.respond("What is in the workspace?"))
            system_prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("MOUNTED ADVENTURE WORKSPACE", system_prompt)
            self.assertIn("no recorded authoritative adventure events", system_prompt)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("unloaded: Quiet Ember", session.respond("adventure unload"))
            self.assertEqual("Adventure workspace: none loaded.", session.respond("adventure status"))

    def test_programmatic_turn_candidate_inbox_is_cleared_on_adventure_mount_transition(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure create Other Ember")
            session.respond("adventure load Quiet Ember")
            batch = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The crew finds a brass key.",
                    "confidence": 0.8,
                }],
            })

            result = AdventureTurnGenerationResult(
                AdventureTurnGenerationRequest(
                    session.adventure_session.record, session.adventure_session.event_count,
                    "No authoritative events.", "I inspect the key.",
                    generation_id="TG-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                ), batch,
            )
            self.assertIn("Presented 1", session.present_adventure_turn_candidates(result))
            self.assertEqual("TC-001", session.select_adventure_turn_candidate("TC-001").candidate.candidate_id)
            session.respond("adventure load Other Ember")

            self.assertFalse(session.adventure_turn_candidate_inbox.active)
            with self.assertRaisesRegex(ValueError, "no adventure-turn candidates"):
                session.select_adventure_turn_candidate("TC-001")
            self.assertEqual([], calls)

    def test_explicit_generation_uses_the_injected_coordinator_and_only_populates_review_inbox(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            provider = self._CandidateProvider({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The hatch opens.",
                    "confidence": 0.8,
                }],
            })
            session = self._session(
                directory, calls, adventure_turn_coordinator=AdventureTurnCoordinator(provider),
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record

            response = session.generate_adventure_turn_candidates(
                user_text="I turn the brass key.", narrator_text="The lock clicks.",
            )

            self.assertIn("Presented 1 untrusted", response)
            self.assertEqual(1, len(provider.requests))
            self.assertEqual("TC-001", session.select_adventure_turn_candidate("TC-001").candidate.candidate_id)
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())
            self.assertFalse(session.adventure_turn.active)
            self.assertEqual([], calls)

    def test_exact_generate_command_requires_staging_and_only_fills_candidate_review_inbox(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            provider = self._CandidateProvider({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The brass hatch opens.",
                    "confidence": 0.9,
                }],
            })
            session = self._session(
                directory, calls, adventure_turn_coordinator=AdventureTurnCoordinator(provider),
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record

            self.assertIn("inactive", session.respond("adventure turn generate I open the hatch."))
            self.assertIn("staging started", session.respond("adventure turn begin"))
            self.assertIn("Usage:", session.respond("adventure turn generate"))
            self.assertIn("Presented 1 untrusted", session.respond("adventure turn generate I open the hatch."))
            self.assertIn("TC-001 [discovery]", session.respond("adventure turn candidates"))
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())
            self.assertEqual([], calls)

    def test_typed_generation_has_a_separate_inbox_and_requires_explicit_stage_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            provider = self._CandidateProvider({
                "schema_version": 1,
                "candidates": [{
                    "mutation": {"kind": "state_set", "key": "current_location", "value": "engine room"},
                    "confidence": 0.9,
                }],
            })
            session = self._session(
                directory, calls,
                adventure_turn_mutation_coordinator=AdventureTurnMutationCoordinator(provider),
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record

            self.assertIn("staging started", session.respond("adventure turn begin"))
            self.assertIn("Presented 1 untrusted typed", session.respond(
                "adventure turn mutations generate I enter the engine room."
            ))
            self.assertIn("TM-001 [state_set]", session.respond("adventure turn mutations"))
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())
            self.assertIn("Staged typed adventure-turn candidate TM-001", session.respond(
                "adventure turn stage mutation candidate TM-001"
            ))
            self.assertIn("Committed 1 staged adventure event", session.respond("adventure turn commit"))
            event = AdventureEventLog(session.adventure_registry, record).events()[0]
            self.assertEqual("state_change", event.event_type)
            self.assertEqual("engine room", event.state_value)
            self.assertEqual("TM-001", event.generation_provenance.candidate_id)
            self.assertEqual("adventure_turn_mutation_generation", event.generation_provenance.task_id)
            self.assertEqual([], calls)

    def test_transcript_generation_requires_explicit_completed_pair_and_keeps_it_untrusted(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            provider = self._CandidateProvider({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery", "summary": "The hatch opens.", "confidence": 0.9,
                }],
            })
            session = self._session(
                directory, calls, adventure_turn_coordinator=AdventureTurnCoordinator(provider),
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record
            session.respond("adventure turn begin")

            self.assertIn("requires the latest two explicit", session.respond("adventure turn generate transcript"))
            session.respond("adventure transcript record user: I turn the brass key.")
            session.respond("adventure transcript record narrator: The hatch groans open.")
            self.assertIn("Presented 1 untrusted", session.respond("adventure turn generate transcript"))
            self.assertEqual("I turn the brass key.", provider.requests[0].user_text)
            self.assertEqual("The hatch groans open.", provider.requests[0].narrator_text)
            self.assertEqual(("AT-000001", "AT-000002"), provider.requests[0].source_record_ids)
            self.assertIn("AT-000001 -> AT-000002", session.respond("adventure turn generation status"))
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())

    def test_default_generated_turn_flow_requires_review_stage_and_commit_before_any_event_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(
                directory, calls,
                chat_response={"message": {"content": json.dumps({
                    "schema_version": 1,
                    "candidates": [{
                        "event_type": "discovery",
                        "summary": "The brass hatch opens.",
                        "confidence": 0.9,
                    }],
                })}},
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record
            session.respond("adventure turn begin")

            self.assertIn("Presented 1 untrusted", session.respond(
                "adventure turn generate I turn the brass key in the hatch."
            ))
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())
            self.assertIn("TC-001 [discovery]", session.respond("adventure turn candidates"))
            self.assertIn("Staged adventure-turn candidate TC-001", session.respond(
                "adventure turn stage candidate TC-001"
            ))
            self.assertIn("Committed 1 staged adventure event", session.respond("adventure turn commit"))
            events = AdventureEventLog(session.adventure_registry, record).events()
            self.assertEqual(1, len(events))
            self.assertEqual("discovery", events[0].event_type)
            self.assertEqual("The brass hatch opens.", events[0].summary)
            self.assertIsNotNone(events[0].generation_provenance)
            self.assertEqual("adventure_turn_generation", events[0].generation_provenance.task_id)
            self.assertEqual("TC-001", session.adventure_turn_candidate_inbox.batch.candidates[0].candidate_id)
            audit = session.respond("adventure event provenance AE-000001")
            self.assertIn("Generation: TG-", audit)
            self.assertIn("Candidate: TC-001", audit)
            self.assertIn("raw prompts and provider output are not retained", audit)
            self.assertEqual(1, len(calls))
            self.assertFalse(calls[0].get("stream"))

    def test_default_generation_uses_the_dedicated_task_profile_and_fails_safely_on_invalid_output(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")

            with self.assertRaisesRegex(RuntimeError, "failed safely"):
                session.generate_adventure_turn_candidates(user_text="I wait.")
            self.assertFalse(session.adventure_turn_candidate_inbox.active)
            self.assertEqual(1, len(calls))
            status = session.respond("adventure turn generation status")
            self.assertIn("failed", status)
            self.assertIn("response_not_json", status)

    def test_failed_replacement_generation_clears_old_candidates_without_aborting_manual_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            provider = self._CandidateProvider({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery", "summary": "The hatch opens.", "confidence": 0.9,
                }],
            })
            session = self._session(
                directory, calls, adventure_turn_coordinator=AdventureTurnCoordinator(provider),
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure turn begin")
            self.assertIn("Presented 1 untrusted", session.respond("adventure turn generate I open the hatch."))
            self.assertIn("Staged adventure-turn candidate", session.respond("adventure turn stage candidate TC-001"))

            provider.payload = {"schema_version": 1, "candidates": []}
            self.assertIn(
                "failed safely", session.respond("adventure turn generate I wait."),
            )
            self.assertFalse(session.adventure_turn_candidate_inbox.active)
            self.assertTrue(session.adventure_turn.active)
            self.assertEqual(["The hatch opens."], [draft.summary for draft in session.adventure_turn.drafts])

    def test_programmatic_candidates_reject_a_generation_origin_that_became_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            batch = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The crew finds a brass key.",
                    "confidence": 0.8,
                }],
            })
            result = AdventureTurnGenerationResult(
                AdventureTurnGenerationRequest(
                    session.adventure_session.record, session.adventure_session.event_count,
                    "No authoritative events.", "I inspect the key.",
                    generation_id="TG-cccccccccccccccccccccccccccccccc",
                ), batch,
            )
            session.respond("adventure record discovery: A different clue is found.")

            with self.assertRaisesRegex(ValueError, "stale"):
                session.present_adventure_turn_candidates(result)
            self.assertFalse(session.adventure_turn_candidate_inbox.active)
            self.assertEqual([], calls)

    def test_exact_candidate_commands_review_and_stage_only_one_selected_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            batch = parse_untrusted_adventure_turn_candidates({
                "schema_version": 1,
                "candidates": [{
                    "event_type": "discovery",
                    "summary": "The crew finds a brass key.",
                    "confidence": 0.8,
                }],
            })
            result = AdventureTurnGenerationResult(
                AdventureTurnGenerationRequest(
                    session.adventure_session.record, session.adventure_session.event_count,
                    "No authoritative events.", "I inspect the key.",
                    generation_id="TG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                ), batch,
            )
            session.present_adventure_turn_candidates(result)

            review = session.respond("adventure turn candidates")
            self.assertIn("TC-001 [discovery]", review)
            self.assertIn("Generation: TG-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", review)
            self.assertIn("untrusted; not staged", review)
            self.assertIn("inactive", session.respond("adventure turn stage candidate TC-001"))
            session.respond("adventure turn begin")
            self.assertIn("Staged adventure-turn candidate TC-001", session.respond("adventure turn stage candidate tc-001"))
            self.assertIn("already staged", session.respond("adventure turn stage candidate TC-001"))
            self.assertIn("TC-001", session.respond("adventure turn inspect"))
            self.assertEqual([], calls)

    def test_load_reads_bounded_event_summaries_without_writing_or_calling_a_model(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            record = session.adventure_registry.resolve_title("Quiet Ember")
            log = AdventureEventLog(session.adventure_registry, record)
            for sequence in range(10):
                log.append("discovery", f"The crew discovers clue {sequence}.", details="Private event detail.")

            loaded = session.respond("adventure load Quiet Ember")
            self.assertIn("Loaded 10 authoritative event(s)", loaded)
            self.assertIn("10 authoritative event(s)", session.respond("adventure status"))
            displayed = session.respond("adventure events")
            self.assertIn("AE-000001", displayed)
            self.assertIn("AE-000010", displayed)
            self.assertNotIn("AE-000002", displayed)
            self.assertEqual([], calls)

            self.assertEqual("unexpected", session.respond("What was discovered?"))
            system_prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("RECENT AUTHORITATIVE ADVENTURE EVENTS", system_prompt)
            self.assertIn("clue 9", system_prompt)
            self.assertIn("clue 0", system_prompt)
            self.assertNotIn("clue 1", system_prompt)
            self.assertNotIn("Private event detail", system_prompt)
            self.assertIn(
                "10 authoritative event(s), 8 in bounded replay context; 0 authoritative state fact(s), 0 selected for context; 0 authoritative relationship fact(s), 0 selected for context; 0 authoritative character-knowledge fact(s), 0 selected for context; 0 declared resource(s), 0 public resource fact(s) selected for context; session-local mount",
                session.context_stats(),
            )

    def test_correction_audit_is_read_only_and_reports_active_and_superseded_history(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            record = session.adventure_session.record
            log = AdventureEventLog(session.adventure_registry, record)
            original = AdventureEvent.from_dict(AdventureEventEnvelope(
                sequence=1, event_id="AE-000001", event_type="state_change",
                recorded_at="2026-08-22T00:00:00+00:00", summary="The crew reaches the bridge.", details=None,
                mutation=AdventureMutation(MUTATION_STATE_SET, state_key="location", state_value="bridge"),
            ).to_dict())
            correction = AdventureEvent.from_dict(AdventureEventEnvelope(
                sequence=2, event_id="AE-000002", event_type="state_change",
                recorded_at="2026-08-22T00:01:00+00:00", summary="The crew reaches the engine room.", details=None,
                supersedes_event_id="AE-000001",
                mutation=AdventureMutation(MUTATION_STATE_SET, state_key="location", state_value="engine room"),
            ).to_dict())
            log.path.write_text(
                "\n".join(json.dumps(event.to_dict()) for event in (original, correction)) + "\n",
                encoding="utf-8",
            )

            inspection = session.respond("adventure corrections")

            self.assertIn("AE-000001 [state_change] superseded by AE-000002", inspection)
            self.assertIn("AE-000002 [state_change] active", inspection)
            self.assertEqual(2, len(log.events()))
            self.assertEqual([], calls)
            self.assertEqual([], session.messages)

    def test_explicit_record_isolated_and_ordinary_chat_never_creates_events(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertIn("none loaded", session.respond("adventure record discovery: A signal appears."))
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertEqual("unexpected", session.respond("The crew finds a signal."))
            self.assertEqual("No authoritative adventure events are recorded for the loaded workspace.", session.respond("adventure events"))

            recorded = session.respond("adventure record discovery: The crew finds an old signal.")
            self.assertIn("AE-000001 [discovery]", recorded)
            self.assertIn("The crew finds an old signal.", session.respond("adventure events"))
            self.assertEqual("Usage: adventure record <event-type>: <summary>", session.respond("adventure record discovery"))
            self.assertIn("unsupported", session.respond("adventure record decoration: The ship is pretty."))
            self.assertEqual(1, session.adventure_session.event_count)
            self.assertEqual([], session.proposals)

    def test_resume_pause_and_end_are_exact_core_lifecycle_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure record discovery: The ship has a hidden deck.")
            session.respond("roleplay begin Quiet Ember")

            paused = session.respond("adventure pause")
            self.assertIn("Adventure paused: Quiet Ember", paused)
            self.assertIn("Roleplay mode ended", paused)
            self.assertFalse(session.adventure_session.active)
            self.assertFalse(session.roleplay_state.active)
            self.assertEqual([], calls)

            resumed = session.respond("adventure resume Quiet Ember")
            self.assertIn("Loaded 1 authoritative event(s)", resumed)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("hidden deck", session.respond("adventure events"))

            session.respond("roleplay begin")
            ended = session.respond("end story now")
            self.assertIn("Adventure session ended: Quiet Ember", ended)
            self.assertIn("Stored events were preserved", ended)
            self.assertFalse(session.adventure_session.active)
            self.assertFalse(session.roleplay_state.active)
            self.assertEqual("No active adventure or roleplay session is running.", session.respond("adventure end"))

    def test_begin_binds_one_existing_workspace_to_roleplay_without_writing_events(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            record = session.adventure_registry.resolve_title("Quiet Ember")
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())

            started = session.respond("adventure begin Quiet Ember")

            self.assertIn("Adventure story session started: Quiet Ember.", started)
            self.assertTrue(session.adventure_session.active)
            self.assertTrue(session.roleplay_state.active)
            self.assertEqual("Quiet Ember", session.roleplay_state.title)
            self.assertEqual([], AdventureEventLog(session.adventure_registry, record).events())
            self.assertIn("loaded adventure: Quiet Ember", session.respond("roleplay status"))
            self.assertEqual("Usage: adventure begin <title>", session.respond("adventure begin"))
            self.assertEqual([], calls)

    def test_session_status_reports_only_the_current_lifecycle_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)

            unbound = session.respond("adventure session")

            self.assertIn("Workspace: none loaded", unbound)
            self.assertIn("Persona:", unbound)
            self.assertIn("Roleplay: inactive", unbound)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure begin Quiet Ember")
            bound = session.respond("adventure session status")
            self.assertIn("Workspace: Quiet Ember", bound)
            self.assertIn("Roleplay: active (Quiet Ember)", bound)
            self.assertIn("Branch: root workspace", bound)
            self.assertNotIn("static identity", bound.casefold())
            self.assertEqual([], calls)

    def test_explicit_story_state_is_event_backed_and_refreshed_in_context(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertEqual("No explicit authoritative story state is recorded for the loaded workspace.", session.respond("adventure state"))
            self.assertIn("AE-000001", session.respond("adventure state set location: bridge"))
            self.assertIn("location: bridge", session.respond("adventure state"))
            self.assertIn("AE-000002", session.respond("adventure state set location: engine room"))
            self.assertIn("location: engine room (AE-000002)", session.respond("adventure state"))
            self.assertEqual("Usage: adventure state set <key>: <value>", session.respond("adventure state set location"))
            self.assertIn("state key", session.respond("adventure state set Current Location: bridge"))
            self.assertEqual([], calls)

            self.assertEqual("unexpected", session.respond("Where is the crew?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("CURRENT AUTHORITATIVE STORY STATE", prompt)
            self.assertIn("location: engine room", prompt)
            self.assertNotIn("location: bridge\n", prompt)
            self.assertIn("1 authoritative state fact(s), 1 selected for context", session.context_stats())

    def test_explicit_state_correction_replaces_current_projection_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure state set location: bridge")

            corrected = session.respond("adventure correct state AE-000001 location: engine room")

            self.assertIn("Corrected adventure state with AE-000002, superseding AE-000001.", corrected)
            self.assertIn("location: engine room (AE-000002)", session.respond("adventure state"))
            audit = session.respond("adventure corrections")
            self.assertIn("AE-000001 [state_change] superseded by AE-000002", audit)
            self.assertIn("AE-000002 [state_change] active", audit)
            self.assertIn("not currently active", session.respond("adventure correct state AE-000001 location: deck"))
            self.assertEqual([], calls)

    def test_explicit_retraction_removes_current_projection_without_deleting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure state set location: bridge")

            retracted = session.respond("adventure retract AE-000001: Incorrect source note")

            self.assertEqual("Retracted adventure event AE-000001 with AE-000002.", retracted)
            self.assertEqual(
                "No explicit authoritative story state is recorded for the loaded workspace.",
                session.respond("adventure state"),
            )
            audit = session.respond("adventure corrections")
            self.assertIn("AE-000001 [state_change] retracted by AE-000002", audit)
            self.assertIn("AE-000002 [retraction] active", audit)
            self.assertIn("not currently active", session.respond("adventure retract AE-000001: Retry"))
            self.assertIn("require `adventure retract", session.respond("adventure record retraction: no"))
            self.assertEqual([], calls)

    def test_checkpoint_commands_create_and_inspect_an_immutable_event_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure record discovery: The crew finds a brass key.")

            created = session.respond("adventure checkpoint Before the hatch")

            self.assertIn("Created adventure checkpoint CP-000001: Before the hatch", created)
            listed = session.respond("adventure checkpoints")
            self.assertIn("CP-000001 Before the hatch (1 authoritative event(s); AE-000001)", listed)
            inspected = session.respond("adventure checkpoint inspect CP-000001")
            self.assertIn("Adventure checkpoint CP-000001: Before the hatch", inspected)
            self.assertIn("Authoritative prefix: 1 event(s); AE-000001.", inspected)
            self.assertIn("no session state, event history, restore, or branch changed", inspected)
            self.assertIn("already exists", session.respond("adventure checkpoint before the hatch"))
            self.assertEqual([], calls)

    def test_fresh_restart_creates_and_mounts_an_isolated_workspace_without_deleting_the_previous_one(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure record discovery: The old story remains here.")
            session.respond("roleplay begin")

            restarted = session.respond("adventure restart fresh New Ember")

            self.assertIn("Fresh adventure started: New Ember.", restarted)
            self.assertIn("Previous adventure preserved: Quiet Ember.", restarted)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("New Ember", session.respond("adventure status"))
            self.assertEqual(
                "No authoritative adventure events are recorded for the loaded workspace.",
                session.respond("adventure events"),
            )
            session.respond("adventure load Quiet Ember")
            self.assertIn("old story remains", session.respond("adventure events"))
            self.assertEqual([], calls)

    def test_established_restart_forks_only_the_verified_checkpoint_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure record discovery: The crew finds a brass key.")
            session.respond("adventure checkpoint Before the hatch")
            session.respond("adventure record choice: The parent opens the hatch.")
            session.respond("roleplay begin")

            restarted = session.respond("adventure restart established CP-000001: Forked Ember")

            self.assertIn("Established-premise adventure started: Forked Ember.", restarted)
            self.assertIn("copied 1 authoritative event(s)", restarted)
            self.assertFalse(session.roleplay_state.active)
            self.assertIn("brass key", session.respond("adventure events"))
            self.assertNotIn("parent opens", session.respond("adventure events"))
            self.assertIn("Branch origin:", session.respond("adventure inspect Forked Ember"))
            session.respond("adventure load Quiet Ember")
            self.assertIn("parent opens", session.respond("adventure events"))
            self.assertIn("Usage:", session.respond("adventure restart established CP-000001"))
            self.assertEqual([], calls)

    def test_mounted_resources_keep_complete_values_but_only_public_values_reach_core_context(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            record = session.adventure_registry.resolve_title("Quiet Ember")
            catalog = AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
                AdventureResourceDefinition("primary_slot", "Primary slot", "equipment", visibility="hidden"),
            ))
            session.adventure_registry.configure_resource_catalog(record, catalog)
            log = AdventureEventLog(session.adventure_registry, record)
            log.append(
                "resource_change", "Fuel reserve increases.",
                resource_id="fuel", resource_operation="increment", resource_value=20,
            )
            log.append(
                "resource_change", "A brass key is equipped.",
                resource_id="primary_slot", resource_operation="equip", resource_value="brass key",
            )

            session.respond("adventure load Quiet Ember")
            listed = session.respond("adventure resources")
            self.assertIn("fuel (Fuel): 20", listed)
            self.assertNotIn("primary_slot", listed)
            self.assertIn("2 declared resource(s), 1 public resource fact(s)", session.respond("adventure status"))
            self.assertEqual("unexpected", session.respond("What resources are available?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("CURRENT PUBLIC ADVENTURE RESOURCES", prompt)
            self.assertIn("fuel (Fuel): 20", prompt)
            self.assertNotIn("primary_slot", prompt)
            self.assertIn("2 declared resource(s), 1 public resource fact(s)", session.context_stats())

    def test_explicit_resource_controls_validate_catalog_and_stage_atomically_without_hidden_leaks(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            record = session.adventure_registry.resolve_title("Quiet Ember")
            session.adventure_registry.configure_resource_catalog(record, AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
                AdventureResourceDefinition("primary_slot", "Primary slot", "equipment", visibility="hidden"),
            )))
            session.respond("adventure load Quiet Ember")

            self.assertIn("fuel (Fuel)", session.respond("adventure resource fuel increment: 20"))
            self.assertIn("fuel (Fuel): 20", session.respond("adventure resources"))
            self.assertIn("outside declared bounds", session.respond("adventure resource fuel decrement: 21"))
            self.assertIn("fuel (Fuel): 20", session.respond("adventure resources"))

            self.assertIn("Adventure turn staging started", session.respond("adventure turn begin"))
            # Stage the public and hidden operations; both remain invisible
            # until the transaction commits.
            self.assertIn("Staged adventure resource fuel", session.respond("adventure turn stage resource fuel increment: 10"))
            self.assertEqual("Staged a hidden adventure resource change.", session.respond(
                "adventure turn stage resource primary_slot equip: brass key",
            ))
            self.assertIn("fuel (Fuel): 20", session.respond("adventure resources"))
            self.assertIn("Committed 2 staged adventure event(s)", session.respond("adventure turn commit"))
            self.assertIn("fuel (Fuel): 30", session.respond("adventure resources"))
            self.assertNotIn("primary_slot", session.respond("adventure resources"))

            self.assertEqual("unexpected", session.respond("What resources are available?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("fuel (Fuel): 30", prompt)
            self.assertNotIn("primary_slot", prompt)
            self.assertNotIn("brass key", prompt)
            self.assertEqual([], session.proposals)

    def test_full_state_inspection_survives_bounded_prompt_context_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            for index in range(13):
                session.respond(f"adventure state set fact_{index:02}: value {index}")

            inspection = session.respond("adventure state")
            self.assertIn("fact_12: value 12", inspection)
            self.assertIn("13 authoritative state fact(s), 12 selected for context", session.respond("adventure status"))

            self.assertEqual("unexpected", session.respond("What is the current story state?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("13 total fact(s); 12 selected for bounded context.", prompt)
            self.assertIn("fact_00: value 0", prompt)
            self.assertNotIn("fact_12: value 12", prompt)
            self.assertIn("13 authoritative state fact(s), 12 selected for context", session.context_stats())

            session.respond("adventure pause")
            session.respond("adventure resume Quiet Ember")
            self.assertIn("fact_12: value 12", session.respond("adventure state"))

    def test_explicit_qualitative_relationship_is_event_backed_and_refreshed_in_context(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertEqual(
                "No explicit authoritative adventure relationships are recorded for the loaded workspace.",
                session.respond("adventure relationships"),
            )
            self.assertIn(
                "AE-000001",
                session.respond("adventure relationship set Vespera trust: guarded"),
            )
            self.assertIn("Vespera / trust: guarded", session.respond("adventure relationships"))
            self.assertIn(
                "AE-000002",
                session.respond("adventure relationship set Vespera trust: cautious"),
            )
            self.assertIn(
                "Vespera / trust: cautious (AE-000002)",
                session.respond("adventure relationships"),
            )
            self.assertEqual(
                "Usage: adventure relationship set <character> <dimension>: <value>",
                session.respond("adventure relationship set Vespera"),
            )
            self.assertIn(
                "relationship dimension",
                session.respond("adventure relationship set Vespera trust-level: cautious"),
            )
            self.assertEqual([], calls)

            self.assertEqual("unexpected", session.respond("How does Vespera feel about us?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("CURRENT AUTHORITATIVE ADVENTURE RELATIONSHIPS", prompt)
            self.assertIn("Vespera / trust: cautious", prompt)
            self.assertNotIn("Vespera / trust: guarded\n", prompt)
            self.assertIn("1 authoritative relationship fact(s), 1 selected for context", session.context_stats())

    def test_mounted_adventure_hides_imported_numeric_relationship_meters_unless_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            relationship = {
                "id": 9, "memory_type": "relationship_context", "summary": "Vespera trust level",
                "details": "Trust: 49/100. Comfort at 58 / 100.", "confidence": 0.9,
            }
            registry = AdventureRegistry(directory, now=lambda: datetime(2026, 8, 15, tzinfo=UTC))
            session = AssistantSession(
                self._config(), "Persona", policy="Policy", adventure_registry=registry,
                chat=lambda **kwargs: calls.append(kwargs) or {"message": {"content": "unexpected"}},
                memory_loader=lambda **kwargs: [relationship],
            )
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")

            self.assertEqual("unexpected", session.respond("How does Vespera feel about us?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertNotIn("49/100", prompt)
            self.assertNotIn("58 / 100", prompt)
            self.assertIn("qualitative internal state", prompt)
            self.assertEqual("Trust: 49/100. Comfort at 58 / 100.", relationship["details"])

            self.assertEqual("unexpected", session.respond("Show Vespera's internal relationship meter scores."))
            self.assertIn("49/100", calls[-1]["messages"][0]["content"])

    def test_explicit_character_knowledge_is_event_backed_and_perspective_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertEqual(
                "No explicit character knowledge or beliefs are recorded for the loaded workspace.",
                session.respond("adventure knowledge"),
            )
            self.assertIn(
                "AE-000001",
                session.respond("adventure knowledge set Vespera believes: the hatch is trapped"),
            )
            self.assertIn("Vespera believes: the hatch is trapped", session.respond("adventure knowledge"))
            self.assertIn(
                "AE-000002",
                session.respond("adventure knowledge set Vespera uncertain: the hatch is trapped"),
            )
            self.assertIn(
                "Vespera uncertain: the hatch is trapped (AE-000002)",
                session.respond("adventure knowledge"),
            )
            self.assertEqual(
                "Usage: adventure knowledge set <character> <knows|believes|uncertain>: <fact>",
                session.respond("adventure knowledge set Vespera"),
            )
            self.assertIn(
                "knowledge status",
                session.respond("adventure knowledge set Vespera guesses: the hatch is trapped"),
            )
            self.assertEqual([], calls)

            self.assertEqual("unexpected", session.respond("What does Vespera know about the hatch?"))
            prompt = calls[-1]["messages"][0]["content"]
            self.assertIn("CHARACTER KNOWLEDGE AND BELIEFS", prompt)
            self.assertIn("Vespera uncertain: the hatch is trapped", prompt)
            self.assertIn("not automatically objective world truth", prompt)
            self.assertIn("1 authoritative character-knowledge fact(s), 1 selected for context", session.context_stats())

    def test_transcript_commands_do_not_create_story_events_or_call_a_model(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")

            self.assertEqual(
                "No presentation transcript is recorded for the loaded workspace.",
                session.respond("adventure transcript"),
            )
            recorded = session.respond(
                "adventure transcript record narrator: The brass hatch groans but stays sealed."
            )
            self.assertIn("AT-000001 [narrator]", recorded)
            transcript = session.respond("adventure transcript")
            self.assertIn("AT-000001 [narrator] The brass hatch groans but stays sealed.", transcript)
            self.assertIn("do not establish adventure events or state", transcript)
            self.assertEqual(
                "No authoritative adventure events are recorded for the loaded workspace.",
                session.respond("adventure events"),
            )
            self.assertEqual(
                "Usage: adventure transcript record <user|narrator>: <text>",
                session.respond("adventure transcript record narrator"),
            )
            self.assertEqual([], calls)
            self.assertEqual([], session.proposals)

    def test_import_bundles_group_multiple_staged_sources_without_canonical_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            staged = AdventureImportLog(session.adventure_registry, session.adventure_session.record)
            for review_id, filename, text in (
                ("DR-details", "details.md", "# Details\n\nVespera guards the hatch."),
                ("DR-transcript", "conversation.md", "# Conversation\n\nThe crew finds a brass key."),
            ):
                document = prepare_document_text(text, filename, domain="personal")
                candidate = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [{
                    "store": True, "subject": "story", "memory_type": "project_context",
                    "summary": f"Reviewed {filename}", "details": text,
                    "importance": 0.8, "confidence": 0.9, "retention": "long_term",
                }]})[0]
                staged.stage(review_id=review_id, document=document, selected=(("C-001", candidate),))

            created = session.respond(
                "adventure import bundle create Quiet Ember source set: AI-000001 AI-000002"
            )
            self.assertIn("Created multi-document import bundle: Quiet Ember source set (AB-000001; 2 staged source(s))", created)
            self.assertIn(
                "AB-000001 Quiet Ember source set (2 staged source(s))",
                session.respond("adventure import bundles"),
            )
            inspected = session.respond("adventure import bundle inspect AB-000001")
            self.assertIn("AI-000001 details.md [assistant_note]", inspected)
            self.assertIn("AI-000002 conversation.md [assistant_note]", inspected)
            self.assertIn("not an adventure event, state, replay fact, memory, or prompt context", inspected)
            audit = session.respond("adventure import bundle status AB-000001")
            self.assertIn("AI-000001:", audit)
            self.assertIn("C-001: current plan unmapped; canonical history: none", audit)
            self.assertIn("AI-000002:", audit)
            self.assertIn("no mapping, event, state, memory, or prompt context was changed", audit)
            self.assertIn(
                "AB-000001",
                session.respond("adventure import bundle create Quiet Ember source set: AI-000001 AI-000002"),
            )
            self.assertIn(
                "references a missing staged import",
                session.respond("adventure import bundle create Bad set: AI-000001 AI-000099"),
            )
            self.assertEqual(
                "Usage: adventure import bundle create <title>: <AI-######> <AI-######> [... ]",
                session.respond("adventure import bundle create"),
            )
            self.assertEqual(
                "Usage: adventure import bundle status <AB-######>",
                session.respond("adventure import bundle status"),
            )
            self.assertEqual([], AdventureEventLog(session.adventure_registry, session.adventure_session.record).events())
            self.assertEqual([], calls)
            self.assertEqual([], session.proposals)

    def test_staged_import_mapping_and_typed_commits_are_explicit_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            catalog = AdventureResourceCatalog((
                AdventureResourceDefinition("fuel", "Fuel", "integer", minimum=0, maximum=100),
            ))
            session.adventure_registry.configure_resource_catalog(session.adventure_session.record, catalog)
            session.adventure_session = session.adventure_session.mount(
                session.adventure_session.record, (), resource_catalog=catalog,
            )
            document = prepare_document_text("# Story\n\nVespera guards the brass hatch.", "story.md", domain="personal")
            candidate = extract_document_memory_candidates(document, lambda _chunk: {"proposals": [{
                "store": True, "subject": "Vespera", "memory_type": "project_context",
                "summary": "Vespera guards the brass hatch", "details": "Vespera guards the brass hatch.",
                "importance": 0.8, "confidence": 0.9, "retention": "long_term",
            }]})[0]
            AdventureImportLog(session.adventure_registry, session.adventure_session.record).stage(
                review_id="DR-reviewed", document=document, selected=(("C-001", candidate),),
            )

            listing = session.respond("adventure imports")
            self.assertIn("AI-000001 story.md [assistant_note] (1 candidate(s))", listing)
            self.assertIn("not authoritative adventure events or state", listing)
            inspection = session.respond("adventure import inspect AI-000001")
            self.assertIn("Adventure import AI-000001", inspection)
            self.assertIn("C-001 [project_context] Vespera guards the brass hatch", inspection)
            self.assertIn("not adventure events, state, replay facts, or memories", inspection)
            self.assertEqual("Adventure import not found.", session.respond("adventure import inspect AI-999999"))
            mapped = session.respond("adventure import map AI-000001 C-001 premise")
            self.assertIn("Mapped AI-000001 C-001 to premise", mapped)
            self.assertIn(
                "C-001 -> premise (IM-000001)",
                session.respond("adventure import mappings AI-000001"),
            )
            committed = session.respond("adventure import commit premise AI-000001 C-001")
            self.assertIn("Committed mapped premise AI-000001 C-001 as AE-000001", committed)
            self.assertIn("[premise] Vespera guards the brass hatch", session.respond("adventure events"))
            self.assertIn("AE-000001", session.respond("adventure import commit premise AI-000001 C-001"))
            self.assertEqual(
                1,
                len(AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()),
            )
            self.assertIn("Mapped AI-000001 C-001 to state", session.respond("adventure import map AI-000001 C-001 state"))
            imported_state = session.respond(
                "adventure import commit state AI-000001 C-001 current_location: chart room"
            )
            self.assertIn("Committed mapped state AI-000001 C-001 as AE-000002", imported_state)
            self.assertIn("current_location = chart room", imported_state)
            self.assertIn("current_location: chart room (AE-000002)", session.respond("adventure state"))
            self.assertIn(
                "AE-000002",
                session.respond("adventure import commit state AI-000001 C-001 current_location: chart room"),
            )
            self.assertEqual(
                2,
                len(AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()),
            )
            self.assertIn(
                "Mapped AI-000001 C-001 to relationship",
                session.respond("adventure import map AI-000001 C-001 relationship"),
            )
            imported_relationship = session.respond(
                "adventure import commit relationship AI-000001 C-001 Vespera trust: cautious"
            )
            self.assertIn("Committed mapped relationship AI-000001 C-001 as AE-000003", imported_relationship)
            self.assertIn("Vespera / trust = cautious", imported_relationship)
            self.assertIn("Vespera / trust: cautious (AE-000003)", session.respond("adventure relationships"))
            self.assertIn(
                "AE-000003",
                session.respond("adventure import commit relationship AI-000001 C-001 Vespera trust: cautious"),
            )
            self.assertEqual(
                3,
                len(AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()),
            )
            self.assertIn(
                "Mapped AI-000001 C-001 to knowledge",
                session.respond("adventure import map AI-000001 C-001 knowledge"),
            )
            imported_knowledge = session.respond(
                "adventure import commit knowledge AI-000001 C-001 Rook believes: the hatch is trapped"
            )
            self.assertIn("Committed mapped knowledge AI-000001 C-001 as AE-000004", imported_knowledge)
            self.assertIn("Rook believes = the hatch is trapped", imported_knowledge)
            self.assertIn("Rook believes: the hatch is trapped (AE-000004)", session.respond("adventure knowledge"))
            self.assertIn(
                "AE-000004",
                session.respond("adventure import commit knowledge AI-000001 C-001 Rook believes: the hatch is trapped"),
            )
            self.assertEqual(
                4,
                len(AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()),
            )
            self.assertIn(
                "Mapped AI-000001 C-001 to resource",
                session.respond("adventure import map AI-000001 C-001 resource"),
            )
            imported_resource = session.respond(
                "adventure import commit resource AI-000001 C-001 fuel set: 80"
            )
            self.assertIn("Committed mapped resource AI-000001 C-001 as AE-000005", imported_resource)
            self.assertIn("fuel set", imported_resource)
            self.assertIn("fuel (Fuel): 80 (AE-000005)", session.respond("adventure resources"))
            self.assertIn(
                "AE-000005",
                session.respond("adventure import commit resource AI-000001 C-001 fuel set: 80"),
            )
            self.assertEqual(
                5,
                len(AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()),
            )
            self.assertIn("Mapped AI-000001 C-001 to exclude", session.respond("adventure import map AI-000001 C-001 exclude"))
            audit = session.respond("adventure import status AI-000001")
            self.assertIn("C-001: current plan exclude (IM-000006)", audit)
            self.assertIn(
                "canonical history: AE-000001 [premise], AE-000002 [state_change], "
                "AE-000003 [relationship_change], AE-000004 [character_knowledge], AE-000005 [resource_change]",
                audit,
            )
            self.assertIn("`exclude` changes only the current plan", audit)
            self.assertEqual("Adventure import not found.", session.respond("adventure import status AI-999999"))
            self.assertEqual(
                "Usage: adventure import status <AI-######>",
                session.respond("adventure import status"),
            )
            self.assertEqual(
                "Usage: adventure import map <AI-######> <C-###> <premise|state|relationship|knowledge|resource|exclude>",
                session.respond("adventure import map AI-000001 C-001"),
            )
            self.assertIn("mapped to exclude, not premise", session.respond("adventure import commit premise AI-000001 C-001"))
            self.assertIn("mapped to exclude, not state", session.respond("adventure import commit state AI-000001 C-001 current_location: chart room"))
            self.assertIn("mapped to exclude, not relationship", session.respond("adventure import commit relationship AI-000001 C-001 Vespera trust: cautious"))
            self.assertIn("mapped to exclude, not knowledge", session.respond("adventure import commit knowledge AI-000001 C-001 Rook believes: the hatch is trapped"))
            self.assertIn("mapped to exclude, not resource", session.respond("adventure import commit resource AI-000001 C-001 fuel set: 80"))
            self.assertEqual([], calls)
            self.assertEqual([], session.proposals)

    def test_explicit_adventure_turn_staging_commits_or_aborts_as_one_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            self.assertIn("none loaded", session.respond("adventure turn begin"))
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            self.assertIn("staging started", session.respond("adventure turn begin"))
            self.assertIn("[discovery]", session.respond("adventure turn stage discovery: The crew finds a hatch."))
            self.assertIn("[choice]", session.respond("adventure turn stage choice: The crew opens it."))
            self.assertIn("2 event(s) staged", session.respond("adventure turn status"))
            inspection = session.respond("adventure turn inspect")
            self.assertIn("1. [discovery] The crew finds a hatch.", inspection)
            self.assertIn("2. [choice] The crew opens it.", inspection)
            self.assertIn("nothing has been committed", inspection)
            self.assertEqual("No authoritative adventure events are recorded for the loaded workspace.", session.respond("adventure events"))
            removed = session.respond("adventure turn remove 1")
            self.assertIn("Removed staged adventure event [discovery]: The crew finds a hatch.", removed)
            self.assertIn("1. [choice] The crew opens it.", session.respond("adventure turn inspect"))
            self.assertIn("Committed 1 staged adventure event(s): AE-000001 through AE-000001.", session.respond("adventure turn commit"))
            self.assertNotIn("finds a hatch", session.respond("adventure events"))
            self.assertIn("AE-000001 [choice] The crew opens it.", session.respond("adventure events"))

            session.respond("adventure turn begin")
            session.respond("adventure turn stage state current_location: chart room")
            session.respond("adventure turn stage discovery: A second hatch appears.")
            self.assertIn("Removed staged adventure event [state_change]", session.respond("adventure turn remove 1"))
            self.assertIn("1. [discovery] A second hatch appears.", session.respond("adventure turn inspect"))
            self.assertIn("staged event number is invalid", session.respond("adventure turn remove 2"))
            self.assertEqual("Usage: adventure turn remove <staged-event-number>", session.respond("adventure turn remove nope"))
            session.respond("adventure turn abort")
            committed = AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()
            self.assertEqual(1, len({event.request_id for event in committed}))
            self.assertIsNotNone(committed[0].request_id)
            self.assertEqual("Adventure turn staging: inactive.", session.respond("adventure turn status"))
            self.assertEqual("Adventure turn staging: inactive.", session.respond("adventure turn inspect"))

            session.respond("adventure turn begin")
            session.respond("adventure turn stage discovery: A second hatch appears.")
            self.assertIn("Discarded 1 staged adventure event(s)", session.respond("adventure turn abort"))
            self.assertNotIn("second hatch", session.respond("adventure events"))
            self.assertEqual([], calls)

    def test_staged_structured_facts_remain_invisible_until_one_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            session = self._session(directory, calls)
            session.respond("adventure create Quiet Ember")
            session.respond("adventure load Quiet Ember")
            session.respond("adventure turn begin")
            self.assertIn("[discovery]", session.respond(
                "adventure turn stage discovery: The crew finds a hatch."
            ))
            self.assertIn("state", session.respond(
                "adventure turn stage state current_location: chart room"
            ))
            self.assertIn("relationship", session.respond(
                "adventure turn stage relationship Vespera trust: cautious"
            ))
            self.assertIn("character knowledge", session.respond(
                "adventure turn stage knowledge Rook believes: the hatch is trapped"
            ))
            self.assertIn("4 event(s) staged", session.respond("adventure turn status"))
            self.assertEqual(
                "No explicit authoritative story state is recorded for the loaded workspace.",
                session.respond("adventure state"),
            )
            self.assertEqual(
                "No explicit authoritative adventure relationships are recorded for the loaded workspace.",
                session.respond("adventure relationships"),
            )
            self.assertEqual(
                "No explicit character knowledge or beliefs are recorded for the loaded workspace.",
                session.respond("adventure knowledge"),
            )
            self.assertIn("Committed 4 staged adventure event(s)", session.respond("adventure turn commit"))
            self.assertIn("current_location: chart room", session.respond("adventure state"))
            self.assertIn("Vespera / trust: cautious", session.respond("adventure relationships"))
            self.assertIn("Rook believes: the hatch is trapped", session.respond("adventure knowledge"))
            events = AdventureEventLog(session.adventure_registry, session.adventure_session.record).events()
            self.assertEqual(
                ["discovery", "state_change", "relationship_change", "character_knowledge"],
                [event.event_type for event in events],
            )
            self.assertEqual(1, len({event.request_id for event in events}))
            self.assertEqual([], calls)

            session.respond("adventure turn begin")
            self.assertEqual(
                "Usage: adventure turn stage state <key>: <value>",
                session.respond("adventure turn stage state current_location"),
            )
            self.assertEqual(
                "Usage: adventure turn stage relationship <character> <dimension>: <value>",
                session.respond("adventure turn stage relationship Vespera"),
            )
            self.assertIn(
                "knowledge status is unsupported",
                session.respond("adventure turn stage knowledge Rook guesses: the hatch is trapped"),
            )
            self.assertEqual(
                "Adventure turn has no staged events. Stage an event or abort the turn.",
                session.respond("adventure turn commit"),
            )
            self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
