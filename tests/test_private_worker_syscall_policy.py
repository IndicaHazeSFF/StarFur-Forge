"""Pure cBPF interpretation/fake installation; never install a native filter."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location("synthetic_policy", Path(__file__).resolve().parents[1]
                                            / "scripts/private_worker_syscall_policy.py")
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def evaluate(number, argument=0, *, arch=policy.ARCH):
    data = struct.pack("<IIQ6Q", number, arch, 0, argument, 0, 0, 0, 0, 0)
    rows, pc, accumulator = policy.program(), 0, 0
    for _ in range(256):
        code, yes, no, value = rows[pc]
        if code == 0x06:
            return value
        if code == 0x20:
            accumulator = struct.unpack_from("<I", data, value)[0]
            pc += 1
        elif code in (0x15, 0x45):
            condition = accumulator == value if code == 0x15 else accumulator & value != 0
            pc += 1 + (yes if condition else no)
        else:
            raise AssertionError("unknown instruction")
    raise AssertionError("unterminated program")


class SyntheticSyscallPolicyTests(unittest.TestCase):
    def test_foreign_and_x32_abis_fail_closed(self):
        for number in (0, 41, 59, 999):
            self.assertEqual(evaluate(number, arch=0x40000003), policy.KILL)
            self.assertEqual(evaluate(number | 0x40000000), policy.KILL)

    def test_explicit_blocked_syscalls_cannot_reach_default_allow(self):
        for number in policy.BLOCKED:
            with self.subTest(number=number):
                self.assertEqual(evaluate(number), policy.DENY)

    def test_only_private_inet_socket_families_permitted(self):
        for family in range(64):
            self.assertEqual(evaluate(41, family),
                             policy.ALLOW if family in (2, 10) else policy.DENY)
        self.assertEqual(evaluate(41, (1 << 32) | 2), policy.DENY)

    def test_clone_namespace_flags_are_denied_individually_and_combined(self):
        for flag in (0x20000, 0x2000000, 0x4000000, 0x8000000,
                     0x10000000, 0x20000000, 0x40000000, policy.NEW_NAMESPACES):
            self.assertEqual(evaluate(56, flag | 17), policy.DENY)
        self.assertEqual(evaluate(56, 1 << 32), policy.DENY)
        self.assertEqual(evaluate(56, 17), policy.ALLOW)
        self.assertEqual(evaluate(435), policy.ENOSYS)

    def test_linux_exec_and_unlisted_calls_remain_allowed_not_production_policy(self):
        for number in (0, 1, 59, 60, 231, 999):
            self.assertEqual(evaluate(number), policy.ALLOW)

    def test_jumps_and_program_bound_are_valid(self):
        rows = policy.program()
        self.assertLessEqual(len(rows), 128)
        for i, (code, yes, no, _) in enumerate(rows):
            if code in (0x15, 0x45):
                self.assertLess(i + 1 + yes, len(rows))
                self.assertLess(i + 1 + no, len(rows))

    def test_missing_no_new_privileges_denies_without_syscall(self):
        lib = Mock()
        lib.prctl.return_value = 0
        with patch.object(policy.Path, "iterdir", return_value=[Path("1")]):
            with self.assertRaisesRegex(ValueError, "no_new_privileges_required"):
                policy.install(lib)
        lib.syscall.assert_not_called()

    def test_multithread_install_denies_without_syscall(self):
        lib = Mock()
        with patch.object(policy.Path, "iterdir", return_value=[Path("1"), Path("2")]):
            with self.assertRaisesRegex(ValueError, "single_thread_required"):
                policy.install(lib)
        lib.syscall.assert_not_called()

    def test_failed_install_is_not_ready(self):
        lib = Mock()
        lib.prctl.return_value = 1
        lib.syscall.return_value = -1
        with patch.object(policy.Path, "iterdir", return_value=[Path("1")]):
            with self.assertRaisesRegex(ValueError, "filter_install_failed"):
                policy.install(lib)

    def test_fake_success_requires_filter_state_observation(self):
        lib = Mock()
        lib.prctl.side_effect = [1, 2]
        lib.syscall.return_value = 0
        with patch.object(policy.Path, "iterdir", return_value=[Path("1")]):
            policy.install(lib)
        lib.syscall.assert_called_once()
