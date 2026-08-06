from pathlib import Path
from pipeline.chunker import chunk_markdown

print("Starting...")

path = Path("canon/manuscript/chapter-prologue.md")  # Change if needed

print("Exists:", path.exists())
print("Absolute:", path.resolve())

chunks = chunk_markdown(path)

print("Chunks:", len(chunks))

for i, chunk in enumerate(chunks):
    print("=" * 60)
    print("Chunk", i)
    print("Heading:", chunk["heading"])
    print("Scene:", chunk["scene_index"])
    print(chunk["text"][:200])

print("Done.")