from pathlib import Path
import re

from pipeline.persona_state import DynamicTraits, MomentaryState, PersonaState


NEUTRAL_PERSONA = (
    "You are a helpful, clear, and respectful assistant. "
    "Answer naturally and directly. Be honest about uncertainty and avoid inventing facts."
)


class Persona(str):
    """Immutable presentation/style instructions with string compatibility."""

    def render_prompt(self):
        return str(self)


def load_persona(path=None):
    """Load persona presentation instructions, falling back safely when unavailable."""
    if path is None:
        return Persona(NEUTRAL_PERSONA)
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return Persona(NEUTRAL_PERSONA)
    if not text or len(text) > 20000:
        return Persona(NEUTRAL_PERSONA)
    return Persona(text)


def _derived_persona_id(path: Path | None) -> str:
    raw = path.stem.casefold() if path is not None else "default"
    normalized = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-_")
    if not normalized or not normalized[0].isalpha():
        return "default"
    return normalized[:64]


def _derived_display_name(prompt: str, fallback: str) -> str:
    """Use a Markdown title when available without interpreting persona prose."""
    for line in prompt.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            title = re.sub(r"\s+(assistant\s+)?persona$", "", match.group(1), flags=re.IGNORECASE).strip()
            if title:
                return title[:120]
    return fallback.replace("-", " ").replace("_", " ").title()


def load_persona_state(path=None, *, persona_id: str | None = None, display_name: str | None = None) -> PersonaState:
    """Return a compatibility state snapshot without changing persona prompt output.

    The complete existing rendered persona prompt remains ``static_identity`` so
    current style instructions are preserved exactly. Dynamic and momentary values
    intentionally remain neutral defaults until a later state-derivation stage.
    """
    resolved_path = Path(path) if path is not None else None
    prompt = load_persona(resolved_path).render_prompt()
    resolved_id = persona_id or _derived_persona_id(resolved_path)
    resolved_name = display_name or _derived_display_name(prompt, resolved_id)
    return PersonaState(
        persona_id=resolved_id,
        display_name=resolved_name,
        static_identity=prompt,
        dynamic_traits=DynamicTraits(),
        momentary_state=MomentaryState(),
    )