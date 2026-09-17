import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.providers import ChatCompletion
from pipeline.research_disclosure import ResearchProviderTarget
from pipeline.research_provider import LocalResearchClaimProvider


class ResearchProviderTests(unittest.TestCase):
    def test_exact_local_target_returns_only_normalized_text(self):
        calls = []
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        provider = LocalResearchClaimProvider(
            target,
            lambda messages, model: calls.append((messages, model)) or ChatCompletion("{}"),
        )
        messages = ({"role": "system", "content": "one"}, {"role": "user", "content": "two"})

        self.assertEqual("{}", provider.propose_claims(messages, model="qwen3:8b"))
        self.assertEqual([(messages, "qwen3:8b")], calls)

    def test_target_mismatch_and_unavailable_provider_fail_closed(self):
        target = ResearchProviderTarget.create("ollama", "qwen3:8b", "local")
        unavailable = LocalResearchClaimProvider(target, lambda *_args: "{}", available=False)
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            unavailable.propose_claims(({}, {}), model="qwen3:8b")
        provider = LocalResearchClaimProvider(target, lambda *_args: "{}")
        with self.assertRaisesRegex(ValueError, "does not match"):
            provider.propose_claims(({}, {}), model="other")

    def test_hosted_target_is_rejected_before_provider_use(self):
        target = ResearchProviderTarget.create("hosted", "remote", "hosted")
        with self.assertRaisesRegex(ValueError, "must be local"):
            LocalResearchClaimProvider(target, lambda *_args: "{}")


if __name__ == "__main__":
    unittest.main()
