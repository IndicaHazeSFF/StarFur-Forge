from dataclasses import FrozenInstanceError
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.tool_web_policy import (
    MAX_WEB_REDIRECT_HOPS,
    WebDestination,
    WebResolutionEvidence,
    evaluate_web_connection,
    evaluate_web_destination,
    evaluate_web_redirect,
)


def evidence(**changes):
    values = {
        "schema_version": 1,
        "host": "example.com",
        "port": 443,
        "addresses": ("93.184.216.34",),
        "resolver_revision": "resolver-v1",
        "observed_at_epoch": 100.0,
        "expires_at_epoch": 200.0,
    }
    values.update(changes)
    return WebResolutionEvidence(**values)


class ToolWebPolicyTests(unittest.TestCase):
    def test_exact_https_destination_with_public_evidence_is_permitted_without_io(self):
        destination = WebDestination(1, "https://example.com/reference?q=starfur")
        with patch.object(socket, "create_connection", side_effect=AssertionError("must not connect")):
            decision = evaluate_web_destination(destination, evidence(), now_epoch=150.0)
        self.assertTrue(decision.permitted)
        self.assertEqual(("93.184.216.34",), decision.approved_addresses)

    def test_non_https_credentials_fragments_and_noncanonical_hosts_reject(self):
        invalid = (
            "http://example.com/",
            "https://user@example.com/",
            "https://example.com/#fragment",
            "https://EXAMPLE.com/",
            "https://example.com:444/",
            "https://example.com\\private",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                WebDestination(1, url)

    def test_literal_local_private_link_local_and_metadata_addresses_reject(self):
        invalid = (
            "https://127.0.0.1/",
            "https://10.0.0.1/",
            "https://169.254.169.254/latest/meta-data/",
            "https://[::1]/",
            "https://localhost/",
            "https://service.localhost/",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                WebDestination(1, url)

    def test_missing_stale_mismatched_and_private_resolution_deny(self):
        destination = WebDestination(1, "https://example.com/")
        self.assertEqual("resolution_missing", evaluate_web_destination(destination, None, now_epoch=150).reason)
        self.assertEqual("resolution_invalid", evaluate_web_destination(destination, {}, now_epoch=150).reason)
        self.assertEqual("resolution_stale", evaluate_web_destination(destination, evidence(), now_epoch=200).reason)
        self.assertEqual(
            "resolution_mismatch",
            evaluate_web_destination(destination, evidence(host="other.example"), now_epoch=150).reason,
        )
        self.assertEqual(
            "destination_forbidden",
            evaluate_web_destination(
                destination, evidence(addresses=("169.254.169.254",)), now_epoch=150,
            ).reason,
        )

    def test_resolution_is_canonical_bounded_and_short_lived(self):
        with self.assertRaisesRegex(ValueError, "unique and sorted"):
            evidence(addresses=("93.184.216.35", "93.184.216.34"))
        with self.assertRaisesRegex(ValueError, "canonical"):
            evidence(addresses=("2001:0db8::1",))
        with self.assertRaisesRegex(ValueError, "lifetime"):
            evidence(expires_at_epoch=401.0)
        with self.assertRaisesRegex(ValueError, "address count"):
            evidence(addresses=())

    def test_contracts_are_immutable_and_decision_is_not_authority(self):
        destination = WebDestination(1, "https://example.com/")
        with self.assertRaises(FrozenInstanceError):
            destination.url = "https://other.example/"
        decision = evaluate_web_destination(destination, evidence(), now_epoch=150)
        rendered = repr(decision).casefold()
        for forbidden in ("grant", "approval", "confirmation", "principal", "provider"):
            self.assertNotIn(forbidden, rendered)

    def test_connect_time_address_must_remain_in_fresh_approved_set(self):
        destination = WebDestination(1, "https://example.com/")
        self.assertTrue(evaluate_web_connection(
            destination, evidence(), connected_address="93.184.216.34", now_epoch=150,
        ).permitted)
        self.assertEqual(
            "address_not_approved",
            evaluate_web_connection(
                destination, evidence(), connected_address="93.184.216.35", now_epoch=150,
            ).reason,
        )
        self.assertEqual(
            "resolution_stale",
            evaluate_web_connection(
                destination, evidence(), connected_address="93.184.216.34", now_epoch=200,
            ).reason,
        )

    def test_connect_time_address_rejects_noncanonical_invalid_and_private_values(self):
        destination = WebDestination(1, "https://example.com/")
        for address, reason in (
            (None, "address_invalid"),
            ("not-an-address", "address_invalid"),
            ("2001:0db8::1", "address_invalid"),
            ("127.0.0.1", "destination_forbidden"),
        ):
            with self.subTest(address=address):
                self.assertEqual(reason, evaluate_web_connection(
                    destination,
                    evidence(addresses=("127.0.0.1",)) if address == "127.0.0.1" else evidence(),
                    connected_address=address,
                    now_epoch=150,
                ).reason)

    def test_redirect_target_is_independently_resolved_and_bounded(self):
        current = WebDestination(1, "https://example.com/start")
        target = WebDestination(1, "https://cdn.example.net/reference")
        target_evidence = evidence(host="cdn.example.net", addresses=("93.184.216.35",))
        decision = evaluate_web_redirect(
            current, target, target_evidence, hop_number=1, now_epoch=150,
        )
        self.assertTrue(decision.permitted)
        self.assertEqual(("93.184.216.35",), decision.approved_addresses)
        self.assertEqual(
            "resolution_mismatch",
            evaluate_web_redirect(current, target, evidence(), hop_number=1, now_epoch=150).reason,
        )
        self.assertEqual(
            "redirect_hop_limit",
            evaluate_web_redirect(
                current, target, target_evidence,
                hop_number=MAX_WEB_REDIRECT_HOPS + 1, now_epoch=150,
            ).reason,
        )

    def test_redirect_loop_and_invalid_hop_reject_without_io(self):
        current = WebDestination(1, "https://example.com/start")
        with patch.object(socket, "getaddrinfo", side_effect=AssertionError("must not resolve")):
            self.assertEqual(
                "redirect_loop",
                evaluate_web_redirect(current, current, evidence(), hop_number=1, now_epoch=150).reason,
            )
        for hop in (0, -1, True, 1.0):
            with self.subTest(hop=hop), self.assertRaises(ValueError):
                evaluate_web_redirect(current, current, evidence(), hop_number=hop, now_epoch=150)


if __name__ == "__main__":
    unittest.main()
