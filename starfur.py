from pathlib import Path
import argparse

from pipeline.sync import run_sync, reanalyze_chapter
from pipeline.rag import ask_starfur
from pipeline.db import (
    connect,
    database_stats,
    get_entity_by_name,
    get_entities,
    get_all_entity_facts,
)
from pipeline.proposal_pipeline import analyze_document
from pipeline.assistant import run_interactive, load_config
from pipeline.canon_writer import export_entities


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
    print(f"Facts:         {stats['entity_facts']}")

    print("\nAssistant Memory")
    print("----------------")
    print(f"All memories:  {stats['assistant_memories']}")
    print(f"Active:        {stats['assistant_active_memories']}")
    print(f"Pending:       {stats['assistant_pending_proposals']}")

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
        facts = connection.execute(
            """
            SELECT
                fact,
                evidence,
                source,
                scene_index,
                chunk_index,
                status
            FROM entity_facts
            WHERE entity_id = ?
            ORDER BY source, scene_index, chunk_index, id
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
    print("\nFacts:")

    if facts:
        for fact in facts:
            print(
                f"  - {fact['fact']}"
            )

            print(
                f"    Source: {fact['source']} "
                f"| scene {fact['scene_index']} "
                f"| chunk {fact['chunk_index']} "
                f"| {fact['status']}"
            )

            if fact["evidence"]:
                print(
                    f"    Evidence: "
                    f"{fact['evidence']}"
                )
    else:
        print("  None recorded")
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


def export_canon():
    entities = get_entities()

    if not entities:
        print("\nNo confirmed entities to export.")
        return

    facts_by_entity = get_all_entity_facts()

    print("\n=== STARFUR CANON EXPORT ===\n")

    created = 0
    updated = 0
    unchanged = 0

    results = export_entities(
        entities,
        facts_by_entity=facts_by_entity,
    )

    for result in results:

        if result["action"] == "created":
            print(
                f"CREATE     {result['name']} "
                f"-> {result['path']}"
            )
            created += 1

        elif result["action"] == "updated":
            print(
                f"UPDATE     {result['name']} "
                f"-> {result['path']}"
            )
            updated += 1

        else:
            print(
                f"UNCHANGED  {result['name']} "
                f"-> {result['path']}"
            )
            unchanged += 1

    print("\n=== EXPORT COMPLETE ===")
    print(f"Created:   {created}")
    print(f"Updated:   {updated}")
    print(f"Unchanged: {unchanged}")
    print(f"Total:     {len(entities)}")
def main():
    parser = argparse.ArgumentParser(
        description="StarFur Forge"
    )

    subparsers = parser.add_subparsers(
        dest="command"
    )

    # -------------------------
    # STATUS
    # -------------------------

    subparsers.add_parser(
        "status",
        help="Show StarFur memory status",
    )

    # -------------------------
    # ANALYZE
    # -------------------------

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a canon document for lore",
    )

    analyze_parser.add_argument(
        "path",
        help="Path to Markdown document",
    )

    # -------------------------
    # ASSISTANT
    # -------------------------

    assistant_parser = subparsers.add_parser(
        "assistant",
        help="Start the local conversational assistant",
    )
    assistant_parser.add_argument(
        "--config",
        help="Path to assistant JSON configuration",
    )
    assistant_parser.add_argument(
        "--debug",
        choices=("off", "summary", "verbose", "trace"),
        help="Retrieval debugging detail level",
    )

    eval_parser = subparsers.add_parser("retrieval-eval", help="Run the checked-in assistant retrieval benchmark")
    eval_parser.add_argument("--strategy", choices=("deterministic", "semantic", "hybrid"), default="deterministic")

    context_parser = subparsers.add_parser("assistant-context", help="Show ranked assistant memory context")
    context_parser.add_argument("query", help="Question or query text")
    context_parser.add_argument("--domain", default=None, help="Assistant memory domain")
    context_parser.add_argument("--limit", type=int, default=8, help="Maximum selected memories")
    context_parser.add_argument("--explain", action="store_true", help="Show selection and exclusion reasons")

    restore_parser = subparsers.add_parser("factory-restore", help=argparse.SUPPRESS)
    restore_parser.add_argument("--backup", type=int, help=argparse.SUPPRESS)
    restore_parser.add_argument("--allow-production-reset", action="store_true", help=argparse.SUPPRESS)


    reset_parser = subparsers.add_parser("factory-reset", help=argparse.SUPPRESS)
    reset_parser.add_argument("--all", action="store_true", help=argparse.SUPPRESS)
    reset_parser.add_argument("--assistant-only", action="store_true", help=argparse.SUPPRESS)
    reset_parser.add_argument("--semantic-only", action="store_true", help=argparse.SUPPRESS)
    reset_parser.add_argument("--confirm", action="store_true", help=argparse.SUPPRESS)
    reset_parser.add_argument("--allow-production-reset", action="store_true", help=argparse.SUPPRESS)

    # -------------------------
    # ENTITY
    # -------------------------

    entity_parser = subparsers.add_parser(
        "entity",
        help="Show a canon entity",
    )

    entity_parser.add_argument(
        "name",
        help="Canonical name or alias",
    )
    # -------------------------
    # ASK
    # -------------------------

    ask_parser = subparsers.add_parser(
        "ask",
        help="Ask StarFur a canon question",
    )

    ask_parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask about canon",
    )
    
    # -------------------------
    # EXPORT
    # -------------------------
    subparsers.add_parser(
        "export",
        help="Export structured memory to canon Markdown",
    )
    subparsers.add_parser(
        "sync",
        help="Synchronize canon with StarFur memory",
    )
    reanalyze_parser = subparsers.add_parser(
        "reanalyze-chapter",
        help="Force structured reanalysis of one canon chapter",
    )
    reanalyze_parser.add_argument(
        "path",
        help="Markdown file inside canon/chapters/",
    )

    # -------------------------
    # DISPATCH
    # -------------------------

    args = parser.parse_args()

    if args.command == "factory-restore":
        from pipeline.reset import CONFIRMATION, factory_restore, list_backups
        backups=list_backups()
        if not backups: print("No backups available.")
        else:
            print("Available backups\n")
            for index,item in enumerate(backups,1): print(f"{index}. {item.name[:8]} {item.name[9:11]}:{item.name[11:13]}")
            selection=args.backup or int(input("Restore backup number: "))
            if selection<1 or selection>len(backups): print("Invalid backup selection.")
            else:
                print("This will replace current assistant memory data.")
                print(f"Type exactly: {CONFIRMATION.replace('Reset','Restore')}")
                typed=input("Confirmation: ")
                if typed != CONFIRMATION.replace("Reset","Restore"): print("Confirmation did not match. Restore cancelled.")
                else:
                    try:
                        chroma_client=None
                        if (backups[selection-1] / "chroma.json").exists():
                            import chromadb
                            from pipeline.ingest import CHROMA_HOST, CHROMA_PORT
                            chroma_client=chromadb.HttpClient(host=CHROMA_HOST,port=CHROMA_PORT)
                        print(f"Factory restore complete: {factory_restore('data/starfur.db',backups[selection-1],confirmation=typed,allow_production=args.allow_production_reset,chroma_client=chroma_client)}")
                    except Exception as error: print(f"Factory restore failed: {error}")

    if args.command == "factory-reset":
        from pipeline.reset import CONFIRMATION, factory_reset
        if sum(bool(flag) for flag in (args.all, args.assistant_only, args.semantic_only)) != 1: print("Choose exactly one reset scope.")
        elif not args.confirm: print("Reset not performed. Add --confirm to continue.")
        else:
            print("WARNING: This is destructive.")
            backup_answer=input("Would you like a backup made before the wipe? [Y/n]: ").strip().casefold()
            make_backup=backup_answer not in {"n","no"}
            print(f"Type exactly: {CONFIRMATION}"); typed=input("Confirmation: ")
            if typed != CONFIRMATION: print("Confirmation did not match. Reset cancelled.")
            else:
                scope="assistant-and-semantic" if args.all else "assistant-only" if args.assistant_only else "semantic-only"
                try:
                    chroma_client=None
                    if scope != "assistant-only":
                        import chromadb
                        from pipeline.ingest import CHROMA_HOST, CHROMA_PORT
                        chroma_client=chromadb.HttpClient(host=CHROMA_HOST,port=CHROMA_PORT)
                    result=factory_reset("data/starfur.db",scope=scope,confirmation=typed,allow_production=args.allow_production_reset,chroma_client=chroma_client,backup=make_backup)
                    print(f"Factory reset complete: {result}")
                except Exception as error: print(f"Factory reset failed: {error}")

    if args.command == "status":
        show_status()

    elif args.command == "analyze":
        analyze(args.path)

    elif args.command == "assistant":
        run_interactive(args.config, debug_level=args.debug) if args.config else run_interactive(debug_level=args.debug)

    elif args.command == "retrieval-eval":
        from pipeline.retrieval_eval import run_benchmark
        result = run_benchmark(strategy=args.strategy)
        print("Retrieval Evaluation\n--------------------")
        print(f"Cases:              {result['cases']}")
        print(f"Top-1 hit rate:     {result['top1_hit_rate']:.1%}")
        print(f"Top-3 hit rate:     {result['top3_hit_rate']:.1%}")
        print(f"Irrelevant results: {result['irrelevant_result_count']}")
        print(f"Repeatability:      {'PASS' if result['repeatability'] else 'FAIL'}")
        if result['failures']:
            print("\nFailures\n--------")
            for failure in result['failures']: print(f"{failure['name']}\n  expected: {failure['expected']}\n  returned: {failure['returned']}")

    elif args.command == "assistant-context":
        from pipeline.db import retrieve_assistant_memories, explain_assistant_memory_retrieval
        domain = args.domain or load_config().domain
        packet = explain_assistant_memory_retrieval(args.query, domain=domain, limit=args.limit) if args.explain else {"selected": retrieve_assistant_memories(args.query, domain=domain, limit=args.limit), "not_selected": []}
        print(f"Query: {args.query}\nDomain: {domain}\n\nSelected memories:")
        if not packet["selected"]: print("  (none)")
        for item in packet["selected"]:
            memory = item["memory"]
            print(f"  [{memory['memory_type']}:{memory['id']}] score={item['score']:.3f} {memory['summary']}")
            if args.explain:
                print("    reasons: " + "; ".join(item["reasons"]))
        if args.explain:
            print("\nNot selected:")
            for item in packet["not_selected"]:
                print(f"  [{item['memory']['memory_type']}:{item['memory']['id']}] score={item['score']:.3f} {item['memory']['summary']}\n    reason: {item['reason']}")

    elif args.command == "entity":
        show_entity(args.name)
        
    elif args.command == "ask":
        question = args.question

        if not question:
            question = input("Ask StarFur: ")

        ask_starfur(question)
        
    elif args.command == "export":
        export_canon()
        
    elif args.command == "sync":
        run_sync()

    elif args.command == "reanalyze-chapter":
        reanalyze_chapter(args.path)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()