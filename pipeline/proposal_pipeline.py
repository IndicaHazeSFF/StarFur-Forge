from pathlib import Path

from pipeline.chunker import chunk_markdown
from pipeline.annotator import annotate
from pipeline.db import (
    add_appearance,
    create_proposal,
    get_entity_by_name,
    get_pending_proposals,
)


def proposal_exists(
    proposed_name,
    source,
    scene_index,
    chunk_index,
):
    """
    Prevent duplicate pending proposals when a document
    is analyzed repeatedly.
    """
    proposals = get_pending_proposals()

    for proposal in proposals:
        if (
            proposal["proposed_name"] == proposed_name
            and proposal["source"] == source
            and proposal["scene_index"] == scene_index
            and proposal["chunk_index"] == chunk_index
        ):
            return True

    return False


def analyze_document(path: Path):
    chunks = chunk_markdown(path)

    source = str(path)

    print("\n=== STARFUR LORE ANALYSIS ===")
    print(f"Source: {source}")
    print(f"Chunks: {len(chunks)}\n")

    proposals_created = 0
    appearances_recorded = 0

    for chunk_index, chunk in enumerate(chunks):

        print(
            f"Analyzing chunk "
            f"{chunk_index + 1}/{len(chunks)}..."
        )

        annotation = annotate(
            chunk["text"]
        )

        # ---------------------------------
        # KNOWN ENTITY APPEARANCES
        # ---------------------------------

        known_entities = annotation.get(
            "known_entities",
            [],
        )

        for known in known_entities:

            name = known.get("name")

            if not name:
                continue

            entity = get_entity_by_name(name)

            if not entity:
                print(
                    f"  WARNING  Registry entity "
                    f"not found: {name}"
                )
                continue

            add_appearance(
                entity_id=entity["id"],
                source=source,
                scene_index=chunk["scene_index"],
                chunk_index=chunk_index,
                context=chunk["text"],
            )

            print(
                f"  APPEAR   {entity['canonical_name']}"
            )

            appearances_recorded += 1

        # ---------------------------------
        # NEW ENTITY PROPOSALS
        # ---------------------------------

        candidates = annotation.get(
            "new_entity_candidates",
            [],
        )

        for candidate in candidates:

            name = candidate.get("name")

            if not name:
                continue

            # Entity may have been confirmed since
            # this document was previously analyzed.
            if get_entity_by_name(name):
                continue

            if proposal_exists(
                name,
                source,
                chunk["scene_index"],
                chunk_index,
            ):
                print(
                    f"  EXISTS   {name}"
                )
                continue

            create_proposal(
                proposal_type="new_entity",
                proposed_name=name,
                proposed_entity_type=candidate.get(
                    "probable_type"
                ),
                description=candidate.get(
                    "reason"
                ),
                evidence=candidate.get(
                    "evidence"
                ),
                source=source,
                scene_index=chunk[
                    "scene_index"
                ],
                chunk_index=chunk_index,
            )

            print(
                f"  PROPOSE  {name}"
            )

            proposals_created += 1

    print("\n=== ANALYSIS COMPLETE ===")
    print(
        f"Appearances processed: "
        f"{appearances_recorded}"
    )
    print(
        f"New proposals: "
        f"{proposals_created}"
    )


if __name__ == "__main__":
    analyze_document(
        Path(
            "canon/manuscript/entity-test.md"
        )
    )