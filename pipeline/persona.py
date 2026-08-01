from pathlib import Path

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