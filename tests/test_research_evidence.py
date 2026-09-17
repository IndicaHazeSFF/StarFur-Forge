import hashlib
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_claims import ResearchClaim, ResearchClaimSet
from pipeline.research_evidence import assess_research_evidence
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def source(ref, url, text):
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, url), "93.184.216.34", 100.0,
        "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    return research_source_from_web_artifact(ref, artifact)


class ResearchEvidenceTests(unittest.TestCase):
    def test_labels_citation_diversity_without_claiming_corroboration(self):
        first = source("TF-a", "https://one.example/a", "One")
        second = source("TF-b", "https://two.example/b", "Two")
        packet = build_research_source_packet("Question?", [first, second])
        claims = ResearchClaimSet(1, packet.packet_sha256, (
            ResearchClaim(1, "RC-001", "One source.", (first.source_id,), 0.8),
            ResearchClaim(1, "RC-002", "Two sources.", (first.source_id, second.source_id), 0.8),
        ))

        assessment = assess_research_evidence(packet, claims)

        self.assertEqual("single_source", assessment.for_claim("RC-001").citation_diversity)
        second_entry = assessment.for_claim("RC-002")
        self.assertEqual("multiple_sources_multiple_hosts", second_entry.citation_diversity)
        self.assertEqual(2, second_entry.cited_source_count)
        self.assertEqual(2, second_entry.cited_host_count)
        self.assertFalse(hasattr(assessment, "verified"))
        self.assertFalse(hasattr(assessment, "corroborated"))

    def test_same_host_and_packet_mismatch_are_handled_conservatively(self):
        first = source("TF-a", "https://example.com/a", "One")
        second = source("TF-b", "https://example.com/b", "Two")
        packet = build_research_source_packet("Question?", [first, second])
        claims = ResearchClaimSet(1, packet.packet_sha256, (
            ResearchClaim(1, "RC-001", "Two sources.", (first.source_id, second.source_id), 0.8),
        ))
        assessment = assess_research_evidence(packet, claims)
        self.assertEqual("multiple_sources_one_host", assessment.for_claim("RC-001").citation_diversity)
        with self.assertRaisesRegex(ValueError, "binding"):
            assess_research_evidence(
                build_research_source_packet("Other?", [first, second]), claims,
            )


if __name__ == "__main__":
    unittest.main()
