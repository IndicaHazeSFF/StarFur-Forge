from pathlib import Path
import re


CANON_ROOT = Path("canon")

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

_No structured facts recorded yet._

## Relationships

_No relationships recorded yet._

## Notes

_Add additional canon notes here._
"""


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
def export_entities(entities):
    """
    Create missing canonical Markdown files for confirmed entities.

    Existing files are never overwritten.
    """
    results = []

    for entity in entities:
        result = create_entity_file(
            canonical_name=entity["canonical_name"],
            entity_type=entity["entity_type"],
            description=entity["description"],
        )

        results.append(
            {
                "name": entity["canonical_name"],
                **result,
            }
        )

    return results