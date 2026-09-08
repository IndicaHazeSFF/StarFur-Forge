import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_contracts import (
    MAX_TOOL_PROPOSAL_BYTES,
    ToolContractRegistry,
    ToolProposal,
    ToolResult,
    build_core_tool_contract_registry,
    decode_tool_proposal_json,
    decode_tool_result_json,
)


def valid_proposal_mapping():
    return {
        "schema_version": 1,
        "tool_id": "sandbox.run",
        "tool_version": 1,
        "arguments": {
            "task_kind": "python_tests",
            "objective": "Run a bounded provider-free exercise.",
            "files": [{"path": "src/main.py", "content": "print('safe')\n"}],
        },
    }


def valid_result_mapping():
    return {
        "schema_version": 1,
        "invocation_id": "TI-test_001",
        "tool_id": "sandbox.run",
        "tool_version": 1,
        "outcome": "completed",
        "exit_code": 0,
        "stdout": "tests passed",
        "stderr": "",
        "error_category": None,
        "artifact_refs": ["TF-report_001"],
    }


class ToolContractTests(unittest.TestCase):
    def test_valid_sandbox_proposal_is_immutable_and_remains_inert(self):
        source = valid_proposal_mapping()
        registry = build_core_tool_contract_registry()

        with patch("builtins.open", side_effect=AssertionError("filesystem call")), patch.object(
            subprocess, "run", side_effect=AssertionError("process call"),
        ):
            proposal = registry.validate_proposal(ToolProposal.from_mapping(source))

        source["arguments"]["objective"] = "changed"
        source["arguments"]["files"][0]["content"] = "changed"
        self.assertEqual("Run a bounded provider-free exercise.", proposal.arguments["objective"])
        self.assertEqual("print('safe')\n", proposal.arguments["files"][0]["content"])
        with self.assertRaises(TypeError):
            proposal.arguments["objective"] = "changed"
        with self.assertRaises(TypeError):
            proposal.arguments["files"][0]["content"] = "changed"
        self.assertNotIn("approved", proposal.public_dict())
        self.assertNotIn("executor", registry.public_dict())
        metadata = registry.public_dict()["contracts"][0]
        self.assertEqual(["sandbox.backend"], metadata["resource_requirements"])
        self.assertEqual(8, metadata["limits"]["max_files"])
        with self.assertRaises(TypeError):
            registry.contracts[0].limits["max_files"] = 99

    def test_proposal_rejects_unknown_contract_and_authority_fields(self):
        registry = build_core_tool_contract_registry()
        unknown = valid_proposal_mapping()
        unknown["tool_version"] = 2
        with self.assertRaisesRegex(ValueError, "unknown"):
            registry.validate_proposal(ToolProposal.from_mapping(unknown))

        for field in ("approved", "confirmed", "principal_id", "policy", "executor"):
            forged = valid_proposal_mapping()
            forged[field] = True
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "fields"):
                ToolProposal.from_mapping(forged)

        nested = valid_proposal_mapping()
        nested["arguments"]["confirmed"] = True
        with self.assertRaisesRegex(ValueError, "fields"):
            registry.validate_proposal(ToolProposal.from_mapping(nested))

    def test_json_decoder_rejects_duplicates_malformed_nonfinite_size_and_depth(self):
        duplicate = '{"schema_version":1,"schema_version":1,"tool_id":"sandbox.run",' \
            '"tool_version":1,"arguments":{}}'
        with self.assertRaisesRegex(ValueError, "duplicate"):
            decode_tool_proposal_json(duplicate)
        with self.assertRaisesRegex(ValueError, "malformed"):
            decode_tool_proposal_json("{not-json")
        with self.assertRaisesRegex(ValueError, "non-finite"):
            decode_tool_proposal_json(
                '{"schema_version":1,"tool_id":"sandbox.run","tool_version":NaN,"arguments":{}}',
            )
        with self.assertRaisesRegex(ValueError, "size limit"):
            decode_tool_proposal_json(" " * (MAX_TOOL_PROPOSAL_BYTES + 1))
        deep = valid_proposal_mapping()
        deep["arguments"] = {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {}}}}}}}}}
        with self.assertRaisesRegex(ValueError, "depth"):
            decode_tool_proposal_json(json.dumps(deep))
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            decode_tool_proposal_json("\ud800")

    def test_sandbox_argument_schema_is_finite_and_byte_bounded(self):
        registry = build_core_tool_contract_registry()
        invalid_path = valid_proposal_mapping()
        invalid_path["arguments"]["files"][0]["path"] = "../secret.txt"
        with self.assertRaisesRegex(ValueError, "path"):
            registry.validate_proposal(ToolProposal.from_mapping(invalid_path))

        duplicate_path = valid_proposal_mapping()
        duplicate_path["arguments"]["files"].append({"path": "src/main.py", "content": "again"})
        with self.assertRaisesRegex(ValueError, "unique"):
            registry.validate_proposal(ToolProposal.from_mapping(duplicate_path))

        oversized = valid_proposal_mapping()
        oversized["arguments"]["files"][0]["content"] = "🦊" * 5000
        with self.assertRaisesRegex(ValueError, "size limit"):
            registry.validate_proposal(ToolProposal.from_mapping(oversized))

    def test_result_envelope_is_strict_bounded_and_contract_matched(self):
        registry = build_core_tool_contract_registry()
        result = registry.validate_result(ToolResult.from_mapping(valid_result_mapping()))
        self.assertEqual(valid_result_mapping(), result.public_dict())

        malformed = valid_result_mapping()
        malformed["authority"] = "granted"
        with self.assertRaisesRegex(ValueError, "fields"):
            ToolResult.from_mapping(malformed)
        failed_without_category = valid_result_mapping()
        failed_without_category["outcome"] = "failed"
        with self.assertRaisesRegex(ValueError, "requires an error"):
            ToolResult.from_mapping(failed_without_category)
        huge_output = valid_result_mapping()
        huge_output["stdout"] = "x" * 8193
        with self.assertRaisesRegex(ValueError, "stdout"):
            ToolResult.from_mapping(huge_output)

        decoded = decode_tool_result_json(json.dumps(valid_result_mapping()))
        self.assertEqual("TI-test_001", decoded.invocation_id)

    def test_contract_registry_is_bounded_and_rejects_duplicates(self):
        contract = build_core_tool_contract_registry().contracts[0]
        with self.assertRaisesRegex(ValueError, "unique"):
            ToolContractRegistry((contract, contract))


if __name__ == "__main__":
    unittest.main()
