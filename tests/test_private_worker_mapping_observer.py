"""Fake records only: never acquire live maps or run a canary."""
import unittest
from dataclasses import replace
from io import BytesIO
from unittest.mock import Mock, patch

from scripts.private_worker_mapping_observer import (
    LOADER, MAX_BYTES, MappingObservation, MappingObservationError, check_resident_mapping,
    check_cooperative_page_coverage,
    ACCEPTANCE_NS, READ_CHUNK, PausedCanaryStamp, capture_bound_mapping,
)


IDENTITY = (8, 1, 77)
SHAPE = ((0, 4096, 0, b"r--p"), (4096, 8192, 4096, b"r-xp"),
         (16384, 4096, 12288, b"r--p"), (20480, 4096, 12288, b"rw-p"))


def maps(base=0x100000, path=LOADER, inode=77, shape=SHAPE):
    return b"".join(
        b"%x-%x %s %08x 08:01 %d %s\n" % (base + start, base + start + size, mode, offset, inode, path)
        for start, size, offset, mode in shape
    )


class MappingObserverTests(unittest.TestCase):
    def check(self, raw, **kw):
        return check_resident_mapping(raw, **({"identity": IDENTITY, "segments": SHAPE} | kw))

    def test_cooperative_equivalent_splits_do_not_change_strict_checker(self):
        split = (SHAPE[0], (4096, 4096, 4096, b"r-xp"),
                 (8192, 4096, 8192, b"r-xp"), *SHAPE[2:])
        self.assertEqual(check_cooperative_page_coverage(maps(shape=split),
                         identity=IDENTITY, segments=SHAPE), MappingObservation(1, 5))
        self.assertEqual(check_cooperative_page_coverage(maps(),
                         identity=IDENTITY, segments=split), MappingObservation(1, 4))
        with self.assertRaises(MappingObservationError):
            self.check(maps(shape=split))

    def test_cooperative_split_cannot_hide_changed_offset_permissions_or_coverage(self):
        for bad_row in ((8192, 4096, 4096, b"r-xp"), (8192, 4096, 8192, b"rw-p"),
                        (8193, 4095, 8193, b"r-xp"), (8192, 2048, 8192, b"r-xp")):
            split = (SHAPE[0], (4096, 4096, 4096, b"r-xp"), bad_row, *SHAPE[2:])
            with self.subTest(row=bad_row), self.assertRaises(MappingObservationError):
                check_cooperative_page_coverage(maps(shape=split), identity=IDENTITY, segments=SHAPE)

    def test_cooperative_cannot_hide_duplicate_deleted_or_shifted_mapping(self):
        for bad in (maps() + maps(0x200000), maps(path=LOADER + b" (deleted)"),
                    maps(inode=99), maps(0x100001)):
            with self.subTest(snapshot=bad), self.assertRaises(MappingObservationError):
                check_cooperative_page_coverage(bad, identity=IDENTITY, segments=SHAPE)

    def test_distinct_segments_at_one_base_inert_and_redacted(self):
        tail = b"200000-201000 rw-p 00000000 00:00 0 [stack]\n"
        with patch("builtins.open", side_effect=AssertionError), patch("subprocess.Popen", side_effect=AssertionError):
            result = self.check(maps() + tail)
        self.assertEqual(result, MappingObservation(1, 4))
        self.assertNotIn("100000", repr(result))

    def test_duplicate_same_inode_and_shadow_loader_refuse(self):
        for extra in (maps(0x200000), maps(0x200000, b"/worker/" + LOADER.rsplit(b"/", 1)[-1], 99)):
            with self.subTest(extra=extra), self.assertRaises(MappingObservationError):
                self.check(maps() + extra)

    def test_wrong_identity_alias_deleted_and_shape_refuse(self):
        for raw in (maps(inode=78), maps(path=b"/worker/renamed.so"), maps(path=LOADER + b" (deleted)"),
                    maps().replace(b"r-xp", b"rwxp"), maps().replace(b"00001000", b"00002000"),
                    maps(shape=SHAPE[:-1]), maps().replace(b"104000", b"103000")):
            with self.subTest(raw=raw), self.assertRaises(MappingObservationError):
                self.check(raw)

    def test_malformed_truncated_oversize_and_invalid_expected_values(self):
        for raw in (maps()[:-1], b"x\n" * MAX_BYTES, maps() + b"garbage\n", maps() + maps()[:20]):
            with self.assertRaisesRegex(MappingObservationError, "^resident mapping observation refused$"):
                self.check(raw)
        for kw in ({"segments": ()}, {"segments": SHAPE[:1]}, {"identity": (8, 1, True)}):
            with self.assertRaises(MappingObservationError):
                self.check(maps(), **kw)


class BoundCaptureTests(unittest.TestCase):
    stamp = PausedCanaryStamp(25, 100, "a" * 32, "b" * 32)

    def capture(self, stream, **changes):
        options = dict(expected=self.stamp, attest_paused=lambda: self.stamp,
                       open_snapshot=lambda: stream, monotonic_ns=lambda: 0,
                       identity=IDENTITY, segments=SHAPE)
        return capture_bound_mapping(**(options | changes))

    def test_one_open_two_attestations_and_owned_stream_closed(self):
        stream = BytesIO(maps())
        opener, attest = Mock(return_value=stream), Mock(return_value=self.stamp)
        self.assertEqual(self.capture(stream, open_snapshot=opener, attest_paused=attest),
                         MappingObservation(1, 4))
        opener.assert_called_once_with()
        self.assertEqual(attest.call_count, 2)
        self.assertTrue(stream.closed)

    def test_initial_refusal_never_opens(self):
        opener = Mock()
        with self.assertRaises(MappingObservationError):
            self.capture(None, open_snapshot=opener, attest_paused=lambda: None)
        opener.assert_not_called()

    def test_reused_pid_new_epoch_resumed_or_new_pause_refuse(self):
        for actual in (replace(self.stamp, start_ticks=101),
                       replace(self.stamp, invocation="c" * 32),
                       replace(self.stamp, pause_nonce="c" * 32), None):
            stream = BytesIO(maps())
            with self.subTest(actual=actual), self.assertRaises(MappingObservationError):
                self.capture(stream, attest_paused=Mock(side_effect=[self.stamp, actual]))
            self.assertTrue(stream.closed)

    def test_limit_and_io_failure_close_stream(self):
        for stream in (BytesIO(b"x" * (MAX_BYTES + 1)), Mock(read=Mock(return_value=b"x" * (READ_CHUNK + 1))),
                       Mock(read=Mock(side_effect=OSError("private detail")))):
            with self.assertRaisesRegex(MappingObservationError, "^bound mapping capture refused$"):
                self.capture(stream)
            if isinstance(stream, BytesIO):
                self.assertTrue(stream.closed)
            else:
                stream.close.assert_called_once_with()

    def test_expired_and_backward_clock_fail_closed(self):
        for now in (ACCEPTANCE_NS, -1):
            stream = BytesIO(maps())
            with self.assertRaises(MappingObservationError):
                self.capture(stream, monotonic_ns=Mock(side_effect=[0, 0, 0, now]))
            self.assertTrue(stream.closed)

    def test_invalid_snapshot_refuses_after_closing(self):
        stream = BytesIO(b"invalid\n")
        with self.assertRaises(MappingObservationError):
            self.capture(stream)
        self.assertTrue(stream.closed)
