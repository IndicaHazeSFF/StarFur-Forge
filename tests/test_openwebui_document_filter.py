"""Static and isolated tests for the deployable OpenWebUI Filter artifact.

The artifact imports OpenWebUI's Pydantic dependency, which is not a StarFur
runtime dependency. Tests provide a tiny compatible fake, so bridge helpers
can be exercised without OpenWebUI or network services.
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest


FILTER_PATH = Path(__file__).resolve().parents[1] / "integrations" / "openwebui" / "starfur_document_filter.py"


class _BaseModel:
    def __init__(self, **values):
        for name, default in self.__class__.__dict__.items():
            if not name.startswith("_") and not callable(default) and not isinstance(default, (classmethod, staticmethod)):
                setattr(self, name, values.get(name, default))
        for name, value in values.items():
            setattr(self, name, value)


def _load_filter_module():
    previous = sys.modules.get("pydantic")
    fake_pydantic = types.ModuleType("pydantic")
    fake_pydantic.BaseModel = _BaseModel
    sys.modules["pydantic"] = fake_pydantic
    try:
        spec = importlib.util.spec_from_file_location("test_starfur_document_filter", FILTER_PATH)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            del sys.modules["pydantic"]
        else:
            sys.modules["pydantic"] = previous


class OpenWebUIDocumentFilterTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_filter_module()
        self.filter = self.module.Filter()

    def test_declares_module_level_file_handler_and_supported_types(self):
        self.assertTrue(self.module.file_handler)
        self.assertEqual(self.module.SUPPORTED_SUFFIXES, frozenset({".md", ".markdown", ".txt"}))
        self.assertEqual(self.filter.valves.OPENWEBUI_BASE_URL, "http://localhost:8080")
        self.assertEqual(self.filter.valves.REVIEW_CACHE_SECONDS, 24 * 60 * 60)

    def test_collects_deduplicated_file_references_from_both_documented_locations(self):
        body = {
            "metadata": {"files": [{"id": "one", "name": "one.md"}]},
            "files": [{"file": {"id": "one", "filename": "one.md"}}, {"id": "two", "name": "two.txt"}],
        }
        references = self.filter._attachment_references(body)
        self.assertEqual([self.filter._file_id(item) for item in references], ["one", "two"])

    def test_strips_attachment_references_to_prevent_second_rag_path(self):
        body = {"metadata": {"files": [{"id": "one"}]}, "files": [{"id": "one"}]}
        self.filter._strip_attachment_references(body)
        self.assertEqual(body["metadata"]["files"], [])
        self.assertEqual(body["files"], [])

    def test_no_attachment_or_existing_context_is_non_mutating(self):
        body = {"messages": [{"role": "user", "content": "Hello"}]}
        self.assertIs(asyncio.run(self.filter.inlet(body)), body)
        existing = {"starfur_document_context": {"review_id": "DR-kept", "limit": 1}}
        self.assertIs(asyncio.run(self.filter.inlet(existing)), existing)
        self.assertEqual(existing["starfur_document_context"]["review_id"], "DR-kept")

    def test_unsupported_or_multiple_files_do_not_inject_context_or_download(self):
        unsupported = {"metadata": {"files": [{"id": "image", "name": "picture.png"}]}}
        asyncio.run(self.filter.inlet(unsupported, __request__=object()))
        self.assertNotIn("starfur_document_context", unsupported)
        multiple = {"metadata": {"files": [{"id": "a", "name": "a.md"}, {"id": "b", "name": "b.txt"}]}}
        asyncio.run(self.filter.inlet(multiple, __request__=object()))
        self.assertNotIn("starfur_document_context", multiple)

    def test_cached_review_binds_only_review_id_and_limit_not_raw_content(self):
        body = {"metadata": {"files": [{"id": "one", "name": "one.md"}]}, "messages": [{"role": "user", "content": "question"}]}
        key = self.filter._cache_key(body["metadata"]["files"][0])
        self.filter._remember_review(key, "DR-cached", 2)
        asyncio.run(self.filter.inlet(body, __request__=object()))
        self.assertEqual(body["starfur_document_context"], {"review_id": "DR-cached", "limit": 3})
        self.assertNotIn("one.md", str(body["messages"]))

    def test_explicit_review_commands_become_controlled_extensions(self):
        review_id = "DR-" + "a" * 32
        listing = {"messages": [{"role": "user", "content": "document review list"}]}
        asyncio.run(self.filter.inlet(listing))
        self.assertEqual(listing["starfur_document_review"], {"action": "list"})

        show = {"messages": [{"role": "user", "content": f"document review {review_id}"}]}
        asyncio.run(self.filter.inlet(show))
        self.assertEqual(show["starfur_document_review"], {"action": "show", "review_id": review_id})

        approve = {"messages": [{"role": "user", "content": f"document approve {review_id} c-001 C-002"}]}
        asyncio.run(self.filter.inlet(approve))
        self.assertEqual(approve["starfur_document_review"]["action"], "approve")
        self.assertEqual(approve["starfur_document_review"]["candidate_ids"], ["C-001", "C-002"])
        self.assertEqual(approve["starfur_document_review"]["confirm"], "create pending proposals")

        reject = {"messages": [{"role": "user", "content": f"document reject {review_id} C-001"}]}
        asyncio.run(self.filter.inlet(reject))
        self.assertEqual(reject["starfur_document_review"]["action"], "reject")
        self.assertEqual(reject["starfur_document_review"]["confirm"], "reject document candidates")

    def test_non_exact_review_text_remains_normal_chat(self):
        body = {"messages": [{"role": "user", "content": "can you document review this?"}]}
        asyncio.run(self.filter.inlet(body))
        self.assertNotIn("starfur_document_review", body)

    def test_new_attachment_annotates_then_binds_only_review_metadata(self):
        calls = []
        events = []

        async def emit(event):
            events.append(event)

        def download(reference, request):
            calls.append(("download", self.filter._file_id(reference), request))
            return "facts.md", "My desktop has an RTX 4070 graphics card."

        def annotate(path, payload):
            calls.append(("annotate", path, payload))
            return {"review": {"id": "DR-created", "candidate_count": 1}}

        self.filter._download_file = download
        self.filter._starfur_json = annotate
        body = {
            "metadata": {"files": [{"id": "new", "name": "facts.md"}]},
            "messages": [{"role": "user", "content": "What graphics card is in the desktop?"}],
        }
        asyncio.run(self.filter.inlet(body, __request__=object(), __event_emitter__=emit))
        self.assertEqual(body["starfur_document_context"], {"review_id": "DR-created", "limit": 3})
        self.assertEqual(calls[0][:2], ("download", "new"))
        self.assertEqual(calls[1][0], "annotate")
        self.assertEqual(calls[1][1], "/v1/starfur/documents/annotate")
        self.assertEqual(calls[1][2]["domain"], "personal")
        self.assertEqual(calls[1][2]["profile"], "auto")
        self.assertNotIn("RTX 4070", str(body["messages"]))
        self.assertIn("DR-created", events[-1]["data"]["description"])
        repeated = {
            "metadata": {"files": [{"id": "new", "name": "facts.md"}]},
            "messages": [{"role": "user", "content": "Tell me about the GPU."}],
        }
        asyncio.run(self.filter.inlet(repeated, __request__=object()))
        self.assertEqual(repeated["starfur_document_context"], {"review_id": "DR-created", "limit": 3})
        self.assertEqual(len(calls), 2, "an active review must be reused rather than re-annotated")

    def test_attachment_download_timeout_reports_sanitized_stage(self):
        events = []

        async def emit(event):
            events.append(event)

        def download(_reference, _request):
            raise TimeoutError("internal endpoint detail must not be exposed")

        self.filter._download_file = download
        body = {
            "metadata": {"files": [{"id": "slow", "name": "story.md"}]},
            "messages": [{"role": "user", "content": "Continue."}],
        }
        asyncio.run(self.filter.inlet(body, __request__=object(), __event_emitter__=emit))
        self.assertNotIn("starfur_document_context", body)
        description = events[-1]["data"]["description"]
        self.assertIn("attachment download failed safely (timed out)", description)
        self.assertNotIn("internal endpoint detail", description)

    def test_annotation_transport_failure_reports_sanitized_stage(self):
        events = []

        async def emit(event):
            events.append(event)

        self.filter._download_file = lambda _reference, _request: ("story.md", "Story text")

        def annotate(_path, _payload):
            raise OSError("private connection detail")

        self.filter._starfur_json = annotate
        body = {
            "metadata": {"files": [{"id": "story", "name": "story.md"}]},
            "messages": [{"role": "user", "content": "Continue."}],
        }
        asyncio.run(self.filter.inlet(body, __request__=object(), __event_emitter__=emit))
        description = events[-1]["data"]["description"]
        self.assertIn("StarFur annotation request failed safely (transport error)", description)
        self.assertNotIn("private connection detail", description)


if __name__ == "__main__":
    unittest.main()
