from dataclasses import replace
from hashlib import sha256
import unittest

from scripts.private_worker_cooperative_charge_scope import (
    APPROVAL, ChargeScope, ChargeScopeRefused, bind_charge_scope,
)


class ChargeScopeTests(unittest.TestCase):
    def setUp(self):
        self.expected = ChargeScope(APPROVAL, 1000, (8, 42), "a" * 64, "b" * 64)

    def test_equal_independent_records_have_canonical_digest(self):
        want = sha256(
            b"starfur-cooperative-charge-scope-v1\nc8l-cooperative-one-shot\n1000\n8\n42\n"
            + b"a" * 64 + b"\n" + b"b" * 64 + b"\n"
        ).hexdigest()
        self.assertEqual(bind_charge_scope(expected=self.expected, observed=replace(self.expected)), want)

    def test_each_independent_binding_must_match(self):
        for field, value in (
            ("approval", "c8-other"), ("directory_uid", 1001),
            ("directory_identity", (9, 42)), ("directory_identity", (8, 43)),
            ("loader_sha256", "c" * 64), ("launch_plan_sha256", "d" * 64),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ChargeScopeRefused):
                bind_charge_scope(expected=self.expected, observed=replace(self.expected, **{field: value}))

    def test_equal_but_invalid_records_refuse(self):
        for field, value in (
            ("directory_uid", True), ("directory_uid", 0),
            ("directory_identity", (8, 0)), ("directory_identity", (True, 42)),
            ("directory_identity", (8, 1 << 64)), ("loader_sha256", "0" * 64),
            ("launch_plan_sha256", "B" * 64), ("launch_plan_sha256", "b" * 64 + "\n"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ChargeScopeRefused):
                bad = replace(self.expected, **{field: value})
                bind_charge_scope(expected=bad, observed=bad)

    def test_distinct_valid_scope_digests_are_separate(self):
        first = bind_charge_scope(expected=self.expected, observed=self.expected)
        second_scope = replace(self.expected, directory_identity=(8, 43))
        second = bind_charge_scope(expected=second_scope, observed=second_scope)
        self.assertNotEqual(first, second)
