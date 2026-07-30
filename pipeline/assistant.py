from dataclasses import dataclass
import json
import re
from pathlib import Path

import ollama

from pipeline.db import (
    create_assistant_memory,
    create_assistant_memory_proposal,
    upsert_assistant_memory_proposal,
    list_assistant_memory_proposals, approve_assistant_memory_proposal, reject_assistant_memory_proposal,
    inspect_assistant_memory_proposal, inspect_assistant_memory,
    get_assistant_memory,
    list_assistant_memories,
    search_assistant_memories, retrieve_assistant_memories,
    update_assistant_memory,
)
from pipeline.domains import normalize_domain
from pipeline.retrieval_debug import RetrievalTrace, normalize_debug_level

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "assistant.json"
DEFAULT_POLICY_PATH = PROJECT_ROOT / "config" / "assistant_policy.md"
MEMORY_POLICIES = ("off", "conservative")
PROPOSAL_FIELDS = {
    "store", "subject", "memory_type", "summary", "details",
    "importance", "confidence", "retention", "domain", "source",
}


@dataclass(frozen=True)
class AssistantConfig:
    chat_model: str
    persona_path: Path
    policy_path: Path
    domain: str
    max_session_messages: int
    max_memories: int
    memory_policy: str
    debug_level: str


def load_config(path=DEFAULT_CONFIG_PATH):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    persona_path = Path(data.get("persona_path", "persona/default.md"))
    if not persona_path.is_absolute():
        persona_path = PROJECT_ROOT / persona_path
    policy_path = Path(data.get("policy_path", "config/assistant_policy.md"))
    if not policy_path.is_absolute():
        policy_path = PROJECT_ROOT / policy_path
    policy = data.get("memory_policy", "conservative")
    if policy not in MEMORY_POLICIES:
        raise ValueError(f"Invalid memory_policy: {policy!r}")
    return AssistantConfig(
        chat_model=data.get("chat_model", "qwen3:8b"),
        persona_path=persona_path,
        policy_path=policy_path,
        domain=normalize_domain(data.get("domain", "personal")),
        max_session_messages=int(data.get("max_session_messages", 20)),
        max_memories=int(data.get("max_memories", 5)),
        memory_policy=policy,
        debug_level=normalize_debug_level(data.get("debug_level", "off")),
    )


def load_policy(path=DEFAULT_POLICY_PATH):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("Assistant policy file is empty.")
    return text


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
    if isinstance(value["importance"], bool) or isinstance(value["confidence"], bool):
        raise ValueError("Memory proposal scores must be JSON numbers.")
    if not isinstance(value["importance"], (int, float)) or not isinstance(value["confidence"], (int, float)):
        raise ValueError("Memory proposal scores must be JSON numbers.")
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
                 memory_updater=update_assistant_memory, debug_level=None, policy=None, proposal_creator=None):
        if config.max_session_messages <= 0:
            raise ValueError("max_session_messages must be positive")
        self.config = config
        self.persona = persona
        self.policy = policy or load_policy()
        self.chat = chat or ollama.chat
        self.memory_loader = memory_loader
        self.memory_creator = memory_creator
        self.memory_searcher = memory_searcher
        self.memory_updater = memory_updater
        self.proposal_creator = proposal_creator
        self.messages = []
        self.proposals = []
        self.last_memory_ids = []
        self.debug_level = normalize_debug_level(debug_level or getattr(config, "debug_level", "off"))
        self.trace = RetrievalTrace(self.debug_level)

    def _context_messages(self, user_text):
        self.trace = RetrievalTrace(self.debug_level)
        if self.memory_loader is list_assistant_memories:
            retrieved = retrieve_assistant_memories(user_text, domain=self.config.domain, limit=max(1, self.config.max_memories))
            memories = [item["memory"] for item in retrieved]
        else:
            memories = self.memory_loader(domain=self.config.domain, status="active", limit=self.config.max_memories)
            retrieved = [{"memory": memory, "score": None, "reasons": ["custom memory loader"]} for memory in memories]
        self.last_memory_ids = [memory["id"] for memory in memories if memory.get("id") is not None]
        self.trace.record("memory_lookup", domain=self.config.domain, count=len(memories), query=user_text, results=retrieved)
        memory_text = "\n".join(f"- {memory['summary']}" for memory in memories) or "(none)"
        self.trace.record("context_assembly", domain=self.config.domain, selected_count=len(memories), message_count=len(self.messages) + 1, context=memory_text)
        recent = self.messages[-self.config.max_session_messages:]
        return [
            {"role": "system", "content": f"{self.persona}\n\nENGINE POLICY:\n{self.policy}\n\nRETRIEVED MEMORY (factual context):\n{memory_text}\n\nEND RETRIEVED MEMORY"},
            *recent,
            {"role": "user", "content": user_text},
        ]

    def _proposal(self, user_text, assistant_text):
        if self.config.memory_policy == "off":
            return None
        prompt = [
            {"role": "system", "content": "Return ONLY one JSON object. Extract facts ONLY from USER FACTUAL INPUT. The assistant response is NON-AUTHORITATIVE context, never evidence. Do not store roleplay, jokes, metaphors, hypotheticals, invented history, filler, or assistant suggestions. Allowed memory_type values are exactly: preference, personal_fact, experience, project_context, relationship_context, ongoing_situation, goal, routine. Allowed retention values are exactly: session, short_term, long_term. importance and confidence must be JSON numbers from 0.0 to 1.0, never labels. If no useful durable user fact exists, return store=false. Required fields: store, subject, memory_type, summary, details, importance, confidence, retention. The engine supplies domain and source."},
            {"role": "user", "content": f"USER FACTUAL INPUT:\n{user_text}\n\nASSISTANT RESPONSE - NON-AUTHORITATIVE:\n{assistant_text}"},
        ]
        self.trace.record("proposal_request", model=self.config.chat_model, messages=prompt, domain=self.config.domain, source="assistant_turn_proposal")
        response = self.chat(model=self.config.chat_model, messages=prompt)
        content = response.get("message", {}).get("content", "").strip()
        self.trace.record("proposal_response", status="received" if content else "empty", response=content)
        try:
            raw = json.loads(content)
            raw.pop("domain", None)
            raw.pop("source", None)
            raw["domain"] = self.config.domain
            raw["source"] = "assistant_turn_proposal"
            proposal = validate_memory_proposal(raw, self.config.domain)
        except Exception as error:
            self.trace.record("proposal_validation", status="invalid", error=str(error))
            repair_prompt = [{"role": "system", "content": "Return ONLY corrected JSON. Do not add facts. Use only the allowed memory_type and retention values. Use numeric importance/confidence. Return store=false if uncertain."}, {"role": "user", "content": f"Invalid proposal: {content}\nValidation error: {error}\nAllowed memory_type: preference, personal_fact, experience, project_context, relationship_context, ongoing_situation, goal, routine\nAllowed retention: session, short_term, long_term"}]
            self.trace.record("proposal_repair_request", attempt=1, messages=repair_prompt)
            repaired = self.chat(model=self.config.chat_model, messages=repair_prompt)
            repaired_content = repaired.get("message", {}).get("content", "").strip()
            self.trace.record("proposal_repair_response", status="received" if repaired_content else "empty", response=repaired_content)
            raw = json.loads(repaired_content)
            raw.pop("domain", None)
            raw.pop("source", None)
            raw["domain"] = self.config.domain
            raw["source"] = "assistant_turn_proposal"
            proposal = validate_memory_proposal(raw, self.config.domain)
        self.trace.record("proposal_validation", status="accepted", store=proposal["store"], domain=proposal["domain"])
        if proposal["store"] and self.proposal_creator:
            result = self.proposal_creator(proposal, domain=self.config.domain, observation_text=user_text)
            proposal["id"] = result.get("proposal_id", result) if isinstance(result, dict) else result
            self.trace.record("proposal_persisted", proposal_id=proposal["id"], status=result.get("action", "pending") if isinstance(result, dict) else "pending")
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
        if lowered == "proposal list":
            rows = list_assistant_memory_proposals(domain=self.config.domain)
            return "\n".join("#" + str(row["id"]) + " [" + row["memory_type"] + "] " + row["summary"] for row in rows) or "No pending assistant proposals."
        if lowered.startswith("memory inspect"):
            parts = text.strip().split()
            if len(parts) != 3 or not parts[2].isdigit(): return "Usage: memory inspect <id>"
            inspected = inspect_assistant_memory(int(parts[2]), domain=self.config.domain)
            return format_assistant_memory(inspected) if inspected else "Memory not found."
        if lowered.startswith("proposal inspect"):
            parts = text.strip().split()
            if len(parts) != 3 or not parts[2].isdigit():
                return "Usage: proposal inspect <id>"
            inspected = inspect_assistant_memory_proposal(int(parts[2]), domain=self.config.domain)
            if not inspected:
                return "Proposal not found."
            return format_assistant_memory_proposal(inspected)
        if lowered.startswith("proposal approve "):
            proposal_id = int(text.strip().split()[-1])
            memory = approve_assistant_memory_proposal(proposal_id, domain=self.config.domain)
            return "Approved proposal #" + str(proposal_id) + " as memory #" + str(memory["id"]) + "."
        if lowered.startswith("proposal reject "):
            proposal_id = int(text.strip().split()[-1])
            reject_assistant_memory_proposal(proposal_id, domain=self.config.domain)
            return "Rejected proposal #" + str(proposal_id) + "."
        return None

    def explain_memory(self, query=None):
        """Return a bounded, provenance-safe explanation payload."""
        retrieval_items = []
        if self.memory_loader is list_assistant_memories:
            retrieval_items = retrieve_assistant_memories(query, domain=self.config.domain, limit=self.config.max_memories) if query is not None else [{"memory":{"id": memory_id}, "reasons": []} for memory_id in self.last_memory_ids]
            target_ids = [item["memory"]["id"] for item in retrieval_items]
            source_memories = {memory_id: inspect_assistant_memory(memory_id, domain=self.config.domain) for memory_id in target_ids}
        else:
            custom = self.memory_loader(domain=self.config.domain, status="active", limit=self.config.max_memories)
            target_ids = self.last_memory_ids if query is None else [memory["id"] for memory in custom if any(token in (memory.get("summary","")+" "+memory.get("details","")).casefold() for token in query.casefold().split())]
            source_memories = {memory["id"]: {"memory": memory, "evidence": []} for memory in custom if memory["id"] in target_ids}
        if not target_ids: return {"status": "ambiguous" if query is None else "no_match", "memories": []}
        payload=[]
        for memory_id in target_ids[:self.config.max_memories]:
            inspected = source_memories.get(memory_id)
            if inspected:
                memory=inspected["memory"]
                payload.append({"memory_id":memory["id"],"summary":memory["summary"],"details":memory.get("details"),"confidence":memory.get("confidence"),"importance":memory.get("importance"),"source":memory.get("source"),"approved_memory_id":memory.get("id"),"evidence":inspected.get("evidence",[]),"retrieval_reasons":next((item.get("reasons",[]) for item in retrieval_items if item["memory"].get("id")==memory["id"]),[])})
        return {"status":"ok" if payload else "no_match","memories":payload}

    def _memory_introspection(self, user_text):
        lowered=user_text.casefold()
        why=any(phrase in lowered for phrase in ("why do you remember", "where did that memory come from", "what made you think that"))
        direct=lowered.startswith("what do you remember about")
        if not (why or direct): return None
        query=None if why else user_text.split("about",1)[1].strip().rstrip("?")
        explanation=self.explain_memory(query)
        if explanation["status"] == "ambiguous": return "I am not sure which memory you mean. Which one should I explain?"
        if explanation["status"] == "no_match": return "I do not have an active canonical memory that matches that."
        explanation_text = (self.persona + "\n\nENGINE POLICY:\n" + self.policy + "\n\nYou are answering a memory-introspection question. Use ONLY the structured explanation JSON below. Explain remembered content and provenance naturally. Do not mention rejected proposals, raw databases, hidden reasoning, or invent causes.\nSTRUCTURED MEMORY EXPLANATION:\n" + json.dumps(explanation, ensure_ascii=False))
        prompt=[{"role":"system","content":explanation_text},{"role":"user","content":user_text}]
        self.trace.record("memory_explanation", query=query, memory_ids=[item["memory_id"] for item in explanation["memories"]], payload=explanation)
        response=self.chat(model=self.config.chat_model,messages=prompt); content=response.get("message",{}).get("content","").strip()
        if not content: raise RuntimeError("Assistant model returned empty content.")
        return content

    def respond(self, user_text):
        user_text = user_text.strip()
        if not user_text:
            return ""
        command_result = self.command(user_text)
        if command_result is None:
            introspection = self._memory_introspection(user_text)
            if introspection is not None:
                return introspection
        if command_result is not None:
            self.trace.record("command", command=user_text)
            return command_result
        messages = self._context_messages(user_text)
        self.trace.record("model_request", model=self.config.chat_model, message_count=len(messages), messages=messages)
        response = self.chat(model=self.config.chat_model, messages=messages)
        content = response.get("message", {}).get("content", "").strip()
        if not content:
            self.trace.record("model_response", model=self.config.chat_model, status="empty")
            raise RuntimeError("Assistant model returned empty content.")
        self.trace.record("model_response", model=self.config.chat_model, status="ok", response=content)
        self.messages.extend([{"role": "user", "content": user_text}, {"role": "assistant", "content": content}])
        self.messages = self.messages[-self.config.max_session_messages:]
        try:
            self._proposal(user_text, content)
        except Exception as error:
            self.trace.record("proposal_error", status="rejected", error=str(error))
        return content

def format_assistant_memory(inspected):
    memory = inspected["memory"]; evidence = inspected.get("evidence", [])
    lines=[f"Memory #{memory['id']}",f"Domain: {memory.get('domain','unknown')}",f"Type: {memory.get('memory_type','unknown')}",f"Subject: {memory.get('subject','unknown')}","","Summary:",memory.get('summary') or '(none)',"","Details:",memory.get('details') or '(none)',"",f"Confidence: {memory.get('confidence','unknown')}",f"Importance: {memory.get('importance','unknown')}",f"Retention: {memory.get('retention','unknown')}",f"Status: {memory.get('status','unknown')}","","Evidence:"]
    if not evidence: lines.append("no recorded evidence provenance")
    for i,item in enumerate(evidence,1): lines.extend([f'{i}. "{item.get("raw_excerpt") or "(observation text unavailable)"}"',f"   Source: {item.get('source','unknown')}",f"   Added: {item.get('observed_at','unknown')}",f"   Observation key: {item.get('evidence_hash') or 'legacy/unavailable'}",f"   Proposal: #{item.get('proposal_id','unknown')}"])
    lines.extend(["",f"Created: {memory.get('created_at','unknown')}",f"Updated: {memory.get('updated_at','unknown')}"])
    return "\n".join(lines)

def format_assistant_memory_proposal(inspected):
    proposal = inspected["proposal"]
    evidence = inspected.get("evidence", [])
    identity = proposal.get("proposal_key") or "legacy/unavailable"
    support = proposal.get("evidence_count") if proposal.get("evidence_count") is not None else "legacy/unavailable"
    lines = [f"Proposal #{proposal['id']}", f"Status: {proposal.get('status', 'unknown')}", f"Domain: {proposal.get('domain', 'unknown')}", f"Type: {proposal.get('memory_type', 'unknown')}", f"Subject: {proposal.get('subject', 'unknown')}", "", "Summary:", proposal.get("summary") or "(none)", "", "Details:", proposal.get("details") or "(none)", "", f"Confidence: {proposal.get('confidence', 'unknown')}", f"Importance: {proposal.get('importance', 'unknown')}", f"Retention: {proposal.get('retention', 'unknown')}", f"Support: {support}", "", f"Identity: {identity}", "", "Evidence:"]
    if not evidence:
        lines.append("no recorded evidence provenance")
    else:
        for index, item in enumerate(evidence, 1):
            observation = item.get("raw_excerpt") or item.get("source_reference") or "(observation text unavailable)"
            lines.extend([f'{index}. "{observation}"', f"   Source: {item.get('source', 'unknown')}", f"   Added: {item.get('observed_at', 'unknown')}", f"   Observation key: {item.get('evidence_hash') or 'legacy/unavailable'}"])
    lines.extend(["", f"Created: {proposal.get('created_at', 'unknown')}", f"Updated: {proposal.get('updated_at', 'unknown')}"])
    return "\n".join(lines)

def run_interactive(config_path=DEFAULT_CONFIG_PATH, input_fn=input, output_fn=print, debug_level=None):
    config = load_config(config_path)
    session = AssistantSession(config, load_persona(config.persona_path), policy=load_policy(config.policy_path), debug_level=debug_level, proposal_creator=upsert_assistant_memory_proposal)
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
        proposal_count_before = len(session.proposals)
        try:
            answer = session.respond(user_text)
        except Exception as error:
            output_fn(f"Assistant error: {error}")
            session.trace.emit(output_fn)
            continue
        if answer:
            output_fn(f"StarFur: {answer}")
        session.trace.emit(output_fn)
        if len(session.proposals) > proposal_count_before:
            proposal = session.proposals[-1]
            if proposal.get("store"):
                output_fn("Memory proposal available for review: " + proposal["summary"])
