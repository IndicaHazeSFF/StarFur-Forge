from pathlib import Path
import re
from pipeline.paths import canonical_source
from pipeline.chunker import chunk_markdown
from pipeline.annotator import AnnotationParseError, annotate
from pipeline.db import (
    add_appearance,
    add_entity_fact,
    clear_source_derived_memory,
    create_proposal,
    get_entity_by_name,
    get_entity_names_and_aliases,
    get_pending_proposals,
)


class DocumentAnalysisError(RuntimeError):
    """Indicates that one or more chunks must be retried for a source."""

    def __init__(self, source, failed_chunks):
        self.source = source
        self.failed_chunks = failed_chunks
        super().__init__(
            f"{len(failed_chunks)} chunk(s) require retry for {source}"
        )


def normalize_proposal_name(name):
    """Normalize only trivial presentation differences for comparison."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", str(name).casefold())).strip()


def proposal_match(name):
    """Return duplicate/possible-match information without merging names."""
    normalized = normalize_proposal_name(name)
    pending = get_pending_proposals()
    confirmed = get_entity_names_and_aliases()
    for proposal in pending:
        other = proposal.get("proposed_name")
        if other and normalize_proposal_name(other) == normalized:
            return {"kind": "pending_duplicate", "match": other}
    for other in confirmed:
        if normalize_proposal_name(other) == normalized:
            return {"kind": "confirmed_duplicate", "match": other}
    possible = []
    for other in [p.get("proposed_name") for p in pending] + confirmed:
        if not other:
            continue
        left, right = normalized, normalize_proposal_name(other)
        if left != right and (left in right or right in left):
            possible.append(other)
    return {"kind": "possible_match", "matches": sorted(set(possible))} if possible else None


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

    source = canonical_source(path)
    
    cleanup = clear_source_derived_memory(
        source
    )

    if (
        cleanup["appearances"]
        or cleanup["pending_proposals"]
        or cleanup["entity_facts"]
    ):
        print(
            "\nCleared stale source memory:"
        )

        print(
            f"  Appearances: "
            f"{cleanup['appearances']}"
        )

        print(
            f"  Pending proposals: "
            f"{cleanup['pending_proposals']}"
        )
        print(
            f"  Entity facts: "
            f"{cleanup['entity_facts']}"
        )
    print("\n=== STARFUR LORE ANALYSIS ===")
    print(f"Source: {source}")
    print(f"Chunks: {len(chunks)}\n")

    proposals_created = 0
    appearances_recorded = 0
    facts_recorded = 0
    failed_chunks = []

    for chunk_index, chunk in enumerate(chunks):

        print(
            f"Analyzing chunk "
            f"{chunk_index + 1}/{len(chunks)}..."
        )

        try:
            annotation = annotate(
                chunk["text"]
            )
        except AnnotationParseError as error:
            failed_chunks.append(
                {
                    "chunk_index": chunk_index,
                    "scene_index": chunk["scene_index"],
                    "error": str(error),
                }
            )
            print(
                f"  RETRY   chunk {chunk_index}: {error}"
            )
            continue

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
        # ENTITY FACTS
        # ---------------------------------

        entity_facts = annotation.get(
            "entity_facts",
            [],
        )

        for entity_fact in entity_facts:

            name = entity_fact.get("entity")
            fact = entity_fact.get("fact")

            if not name or not fact:
                continue

            entity = get_entity_by_name(name)

            if not entity:
                print(
                    f"  WARNING  Fact entity "
                    f"not found: {name}"
                )
                continue

            add_entity_fact(
                entity_id=entity["id"],
                fact=fact,
                evidence=entity_fact.get(
                    "evidence"
                ),
                fact_type=entity_fact.get(
                    "fact_type"
                ),
                source=source,
                scene_index=chunk[
                    "scene_index"
                ],
                chunk_index=chunk_index,
            )

            print(
                f"  FACT     "
                f"{entity['canonical_name']}"
            )

            facts_recorded += 1
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

            match = proposal_match(name)
            if match and match["kind"] in {"confirmed_duplicate", "pending_duplicate"}:
                print(f"  EXISTS   {name} (matches {match['match']})")
                continue
            if match and match["kind"] == "possible_match":
                print(
                    f"  REVIEW   {name} possible matches: "
                    + ", ".join(match["matches"])
                )

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
        f"Facts processed: "
        f"{facts_recorded}"
    )
    print(
        f"New proposals: "
        f"{proposals_created}"
    )

    if failed_chunks:
        print(
            f"Retry required for {len(failed_chunks)} chunk(s)."
        )
        raise DocumentAnalysisError(
            source=source,
            failed_chunks=failed_chunks,
        )


if __name__ == "__main__":
    analyze_document(
        Path(
            "canon/manuscript/entity-test.md"
        )
    )