"""Pure bytecode interpretation only, never install filters or start workers."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from tests.test_private_worker_syscall_policy import evaluate, policy as interpreter

spec = importlib.util.spec_from_file_location("cwd_policy", Path(__file__).resolve().parents[1]
                                            / "scripts/private_worker_cwd_policy.py")
cwd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cwd)


def guarded(number, argument=0, *, arch=cwd.base.ARCH):
    with patch.object(interpreter, "program", new=cwd.program):
        return evaluate(number, argument, arch=arch)


class SyntheticCwdPolicyTests(unittest.TestCase):
    def test_cwd_changes_deny_independent_of_pointer_or_fd(self):
        for number in (80, 81):
            for argument in (0, 1, 3, 0xFFFFFFFFFFFFFFFF):
                self.assertEqual(guarded(number, argument), cwd.base.DENY)

    def test_original_policy_is_not_silently_modified(self):
        for number in (80, 81):
            self.assertEqual(evaluate(number), cwd.base.ALLOW)
        self.assertIsNot(cwd.base, interpreter)

    def test_all_other_tested_syscalls_preserve_original_semantics(self):
        for number in range(451):
            if number in (80, 81): continue
            for argument in (0, 2, cwd.base.NEW_NAMESPACES):
                self.assertEqual(guarded(number, argument), evaluate(number, argument))

    def test_arch_and_x32_refuse_before_cwd_branch(self):
        for number in (0, 80, 81, 999):
            self.assertEqual(guarded(number, arch=0x40000003), cwd.base.KILL)
            self.assertEqual(guarded(number | 0x40000000), cwd.base.KILL)

    def test_bounded_immutable_terminating_jumps(self):
        rows = cwd.program()
        self.assertIs(type(rows), tuple); self.assertLessEqual(len(rows), 128)
        for i, (code, yes, no, _) in enumerate(rows):
            if code in (0x15, 0x45):
                self.assertLess(i + 1 + yes, len(rows)); self.assertLess(i + 1 + no, len(rows))

    def test_missing_expected_tail_and_oversized_base_deny(self):
        for value in ((), ((0x06, 0, 0, cwd.base.DENY),),
                      ((0x20, 0, 0, 0),) * 128 + ((0x06, 0, 0, cwd.base.ALLOW),)):
            with patch.object(cwd.base, "program", return_value=value):
                with self.assertRaises(ValueError): cwd.program()

    def test_program_construction_has_no_io_or_installer(self):
        with patch("builtins.open", side_effect=AssertionError), \
             patch("ctypes.CDLL", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError):
            self.assertTrue(cwd.program())
        self.assertTrue(callable(cwd.install))  # explicit only, never called by program()

    def test_install_requires_one_thread_and_no_new_privileges(self):
        for tasks, privileges in (([Path("1"), Path("2")], 1), ([Path("1")], 0)):
            lib = Mock(); lib.prctl.return_value = privileges
            with patch.object(cwd.Path, "iterdir", return_value=tasks):
                with self.assertRaises(ValueError): cwd.install(lib)
            lib.syscall.assert_not_called()

    def test_fake_install_checks_kernel_return_and_state(self):
        for result, observed in ((-1, 2), (0, 0), (0, 2)):
            lib = Mock(); lib.prctl.side_effect = [1, observed]; lib.syscall.return_value = result
            with patch.object(cwd.Path, "iterdir", return_value=[Path("1")]):
                if result == 0 and observed == 2: cwd.install(lib)
                else:
                    with self.assertRaises(ValueError): cwd.install(lib)
            lib.syscall.assert_called_once()

    def test_explicit_header_preflight_requires_exact_numbers_and_clone_fs(self):
        good = "\n".join(f"#define __NR_{name} {number}" for name, number in
                         (("fstat", 5), ("getcwd", 79), ("chdir", 80), ("fchdir", 81), ("unshare", 272)))
        for header, sched, valid in ((good, "#define CLONE_FS 0x00000200", True),
                                      (good.replace("chdir 80", "chdir 99"), "#define CLONE_FS 0x200", False),
                                      (good, "#define CLONE_FS 0x400", False)):
            with patch.object(cwd.base, "verify_abi") as base_check, \
                 patch.object(cwd.Path, "read_text", side_effect=[header, sched]):
                if valid: cwd.verify_abi()
                else:
                    with self.assertRaises(ValueError): cwd.verify_abi()
            base_check.assert_called_once()

    def test_unknown_calls_remain_allowed_not_production_policy(self):
        self.assertEqual(guarded(999), cwd.base.ALLOW)
