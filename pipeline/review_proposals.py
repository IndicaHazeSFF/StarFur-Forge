from pipeline.db import (
    connect,
    create_entity,
    get_entity_by_name,
    get_pending_proposals,
)


def mark_proposal(proposal_id, status):
    with connect() as connection:
        connection.execute(
            """
            UPDATE proposals
            SET status = ?
            WHERE id = ?
            """,
            (status, proposal_id),
        )

        connection.commit()


def approve_proposal(proposal):
    name = proposal["proposed_name"]
    entity_type = (
        proposal["proposed_entity_type"]
        or "unknown"
    )

    existing = get_entity_by_name(name)

    if existing:
        print(
            f"\nAlready exists as "
            f"{existing['canonical_name']} "
            f"({existing['entity_type']})."
        )

        mark_proposal(
            proposal["id"],
            "approved",
        )

        return

    entity_id = create_entity(
        canonical_name=name,
        entity_type=entity_type,
        description=proposal["description"],
    )

    mark_proposal(
        proposal["id"],
        "approved",
    )

    print(
        f"\nCONFIRMED: {name}"
        f" [{entity_type}]"
        f" -> entity #{entity_id}"
    )


def edit_proposal(proposal):
    print("\nLeave blank to keep current value.\n")

    current_name = (
        proposal["proposed_name"] or ""
    )

    current_type = (
        proposal["proposed_entity_type"]
        or "unknown"
    )

    current_description = (
        proposal["description"] or ""
    )

    name = input(
        f"Name [{current_name}]: "
    ).strip()

    entity_type = input(
        f"Type [{current_type}]: "
    ).strip()

    description = input(
        f"Description [{current_description}]: "
    ).strip()

    if not name:
        name = current_name

    if not entity_type:
        entity_type = current_type

    if not description:
        description = current_description

    with connect() as connection:
        connection.execute(
            """
            UPDATE proposals
            SET proposed_name = ?,
                proposed_entity_type = ?,
                description = ?
            WHERE id = ?
            """,
            (
                name,
                entity_type,
                description,
                proposal["id"],
            ),
        )

        connection.commit()

    print("\nProposal updated.")


def display_proposal(proposal, number, total):
    print("\n" + "=" * 70)
    print(
        f"STARFUR LORE REVIEW "
        f"[{number}/{total}]"
    )
    print("=" * 70)

    print(
        f"\nProposal #{proposal['id']}"
    )

    print(
        f"\nName: "
        f"{proposal['proposed_name']}"
    )

    print(
        f"Type: "
        f"{proposal['proposed_entity_type']}"
    )

    if proposal["description"]:
        print(
            f"\nReason:\n"
            f"{proposal['description']}"
        )

    if proposal["evidence"]:
        print(
            f"\nEvidence:\n"
            f"{proposal['evidence']}"
        )

    print(
        f"\nSource: {proposal['source']}"
    )

    print(
        f"Scene: {proposal['scene_index']} "
        f"| Chunk: {proposal['chunk_index']}"
    )

    print(
        "\n[A] Approve"
        "\n[E] Edit"
        "\n[R] Reject"
        "\n[S] Skip"
        "\n[Q] Quit"
    )


def main():
    while True:
        proposals = get_pending_proposals()

        if not proposals:
            print(
                "\nNo pending lore proposals."
            )
            return

        proposal = proposals[0]

        display_proposal(
            proposal,
            1,
            len(proposals),
        )

        choice = input(
            "\nChoice: "
        ).strip().lower()

        if choice == "a":
            approve_proposal(proposal)

        elif choice == "e":
            edit_proposal(proposal)

        elif choice == "r":
            mark_proposal(
                proposal["id"],
                "rejected",
            )

            print(
                f"\nREJECTED: "
                f"{proposal['proposed_name']}"
            )

        elif choice == "s":
            print("\nSkipped.")
            return

        elif choice == "q":
            print("\nReview ended.")
            return

        else:
            print(
                "\nInvalid choice. "
                "Use A, E, R, S, or Q."
            )


if __name__ == "__main__":
    main()
