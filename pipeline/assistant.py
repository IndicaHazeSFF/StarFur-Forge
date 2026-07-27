from dataclasses import dataclass
import json
from pathlib import Path

import ollama

from pipeline.db import list_assistant_memories
from pipeline.domains import normalize_domain

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "assistant.json"


@dataclass(frozen=True)
class AssistantConfig:
    chat_model: str
    persona_path: Path
    domain: str
    max_session_messages: int
    max_memories: int


def load_config(path=DEFAULT_CONFIG_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    persona_path = Path(data.get("persona_path", "persona/default.md"))
    if not persona_path.is_absolute():
        persona_path = PROJECT_ROOT / persona_path
    return AssistantConfig(
        chat_model=data.get("chat_model", "qwen3:8b"),
        persona_path=persona_path,
        domain=normalize_domain(data.get("domain", "personal")),
        max_session_messages=int(data.get("max_session_messages", 20)),
        max_memories=int(data.get("max_memories", 5)),
    )


def load_persona(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Persona file is empty.")
    return text


class AssistantSession:
    def __init__(self, config, persona, chat=None, memory_loader=list_assistant_memories):
        if config.max_session_messages <= 0:
            raise ValueError("max_session_messages must be positive")
        self.config = config
        self.persona = persona
        self.chat = chat or ollama.chat
        self.memory_loader = memory_loader
        self.messages = []

    def _context_messages(self, user_text):
        memories = self.memory_loader(
            domain=self.config.domain,
            status="active",
            limit=self.config.max_memories,
        )
        memory_text = "\n".join(
            f"- {memory['summary']}" for memory in memories
        ) or "(none)"
        recent = self.messages[-self.config.max_session_messages:]
        return [
            {
                "role": "system",
                "content": (
                    f"{self.persona}\n\n"
                    "Relevant active memories (reference only; do not invent):\n"
                    f"{memory_text}"
                ),
            },
            *recent,
            {"role": "user", "content": user_text},
        ]

    def respond(self, user_text):
        user_text = user_text.strip()
        if not user_text:
            return ""
        response = self.chat(
            model=self.config.chat_model,
            messages=self._context_messages(user_text),
        )
        content = response.get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("Assistant model returned empty content.")
        self.messages.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": content},
        ])
        self.messages = self.messages[-self.config.max_session_messages:]
        return content


def run_interactive(config_path=DEFAULT_CONFIG_PATH, input_fn=input, output_fn=print):
    config = load_config(config_path)
    persona = load_persona(config.persona_path)
    session = AssistantSession(config, persona)
    output_fn("StarFur Assistant (type 'quit' or 'exit' to leave)")
    while True:
        try:
            user_text = input_fn("You: ")
        except (EOFError, KeyboardInterrupt):
            output_fn("\nGoodbye.")
            return
        if user_text.strip().casefold() in {"quit", "exit"}:
            output_fn("Goodbye.")
            return
        try:
            answer = session.respond(user_text)
        except Exception as error:
            output_fn(f"Assistant error: {error}")
            continue
        if answer:
            output_fn(f"StarFur: {answer}")
