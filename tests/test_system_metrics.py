import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.system_metrics import LocalSystemMetricsProvider, NullSystemMetricsProvider, SystemMetricsSnapshot


class SystemMetricsTests(unittest.TestCase):
    def test_null_provider_is_explicitly_unavailable_and_bounded(self):
        value = NullSystemMetricsProvider().snapshot().public_dict()

        self.assertEqual(value["status"], "unavailable")
        self.assertEqual(value["reason"], "not_configured")
        self.assertIsNone(value["cpu"]["usage_percent"])
        self.assertEqual(value["gpu"]["status"], "unavailable")

    def test_local_provider_uses_aggregate_values_without_external_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("pipeline.system_metrics.os.cpu_count", return_value=8), patch.object(
                LocalSystemMetricsProvider, "_linux_memory", return_value=(1024, 512),
            ):
                value = LocalSystemMetricsProvider(directory).snapshot().public_dict()

        self.assertEqual(value["status"], "partial")
        self.assertEqual(value["cpu"]["logical_cores"], 8)
        self.assertEqual(value["memory"], {"total_bytes": 1024, "available_bytes": 512})
        self.assertGreater(value["storage"]["total_bytes"], 0)
        self.assertIsNone(value["gpu"]["name"])

    def test_snapshot_rejects_impossible_aggregate_values(self):
        with self.assertRaisesRegex(ValueError, "available memory"):
            SystemMetricsSnapshot("partial", memory_total_bytes=10, memory_available_bytes=11)


if __name__ == "__main__":
    unittest.main()
