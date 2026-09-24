from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_audit import TOOL_AUDIT_REASONS
from pipeline.tool_contracts import ToolResult


class ToolBrokerFailureCategoryTests(unittest.TestCase):
    def test_safe_supervisor_failure_categories_are_audit_allowlisted(self):
        # The broker may surface only these bounded contract labels, never a
        # backend exception, address, URL, or parser detail.
        for category in (
            "validation_failed", "permission_denied", "backend_unavailable", "execution_failed",
            "transport_policy_rejected", "response_binding_rejected",
            "content_preparation_rejected",
        ):
            with self.subTest(category=category):
                result = ToolResult(
                    1, "TI-category_test", "web.fetch", 1, "failed", None, "", "", category,
                )
                self.assertEqual(category, result.error_category)
                self.assertIn(category, TOOL_AUDIT_REASONS)


if __name__ == "__main__":
    unittest.main()
