import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import annotator


class AnnotatorRetryTests(unittest.TestCase):
    def setUp(self):
        self.prompt_patch = patch.object(
            annotator,
            "build_system_prompt",
            return_value="test prompt",
        )
        self.prompt_patch.start()

    def tearDown(self):
        self.prompt_patch.stop()

    def test_malformed_output_is_retried_and_valid_output_keeps_schema(self):
        valid = {"known_entities": [{"name": "Elias Voss", "type": "character"}]}
        responses = [
            {"message": {"content": "not json"}},
            {"message": {"content": ""}},
            {"message": {"content": json.dumps(valid)}},
        ]

        with patch.object(annotator.ollama, "chat", side_effect=responses, create=True) as chat:
            with patch.object(annotator, "record_llm_performance"):
                with self.assertLogs("pipeline.annotator", level="WARNING") as logs:
                    result = annotator.annotate("chapter prose")

        self.assertEqual(chat.call_count, 3)
        self.assertEqual(result["known_entities"], valid["known_entities"])
        self.assertEqual(result["entity_facts"], [])
        self.assertEqual(result["events"], [])
        self.assertEqual(len(logs.records), 2)
        self.assertIn("malformed JSON", logs.records[0].message)
        self.assertIn("empty message content", logs.records[1].message)

    def test_nested_wrong_type_is_retried(self):
        responses = [
            {
                "message": {
                    "content": json.dumps({"known_entities": ["Elias Voss"]})
                }
            },
            {"message": {"content": json.dumps({"known_entities": []})}},
        ]

        with patch.object(
            annotator.ollama,
            "chat",
            side_effect=responses,
            create=True,
        ) as chat:
            with patch.object(annotator, "record_llm_performance"):
                with self.assertLogs("pipeline.annotator", level="WARNING") as logs:
                    result = annotator.annotate("chapter prose")

        self.assertEqual(chat.call_count, 2)
        self.assertEqual(result["known_entities"], [])
        self.assertIn("known_entities", logs.records[0].message)
        self.assertIn("must be an object", logs.records[0].message)

    def test_annotation_sets_a_hard_output_token_ceiling(self):
        response = {"message": {"content": json.dumps({})}}

        with patch.object(
            annotator.ollama,
            "chat",
            return_value=response,
            create=True,
        ) as chat:
            with patch.object(annotator, "record_llm_performance"):
                annotator.annotate("chapter prose")

        options = chat.call_args.kwargs["options"]
        self.assertEqual(
            options["num_predict"],
            annotator.ANNOTATION_MAX_OUTPUT_TOKENS,
        )

    def test_persistent_invalid_output_raises_retryable_parse_error(self):
        responses = [
            {"message": {"content": ""}},
            {"message": {"content": "{} trailing"}},
            {"message": {"content": "still invalid"}},
        ]

        with patch.object(annotator.ollama, "chat", side_effect=responses, create=True) as chat:
            with patch.object(annotator, "record_llm_performance"):
                with self.assertLogs("pipeline.annotator", level="WARNING") as logs:
                    with self.assertRaises(annotator.AnnotationParseError) as raised:
                        annotator.annotate("chapter prose")

        self.assertEqual(chat.call_count, annotator.ANNOTATION_MAX_ATTEMPTS)
        self.assertEqual(raised.exception.attempts, 3)
        self.assertEqual(len(logs.records), 3)


if __name__ == "__main__":
    unittest.main()
