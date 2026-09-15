import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_registry import MAX_REGISTERED_TOOLS, ToolDescriptor, ToolRegistry, build_core_tool_registry


class ToolRegistryTests(unittest.TestCase):
    def test_registry_is_stable_description_metadata_only(self):
        read = ToolDescriptor(
            "workspace.inspect", "Inspect workspace", "Read bounded workspace metadata.",
            "read_only", "workspace.read",
        )
        write = ToolDescriptor(
            "workspace.write", "Write workspace", "Create or update an approved workspace file.",
            "mutating", "workspace.write", requires_confirmation=True,
        )
        registry = ToolRegistry((write, read))

        self.assertEqual(("workspace.inspect", "workspace.write"), tuple(
            item.tool_id for item in registry.descriptors
        ))
        self.assertIs(read, registry.get("workspace.inspect"))
        self.assertIsNone(registry.get("missing"))
        self.assertEqual({
            "schema_version": 1,
            "tools": [read.public_dict(), write.public_dict()],
        }, registry.public_dict())

    def test_mutating_and_invalid_descriptors_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "require confirmation"):
            ToolDescriptor("workspace.write", "Write", "Changes a file.", "mutating", "workspace.write")
        with self.assertRaisesRegex(ValueError, "identifier"):
            ToolDescriptor("Bad id", "Read", "Reads.", "read_only", "workspace.read")
        with self.assertRaisesRegex(ValueError, "permission scope"):
            ToolDescriptor("workspace.inspect", "Read", "Reads.", "read_only", "Bad scope")

    def test_registry_rejects_duplicate_or_non_descriptor_entries(self):
        descriptor = ToolDescriptor("workspace.inspect", "Inspect", "Reads.", "read_only", "workspace.read")
        with self.assertRaisesRegex(ValueError, "unique"):
            ToolRegistry((descriptor, descriptor))
        with self.assertRaisesRegex(TypeError, "entries"):
            ToolRegistry((object(),))

    def test_descriptor_and_registry_metadata_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "identifier"):
            ToolDescriptor("a" * 81, "Read", "Reads.", "read_only", "workspace.read")
        with self.assertRaisesRegex(ValueError, "title"):
            ToolDescriptor("workspace.inspect", "x" * 121, "Reads.", "read_only", "workspace.read")
        descriptors = tuple(ToolDescriptor(
            f"tool.{index}", f"Tool {index}", "Bounded.", "read_only", "workspace.read",
        ) for index in range(MAX_REGISTERED_TOOLS + 1))
        with self.assertRaisesRegex(ValueError, "limit"):
            ToolRegistry(descriptors)

    def test_core_registry_describes_sandbox_without_exposing_an_executor(self):
        registry = build_core_tool_registry()
        descriptor = registry.get("sandbox.run")
        self.assertIsNotNone(descriptor)
        self.assertEqual("mutating", descriptor.access_mode)
        self.assertTrue(descriptor.requires_confirmation)
        self.assertNotIn("executor", registry.public_dict())

    def test_core_registry_describes_confirmed_public_fetch_without_network_authority(self):
        registry = build_core_tool_registry()
        descriptor = registry.get("web.fetch")
        self.assertIsNotNone(descriptor)
        self.assertEqual("read_only", descriptor.access_mode)
        self.assertEqual("network.fetch.public", descriptor.permission_scope)
        self.assertTrue(descriptor.requires_confirmation)
        rendered = repr(descriptor.public_dict()).casefold()
        for forbidden in ("executor", "socket", "credential", "cookie"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
