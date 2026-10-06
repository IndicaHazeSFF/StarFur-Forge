import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_process_gate import ProviderProcessGate, ProviderProcessGateError


class ProviderProcessGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_provider_lease_is_nonblocking_and_reusable_after_release(self):
        first = ProviderProcessGate(self.root, id_factory=lambda: "a" * 24)
        second = ProviderProcessGate(self.root, id_factory=lambda: "b" * 24)

        admitted = first.try_acquire("ollama")
        self.assertEqual("admitted", admitted.status)
        self.assertTrue(admitted.lease.active)
        self.assertEqual("deferred", second.try_acquire("ollama").status)
        self.assertTrue(first.release(admitted.lease))
        self.assertFalse(first.release(admitted.lease))
        reacquired = second.try_acquire("ollama")
        self.assertEqual("admitted", reacquired.status)
        self.assertTrue(second.release(reacquired.lease))

    def test_different_provider_ids_use_independent_content_free_paths(self):
        gate = ProviderProcessGate(self.root)
        ollama = gate.try_acquire("ollama")
        specialist = gate.try_acquire("specialist")

        self.assertEqual("admitted", ollama.status)
        self.assertEqual("admitted", specialist.status)
        self.assertNotEqual(gate.lock_path("ollama"), gate.lock_path("specialist"))
        self.assertNotIn("ollama", gate.lock_path("ollama").name)
        self.assertTrue(gate.release(ollama.lease))
        self.assertTrue(gate.release(specialist.lease))

    def test_foreign_lease_and_unsafe_roots_fail_closed(self):
        first = ProviderProcessGate(self.root)
        second = ProviderProcessGate(self.root)
        admitted = first.try_acquire("ollama")

        self.assertFalse(second.release(admitted.lease))
        with self.assertRaisesRegex(ProviderProcessGateError, "absolute"):
            ProviderProcessGate(Path("relative"))
        with self.assertRaisesRegex(ProviderProcessGateError, "unavailable"):
            ProviderProcessGate(self.root / "missing")
        self.assertTrue(first.release(admitted.lease))

    def test_process_exit_releases_the_os_owned_lease_without_stale_metadata(self):
        child = textwrap.dedent("""
            import os
            from pathlib import Path
            import sys
            sys.path.insert(0, sys.argv[2])
            from pipeline.provider_process_gate import ProviderProcessGate

            gate = ProviderProcessGate(Path(sys.argv[1]))
            admission = gate.try_acquire("ollama")
            if admission.status != "admitted":
                raise SystemExit(77)
            print("ready", flush=True)
            sys.stdin.read(1)
            os._exit(0)
        """)
        repository_root = Path(__file__).resolve().parents[1]
        process = subprocess.Popen(
            [sys.executable, "-c", child, str(self.root), str(repository_root)],
            cwd=repository_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual("ready", process.stdout.readline().strip())
            gate = ProviderProcessGate(self.root)
            self.assertEqual("deferred", gate.try_acquire("ollama").status)
            process.stdin.write("x")
            process.stdin.flush()
            process.stdin.close()
            process.stdin = None
            self.assertEqual(0, process.wait(timeout=15), process.stderr.read())
            recovered = gate.try_acquire("ollama")
            self.assertEqual("admitted", recovered.status)
            self.assertTrue(gate.release(recovered.lease))
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


if __name__ == "__main__":
    unittest.main()
