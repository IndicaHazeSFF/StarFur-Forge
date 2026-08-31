import unittest
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.provider_registry import ChatProviderRegistration, ChatProviderRegistry


class FakeChatProvider:
    name = "Fake Provider"

    def complete(self, messages, *, model=None, options=None, stream=False):
        return {"message": {"content": "unused"}}

    def list_models(self):
        return []

    def probe_health(self):
        return {"models": []}


class ProviderRegistryTests(unittest.TestCase):
    def test_registry_uses_stable_ids_without_constructing_or_calling_provider(self):
        provider = FakeChatProvider()
        registry = ChatProviderRegistry({
            "Local Ollama": ChatProviderRegistration("Local Ollama", provider),
        })

        self.assertEqual(("local-ollama",), registry.ids())
        self.assertIs(provider, registry.get("LOCAL ollama"))
        self.assertIsNone(registry.get("missing"))

    def test_registry_rejects_non_chat_adapters_and_mismatched_keys(self):
        with self.assertRaises(TypeError):
            ChatProviderRegistration("invalid", object())
        provider = FakeChatProvider()
        with self.assertRaises(ValueError):
            ChatProviderRegistry({
                "one": ChatProviderRegistration("two", provider),
            })


if __name__ == "__main__":
    unittest.main()
