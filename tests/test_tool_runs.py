import errno
import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_contracts import ToolProposal, build_core_tool_contract_registry
from pipeline.tool_grants import ToolInvocationIssuer
from pipeline.tool_runs import (
    MAX_TOOL_RUN_JOURNAL_BYTES,
    MAX_TOOL_RUN_RECORD_BYTES,
    TOOL_RUN_JOURNAL_SCHEMA_VERSION,
    ToolRunJournal,
    ToolRunJournalError,
    ToolRunReplayError,
)


def proposal(objective="Verify journal."):
    return ToolProposal.from_mapping({
        "schema_version": 1, "tool_id": "sandbox.run", "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests", "objective": objective,
            "files": [{"path": "main.py", "content": "print('journal')"}],
        },
    })


class ToolRunJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.contracts = build_core_tool_contract_registry()
        self._owned_journals = []

    def owned_journal(
        self, root=None, *, clock=lambda: 1001.0, maximum_records=1024,
        owner_id="core.test", owner_epoch="TO-owner-001",
    ):
        journal = ToolRunJournal(
            self.root if root is None else root,
            clock=clock,
            maximum_records=maximum_records,
            owner_epoch_factory=lambda: owner_epoch,
        )
        owner = journal.acquire_owner(owner_id)

        def release_if_active():
            if owner.active:
                journal.release_owner(owner)

        self._owned_journals.append((journal, owner))
        return journal, owner

    def tearDown(self):
        for journal, owner in reversed(self._owned_journals):
            if owner.active:
                journal.release_owner(owner)
        self.temporary.cleanup()

    def invocation(self, run_id="TI-run_1", *, expires_at=1300.0, objective="Verify journal."):
        issuer = ToolInvocationIssuer(self.contracts, clock=lambda: expires_at - 300.0)
        return issuer.issue(
            proposal(objective), invocation_id=run_id, trusted_principal_id="local.owner",
            session_instance_id="session-001", persona_id="murr", adventure_id=None,
            policy_revision="policy-v1", lifetime_seconds=300,
        )

    @staticmethod
    def record(sequence, kind, run_id="TI-run_1", **overrides):
        values = {
            "schema_version": TOOL_RUN_JOURNAL_SCHEMA_VERSION,
            "sequence": sequence,
            "kind": kind,
            "run_id": run_id,
            "tool_id": "sandbox.run",
            "tool_version": 1,
            "session_instance_id": "session-001",
            "binding_fingerprint": "a" * 64,
            "owner_id": "core.test",
            "owner_epoch": "TO-owner-001",
            "expires_at": 1300.0,
            "state": "awaiting_approval" if kind == "intent" else "completed",
            "reason": "submitted" if kind == "intent" else "completed",
            "timestamp": 1000.0 + sequence,
        }
        values.update(overrides)
        return values

    def write_records(self, *records):
        self.root.joinpath("tool-runs.jsonl").write_text(
            "".join(json.dumps(item, allow_nan=True) + "\n" for item in records),
            encoding="utf-8",
        )

    def test_intent_outcome_round_trip_is_payload_free_and_idempotent(self):
        journal, owner = self.owned_journal()
        invocation = self.invocation()
        intent = journal.record_intent(invocation, owner=owner)
        with self.assertRaisesRegex(ToolRunReplayError, "already admitted"):
            journal.record_intent(invocation, owner=owner)
        outcome = journal.record_outcome(
            invocation, owner=owner, state="completed", reason="completed",
        )

        self.assertEqual(("intent", "outcome"), tuple(item.kind for item in journal.records()))
        self.assertEqual("completed", outcome.state)
        rendered = journal.path.read_text(encoding="utf-8")
        for forbidden in ("arguments", "objective", "files", "operation_digest", "resource_refs"):
            self.assertNotIn(forbidden, rendered)
        self.assertEqual(outcome, journal.record_outcome(
            invocation, owner=owner, state="completed", reason="completed",
        ))
        with self.assertRaisesRegex(ToolRunJournalError, "conflicting"):
            journal.record_outcome(
                invocation, owner=owner, state="failed", reason="failed",
            )

    def test_restart_reconciliation_marks_intent_unknown_without_execution(self):
        invocation = self.invocation(expires_at=1300.0)
        first, first_owner = self.owned_journal(owner_epoch="TO-owner-001")
        first.record_intent(invocation, owner=first_owner)
        first.release_owner(first_owner)

        restarted, restarted_owner = self.owned_journal(
            clock=lambda: 1100.0, owner_epoch="TO-owner-002",
        )
        recovered = restarted.reconcile(owner=restarted_owner)

        self.assertEqual(1, len(recovered))
        self.assertEqual(("outcome_unknown", "restart_reconciliation"), (
            recovered[0].state, recovered[0].reason,
        ))
        self.assertEqual((), restarted.reconcile(owner=restarted_owner))

    def test_expired_session_is_unknown_not_authorized(self):
        invocation = self.invocation(expires_at=1100.0)
        journal, owner = self.owned_journal()
        journal.record_intent(invocation, owner=owner)

        recovered = journal.reconcile(owner=owner, now=1200.0)

        self.assertEqual("owner_session_expired", recovered[0].reason)
        self.assertEqual("outcome_unknown", journal.records()[-1].state)

    def test_truncated_or_conflicting_pending_journal_fails_closed(self):
        journal, owner = self.owned_journal()
        journal.record_intent(self.invocation(), owner=owner)
        journal.path.write_text('{"schema_version":1}', encoding="utf-8")
        with self.assertRaisesRegex(ToolRunJournalError, "truncated"):
            journal.records()

        journal.path.unlink()
        journal.record_intent(self.invocation(), owner=owner)
        journal.pending_path.write_text(json.dumps({
            "schema_version": TOOL_RUN_JOURNAL_SCHEMA_VERSION,
            "sequence": 1, "kind": "intent", "run_id": "TI-other",
            "tool_id": "sandbox.run", "tool_version": 1, "session_instance_id": "session-001",
            "binding_fingerprint": "b" * 64, "owner_id": owner.owner_id,
            "owner_epoch": owner.owner_epoch,
            "expires_at": 1300.0, "state": "awaiting_approval", "reason": "submitted", "timestamp": 1001.0,
        }) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ToolRunJournalError, "conflicts"):
            journal.records()

    def test_valid_pending_extension_is_recovered(self):
        journal, owner = self.owned_journal()
        invocation = self.invocation()
        intent = journal.record_intent(invocation, owner=owner)
        existing = journal.path.read_text(encoding="utf-8")
        outcome = intent.to_dict() | {
            "sequence": 2, "kind": "outcome", "state": "outcome_unknown",
            "reason": "restart_reconciliation", "timestamp": 1002.0,
        }
        journal.pending_path.write_text(existing + json.dumps(outcome, sort_keys=True) + "\n", encoding="utf-8")

        records = journal.records()

        self.assertEqual(2, len(records))
        self.assertFalse(journal.pending_path.exists())
        self.assertEqual("outcome_unknown", records[-1].state)

    def test_capacity_fails_closed_without_deleting_terminal_replay_evidence(self):
        journal, owner = self.owned_journal(maximum_records=2)
        first = self.invocation("TI-first")
        second = self.invocation("TI-second")
        journal.record_intent(first, owner=owner)
        journal.record_outcome(first, owner=owner, state="completed", reason="completed")
        with self.assertRaisesRegex(ToolRunJournalError, "capacity is exhausted"):
            journal.record_intent(second, owner=owner)

        records = journal.records()

        self.assertEqual(("TI-first", "TI-first"), tuple(item.run_id for item in records))
        self.assertEqual((1, 2), tuple(item.sequence for item in records))

    def test_schema_numbers_nonfinite_values_and_reason_pairs_are_strict(self):
        journal = ToolRunJournal(self.root)
        invalid_records = (
            self.record(1, "intent", schema_version=True),
            self.record(1, "intent", tool_version=True),
            self.record(1, "intent", expires_at=float("nan")),
            self.record(1, "intent", reason="completed"),
            self.record(1, "outcome", state="outcome_unknown", reason="completed"),
        )
        for invalid in invalid_records:
            with self.subTest(invalid=invalid):
                self.write_records(invalid)
                with self.assertRaises(ToolRunJournalError):
                    journal.records()

    def test_reader_rejects_invalid_encoding_record_size_and_total_size(self):
        journal = ToolRunJournal(self.root)
        journal.path.write_bytes(b"\xff\n")
        with self.assertRaisesRegex(ToolRunJournalError, "encoding"):
            journal.records()

        journal.path.write_bytes(b"x" * (MAX_TOOL_RUN_RECORD_BYTES + 1) + b"\n")
        with self.assertRaisesRegex(ToolRunJournalError, "record size"):
            journal.records()

        journal.path.write_bytes(b"x" * (MAX_TOOL_RUN_JOURNAL_BYTES + 1))
        with self.assertRaisesRegex(ToolRunJournalError, "size limit"):
            journal.records()

    def test_duplicate_keys_and_excessive_json_depth_fail_closed(self):
        journal = ToolRunJournal(self.root)
        duplicate = json.dumps(self.record(1, "intent"))[:-1] + ',"sequence":1}\n'
        journal.path.write_text(duplicate, encoding="utf-8")
        with self.assertRaises(ToolRunJournalError):
            journal.records()

        nested = self.record(1, "intent")
        nested["state"] = {"too": {"deep": {"to": "accept"}}}
        self.write_records(nested)
        with self.assertRaises(ToolRunJournalError):
            journal.records()

    def test_outcome_must_match_intent_binding_and_monotonic_time(self):
        journal = ToolRunJournal(self.root)
        mutations = (
            {"tool_id": "other.tool"},
            {"tool_version": 2},
            {"session_instance_id": "session-002"},
            {"expires_at": 1301.0},
        )
        for changed in mutations:
            with self.subTest(changed=changed):
                self.write_records(
                    self.record(1, "intent"),
                    self.record(2, "outcome", **changed),
                )
                with self.assertRaisesRegex(ToolRunJournalError, "binding"):
                    journal.records()

        self.write_records(
            self.record(1, "intent", timestamp=1002.0),
            self.record(2, "outcome", timestamp=1001.0),
        )
        with self.assertRaisesRegex(ToolRunJournalError, "binding|monotonic"):
            journal.records()

    def test_storage_substitution_is_rejected(self):
        journal = ToolRunJournal(self.root)
        journal.path.mkdir()
        with self.assertRaisesRegex(ToolRunJournalError, "protected regular file"):
            journal.records()
        journal.path.rmdir()

        outside = self.root / "outside.jsonl"
        outside.write_text(json.dumps(self.record(1, "intent")) + "\n", encoding="utf-8")
        try:
            self.root.joinpath("tool-runs.jsonl").hardlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("hard links are unavailable on this test filesystem")
        with self.assertRaisesRegex(ToolRunJournalError, "multiple links"):
            journal.records()

    def test_relative_or_reparse_root_is_not_accepted(self):
        with self.assertRaisesRegex(ToolRunJournalError, "absolute"):
            ToolRunJournal("relative-journal-root")

        link = self.root.parent / f"{self.root.name}-link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            return
        try:
            with self.assertRaisesRegex(ToolRunJournalError, "protected directory"):
                ToolRunJournal(link)
        finally:
            link.unlink()

    def test_fsync_or_replace_failure_preserves_recoverable_pending_intent(self):
        invocation = self.invocation()
        faults = (
            ("fsync", mock.patch(
                "pipeline.tool_runs.os.fsync",
                side_effect=OSError(errno.ENOSPC, "synthetic full disk"),
            )),
            ("replace", mock.patch(
                "pipeline.tool_runs.os.replace",
                side_effect=OSError(errno.EIO, "synthetic replace failure"),
            )),
        )
        for label, fault in faults:
            with self.subTest(label=label):
                fault_root = self.root / label
                fault_root.mkdir()
                journal, owner = self.owned_journal(
                    fault_root, owner_epoch=f"TO-fault-{label}",
                )
                with fault:
                    with self.assertRaisesRegex(ToolRunJournalError, "cannot be written"):
                        journal.record_intent(invocation, owner=owner)
                recovered = journal.records()
                self.assertEqual(("intent",), tuple(item.kind for item in recovered))
                self.assertEqual(invocation.invocation_id, recovered[0].run_id)

    def test_malformed_pending_file_remains_quarantined_and_fails_closed(self):
        journal, owner = self.owned_journal()
        journal.record_intent(self.invocation(), owner=owner)
        authoritative = journal.path.read_bytes()
        journal.pending_path.write_bytes(authoritative + b'{"schema_version":2')

        with self.assertRaisesRegex(ToolRunJournalError, "truncated"):
            journal.records()

        self.assertEqual(authoritative, journal.path.read_bytes())
        self.assertTrue(journal.pending_path.exists())

    def test_stale_prefix_pending_file_is_discarded_without_rewriting_history(self):
        journal, owner = self.owned_journal()
        invocation = self.invocation()
        journal.record_intent(invocation, owner=owner)
        intent_only = journal.path.read_bytes()
        journal.record_outcome(
            invocation, owner=owner, state="completed", reason="completed",
        )
        authoritative = journal.path.read_bytes()
        journal.pending_path.write_bytes(intent_only)

        records = journal.records()

        self.assertEqual(("intent", "outcome"), tuple(item.kind for item in records))
        self.assertEqual(authoritative, journal.path.read_bytes())
        self.assertFalse(journal.pending_path.exists())

    def test_live_owner_is_exclusive_and_same_epoch_is_not_reconciled(self):
        first, owner = self.owned_journal(owner_epoch="TO-live-owner")
        first.record_intent(self.invocation(), owner=owner)

        with self.assertRaises(AttributeError):
            owner.owner_id = "core.mutated"
        with self.assertRaises(AttributeError):
            owner.owner_epoch = "TO-mutated"

        second = ToolRunJournal(
            self.root, clock=lambda: 1002.0,
            owner_epoch_factory=lambda: "TO-second-owner",
        )
        with self.assertRaisesRegex(ToolRunJournalError, "owner lease is unavailable"):
            second.acquire_owner("core.second")
        self.assertEqual((), first.reconcile(owner=owner, now=1002.0))
        self.assertEqual(("intent",), tuple(item.kind for item in first.records()))

        first.release_owner(owner)
        replacement = second.acquire_owner("core.second")
        self._owned_journals.append((second, replacement))
        recovered = second.reconcile(owner=replacement, now=1002.0)
        self.assertEqual(1, len(recovered))
        self.assertEqual("restart_reconciliation", recovered[0].reason)

    def test_released_or_foreign_owner_cannot_mutate_journal(self):
        first, owner = self.owned_journal(owner_epoch="TO-first-owner")
        second_root = self.root / "other"
        second_root.mkdir()
        second, foreign = self.owned_journal(
            second_root, owner_id="core.other", owner_epoch="TO-other-owner",
        )
        invocation = self.invocation()
        with self.assertRaisesRegex(ToolRunJournalError, "invalid or inactive"):
            first.record_intent(invocation, owner=foreign)

        first.release_owner(owner)
        with self.assertRaisesRegex(ToolRunJournalError, "invalid or inactive"):
            first.record_intent(invocation, owner=owner)

    def test_historical_run_id_cannot_reenter_admission_after_restart(self):
        first, owner = self.owned_journal(owner_epoch="TO-first-owner")
        original = self.invocation()
        first.record_intent(original, owner=owner)
        first.record_outcome(
            original, owner=owner, state="completed", reason="completed",
        )
        first.release_owner(owner)

        restarted, restarted_owner = self.owned_journal(
            clock=lambda: 1002.0, owner_id="core.restart",
            owner_epoch="TO-restarted-owner",
        )
        with self.assertRaisesRegex(ToolRunReplayError, "already admitted"):
            restarted.record_intent(original, owner=restarted_owner)
        conflicting = self.invocation(objective="Different operation content.")
        with self.assertRaisesRegex(ToolRunReplayError, "conflicts"):
            restarted.record_intent(conflicting, owner=restarted_owner)
        self.assertEqual(2, len(restarted.records()))

    def test_second_process_cannot_take_a_live_owner_lease(self):
        journal, owner = self.owned_journal(owner_epoch="TO-parent-owner")
        child = textwrap.dedent("""
            import sys
            from pathlib import Path
            sys.path.insert(0, sys.argv[2])
            from pipeline.tool_runs import ToolRunJournal, ToolRunJournalError

            journal = ToolRunJournal(
                Path(sys.argv[1]), owner_epoch_factory=lambda: "TO-child-owner",
            )
            try:
                journal.acquire_owner("core.child")
            except ToolRunJournalError:
                raise SystemExit(79)
            raise SystemExit(0)
        """)
        repository_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "-c", child, str(self.root), str(repository_root)],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(79, completed.returncode, completed.stderr)
        self.assertTrue(owner.active)
        self.assertEqual((), journal.records())

    def test_process_death_after_pending_fsync_recovers_without_duplicate_history(self):
        child = textwrap.dedent("""
            import os
            import sys
            from pathlib import Path
            from unittest import mock
            sys.path.insert(0, sys.argv[2])
            from pipeline.tool_runs import ToolRunJournal, ToolRunRecord

            root = Path(sys.argv[1])
            journal = ToolRunJournal(
                root, clock=lambda: 1001.0,
                owner_epoch_factory=lambda: "TO-crashed-owner",
            )
            owner = journal.acquire_owner("core.crash-test")
            record = ToolRunRecord(
                1, "intent", "TI-crash-smoke", "sandbox.run", 1,
                "session-001", "a" * 64, owner.owner_id, owner.owner_epoch,
                1300.0, "awaiting_approval", "submitted", 1001.0,
            )
            with journal._locked():
                with mock.patch("pipeline.tool_runs.os.replace", side_effect=lambda *_: os._exit(73)):
                    journal._replace_locked([record])
        """)
        repository_root = Path(__file__).resolve().parents[1]
        completed = subprocess.run(
            [sys.executable, "-c", child, str(self.root), str(repository_root)],
            cwd=repository_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(73, completed.returncode, completed.stderr)

        journal, owner = self.owned_journal(
            clock=lambda: 1002.0, owner_id="core.recovery",
            owner_epoch="TO-recovery-owner",
        )
        recovered = journal.reconcile(owner=owner)
        records = journal.records()

        self.assertEqual(1, len(recovered))
        self.assertEqual(2, len(records))
        self.assertEqual("TI-crash-smoke", records[0].run_id)
        self.assertEqual("outcome_unknown", records[1].state)
        self.assertEqual("restart_reconciliation", records[1].reason)
        self.assertFalse(journal.pending_path.exists())
        self.assertEqual(records, journal.records())


if __name__ == "__main__":
    unittest.main()
