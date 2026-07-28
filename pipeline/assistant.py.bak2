from dataclasses import dataclass
import json
from pathlib import Path

import ollama

from pipeline.db import (
    create_assistant_memory,
    get_assistant_memory,
    list_assistant_memories,
    search_assistant_memories,
    update_assistant_memory,
)
from pipeline.domains import normalize_domain

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "assistant.json"
MEMORY_POLICIES = ("off", "conservative")
PROPOSAL_FIELDS = {
    "store", "subject", "memory_type", "summary", "details",
    "importance", "confidence", "retention", "domain", "source",
}


@dataclass(frozen=True)
class AssistantConfig:
    chat_model: str
    persona_path: Path
    domain: str
    max_session_messages: int
    max_memories: int
    memory_policy: str


def load_config(path=DEFAULT_CONFIG_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    persona_path = Path(data.get("persona_path", "persona/default.md"))
    if not persona_path.is_absolute():
        persona_path = PROJECT_ROOT / persona_path
    policy = data.get("memory_policy", "conservative")
    if policy not in MEMORY_POLICIES:
        raise ValueError(f"Invalid memory_policy: {policy!r}")
    return AssistantConfig(
        chat_model=data.get("chat_model", "qwen3:8b"),
        persona_path=persona_path,
        domain=normalize_domain(data.get("domain", "personal")),
        max_session_messages=int(data.get("max_session_messages", 20)),
        max_memories=int(data.get("max_memories", 5)),
        memory_policy=policy,
    )


def load_persona(path):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Persona file is empty.")
    return text


def validate_memory_proposal(value, default_domain):
    if not isinstance(value, dict) or set(value) - PROPOSAL_FIELDS:
        raise ValueError("Memory proposal must be an object with known fields.")
    required = {"store", "subject", "memory_type", "summary", "importance", "confidence", "retention", "domain", "source"}
    if not required.issubset(value):
        raise ValueError("Memory proposal is missing required fields.")
    if not isinstance(value["store"], bool) or not isinstance(value["subject"], str) or not value["subject"].strip():
        raise ValueError("Invalid memory proposal subject/store.")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("Invalid memory proposal summary.")
    if "details" in value and value["details"] is not None and not isinstance(value["details"], str):
        raise ValueError("Invalid memory proposal details.")
    from pipeline.db import normalize_memory_type, normalize_retention
    normalize_memory_type(value["memory_type"])
    normalize_retention(value["retention"])
    domain = normalize_domain(value["domain"])
    if not 0 <= value["importance"] <= 1 or not 0 <= value["confidence"] <= 1:
        raise ValueError("Memory proposal scores must be between 0 and 1.")
    return {
        **value,
        "domain": domain,
        "details": value.get("details"),
        "source": str(value["source"]),
    }


class AssistantSession:
    def __init__(self, config, persona, chat=None, memory_loader=list_assistant_memories,
                 memory_creator=create_assistant_memory, memory_searcher=search_assistant_memories,
                 memory_updater=update_assistant_memory):
        if config.max_session_messages <= 0:
            raise ValueError("max_session_messages must be positive")
        self.config = config
        self.persona = persona
        self.chat = chat or ollama.chat
        self.memory_loader = memory_loader
        self.memory_creator = memory_creator
        self.memory_searcher = memory_searcher
        self.memory_updater = memory_updater
        self.messages = []
        self.proposals = []

    def _context_messages(self, user_text):
        memories = self.memory_loader(domain=self.config.domain, status="active", limit=self.config.max_memories)
        memory_text = "\n".join(f"- {memory['summary']}" for memory in memories) or "(none)"
        recent = self.messages[-self.config.max_session_messages:]
        return [
            {"role": "system", "content": f"{self.persona}\n\nRelevant active memories (reference only; do not invent):\n{memory_text}"},
            *recent,
            {"role": "user", "content": user_text},
        ]

    def _proposal(self, user_text, assistant_text):
        if self.config.memory_policy == "off":
            return None
        prompt = [
            {"role": "system", "content": "Return ONLY JSON. Propose a memory only if this completed turn contains information likely useful later. Do not store jokes, filler, or temporary wording. Required fields: store (boolean), subject, memory_type, summary, details, importance, confidence, retention, domain, source. Use only valid schema values."},
            {"role": "user", "content": f"USER: {user_text}\nASSISTANT: {assistant_text}"},
        ]
        response = self.chat(model=self.config.chat_model, messages=prompt)
        content = response.get("message", {}).get("content", "").strip()
        proposal = validate_memory_proposal(json.loads(content), self.config.domain)
        self.proposals.append(proposal)
        return proposal

    def explicit_remember(self, text):
        summary = text.strip()
        if not summary:
            raise ValueError("Remember command needs content.")
        memory_id = self.memory_creator(
            subject="User", memory_type="personal_fact", summary=summary,
            importance=0.9, confidence=1.0, retention="long_term",
            source="explicit:user", domain=self.config.domain,
        )
        return f"Remembered (memory #{memory_id})."

    def explicit_forget(self, text):
        matches = self.memory_searcher(text.strip(), domain=self.config.domain, status="active", limit=1)
        if not matches:
            return "No active matching memory found."
        memory = matches[0]
        self.memory_updater(memory["id"], domain=self.config.domain, status="forgotten")
        return f"Forgotten memory #{memory['id']}."

    def command(self, text):
        lowered = text.strip().casefold()
        if lowered.startswith("remember this:") or lowered.startswith("remember:"):
            return self.explicit_remember(text.split(":", 1)[1])
        if lowered.startswith("forget this:") or lowered.startswith("forget:"):
            return self.explicit_forget(text.split(":", 1)[1])
        if lowered == "memory list":
            memories = self.memory_loader(domain=self.config.domain, status="active", limit=100)
            return "\n".join(f"#{m['id']} [{m['memory_type']}] {m['summary']}" for m in memories) or "No active memories."
        if lowered.startswith("memory search "):
            memories = self.memory_searcher(text.strip()[14:], domain=self.config.domain, status="active", limit=20)
            return "\n".join(f"#{m['id']} [{m['memory_type']}] {m['summary']}" for m in memories) or "No matching active memories."
        return None

    def respond(self, user_text):
        user_text = user_text.strip()
        if not user_text:
            return ""
        command_result = self.command(user_text)
        if command_result is not None:
            return command_result
        response = self.chat(model=self.config.chat_model, messages=self._context_messages(user_text))
        content = response.get("message", {}).get("content", "").strip()
        if not content:
            raise RuntimeError("Assistant model returned empty content.")
        self.messages.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": content}])
        self.messages = self.messages[-self.config.max_session_messages:]
        try:
            self._proposal(user_text, content)
        except Exception:
            pass
        return content


def run_interactive(config_path=DEFAULT_CONFIG_PATH, input_fn=input, output_fn=print):
    config = load_config(config_path)
    session = AssistantSession(config, load_persona(config.persona_path))
    output_fn("StarFur Assistant (remember this:, forget this:, memory list, memory search; quit to exit)")
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
        if session.proposals:
            proposal = session.proposals[-1]
            if proposal.get("store"):
                output_fn("Memory proposal available for review: " + proposal["summary"])
