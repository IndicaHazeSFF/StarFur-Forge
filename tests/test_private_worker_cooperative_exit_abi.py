import struct
import unittest

from scripts.private_worker_cooperative_exit_abi import ExitInfoRefused, decode_exit_status


class CooperativeExitABITests(unittest.TestCase):
    def response(self, mask, status):
        return struct.pack("<Q", mask) + b"\xa5" * 52 + struct.pack("<i", status)

    def test_status_is_raw_signed_and_ancillary_data_not_returned(self):
        for status in (0, 42 << 8, 9, -1):
            with self.subTest(status=status):
                self.assertEqual(decode_exit_status(self.response(0b1111, status)), status)

    def test_zero_without_exit_bit_is_not_success(self):
        for mask in (0, 0b0111, 1 << 59):
            with self.subTest(mask=mask), self.assertRaises(ExitInfoRefused):
                decode_exit_status(self.response(mask, 0))

    def test_short_overlong_or_mutable_response_refuses(self):
        response = self.response(8, 0)
        for bad in (response[:-1], response + b"\0" * 8, bytearray(response), None):
            with self.assertRaises(ExitInfoRefused):
                decode_exit_status(bad)
