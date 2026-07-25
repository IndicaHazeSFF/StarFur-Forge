from pathlib import Path
import re
import os

CANON_ROOT = Path("canon")
FACTS_START = "<!-- STARFUR:FACTS:START -->"
FACTS_END = "<!-- STARFUR:FACTS:END -->"
TYPE_DIRECTORIES = {
    "character": "characters",
    "location": "locations",
    "organization": "organizations",
    "technology": "technology",
    "object": "objects",
    "concept": "concepts",
    "unknown": "entities",
}


def slugify(name: str) -> str:
    """
    Convert an entity name into a safe Markdown filename.

    Example:
        Murr Lavenfur -> murr-lavenfur
        The System    -> the-system
    """
    slug = name.lower().strip()

    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        slug,
    )

    return slug.strip("-")


def get_entity_path(
    canonical_name: str,
    entity_type: str,
) -> Path:
    """
    Determine where an entity's canon file belongs.
    """
    directory = TYPE_DIRECTORIES.get(
        entity_type,
        "entities",
    )

    filename = (
        slugify(canonical_name)
        + ".md"
    )

    return CANON_ROOT / directory / filename


def build_entity_markdown(
    canonical_name: str,
    entity_type: str,
    description=None,
    aliases=None,
) -> str:
    """
    Build the initial Markdown document for an entity.

    This is intentionally conservative. StarFur creates the
    initial scaffold but does not invent additional lore.
    """
    aliases = aliases or []

    if aliases:
        alias_yaml = "\n".join(
            f'  - "{alias}"'
            for alias in aliases
        )
    else:
        alias_yaml = "  []"

    description_text = (
        description
        if description
        else "_No description recorded yet._"
    )

    return f"""---
name: "{canonical_name}"
type: "{entity_type}"
status: "confirmed"
aliases:
{alias_yaml}
---

# {canonical_name}

## Summary

{description_text}

## Canon Facts

{FACTS_START}
_No structured facts recorded yet._
{FACTS_END}
## Relationships

_No relationships recorded yet._

## Notes

_Add additional canon notes here._
"""

def render_facts(facts) -> str:
    """
    Render structured entity facts as Markdown.
    """
    if not facts:
        return "_No structured facts recorded yet._"

    lines = []

    for fact in facts:
        lines.append(
            f"- {fact['fact']}"
        )

    return "\n".join(lines)
    
def replace_managed_section(
    content: str,
    start_marker: str,
    end_marker: str,
    rendered: str,
) -> str:
    """
    Replace only the content inside a StarFur-managed
    Markdown section.
    """
    start = content.find(start_marker)
    end = content.find(end_marker)

    if start == -1 or end == -1:
        return content

    if end < start:
        return content

    before = content[
        :start + len(start_marker)
    ]

    after = content[end:]

    return (
        before
        + "\n"
        + rendered.strip()
        + "\n"
        + after
    )  
def ensure_facts_markers(content: str) -> str:
    """
    Add StarFur fact-management markers to older entity
    files that predate managed sections.
    """
    if (
        FACTS_START in content
        and FACTS_END in content
    ):
        return content

    heading = "## Canon Facts"
    next_heading = "## Relationships"

    start = content.find(heading)
    end = content.find(next_heading)

    if start == -1 or end == -1:
        return content

    section_start = start + len(heading)

    return (
        content[:section_start]
        + "\n\n"
        + FACTS_START
        + "\n"
        + FACTS_END
        + "\n\n"
        + content[end:]
    )    
def create_entity_file(
    canonical_name: str,
    entity_type: str,
    description=None,
    aliases=None,
):
    """
    Create a new canonical Markdown entity file.

    Existing files are NEVER overwritten.
    """
    path = get_entity_path(
        canonical_name,
        entity_type,
    )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if path.exists():
        return {
            "created": False,
            "path": path,
            "reason": "exists",
        }

    content = build_entity_markdown(
        canonical_name=canonical_name,
        entity_type=entity_type,
        description=description,
        aliases=aliases,
    )

    path.write_text(
        content,
        encoding="utf-8",
    )

    return {
        "created": True,
        "path": path,
        "reason": "created",
    }
def update_entity_facts(
    path: Path,
    facts,
):
    """
    Update only the StarFur-managed facts region of an
    existing canonical entity file.
    """
    if not path.exists():
        return False

    original = path.read_text(
        encoding="utf-8"
    )

    content = ensure_facts_markers(
        original
    )

    content = replace_managed_section(
        content=content,
        start_marker=FACTS_START,
        end_marker=FACTS_END,
        rendered=render_facts(facts),
    )

    if content == original:
        return False

    if original.strip() and not content.strip():
        raise RuntimeError(
            f"Refusing to replace non-empty canon file "
            f"with empty content: {path}"
        )

    if FACTS_START not in content:
        raise RuntimeError(
            f"Missing facts start marker: {path}"
        )

    if FACTS_END not in content:
        raise RuntimeError(
            f"Missing facts end marker: {path}"
        )

    temp_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temp_path.write_text(
        content,
        encoding="utf-8",
    )

    if temp_path.stat().st_size == 0:
        temp_path.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"Refusing empty canon update: {path}"
        )

    os.replace(
        temp_path,
        path,
    )

    return True
def export_entities(
    entities,
    facts_by_entity=None,
):
    """
    Create missing canonical Markdown files and update
    StarFur-managed facts in existing files.
    """
    results = []
    facts_by_entity = facts_by_entity or {}

    for entity in entities:
        entity_id = entity["id"]

        result = create_entity_file(
            canonical_name=entity["canonical_name"],
            entity_type=entity["entity_type"],
            description=entity["description"],
        )

        path = result["path"]

        updated = update_entity_facts(
            path=path,
            facts=facts_by_entity.get(
                entity_id,
                [],
            ),
        )

        if result["created"]:
            action = "created"
        elif updated:
            action = "updated"
        else:
            action = "unchanged"

        results.append(
            {
                "name": entity["canonical_name"],
                "path": path,
                "created": result["created"],
                "updated": updated,
                "action": action,
            }
        )

    return results