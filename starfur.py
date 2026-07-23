from pathlib import Path
import argparse

from pipeline.db import (
    connect,
    database_stats,
    get_entity_by_name,
)
from pipeline.proposal_pipeline import analyze_document


def show_status():
    stats = database_stats()

    print("\n=== STARFUR FORGE ===\n")

    print("Structured Memory")
    print("-----------------")
    print(f"Entities:      {stats['entities']}")
    print(f"Aliases:       {stats['aliases']}")
    print(f"Appearances:   {stats['appearances']}")
    print(f"Relationships: {stats['relationships']}")
    print(f"Events:        {stats['events']}")
    print(f"Proposals:     {stats['proposals']}")


def analyze(path_string):
    path = Path(path_string)

    if not path.exists():
        print(f"File not found: {path}")
        return

    analyze_document(path)


def show_entity(name):
    entity = get_entity_by_name(name)

    if not entity:
        print(f"\nEntity not found: {name}")
        return

    entity_id = entity["id"]

    with connect() as connection:

        aliases = connection.execute(
            """
            SELECT alias
            FROM aliases
            WHERE entity_id = ?
            ORDER BY alias
            """,
            (entity_id,),
        ).fetchall()

        appearances = connection.execute(
            """
            SELECT
                source,
                scene_index,
                chunk_index
            FROM appearances
            WHERE entity_id = ?
            ORDER BY source, scene_index, chunk_index
            """,
            (entity_id,),
        ).fetchall()

        outgoing_relationships = connection.execute(
            """
            SELECT
                relationships.relationship_type,
                entities.canonical_name AS target,
                relationships.description
            FROM relationships
            JOIN entities
                ON relationships.object_entity_id = entities.id
            WHERE relationships.subject_entity_id = ?
            ORDER BY entities.canonical_name
            """,
            (entity_id,),
        ).fetchall()

        incoming_relationships = connection.execute(
            """
            SELECT
                relationships.relationship_type,
                entities.canonical_name AS source_name,
                relationships.description
            FROM relationships
            JOIN entities
                ON relationships.subject_entity_id = entities.id
            WHERE relationships.object_entity_id = ?
            ORDER BY entities.canonical_name
            """,
            (entity_id,),
        ).fetchall()

    print("\n" + "=" * 70)
    print(f"STARFUR ENTITY #{entity_id}")
    print("=" * 70)

    print(f"\nName: {entity['canonical_name']}")
    print(f"Type: {entity['entity_type']}")
    print(f"Status: {entity['status']}")

    if entity["description"]:
        print(
            f"\nDescription:\n"
            f"{entity['description']}"
        )

    print("\nAliases:")

    if aliases:
        for alias in aliases:
            print(f"  - {alias['alias']}")
    else:
        print("  None")

    print("\nAppearances:")

    if appearances:
        for appearance in appearances:
            print(
                f"  - {appearance['source']} "
                f"| scene {appearance['scene_index']} "
                f"| chunk {appearance['chunk_index']}"
            )
    else:
        print("  None recorded")

    print("\nRelationships:")

    relationship_found = False

    for relationship in outgoing_relationships:
        relationship_found = True

        print(
            f"  - {entity['canonical_name']} "
            f"--{relationship['relationship_type']}--> "
            f"{relationship['target']}"
        )

        if relationship["description"]:
            print(
                f"    {relationship['description']}"
            )

    for relationship in incoming_relationships:
        relationship_found = True

        print(
            f"  - {relationship['source_name']} "
            f"--{relationship['relationship_type']}--> "
            f"{entity['canonical_name']}"
        )

        if relationship["description"]:
            print(
                f"    {relationship['description']}"
            )

    if not relationship_found:
        print("  None recorded")


def main():
    parser = argparse.ArgumentParser(
        description="StarFur Forge"
    )

    subparsers = parser.add_subparsers(
        dest="command"
    )

    subparsers.add_parser(
        "status",
        help="Show StarFur memory status",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a canon document for lore",
    )

    analyze_parser.add_argument(
        "path",
        help="Path to Markdown document",
    )

    entity_parser = subparsers.add_parser(
        "entity",
        help="Show a canon entity",
    )

    entity_parser.add_argument(
        "name",
        help="Canonical name or alias",
    )

    args = parser.parse_args()

    if args.command == "status":
        show_status()

    elif args.command == "analyze":
        analyze(args.path)

    elif args.command == "entity":
        show_entity(args.name)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()