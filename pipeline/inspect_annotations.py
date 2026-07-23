from pathlib import Path
import json

from pipeline.chunker import chunk_markdown
from pipeline.annotator import annotate


SOURCE = Path("canon/manuscript/entity-test.md")


def main():
    chunks = chunk_markdown(SOURCE)

    print("\n=== STARFUR ANNOTATION TEST ===")
    print(f"Source: {SOURCE}")
    print(f"Chunks: {len(chunks)}")

    for index, chunk in enumerate(chunks):

        print("\n" + "=" * 70)
        print(
            f"CHUNK {index} | "
            f"scene={chunk['scene_index']} | "
            f"chars={len(chunk['text'])}"
        )
        print("=" * 70)

        print("\nTEXT:\n")
        print(chunk["text"])

        print("\nANNOTATION:\n")

        annotation = annotate(
            chunk["text"]
        )

        print(
            json.dumps(
                annotation,
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
