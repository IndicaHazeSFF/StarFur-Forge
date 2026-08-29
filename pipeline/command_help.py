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
                "proposal scope <id> <scope|type-derived>",
            ),
            notes=("For `proposal approve all`, StarFur requires a second confirmation: `approve all`. Scope changes are explicit; `type-derived` clears an explicit scope.",),
        )

    if _contains_any(value, (
        "how do i start roleplay", "how can i start roleplay", "how do i begin roleplay",
        "how do i start an adventure", "how can i start an adventure", "roleplay mode",
    )):
        return CommandHelp(
            intent="roleplay_session",
            title="To start or end the current session's bounded roleplay mode, use:",
            commands=("roleplay begin [optional title]", "roleplay status", "roleplay end"),
            notes=("You can also say 'let's roleplay' or 'let's go on an adventure'. This initial mode is session-only; no adventure workspace or replay history is created yet.",),
        )

    if _contains_any(value, (
        "how do i create an adventure", "how can i create an adventure",
        "how do i list adventures", "how can i list adventures",
        "how do i inspect an adventure", "how can i inspect an adventure",
        "how do i resume an adventure", "how can i resume an adventure",
        "how do i begin a saved adventure", "how can i begin a saved adventure",
        "how do i start an existing adventure", "how can i start an existing adventure",
        "how do i start a fresh adventure", "how can i start a fresh adventure",
        "how do i restart an adventure", "how can i restart an adventure",
        "how do i create an adventure checkpoint", "how can i create an adventure checkpoint",
        "how do i list adventure checkpoints", "how can i list adventure checkpoints",
        "how do i pause an adventure", "how can i pause an adventure",
        "how do i end an adventure", "how can i end an adventure",
        "how do i record an adventure event", "how can i record an adventure event",
        "how do i correct an adventure event", "how can i correct an adventure event",
        "how do i retract an adventure event", "how can i retract an adventure event",
        "how do i see story state", "how can i see story state",
        "how do i set story state", "how can i set story state",
        "how do i see adventure relationships", "how can i see adventure relationships",
        "how do i set adventure relationships", "how can i set adventure relationships",
        "how do i see character knowledge", "how can i see character knowledge",
        "how do i set character knowledge", "how can i set character knowledge",
        "how do i stage an adventure turn", "how can i stage an adventure turn",
        "how do i commit an adventure turn", "how can i commit an adventure turn",
        "how do i change adventure resources", "how can i change adventure resources",
        "how do i manage adventure resources", "how can i manage adventure resources",
    )):
        return CommandHelp(
            intent="adventure_registry",
            title="To prepare or inspect an isolated future adventure workspace, use:",
            commands=("adventure list", "adventure create <title>", "adventure inspect <title>", "adventure load <title>", "adventure resume <title>", "adventure begin <title>", "adventure restart fresh <new title>", "adventure restart established <checkpoint-id|label>: <new title>", "adventure session", "adventure status", "adventure events", "adventure event provenance <AE-######>", "adventure imports", "adventure import inspect <AI-######>", "adventure import bundles", "adventure import bundle create <title>: <AI-######> <AI-######> [... ]", "adventure import bundle inspect <AB-######>", "adventure import bundle status <AB-######>", "adventure import map <AI-######> <C-###> <premise|state|relationship|knowledge|resource|exclude>", "adventure import mappings <AI-######>", "adventure import status <AI-######>", "adventure import commit premise <AI-######> <C-###>", "adventure import commit state <AI-######> <C-###> <key>: <value>", "adventure import commit relationship <AI-######> <C-###> <character> <dimension>: <value>", "adventure import commit knowledge <AI-######> <C-###> <character> <knows|believes|uncertain>: <fact>", "adventure import commit resource <AI-######> <C-###> <resource-id> <operation>[: <value>]", "adventure transcript", "adventure transcript record <user|narrator>: <text>", "adventure checkpoint <label>", "adventure checkpoints", "adventure checkpoint inspect <checkpoint-id|label>", "adventure corrections", "adventure retract <AE-######>: <reason>", "adventure state", "adventure state set <key>: <value>", "adventure correct state <AE-######> <key>: <value>", "adventure relationships", "adventure relationship set <character> <dimension>: <value>", "adventure correct relationship <AE-######> <character> <dimension>: <value>", "adventure knowledge", "adventure knowledge set <character> <knows|believes|uncertain>: <fact>", "adventure correct knowledge <AE-######> <character> <knows|believes|uncertain>: <fact>", "adventure resources", "adventure resource <resource-id> <operation>[: <value>]", "adventure correct resource <AE-######> <resource-id> <operation>[: <value>]", "adventure turn begin", "adventure turn status", "adventure turn generate <completed user-turn text>", "adventure turn generate transcript", "adventure turn generation status", "adventure turn candidates", "adventure turn mutations generate <completed user-turn text>", "adventure turn mutations generate transcript", "adventure turn mutation generation status", "adventure turn mutations", "adventure turn inspect", "adventure turn remove <staged-event-number>", "adventure turn stage candidate <TC-###>", "adventure turn stage mutation candidate <TM-###>", "adventure turn stage <event-type>: <summary>", "adventure turn stage resource <resource-id> <operation>[: <value>]", "adventure turn commit", "adventure turn abort", "adventure record <event-type>: <summary>", "adventure pause", "adventure end", "adventure unload"),
            notes=("`adventure restart fresh <new title>` creates and mounts a completely isolated new workspace; the previous adventure stays unchanged and no events, state, checkpoints, or roleplay context carry over. `adventure restart established <checkpoint-id|label>: <new title>` creates and mounts an isolated child workspace from one verified checkpoint of the currently loaded adventure; it copies only that authoritative prefix and immutable scenario catalog, records the parent/checkpoint origin, and excludes later parent events, checkpoints, and roleplay context. It is not a restore or rewind. `adventure checkpoint <label>` names the current immutable authoritative event-log prefix; `adventure checkpoints` lists those references; `adventure checkpoint inspect` recomputes only that prefix's bounded derived facts. `adventure corrections` is a read-only audit of active, superseded, and retracted event IDs. The four `adventure correct` forms append one schema-v2 typed replacement for a currently active state, relationship, character-knowledge, or resource event. `adventure retract` appends a Core-owned audit event that makes one currently active event stop affecting projections; it never deletes history and cannot retract a retraction. These controls never infer edits from narration, correct ordinary prose events, or resolve contradictions. `adventure turn` stages up to sixteen ordinary validated event drafts in memory. `adventure turn generate` is an explicit, model-backed request for untrusted ordinary-event candidates; it only fills the review inbox. Use `adventure turn generate transcript` only after explicitly recording the latest adjacent `user` then `narrator` transcript pair. That source remains untrusted presentation history, not story truth. Review candidates and stage only the desired ones before `adventure turn commit` appends the whole batch; `adventure turn abort` discards it. Existing state/relationship/knowledge controls remain immediate in this initial transaction slice. `adventure state set` records one explicit current-state value; keys use lowercase letters, numbers, and underscores (for example `current_location`). `adventure relationship set` records one qualitative character/dimension value (for example `Vespera trust: cautious`); it never infers a relationship from narration. `adventure knowledge set` records one character-specific perspective (for example `Vespera believes: the hatch is trapped`); beliefs and uncertainty are not automatically world truth. `adventure resource` validates an operation against the workspace's immutable scenario catalog; use JSON only when a structured value such as an inventory item/count pair is needed. Public values appear in `adventure resources`; hidden values never reach ordinary prompts or inspection. `adventure resume` loads a saved workspace but does not start roleplay automatically. `adventure pause` and `adventure end` preserve stored events; `end story now` is an exact immediate alias. Use only these event types: choice, discovery, promise, lie, relationship_change, emotional_transition, state_change, unresolved_hook, character_knowledge, inventory_change, location_change, or resource_change. Recording is explicit; ordinary narration is never captured automatically.",),
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
        "how do i inspect persona assets", "how can i inspect persona assets",
        "how do i see persona asset slots", "how can i see persona asset slots",
    )):
        return CommandHelp(
            intent="persona_assets",
            title="To inspect the active persona's declared visual asset slots, use:",
            commands=("persona assets",),
            notes=("This is read-only package metadata; it does not expose paths or load asset files.",),
        )
    if _contains_any(value, (
        "how do i change resident action", "how can i change resident action",
        "how do i change what murr is doing", "how can i change what murr is doing",
        "how do i set apartment activity", "how can i set apartment activity",
    )):
        return CommandHelp(
            intent="resident_action",
            title="To set the current persona's explicit apartment activity, use:",
            commands=(
                "resident status",
                "resident action <idle|resting|reading|working|waiting|chatting|adventuring>",
                "resident action clear",
            ),
            notes=("This is restart-ephemeral presentation state only. It does not start work, call a provider, or change memory.",),
        )
    if _contains_any(value, ("how do i switch persona", "how can i switch persona", "how do i change persona", "how can i change persona", "how do i list personas", "how can i list personas", "how do i select a persona", "how can i select a persona")):
        return CommandHelp(
            intent="persona_selection",
            title="To view or change the active persona for this session, use:",
            commands=("persona list", "persona current", "persona use <persona-id>", "persona inspect"),
            notes=("Selecting a persona clears only this session's recent conversation context; shared memory and system capabilities stay unchanged.",),
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
                "memory scope <id> <scope|type-derived>",
            ),
            notes=("Forgetting is a soft status change that preserves historical provenance. Scope changes are explicit; `type-derived` clears an explicit scope.",),
        )

    return None


__all__ = ["CommandHelp", "detect_command_help"]
