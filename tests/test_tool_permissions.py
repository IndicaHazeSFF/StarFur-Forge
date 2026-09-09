import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_permissions import PermissionGrant, evaluate_tool_permission
from pipeline.tool_registry import ToolDescriptor


class ToolPermissionTests(unittest.TestCase):
    def setUp(self):
        self.read = ToolDescriptor("workspace.inspect", "Inspect", "Reads metadata.", "read_only", "workspace.read")
        self.write = ToolDescriptor(
            "workspace.write", "Write", "Changes a file.", "mutating", "workspace.write", requires_confirmation=True,
        )

    def test_exact_scope_and_access_mode_are_required(self):
        self.assertEqual("scope_not_granted", evaluate_tool_permission(self.read).reason)
        self.assertEqual("scope_not_granted", evaluate_tool_permission(
            self.read, (PermissionGrant("workspace", frozenset({"read_only"})),),
        ).reason)
        self.assertEqual("access_not_granted", evaluate_tool_permission(
            self.write, (PermissionGrant("workspace.write", frozenset({"read_only"})),), confirmed=True,
        ).reason)

    def test_mutating_descriptor_needs_explicit_confirmation_after_a_grant(self):
        grants = (PermissionGrant("workspace.write", frozenset({"mutating"})),)
        self.assertEqual("confirmation_required", evaluate_tool_permission(self.write, grants).reason)
        self.assertEqual({"allowed": True, "reason": "granted"}, evaluate_tool_permission(
            self.write, grants, confirmed=True,
        ).public_dict())

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "scope"):
            PermissionGrant("bad scope", frozenset({"read_only"}))
        with self.assertRaisesRegex(ValueError, "access modes"):
            PermissionGrant("workspace.read", frozenset({"network"}))
        with self.assertRaisesRegex(TypeError, "grants"):
            evaluate_tool_permission(self.read, (object(),))
        with self.assertRaisesRegex(TypeError, "confirmation"):
            evaluate_tool_permission(self.read, confirmed="yes")


if __name__ == "__main__":
    unittest.main()
