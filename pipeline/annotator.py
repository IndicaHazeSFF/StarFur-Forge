import json
import ollama

from pipeline.db import get_entities


ANNOTATION_MODEL = "qwen3:8b"


def build_registry():
    """
    Build a compact registry of confirmed entities
    for the annotation model.
    """
    entities = get_entities()

    registry = []

    for entity in entities:
        registry.append(
            {
                "name": entity["canonical_name"],
                "type": entity["entity_type"],
            }
        )

    return registry


def build_system_prompt():
    registry = build_registry()

    registry_json = json.dumps(
        registry,
        indent=2,
        ensure_ascii=False,
    )

    return f"""
You are a semantic annotation system for a fictional universe.

You are given a registry of entities that have already been confirmed
as canon.

CONFIRMED ENTITY REGISTRY:

{registry_json}

Analyze the supplied manuscript passage.

Your job is to distinguish between:

1. Confirmed entities already present in the registry.
2. Potential new entities not present in the registry.
3. Ordinary scene details that should NOT become entities.

Do not invent lore.

Return ONLY valid JSON.

Use exactly this structure:

{{
  "known_entities": [],
  "new_entity_candidates": [],
  "events": [],
  "worldbuilding": []
}}

KNOWN ENTITIES

Each known entity must use:

{{
  "name": "canonical registry name",
  "type": "registry type"
}}

Only include an entity if it appears or is directly referenced
in the passage.

Always use the canonical name from the registry.


NEW ENTITY CANDIDATES

Use:

{{
  "name": "name or concise identifier",
  "probable_type": "character|location|organization|technology|object|concept|unknown",
  "reason": "why this may deserve a persistent canon entry",
  "evidence": "brief evidence from the passage"
}}

Be conservative.

A new entity candidate should represent something that may matter
outside this individual scene.

DO NOT propose ordinary scenery or incidental objects merely because
they are mentioned.

Examples that normally should NOT become entities:

doors
tables
walls
lighting
ordinary clothing
chairs
generic corridors
generic rooms

An unnamed thing MAY be proposed if the text strongly indicates that
it has unusual worldbuilding or narrative significance.


EVENTS

Return concise descriptions of significant events.

Do not list every physical action.


WORLDBUILDING

Return important setting facts, rules, capabilities, institutions,
technologies, or social facts established by the passage.

Prefer omission over speculation.
"""


def annotate(text: str):
    response = ollama.chat(
        model=ANNOTATION_MODEL,
        messages=[
            {
                "role": "system",
                "content": build_system_prompt(),
            },
            {
                "role": "user",
                "content": text,
            },
        ],
        format="json",
        options={
            "temperature": 0,
        },
    )

    raw = response["message"]["content"]

    try:
        return json.loads(raw)

    except json.JSONDecodeError:
        print("\n=== INVALID JSON FROM MODEL ===\n")
        print(raw)
        raise
