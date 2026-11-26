import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.private_worker_cooperative_charge import RECEIPT, ChargeRefused, charge_once


@unittest.skipUnless(sys.platform == "linux", "Linux directory-fd contract")
class CooperativeChargeTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.addCleanup(os.close, self.fd)
        s = os.fstat(self.fd)
        self.identity = (s.st_dev, s.st_ino)

    def charge(self, *, token="1"*32, identity=None, fd=None):
        charge_once(self.fd if fd is None else fd,
                    directory_identity=self.identity if identity is None else identity,
                    attempt=token, scope_digest="2"*64)

    def test_same_approval_cannot_charge_again_with_new_handle_or_token(self):
        self.charge()
        receipt = self.root / RECEIPT
        stored = receipt.read_bytes()
        self.assertEqual(stored, b"starfur-c8l-charge-v1\n" + b"1"*32 + b"\n" + b"2"*64 + b"\n")
        self.assertEqual(stat.S_IMODE(receipt.stat().st_mode), 0o600)
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(ChargeRefused):
                self.charge(fd=fd, token="3"*32)
        finally:
            os.close(fd)
        self.assertEqual(receipt.read_bytes(), stored)

    def test_empty_entry_refuses_without_overwriting(self):
        receipt = self.root / RECEIPT
        receipt.touch()
        with self.assertRaises(ChargeRefused):
            self.charge()
        self.assertEqual(receipt.read_bytes(), b"")

    def test_symlink_refuses_without_touching_target(self):
        target = self.root / "untouched"
        target.write_bytes(b"control")
        (self.root / RECEIPT).symlink_to(target)
        with self.assertRaises(ChargeRefused):
            self.charge()
        self.assertEqual(target.read_bytes(), b"control")

    def test_wrong_identity_refuses_before_creation(self):
        with self.assertRaises(ChargeRefused):
            self.charge(identity=(self.identity[0], self.identity[1]+1))
        self.assertFalse((self.root / RECEIPT).exists())

    def test_ambiguous_fsync_leaves_entry_and_refuses_reuse(self):
        with patch("scripts.private_worker_cooperative_charge.os.fsync",
                   side_effect=[None, OSError("directory fsync failed")]) as sync:
            with self.assertRaises(ChargeRefused):
                self.charge()
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(sync.call_args.args, (self.fd,))
        self.assertTrue((self.root / RECEIPT).exists())
        with self.assertRaises(ChargeRefused):
            self.charge()

    def test_partial_write_keeps_charge_blocking_entry(self):
        real_write = os.write
        with patch("scripts.private_worker_cooperative_charge.os.write",
                   side_effect=lambda fd, data: real_write(fd, data[:1])):
            with self.assertRaises(ChargeRefused):
                self.charge()
        self.assertEqual((self.root / RECEIPT).read_bytes(), b"s")
        with self.assertRaises(ChargeRefused):
            self.charge()
