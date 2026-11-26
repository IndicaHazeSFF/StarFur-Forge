"""Supplied rows only; no native descriptor or process operations."""

from dataclasses import replace
import unittest

from scripts.private_worker_cooperative_fds import (
    DescriptorReviewError, Direction, PipeEnd, check_descriptor_split,
)


class DescriptorSplitTests(unittest.TestCase):
    def setUp(self):
        self.parent = (PipeEnd(7, 3, 90, Direction.READ, True, True),
                       PipeEnd(8, 3, 91, Direction.WRITE, True, True))
        self.child = (PipeEnd(4, 3, 90, Direction.WRITE, False, True),
                      PipeEnd(5, 3, 91, Direction.READ, False, True))

    def check(self, **overrides):
        return check_descriptor_split(**{
            "ready_identity": (3, 90), "release_identity": (3, 91),
            "parent": self.parent, "child": self.child, **overrides,
        })

    def test_exact_split_and_order_independent_inventory(self):
        self.assertIsNone(self.check())
        self.assertIsNone(self.check(child=self.child[::-1]))

    def test_child_inheritance_direction_identity_and_fd_must_match(self):
        for change in ({"close_on_exec": True}, {"direction": Direction.READ},
                       {"inode": 95}, {"fd": 9}, {"anonymous_pipe": False},
                       {"device": True}):
            with self.subTest(change=change), self.assertRaises(DescriptorReviewError):
                self.check(child=(replace(self.child[0], **change), self.child[1]))

    def test_duplicate_and_extra_channels_refuse(self):
        for ends in ((self.child[0], self.child[0]), self.child + self.child[:1],
                     self.child[:1], list(self.child)):
            with self.subTest(ends=ends), self.assertRaises(DescriptorReviewError):
                self.check(child=ends)
        with self.assertRaises(DescriptorReviewError):
            self.check(ready_identity=(3, 91))

    def test_parent_ends_stay_cloexec_and_complement_child(self):
        for change in ({"close_on_exec": False}, {"direction": Direction.WRITE},
                       {"fd": self.parent[1].fd}, {"inode": 91}):
            with self.subTest(change=change), self.assertRaises(DescriptorReviewError):
                self.check(parent=(replace(self.parent[0], **change), self.parent[1]))
