"""Structural fixture checks only; no files, loader, processes or native unit."""
import importlib.util
from pathlib import Path
import struct
from hashlib import sha256
import unittest
from unittest.mock import patch

from pipeline.document_job_worker_elf import _inspect_metadata, inspect_worker_elf, WorkerElfError
from pipeline.document_job_worker_elf_search import review_worker_elf_search

spec = importlib.util.spec_from_file_location("loader_fixture", Path(__file__).resolve().parents[1]
                                            / "scripts/private_worker_loader_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class LoaderFixtureTests(unittest.TestCase):
    def test_c4_fixture_bytes_remain_identical_to_verified_native_checkpoint(self):
        self.assertEqual(sha256(fixture.canary_bytes()).hexdigest(), "5219dd61126b4a1e04ad986f2df4df59ab1478ea4665658b4f7a647b38e62786")
        self.assertEqual(sha256(fixture.library_bytes()).hexdigest(), "2100c3eef9c15c7e27a74f1667f8fe119e1c49c31c228dbead7be1169d7476ae")
        self.assertEqual(sha256(fixture.library_bytes(decoy=True)).hexdigest(), "52e6357b2736a445fa122b270f9a41785ce67aaab0d30ac3f409141dd46433b4")

    def test_c5_fixed_mixed_path_stays_unaccepted_by_core(self):
        raw = fixture.cwd_canary_bytes()
        metadata, search = _inspect_metadata(raw, review_search=True)
        self.assertEqual(search, {29: "$ORIGIN:/build/llama-server-cpu/bin:"})
        self.assertEqual(metadata.needed, ("libfixture.so",))
        self.assertEqual(review_worker_elf_search(raw).category, "mixed_or_unsupported")
        with self.assertRaises(WorkerElfError): inspect_worker_elf(raw)
        self.assertEqual(len(raw), 8192)

    def test_c5_fixed_code_interpretation_checks_fd_errno_and_cwd_after_exec(self):
        # Tiny fixed-opcode interpreter, never machine execution. Native gate is separate.
        def interpret(*, valid_fd=True, chdir=-1, fchdir=-1, cwd=b"/cwd\0", directory=True):
            raw = bytearray(fixture.cwd_canary_bytes()); struct.pack_into("<Q", raw, 0x1200, 0x500000)
            pc, rax, rdi, rsi, equal = 0x400, 0, 0, 0, False
            def value(address, count):
                if address == 0x500000: return 42
                return int.from_bytes(raw[address - 0x400000:address - 0x400000 + count], "little")
            for _ in range(128):
                op = bytes(raw[pc:pc + 3])
                if raw[pc] in (0xB8, 0xBE, 0xBF):
                    n = struct.unpack_from("<I", raw, pc + 1)[0]
                    if raw[pc] == 0xB8: rax = n
                    elif raw[pc] == 0xBE: rsi = n
                    else: rdi = n
                    pc += 5
                elif op in (b"\x48\x8d\x35", b"\x48\x8d\x3d", b"\x48\x8b\x05"):
                    address = 0x400000 + pc + 7 + struct.unpack_from("<i", raw, pc + 3)[0]
                    if op == b"\x48\x8d\x35": rsi = address
                    elif op == b"\x48\x8d\x3d": rdi = address
                    else: rax = value(address, 8)
                    pc += 7
                elif raw[pc:pc + 2] == b"\x8b\x05":
                    address = 0x400000 + pc + 6 + struct.unpack_from("<i", raw, pc + 2)[0]
                    rax = value(address, 4); pc += 6
                elif raw[pc:pc + 2] == b"\x8b\x38": rdi = value(rax, 4); pc += 2
                elif raw[pc] == 0x25: rax &= struct.unpack_from("<I", raw, pc + 1)[0]; pc += 5
                elif raw[pc] == 0x3D: equal = rax == struct.unpack_from("<I", raw, pc + 1)[0]; pc += 5
                elif op == b"\x48\x83\xf8":
                    equal = rax == struct.unpack_from("<b", raw, pc + 3)[0]; pc += 4
                elif raw[pc:pc + 2] in (b"\x81\x3d", b"\x80\x3d"):
                    count = 4 if raw[pc] == 0x81 else 1; size = 6 + count
                    address = 0x400000 + pc + size + struct.unpack_from("<i", raw, pc + 2)[0]
                    equal = value(address, count) == int.from_bytes(raw[pc + 6:pc + size], "little"); pc += size
                elif raw[pc:pc + 2] == b"\x0f\x85":
                    jump = struct.unpack_from("<i", raw, pc + 2)[0]; pc += 6 + (0 if equal else jump)
                elif raw[pc:pc + 2] == b"\x0f\x05":
                    if rax == 60: return rdi
                    if rax == 5:
                        self.assertEqual(rdi, 3)
                        struct.pack_into("<I", raw, rsi - 0x400000 + 24, 0x4000 if directory else 0x8000)
                        rax = 0 if valid_fd else -9
                    elif rax == 80:
                        self.assertEqual(raw[rdi - 0x400000:rdi - 0x400000 + 7], b"/decoy\0"); rax = chdir
                    elif rax == 81: self.assertEqual(rdi, 3); rax = fchdir
                    elif rax == 79:
                        raw[rdi - 0x400000:rdi - 0x400000 + len(cwd)] = cwd; rax = len(cwd)
                    else: self.fail("unexpected fixture syscall")
                    pc += 2
                else: self.fail("unexpected fixture opcode")
            self.fail("fixture did not terminate")
        self.assertEqual(interpret(), 42)
        for changes in (dict(valid_fd=False), dict(directory=False), dict(chdir=0),
                        dict(fchdir=0), dict(chdir=-13), dict(cwd=b"/bad\0"), dict(cwd=b"/cwdX")):
            self.assertEqual(interpret(**changes), 112)

    def test_inert_deterministic_fixed_bounded_output(self):
        with patch("builtins.open", side_effect=AssertionError), \
             patch("subprocess.Popen", side_effect=AssertionError), \
             patch("socket.socket", side_effect=AssertionError):
            self.assertEqual(fixture.canary_bytes(), fixture.canary_bytes())
            self.assertEqual(len(fixture.canary_bytes()), 8192)
            self.assertEqual(len(fixture.library_bytes()), 8192)

    def test_main_names_only_synthetic_library_and_fixed_interpreter(self):
        raw = fixture.canary_bytes()
        value, search = _inspect_metadata(raw, review_search=True)
        self.assertEqual(value.needed, ("libfixture.so",))
        self.assertEqual(value.interpreter, "/lib64/ld-linux-x86-64.so.2")
        self.assertEqual(search, {29: "$ORIGIN"})
        self.assertEqual(review_worker_elf_search(raw).category, "exact_origin")
        with self.assertRaises(WorkerElfError):
            inspect_worker_elf(raw)

    def test_library_is_data_only_no_dependencies_or_interpreter(self):
        value = inspect_worker_elf(fixture.library_bytes())
        self.assertEqual(value.needed, ())
        self.assertIsNone(value.interpreter)
        self.assertEqual(value.object_kind, "shared_object")

    def test_fixed_symbol_data_intended_and_decoy_differ_only_by_value(self):
        intended, decoy = fixture.library_bytes(), fixture.library_bytes(decoy=True)
        self.assertEqual(struct.unpack_from("<I", intended, 0x1200)[0], 42)
        self.assertEqual(struct.unpack_from("<I", decoy, 0x1200)[0], 13)
        self.assertEqual([i for i, pair in enumerate(zip(intended, decoy)) if pair[0] != pair[1]], [0x1200])

    def test_fixed_glob_dat_relocation_and_sysv_symbol_table(self):
        raw = fixture.canary_bytes()
        self.assertEqual(struct.unpack_from("<QQq", raw, 0x800), (0x401200, (1 << 32) | 6, 0))
        self.assertEqual(struct.unpack_from("<IIIII", raw, 0x780), (1, 2, 1, 0, 0))
        self.assertEqual(struct.unpack_from("<IBBHQQ", raw, 0x718), (1, 0x11, 0, 0, 0, 4))

    def test_no_writable_executable_load_segment(self):
        for raw in (fixture.canary_bytes(), fixture.library_bytes()):
            count = struct.unpack_from("<H", raw, 56)[0]
            for i in range(count):
                row = struct.unpack_from("<IIQQQQQQ", raw, 64 + 56 * i)
                if row[0] == 1:
                    self.assertNotEqual(row[1] & 3, 3)

    def test_decoy_selector_is_not_arbitrary_payload_or_integer(self):
        for value in (1, 13, "PRIVATE", None):
            with self.assertRaises(ValueError):
                fixture.library_bytes(decoy=value)
