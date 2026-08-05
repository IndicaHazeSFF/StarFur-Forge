"""Deterministic, read-only help payloads for direct command questions.

Core owns command syntax and safety rules. Personas may later add presentation around
these payloads, but must not rewrite the rendered command block.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandHelp:
    """A concise, public instruction payload for one command family."""

    intent: str
    title: str
    commands: tuple[str, ...]
    notes: tuple[str, ...] = ()

    def render(self) -> str:
        lines = [self.title, ""]
        lines.extend(f"  {command}" for command in self.commands)
        if self.notes:
            lines.extend(["", *self.notes])
        return "\n".join(lines)


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    return any(term in value for term in terms)


def detect_command_help(query: str) -> CommandHelp | None:
    """Return exact Core help for clear command-use questions only.

    Ordinary capability or conversational questions intentionally return ``None``
    so they retain normal persona/model behavior.
    """
    value = " ".join((query or "").casefold().split())
    if not value:
        return None

    if _contains_any(value, (
        "how do i approve", "how can i approve", "approve new memories",
        "approve memories", "look at proposals", "show proposals", "where are proposals",
        "see proposals", "view proposals", "review new memories", "review your new memories",
        "review my new memories", "how do i review", "how can i review",
        "pending memories", "memories pending", "memories for approval",
    )):
        return CommandHelp(
            intent="proposal_review",
            title="To review proposed memories, use:",
            commands=(
                "proposal list",
                "proposal inspect <id>",
                "proposal approve <id>",
                "proposal reject <id>",
                "proposal approve all",
            ),
            notes=("For `proposal approve all`, StarFur requires a second confirmation: `approve all`.",),
        )

    if _contains_any(value, (
        "how do i show context", "how can i show context", "how do i see context",
        "how can i see context", "how do i view context", "context diagnostics",
        "context diagnostic", "context statistics", "context stats help",
    )):
        return CommandHelp(
            intent="context_diagnostics",
            title="To view read-only diagnostics for the most recent completed turn, use:",
            commands=("context stats",),
            notes=("This command does not call a model or change memories, proposals, SQLite, or Chroma.",),
        )

    if _contains_any(value, (
        "how do i select a model", "how can i select a model", "how do i switch models",
        "how can i switch models", "how do i change models", "how can i change models",
        "how do i view models", "how can i view models", "how do i list models",
    )):
        return CommandHelp(
            intent="model_selection",
            title="To view or change the active local chat model, use:",
            commands=("model list", "model current", "model use <model-name>"),
            notes=("Changing models affects later chat and proposal-extraction calls in this session.",),
        )

    if _contains_any(value, ("how do i inspect the persona", "how can i inspect the persona", "how do i inspect murr", "how can i inspect murr")):
        return CommandHelp(
            intent="persona_inspection",
            title="To view the read-only Persona Runtime state, use:",
            commands=("persona inspect",),
            notes=("This shows bounded state metadata and does not display the full persona prompt or change state.",),
        )
    if _contains_any(value, (
        "how do i remember", "how can i remember", "how do i save a memory",
        "how can i save a memory", "how do i forget", "how can i forget",
        "how do i make you forget", "how can i make you forget",
        "how do i get you to forget", "how can i get you to forget",
        "how do i remove a memory", "how can i remove a memory",
        "how do i list memories", "how can i list memories", "how do i search memories",
        "how can i search memories", "how do i inspect a memory", "how can i inspect a memory",
    )):
        return CommandHelp(
            intent="memory_controls",
            title="To manage active assistant memories in the current domain, use:",
            commands=(
                "remember this: <fact to store>",
                "forget this: <memory to deactivate>",
                "memory list",
                "memory search <query>",
                "memory inspect <id>",
            ),
            notes=("Forgetting is a soft status change that preserves historical provenance.",),
        )

    return None


__all__ = ["CommandHelp", "detect_command_help"]