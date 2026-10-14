"""Pure input framing for Core controls; never dispatch or split a request.

An unquoted command-shaped line inside a multiline request is ambiguous. Reject
the whole request instead of executing any subset or letting a model invent
command results. Quoted/fenced examples remain data, not command authority.
"""

from __future__ import annotations


MIXED_CONTROL_INPUT_GUIDANCE = (
    "Mixed or multiline Core control input was not processed. "
    "Send chat text and each Core command as separate messages. "
    "Use `context stats` by itself for real diagnostics. "
    "Quote command examples or place them in a fenced code block when discussing them. "
    "No command or model request was run."
)

_CONTEXT_STATS_REQUESTS = frozenset({
    "context stats",
    "show context stats", "show me context stats", "display context stats",
    "show context diagnostics", "show me context diagnostics", "display context diagnostics",
    "show current context stats", "show my context stats",
    "what are my context stats", "what are my current context stats",
    "what are the current context stats",
})
# A framing hint only, not a dispatcher or authoritative command catalog.
# Limit second words so ordinary prose such as "memory fades" remains chat.
_CONTROL_VERBS = {
    "adventure": frozenset({
        "list", "create", "inspect", "load", "refresh", "resume", "begin", "restart",
        "session", "status", "events", "event", "imports", "import", "transcript",
        "checkpoint", "checkpoints", "corrections", "retract", "state", "correct",
        "relationships", "relationship", "knowledge", "participants", "participant",
        "resources", "resource", "turn", "record", "pause", "end", "unload",
    }),
    "tool": frozenset({
        "help", "list", "status", "preview", "propose", "grant", "approve", "prepare",
        "execute", "artifact", "deny", "revoke", "cancel", "fetch", "search", "research",
    }),
    "persona": frozenset({"list", "current", "curretn", "use", "inspect", "assets"}),
    "resident": frozenset({"status", "action"}),
    "routing": frozenset({"status", "probe"}),
    "route": frozenset({"status", "probe"}),
    "focus": frozenset({"mode"}),
    "model": frozenset({"list", "current", "use"}),
    "roleplay": frozenset({"begin", "end", "status"}),
    "memory": frozenset({"list", "search", "inspect", "scope"}),
    "proposal": frozenset({"list", "inspect", "approve", "reject", "scope"}),
}
_EXACT_CONTROLS = frozenset({
    "approve all", "list models", "list personas", "adventures", "quit", "exit",
})
_FACT_CONTROL_PREFIXES = ("remember:", "remember this:", "forget:", "forget this:")


def is_context_stats_request(text: str) -> bool:
    """Match only whole-message, documented read-only diagnostic requests."""
    value = text.strip().casefold()
    if value.endswith("?"):
        value = value[:-1]
    return value in _CONTEXT_STATS_REQUESTS


def _is_control_line(line: str) -> bool:
    value = line.strip().casefold()
    words = value.split(maxsplit=2)
    verbs = _CONTROL_VERBS.get(words[0])
    return (
        is_context_stats_request(value)
        or value in _EXACT_CONTROLS
        or (verbs is not None and (len(words) == 1 or words[1] in verbs))
        or value.startswith(_FACT_CONTROL_PREFIXES)
    )


def has_ambiguous_multiline_controls(text: str) -> bool:
    """Identify unquoted control lines in a multiline message without authority.

    Only nonempty lines count. Markdown blockquotes, quoted strings, and inline
    code do not match control prefixes. Backtick/tilde fenced blocks are skipped;
    a closing fence must use the same marker, at least the opening length, and
    no trailing content. This is conservative input framing, not a Markdown
    parser, command syntax validator, or security sandbox.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    fence_marker = None
    fence_length = 0
    for line in lines:
        marker = line[0]
        length = len(line) - len(line.lstrip(marker))
        if fence_marker is not None:
            if marker == fence_marker and length >= fence_length and not line[length:].strip():
                fence_marker = None
            continue
        if marker in {"`", "~"} and length >= 3:
            fence_marker, fence_length = marker, length
            continue
        if _is_control_line(line):
            return True
    return False


__all__ = [
    "MIXED_CONTROL_INPUT_GUIDANCE", "has_ambiguous_multiline_controls", "is_context_stats_request",
]
