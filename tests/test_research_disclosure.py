import hashlib
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.research_disclosure import (
    ResearchDisclosureIntent,
    ResearchProviderTarget,
    evaluate_research_disclosure,
)
from pipeline.research_sources import build_research_source_packet, research_source_from_web_artifact
from pipeline.tool_web_connector import WebFetchedArtifact
from pipeline.tool_web_parser import QuarantinedWebText
from pipeline.tool_web_policy import WebDestination


def source_packet():
    text = "A public source fact."
    digest = hashlib.sha256(text.encode()).hexdigest()
    artifact = WebFetchedArtifact(
        1, "a" * 64, WebDestination(1, "https://example.com/fact"),
        "93.184.216.34", 100.0, "b" * 64, "c" * 64,
        QuarantinedWebText(1, "text/plain", "untrusted_external", text, len(text), digest, digest),
    )
    source = research_source_from_web_artifact("TF-fact_1", artifact)
    return build_research_source_packet("What is the fact?", [source])


class ResearchDisclosureTests(unittest.TestCase):
    def test_exact_public_packet_to_local_provider_is_permitted(self):
        packet = source_packet()
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        intent = ResearchDisclosureIntent.from_packet(packet, target)
        decision = evaluate_research_disclosure(intent, packet)
        self.assertEqual("permitted", decision.status)
        self.assertEqual("permitted_public_local", decision.reason)

    def test_hosted_provider_is_denied_without_an_exception_path(self):
        packet = source_packet()
        target = ResearchProviderTarget.create("hosted", "model-v1", "hosted")
        decision = evaluate_research_disclosure(
            ResearchDisclosureIntent.from_packet(packet, target), packet,
        )
        self.assertEqual("denied", decision.status)
        self.assertEqual("hosted_disclosure_unsupported", decision.reason)

    def test_stale_packet_and_tampered_intent_deny(self):
        packet = source_packet()
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        intent = ResearchDisclosureIntent.from_packet(packet, target)
        stale = type(intent)(
            1, "0" * 64, intent.source_count, intent.source_character_count,
            intent.data_classification, intent.purpose, target, intent.policy_revision,
        )
        self.assertEqual("packet_binding_mismatch", evaluate_research_disclosure(stale, packet).reason)
        changed = type(intent)(
            1, intent.packet_sha256, intent.source_count, intent.source_character_count - 1,
            intent.data_classification, intent.purpose, target, intent.policy_revision,
        )
        self.assertEqual("intent_mismatch", evaluate_research_disclosure(changed, packet).reason)

    def test_target_digest_cannot_be_forged(self):
        with self.assertRaisesRegex(ValueError, "digest is inconsistent"):
            ResearchProviderTarget(1, "ollama", "qwen3:8b", "local", "0" * 64)
        target = ResearchProviderTarget.create(
            "ollama", "hf.co/google/gemma-4-12B-it-qat-q4_0-gguf:latest", "local",
        )
        self.assertTrue(target.target_sha256)


if __name__ == "__main__":
    unittest.main()
