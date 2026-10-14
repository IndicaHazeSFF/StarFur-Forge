import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.command_input import has_ambiguous_multiline_controls, is_context_stats_request


class CommandInputTests(unittest.TestCase):
    def test_mixed_requests_are_rejected_without_parsing_or_dispatch(self):
        for control in (
            "context stats", "show me context diagnostics", "routing probe",
            "adventure turn commit", "tool execute TI-example", "tool grant TI-example",
            "persona use nova", "model use another-model", "focus mode on",
            "proposal approve all", "approve all", "memory scope M-001 personal",
            "remember this: a fact", "forget: a fact", "roleplay begin story", "quit",
        ):
            for separator in ("\n", "\r\n", "\r"):
                with self.subTest(control=control, separator=separator):
                    self.assertTrue(has_ambiguous_multiline_controls("ordinary chat" + separator + control))
                    self.assertTrue(has_ambiguous_multiline_controls(control + separator + "ordinary chat"))

    def test_multiple_control_lines_are_not_a_batch(self):
        self.assertTrue(has_ambiguous_multiline_controls("routing status\ncontext stats"))
        self.assertTrue(has_ambiguous_multiline_controls("  TOOL GRANT TI-example\n tool approve TI-example"))

    def test_blank_lines_do_not_make_one_control_ambiguous(self):
        for text in ("", "\n\n", "context stats", "\n context stats \n\n", "tool grant TI-example"):
            self.assertFalse(has_ambiguous_multiline_controls(text))

    def test_ordinary_multiline_prose_is_preserved(self):
        self.assertFalse(has_ambiguous_multiline_controls(
            "Please discuss this poem.\nMemory fades with time.\nModel the moon in clay.\n"
            "The character asks about context stats in the story."
        ))

    def test_fenced_and_quoted_command_examples_remain_data(self):
        for text in (
            "Explain these controls:\n```text\ncontext stats\ntool grant TI-example\n```",
            "Explain:\n~~~\ncontext stats\n~~~",
            "Explain:\n> context stats\n> tool grant TI-example",
            'Explain:\n"context stats"\n\'adventure turn commit\'',
            "Explain:\n`context stats`\n`tool grant TI-example`",
            "Explain:\n````\n```\ncontext stats\n```\n````",
            "Explain this incomplete code block:\n```\ncontext stats",
        ):
            self.assertFalse(has_ambiguous_multiline_controls(text))

    def test_controls_after_closed_fences_are_still_rejected(self):
        self.assertTrue(has_ambiguous_multiline_controls("```\ncontext stats\n```\ncontext stats"))
        self.assertTrue(has_ambiguous_multiline_controls("~~~\ncontext stats\n~~~~\nmodel current"))

    def test_only_whole_documented_diagnostic_requests_match(self):
        for text in ("context stats", "Show me context diagnostics", "what are my current context stats?", "display context stats"):
            self.assertTrue(is_context_stats_request(text))
        for text in (
            "How do I show context diagnostics?", "Explain the context stats command.",
            "invent fictional context stats", "context stats\nother text", '"context stats"',
            "write a story and show context stats", "show context stats for another conversation",
        ):
            self.assertFalse(is_context_stats_request(text))


if __name__ == "__main__":
    unittest.main()
