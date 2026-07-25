from pathlib import Path

from tqdm import tqdm

from pipeline.proposal_pipeline import analyze_document


def main():
    chapters = sorted(Path("canon/chapters").glob("*.md"))

    print(f"\nFound {len(chapters)} chapter(s).\n")

    for chapter in tqdm(
        chapters,
        desc="Analyzing chapters",
        unit="chapter",
        colour="green",
    ):
        tqdm.write(f"\n{'=' * 70}")
        tqdm.write(f"{chapter.name}")
        tqdm.write(f"{'=' * 70}")

        try:
            analyze_document(chapter)

        except Exception as e:
            tqdm.write(f"ERROR: {chapter.name}: {e}")

    print("\n✓ All chapters processed.")


if __name__ == "__main__":
    main()
