"""Fake C4 supervisor checks; never run units, namespaces, loaders or providers."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, MagicMock, patch

spec = importlib.util.spec_from_file_location("loader_smoke", Path(__file__).resolve().parents[1]
                                            / "scripts/private_worker_loader_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)
UNIT = "starfur-c4-" + "a" * 32 + ".service"
ROOT = "/tmp/sf-worker-loader-" + "a" * 32 + "-abcdefgh"


def info(fd, raw, *, unsafe=False):
    return SimpleNamespace(st_dev=1, st_ino=fd, st_uid=0,
        st_mode=(stat.S_IFREG | (0o666 if unsafe else 0o755)) if fd == 14 else stat.S_IFDIR | 0o755,
        st_nlink=1 if fd == 14 else 2, st_size=len(raw) if fd == 14 else 4096,
        st_mtime_ns=1, st_ctime_ns=1)


class LoaderSmokeFakeTests(unittest.TestCase):
    def test_c8_fixed_direct_loader_argv_and_four_correlated_cases(self):
        unit = UNIT.replace('-c4-', '-c8-')
        self.assertIn('--unit=' + unit, smoke.unit_command(unit, ROOT, smoke.PYTHON, smoke.SCRIPT))
        self.assertEqual(smoke.cases(True), (('positive',42),('decoy',13),('negative',127),('transitive',127)))
        self.assertEqual(smoke.canary_command('positive', True),
                         ('/lib64/ld-linux-x86-64.so.2','--inhibit-cache','--library-path','/positive',
                          '--glibc-hwcaps-mask','','/positive/main'))
        self.assertEqual(smoke.success_record('a'*64, True)['pinned'], 6)
        for label in ('../bad', 'arbitrary', 'positive;exit'):
            with self.assertRaises(smoke.Refusal): smoke.canary_command(label, True)
        with self.assertRaises(smoke.Refusal): smoke.main('a'*64, cwd=True, lookup=True)

    def test_c5_has_distinct_bound_unit_identity_with_same_resource_caps(self):
        unit = UNIT.replace("-c4-", "-c5-")
        args = smoke.unit_command(unit, ROOT, smoke.PYTHON, smoke.SCRIPT)
        self.assertIn("--unit=" + unit, args)
        self.assertIn("--property=RuntimeMaxSec=10s", args)
        with self.assertRaises(smoke.Refusal):
            smoke.main("a" * 64, cwd="yes")

    def test_valid_cwd_probes_require_eperm_and_stable_empty_cwd(self):
        for error in (1, 13, None):
            with patch.object(smoke.os, "getcwd", return_value="/cwd"), \
                 patch.object(smoke.os, "stat", return_value=info(13, b"")), \
                 patch.object(smoke.Path, "iterdir", return_value=[]), \
                 patch.object(smoke.os, "open", return_value=3), \
                 patch.object(smoke.os, "close") as close, \
                 patch.object(smoke.os, "chdir", side_effect=OSError(error, "closed") if error else None), \
                 patch.object(smoke.os, "fchdir", side_effect=OSError(error, "closed") if error else None):
                if error == 1: smoke.probe_cwd_locked()
                else:
                    with self.assertRaises(smoke.Refusal): smoke.probe_cwd_locked()
            close.assert_called_once_with(3)

    def test_only_internal_decoy_directory_survives_as_inheritable_fd3(self):
        with patch.object(smoke.os, "open", return_value=0), \
             patch.object(smoke.os, "dup2") as duplicate, patch.object(smoke.os, "close") as close, \
             patch.object(smoke.os, "fstat", return_value=info(13, b"")), \
             patch.object(smoke.os, "stat", return_value=info(13, b"")), \
             patch.object(smoke.os, "get_inheritable", return_value=True), \
             patch.object(smoke.root_test, "close_except") as prune:
            smoke.keep_private_decoy_fd()
        duplicate.assert_called_once_with(0, 3, inheritable=True)
        close.assert_called_once_with(0); prune.assert_called_once_with({3})

    def test_explicit_measured_loader_digest_required_before_host_actions(self):
        with patch.object(smoke.resource, "parent_snapshot") as inspect, \
             patch.object(smoke, "acquire_loader") as acquire:
            for value in (None, "PRIVATE", "a" * 63, "A" * 64):
                with self.assertRaises(smoke.Refusal): smoke.main(value)
        inspect.assert_not_called(); acquire.assert_not_called()

    def test_diagnostics_are_closed_labels_never_raw_exception_content(self):
        self.assertEqual(smoke.failure_label(ValueError("PRIVATE CONTENT")), "ValueError")
        self.assertEqual(smoke.failure_label(smoke.Refusal("PRIVATE CONTENT")), "native_error")
        self.assertEqual(smoke.failure_label(smoke.root_test.Refusal("STOP:positive:result_refused")),
                         "STOP:positive:result_refused")

    def test_exact_transient_unit_caps_and_sanitized_argv(self):
        args = smoke.unit_command(UNIT, ROOT, smoke.PYTHON, smoke.SCRIPT)
        for flag in ("--user", "--collect", "--slice=-.slice", "--expand-environment=no",
                     "--property=CPUQuota=100%", "--property=MemoryMax=268435456",
                     "--property=MemorySwapMax=0", "--property=TasksMax=16",
                     "--property=RuntimeMaxSec=10s", "--property=TimeoutStopSec=2s",
                     "--property=StandardOutput=null", "--property=StandardError=null"):
            self.assertIn(flag, args)
        self.assertEqual(args[-4:], (smoke.SCRIPT, "--worker", UNIT, ROOT))
        self.assertNotIn("--system", args)

    def test_cross_unit_directory_and_executable_names_refuse(self):
        for unit, root in (("ollama.service", ROOT), (UNIT, ROOT + "/.."),
                           (UNIT, ROOT.replace("a" * 32, "b" * 32))):
            with self.assertRaises(smoke.Refusal):
                smoke.names(unit, root)
        with self.assertRaises(smoke.Refusal):
            smoke.unit_command(UNIT, ROOT, "/usr/bin/python", smoke.SCRIPT)

    def test_fixed_loader_is_anchored_nofollow_measured_and_all_fds_close(self):
        raw = smoke.fixture_bytes.library_bytes()
        with patch.object(smoke.os, "open", side_effect=[10, 11, 12, 13, 14]) as acquire, \
             patch.object(smoke.os, "fstat", side_effect=lambda fd: info(fd, raw)), \
             patch.object(smoke.os, "stat", return_value=info(14, raw)), \
             patch.object(smoke.os, "read", side_effect=[raw, b""]), \
             patch.object(smoke.os, "close") as close:
            result = smoke.acquire_loader()
        self.assertEqual(result, (raw, sha256(raw).hexdigest()))
        self.assertEqual(close.call_count, 5)
        for call in acquire.call_args_list:
            self.assertTrue(call.args[1] & smoke.os.O_NOFOLLOW)
        self.assertTrue(acquire.call_args.args[1] & smoke.os.O_NONBLOCK)

    def test_unsafe_loader_denies_before_read_and_closes_directories(self):
        raw = smoke.fixture_bytes.library_bytes()
        with patch.object(smoke.os, "open", side_effect=[10, 11, 12, 13]), \
             patch.object(smoke.os, "fstat", side_effect=lambda fd: info(fd, raw)), \
             patch.object(smoke.os, "stat", return_value=info(14, raw, unsafe=True)), \
             patch.object(smoke.os, "read") as read, patch.object(smoke.os, "close") as close:
            with self.assertRaises(smoke.Refusal): smoke.acquire_loader()
        read.assert_not_called(); self.assertEqual(close.call_count, 4)

    def test_loader_acceptance_deadline_and_interrupt_close_handles(self):
        raw = smoke.fixture_bytes.library_bytes()
        for interrupted in (False, True):
            with patch.object(smoke.os, "open", side_effect=[10, 11, 12, 13, 14]), \
                 patch.object(smoke.os, "fstat", side_effect=lambda fd: info(fd, raw)), \
                 patch.object(smoke.os, "stat", return_value=info(14, raw)), \
                 patch.object(smoke.os, "read", side_effect=KeyboardInterrupt) as read, \
                 patch.object(smoke.os, "close") as close, \
                 patch.object(smoke.time, "monotonic", side_effect=[0, 1] if interrupted else [0, 3]):
                with self.assertRaises(KeyboardInterrupt if interrupted else smoke.Refusal):
                    smoke.acquire_loader()
            self.assertEqual(close.call_count, 5)
            if not interrupted: read.assert_not_called()

    def test_fixture_write_is_exclusive_nofollow_bounded(self):
        with patch.object(smoke.os, "open") as create:
            for raw in (b"", "PRIVATE", b"x" * (smoke.MAX_LOADER + 1)):
                with self.assertRaises(smoke.Refusal): smoke.write_new("/tmp/unused", raw, 0o500)
        create.assert_not_called()
        output = Mock()
        manager = MagicMock(); manager.__enter__.return_value = output
        with patch.object(smoke.os, "open", return_value=17) as create, \
             patch.object(smoke.os, "fdopen", return_value=manager):
            smoke.write_new("/tmp/never-created", b"fixed", 0o500)
        self.assertTrue(create.call_args.args[1] & smoke.os.O_EXCL)
        self.assertTrue(create.call_args.args[1] & smoke.os.O_NOFOLLOW)

    def test_loader_copy_bad_digest_or_size_denies_before_open(self):
        with patch.object(smoke.os, "open") as acquire:
            for digest, size in (("PRIVATE", 100), ("a" * 64, True), ("a" * 64, smoke.MAX_LOADER + 1)):
                with self.assertRaises(smoke.Refusal):
                    smoke.read_loader_copy(Path("/tmp/not-created"), digest, size)
        acquire.assert_not_called()

    def test_process_pin_uses_closed_expected_metadata(self):
        cfg = dict(unit=UNIT, cgroup="/user.slice/exact", uid=1000)
        with patch.object(smoke.root_test, "only_child", return_value=20), \
             patch.object(smoke.resource, "pin_record", return_value=21) as pin:
            self.assertEqual(smoke.pinned_child(10, cfg, ("fixed",)), (20, 21))
        self.assertEqual(pin.call_args.kwargs["ppid"], 10)
        self.assertEqual(pin.call_args.kwargs["cgroup"], cfg["cgroup"])
