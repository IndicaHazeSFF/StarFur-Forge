import hashlib
import json
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import parse_research_claims, research_claim_json_schema
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def packet():
    text = "The referenced standard was published in 1969."
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, "https://example.com/standard"),
        "93.184.216.34", 100.0, "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    source = research_source_from_web_artifact("TF-standard_1", artifact)
    return build_research_source_packet("When was the standard published?", [source])


def output(source_packet, **changes):
    value = {
        "schema_version": 1,
        "packet_sha256": source_packet.packet_sha256,
        "claims": [{
            "claim_id": "RC-001",
            "statement": "The referenced standard was published in 1969.",
            "source_ids": [source_packet.source_ids()[0]],
            "confidence": 0.9,
        }],
    }
    value.update(changes)
    return json.dumps(value)


class ResearchClaimTests(unittest.TestCase):
    def test_provider_schema_is_exactly_bound_but_not_a_replacement_for_parsing(self):
        source_packet = packet()
        schema = research_claim_json_schema(source_packet)

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            source_packet.packet_sha256,
            schema["properties"]["packet_sha256"]["const"],
        )
        self.assertEqual(
            list(source_packet.source_ids()),
            schema["properties"]["claims"]["items"]["properties"]["source_ids"]["items"]["enum"],
        )
        self.assertEqual(16, schema["properties"]["claims"]["maxItems"])
        # The strict parser remains authoritative even when provider-side
        # schema guidance exists.
        with self.assertRaises(ValueError):
            parse_research_claims("{}", source_packet)

    def test_exact_packet_local_citation_is_accepted_as_untrusted_claim(self):
        source_packet = packet()
        result = parse_research_claims(output(source_packet), source_packet)
        self.assertEqual(source_packet.packet_sha256, result.packet_sha256)
        self.assertEqual((source_packet.source_ids()[0],), result.claims[0].source_ids)

    def test_one_whole_response_json_fence_is_recovered_then_validated_strictly(self):
        source_packet = packet()
        fenced = "```json\n" + output(source_packet) + "\n```\n"
        result = parse_research_claims(fenced, source_packet)
        self.assertEqual(source_packet.packet_sha256, result.packet_sha256)

        for malformed in (
            "Here is the JSON:\n```json\n" + output(source_packet) + "\n```",
            "```python\n" + output(source_packet) + "\n```",
            "```json\n[]\n```",
            "```json\n" + output(source_packet) + "\n```\nextra",
        ):
            with self.subTest(malformed=malformed[:24]), self.assertRaisesRegex(ValueError, "strict JSON|fence"):
                parse_research_claims(malformed, source_packet)

    def test_stale_packet_and_unknown_citation_reject(self):
        source_packet = packet()
        with self.assertRaisesRegex(ValueError, "stale or mismatched"):
            parse_research_claims(output(source_packet, packet_sha256="0" * 64), source_packet)
        raw = json.loads(output(source_packet))
        raw["claims"][0]["source_ids"] = ["RS-" + "0" * 24]
        with self.assertRaisesRegex(ValueError, "outside its packet"):
            parse_research_claims(json.dumps(raw), source_packet)

    def test_unknown_duplicate_and_authority_fields_reject(self):
        source_packet = packet()
        raw = json.loads(output(source_packet))
        raw["claims"][0]["approval"] = True
        with self.assertRaisesRegex(ValueError, "fields are invalid"):
            parse_research_claims(json.dumps(raw), source_packet)
        duplicate = (
            '{"schema_version":1,"schema_version":1,"packet_sha256":"'
            + source_packet.packet_sha256 + '","claims":[]}'
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON keys"):
            parse_research_claims(duplicate, source_packet)

    def test_claims_must_be_ordered_bounded_and_cited(self):
        source_packet = packet()
        raw = json.loads(output(source_packet))
        raw["claims"][0]["claim_id"] = "RC-002"
        with self.assertRaisesRegex(ValueError, "ordered"):
            parse_research_claims(json.dumps(raw), source_packet)
        raw = json.loads(output(source_packet))
        raw["claims"][0]["source_ids"] = []
        with self.assertRaisesRegex(ValueError, "citations"):
            parse_research_claims(json.dumps(raw), source_packet)

    def test_empty_claim_set_is_valid_inability_to_extract(self):
        source_packet = packet()
        result = parse_research_claims(
            json.dumps({
                "schema_version": 1,
                "packet_sha256": source_packet.packet_sha256,
                "claims": [],
            }),
            source_packet,
        )
        self.assertEqual((), result.claims)


if __name__ == "__main__":
    unittest.main()
