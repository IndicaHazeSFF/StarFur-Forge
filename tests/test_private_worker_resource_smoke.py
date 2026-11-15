"""Fake/pure R0 checks. No unit, cgroup, fork or resource workload at discovery."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("resource_smoke", Path(__file__).resolve().parents[1]
                                            / "scripts/private_worker_resource_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
TOKEN = "a" * 32
UNIT = "starfur-r0-" + TOKEN + ".service"
ROOT = "/tmp/sf-worker-resource-" + TOKEN + "-abcdefgh"


class ResourceSmokeTests(unittest.TestCase):
    def test_command_is_exact_user_only_transient_and_sanitized(self):
        args = smoke.unit_command(UNIT, ROOT, "/home/roger/StarFur-Forge/.venv/bin/python",
                                 "/home/roger/StarFur-Forge/scripts/private_worker_resource_smoke.py")
        self.assertIn("--user", args)
        self.assertIn("--collect", args)
        self.assertIn("--slice=-.slice", args)
        self.assertIn("--expand-environment=no", args)
        self.assertIn("--property=RuntimeMaxSec=10s", args)
        self.assertIn("--property=MemoryMax=268435456", args)
        self.assertIn("--property=MemorySwapMax=0", args)
        self.assertIn("--property=TasksMax=16", args)
        self.assertIn("--property=CPUQuota=100%", args)
        self.assertIn("--property=StandardOutput=null", args)
        self.assertIn("--property=StandardError=null", args)
        index = args.index("/usr/bin/env")
        self.assertEqual(args[index + 1:index + 4], ("-i", "LANG=C.UTF-8", "PATH=/usr/bin:/bin"))
        self.assertNotIn("--system", args)
        self.assertNotIn("--remain-after-exit", args)

    def test_name_path_and_cross_fixture_binding_deny(self):
        for unit, root in (("ollama.service", ROOT), (UNIT, "/tmp/other"),
                           (UNIT, ROOT.replace(TOKEN, "b" * 32)), (UNIT, ROOT + "/../else")):
            with self.assertRaises(smoke.Refusal):
                smoke.validate_names(unit, root)

    def test_nonreviewed_interpreter_or_script_deny(self):
        with self.assertRaisesRegex(smoke.Refusal, "executable_path_refused"):
            smoke.unit_command(UNIT, ROOT, "/mnt/c/python.exe", "/tmp/script")

    def test_kernel_limits_exact(self):
        smoke.verify_limits({"cpu.max": "100000 100000\n", "memory.max": "268435456\n",
                             "memory.swap.max": "0\n", "pids.max": "16\n"})

    def test_unlimited_or_weaker_kernel_limits_deny(self):
        limits = {"cpu.max": "100000 100000", "memory.max": "268435456",
                  "memory.swap.max": "0", "pids.max": "16"}
        for key, value in (("cpu.max", "max 100000"), ("cpu.max", "200000 100000"),
                           ("memory.max", "max"), ("memory.swap.max", "100"),
                           ("pids.max", "max")):
            with self.subTest(key=key), self.assertRaises(smoke.Refusal):
                smoke.verify_limits({**limits, key: value})

    def test_manager_environment_has_no_ambient_credentials(self):
        with patch.dict("os.environ", {"PRIVATE_TOKEN": "not-forwarded"}):
            env = smoke.manager_environment(1000)
        self.assertNotIn("PRIVATE_TOKEN", env)
        self.assertEqual(env["DBUS_SESSION_BUS_ADDRESS"], "unix:path=/run/user/1000/bus")

    def unit_info(self):
        return {"Id": UNIT, "Transient": "yes", "LoadState": "loaded", "Slice": "-.slice",
                "InvocationID": TOKEN, "ControlGroup":
                "/user.slice/user-1000.slice/user@1000.service/" + UNIT,
                "Type": "exec", "RuntimeMaxUSec": "10s", "TimeoutStopUSec": "2s",
                "KillMode": "control-group", "SendSIGKILL": "yes", "Restart": "no",
                "NoNewPrivileges": "yes", "StandardInput": "null", "StandardOutput": "null",
                "StandardError": "null", "CollectMode": "inactive-or-failed"}

    def test_exact_unit_policy_and_root_slice_required(self):
        info = self.unit_info()
        self.assertEqual(smoke.check_unit(info, UNIT, 1000), info["ControlGroup"])
        for key, value in (("Transient", "no"), ("Slice", "app.slice"),
                           ("InvocationID", ""), ("ControlGroup", "/system.slice/ollama.service"),
                           ("KillMode", "process"), ("RuntimeMaxUSec", "infinity"),
                           ("StandardOutput", "journal")):
            with self.subTest(key=key), self.assertRaises(smoke.Refusal):
                smoke.check_unit({**info, key: value}, UNIT, 1000)

    def test_malformed_or_cross_group_record_denies_before_pidfd(self):
        with patch.object(smoke.os, "pidfd_open") as acquire:
            with self.assertRaises(smoke.Refusal):
                smoke.pin_record({"pid": 100}, unit=UNIT, uid=1000, role="worker", cgroup="/x",
                                 expected_argv=())
        acquire.assert_not_called()

    def test_manager_metadata_unknown_or_duplicate_fields_deny(self):
        for raw in (b"Id=" + UNIT.encode() + b"\nId=other\n", b"PRIVATE=data\n"):
            result = Mock(stdout=raw, returncode=0)
            with patch.object(smoke, "command", return_value=result):
                with self.assertRaises(smoke.Refusal):
                    smoke.unit_info(UNIT, 1000)

    def test_manager_command_never_uses_shell_or_unbounded_wait(self):
        completed = Mock(stdout=b"", returncode=0)
        with patch.object(smoke.subprocess, "run", return_value=completed) as execute:
            smoke.command(("/usr/bin/systemctl", "--user", "show", UNIT), 1000)
        self.assertNotIn("shell", execute.call_args.kwargs)
        self.assertEqual(execute.call_args.kwargs["timeout"], 3)
