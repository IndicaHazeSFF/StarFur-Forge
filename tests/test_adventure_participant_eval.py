import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline.adventure_participant_eval import (
    BENCHMARK_VERSION, FIXTURE_FINGERPRINT, format_adventure_participant_result,
    run_adventure_participant_benchmark,
)


class AdventureParticipantEvaluationTests(unittest.TestCase):
    def test_frozen_cases_are_repeatable_with_no_live_provider_or_production_memory(self):
        with patch("pipeline.db.connect", side_effect=AssertionError("production DB forbidden")):
            first = run_adventure_participant_benchmark()
            second = run_adventure_participant_benchmark()
        self.assertEqual(first, second)
        self.assertEqual(BENCHMARK_VERSION, first["benchmark_version"])
        self.assertEqual(FIXTURE_FINGERPRINT, first["fixture_fingerprint"])
        self.assertEqual(64, len(FIXTURE_FINGERPRINT))
        self.assertEqual("adventure-participant-lifecycle-v2", first["benchmark_version"])
        self.assertEqual(11, len(first["results"]))
        self.assertTrue(first["repeatability"])
        self.assertEqual(1.0, first["participant_lifecycle_pass_rate"])
        self.assertTrue(all(case["pass"] for case in first["results"]))
        rendered = format_adventure_participant_result(first)
        self.assertIn("100.0%", rendered)
        self.assertIn("not a live-model quality", rendered)

    def test_results_exclude_prose_prompts_identifiers_and_paths(self):
        result = run_adventure_participant_benchmark()
        text = json.dumps(result)
        for prohibited in ("Synthetic", "TPG-", "AT-", "adventure:", "summary", "messages", "question", "prompt", "\\", "raw_output"):
            self.assertNotIn(prohibited, text)
        cases = {case["name"]: case for case in result["results"]}
        self.assertEqual(0, cases["review_only"]["actual_transcript_records"])
        self.assertEqual(2, cases["record_once"]["actual_transcript_records"])
        self.assertEqual(2, cases["pacing"]["actual_provider_calls"])
        self.assertEqual(3, cases["interruption"]["actual_provider_calls"])
        self.assertEqual(1, cases["stale_origin"]["actual_events"])
        self.assertEqual(0, cases["binding_required"]["actual_provider_calls"])
        for name in ("binding_ended", "binding_replaced"):
            self.assertEqual(1, cases[name]["actual_provider_calls"])
            self.assertEqual(0, cases[name]["actual_candidates"])
            self.assertEqual(0, cases[name]["actual_transcript_records"])
        self.assertEqual(2, cases["binding_recovery"]["actual_provider_calls"])
        self.assertEqual(1, cases["binding_recovery"]["actual_candidates"])
        self.assertTrue(all(case["actual_staged"] == 0 for case in cases.values()))

    def test_repeatability_is_measured_not_assumed(self):
        import pipeline.adventure_participant_eval as evaluation
        with patch.object(evaluation, "_run_once", side_effect=[
            [{"name": "fixture", "pass": True}], [{"name": "fixture", "pass": False}],
        ]):
            self.assertFalse(run_adventure_participant_benchmark()["repeatability"])

    def test_cli_runs_without_services_and_records_only_when_requested(self):
        with patch.dict(sys.modules, {"chromadb": types.ModuleType("chromadb")}):
            import starfur
        from pipeline.experiment_ledger import load_benchmark_results
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "participant.jsonl"
            for record in (False, True):
                arguments = ["starfur.py", "adventure-participant-eval"]
                if record:
                    arguments.extend(["--record-ledger", str(ledger), "--run-id", "participant-fixture-001"])
                output = io.StringIO()
                with patch.object(sys, "argv", arguments), redirect_stdout(output), patch(
                    "pipeline.db.connect", side_effect=AssertionError("production DB forbidden")
                ):
                    starfur.main()
                self.assertIn("Cases:              11", output.getvalue())
                self.assertIn("Repeatability:      PASS", output.getvalue())
                self.assertEqual(record, ledger.exists())
            records = load_benchmark_results(ledger)
            self.assertEqual(1, len(records))
            self.assertEqual(BENCHMARK_VERSION, records[0]["benchmark_version"])
            self.assertEqual(11, len(records[0]["cases"]))
            self.assertNotIn("Synthetic", ledger.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
