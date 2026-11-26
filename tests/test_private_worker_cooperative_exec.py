import unittest
from dataclasses import replace
from unittest.mock import Mock

from scripts.private_worker_cooperative_exec import prepare_exec_slots
from scripts.private_worker_cooperative_fds import DescriptorReviewError, Direction, PipeEnd


class CooperativeExecTests(unittest.TestCase):
    def setup_case(self, inputs):
        identities = ((1, 42), (1, 43))
        parents = tuple(
            PipeEnd(fd, *identity, direction, True, True)
            for fd, identity, direction in zip((8, 9), identities, (Direction.READ, Direction.WRITE))
        )
        children = tuple(
            PipeEnd(fd, *identity, direction, True, True)
            for fd, identity, direction in zip(inputs, identities, (Direction.WRITE, Direction.READ))
        )
        table = {end.fd: (end, False) for end in children}

        def dup(fd, target, cloexec):
            if target in table:
                raise AssertionError("would clobber an occupied slot")
            row, blocking = table[fd]
            table[target] = replace(row, fd=target, close_on_exec=cloexec), blocking
            return target

        def dup_scratch(fd, minimum):
            return dup(fd, next(slot for slot in range(minimum, 20) if slot not in table), True)

        ops = Mock()
        ops.inventory.side_effect = lambda: frozenset(table)
        ops.observe.side_effect = lambda fd, identity: table[fd][0]
        ops.get_blocking.side_effect = lambda fd: table[fd][1]
        ops.close.side_effect = table.pop
        ops.dup_cloexec.side_effect = dup_scratch
        ops.dup_to_inheritable.side_effect = lambda fd, target: dup(fd, target, False)
        ops.set_blocking.side_effect = lambda fd, blocking: table.update({fd: (table[fd][0], blocking)})
        kwargs = dict(ready_identity=identities[0], release_identity=identities[1],
                      parent=parents, child=children, ops=ops)
        return table, ops, kwargs

    def test_overlapping_swapped_and_low_inputs(self):
        for inputs in ((4, 5), (5, 4), (0, 1), (6, 4), (5, 7), (14, 15)):
            with self.subTest(inputs=inputs):
                table, ops, kwargs = self.setup_case(inputs)
                a, b = prepare_exec_slots(**kwargs)
                self.assertEqual(set(table), {4, 5})
                self.assertEqual((a.fd, a.direction, a.close_on_exec), (4, Direction.WRITE, False))
                self.assertEqual((b.fd, b.direction, b.close_on_exec), (5, Direction.READ, False))
                self.assertFalse(table[4][1])
                self.assertTrue(table[5][1])
                ops.set_blocking.assert_called_once()

    def test_unknown_descriptor_is_not_closed_or_clobbered(self):
        for unexpected in (3, 4, 5, 19):
            with self.subTest(unexpected=unexpected):
                table, ops, kwargs = self.setup_case((0, 1))
                table[unexpected] = None
                with self.assertRaises(DescriptorReviewError):
                    prepare_exec_slots(**kwargs)
                ops.close.assert_not_called()
                ops.dup_cloexec.assert_not_called()

    def test_wrong_initial_blocking_does_not_mutate(self):
        table, ops, kwargs = self.setup_case((4, 5))
        table[5] = table[5][0], True
        with self.assertRaises(DescriptorReviewError):
            prepare_exec_slots(**kwargs)
        ops.close.assert_not_called()
        ops.set_blocking.assert_not_called()

    def test_partial_scratch_duplication_cleans_owned_numbers(self):
        table, ops, kwargs = self.setup_case((5, 4))
        duplicate = ops.dup_cloexec.side_effect

        def fail_second(fd, minimum):
            if fd == 4:
                raise OSError("dup failed")
            return duplicate(fd, minimum)

        ops.dup_cloexec.side_effect = fail_second
        with self.assertRaises(DescriptorReviewError):
            prepare_exec_slots(**kwargs)
        self.assertEqual(table, {})
        self.assertEqual(sorted(c.args[0] for c in ops.close.call_args_list), [4, 5, 6])

    def test_partial_target_installation_cleans_new_slot_and_scratch(self):
        table, ops, kwargs = self.setup_case((5, 4))
        duplicate = ops.dup_to_inheritable.side_effect

        def fail_second(fd, slot):
            if slot == 5:
                raise OSError("dup failed")
            return duplicate(fd, slot)

        ops.dup_to_inheritable.side_effect = fail_second
        with self.assertRaises(DescriptorReviewError):
            prepare_exec_slots(**kwargs)
        self.assertEqual(table, {})
        self.assertEqual([c.args[0] for c in ops.close.call_args_list], [5, 4, 4, 6, 7])

    def test_ambiguous_close_is_never_retried(self):
        table, ops, kwargs = self.setup_case((4, 5))

        def report_failure(fd):
            table.pop(fd)
            if fd == 4:
                raise OSError("close outcome ambiguous")

        ops.close.side_effect = report_failure
        with self.assertRaises(DescriptorReviewError):
            prepare_exec_slots(**kwargs)
        self.assertEqual(table, {})
        self.assertEqual([c.args[0] for c in ops.close.call_args_list].count(4), 1)
        ops.dup_to_inheritable.assert_not_called()

    def test_final_extra_descriptor_refuses_and_closes_only_its_own(self):
        table, ops, kwargs = self.setup_case((4, 5))

        def final_extra(fd, identity):
            if fd == 5 and not table[fd][0].close_on_exec:
                table[17] = None
            return table[fd][0]

        ops.observe.side_effect = final_extra
        with self.assertRaises(DescriptorReviewError):
            prepare_exec_slots(**kwargs)
        self.assertEqual(table, {17: None})

    def test_final_release_reader_must_actually_be_blocking(self):
        table, ops, kwargs = self.setup_case((4, 5))
        ops.set_blocking.side_effect = None
        with self.assertRaises(DescriptorReviewError):
            prepare_exec_slots(**kwargs)
        self.assertEqual(table, {})
