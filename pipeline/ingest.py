from pathlib import Path
import hashlib

import chromadb
import ollama

from pipeline.chunker import chunk_markdown


CANON_ROOT = Path("canon")

CHROMA_HOST = "localhost"
CHROMA_PORT = 8000

COLLECTION_NAME = "starfur_canon"
EMBED_MODEL = "nomic-embed-text"


def embed(text: str):
    response = ollama.embed(
        model=EMBED_MODEL,
        input=text,
    )
    return response["embeddings"][0]


def file_hash(path: Path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def chunk_id(relative_path: str, index: int, text: str):
    digest = hashlib.sha256(
        f"{relative_path}:{index}:{text}".encode("utf-8")
    ).hexdigest()[:16]

    return f"chunk-{digest}"


def document_type(path: Path):
    relative = path.relative_to(CANON_ROOT)

    if len(relative.parts) > 1:
        return relative.parts[0]

    return "unknown"


def existing_hash(collection, source: str):
    result = collection.get(
        where={"source": source},
        include=["metadatas"],
    )

    if not result["metadatas"]:
        return None

    return result["metadatas"][0].get("file_hash")


def indexed_sources(collection):
    result = collection.get(
        include=["metadatas"]
    )

    sources = set()

    for metadata in result["metadatas"]:
        source = metadata.get("source")

        if source:
            sources.add(source)

    return sources


def ingest_file(collection, path: Path):
    relative = str(
        path.relative_to(CANON_ROOT)
    )

    digest = file_hash(path)

    old_hash = existing_hash(
        collection,
        relative,
    )

    if old_hash == digest:
        print(f"SKIP     {relative}")
        return 0, "unchanged"

    if old_hash:
        print(f"UPDATE   {relative}")
    else:
        print(f"NEW      {relative}")

    chunks = chunk_markdown(path)

    # Remove stale chunks belonging to the
    # previous version of this document.
    collection.delete(
        where={"source": relative}
    )

    for index, chunk in enumerate(chunks):

        text = chunk["text"]

        metadata = {
            "source": relative,
            "filename": path.name,
            "document_type": document_type(path),
            "chunk_index": index,
            "scene_index": chunk["scene_index"],
            "file_hash": digest,
        }

        # Copy document frontmatter into Chroma metadata.
        #
        # Example:
        #
        # chapter: 1
        #
        # becomes:
        #
        # doc_chapter: "1"
        #
        frontmatter = chunk.get(
            "frontmatter",
            {}
        )

        for key, value in frontmatter.items():
            if value is not None:
                metadata[f"doc_{key}"] = str(value)

        # Preserve the nearest Markdown heading.
        if chunk["heading"]:
            metadata["heading"] = chunk["heading"]

        vector = embed(text)

        collection.upsert(
            ids=[
                chunk_id(
                    relative,
                    index,
                    text,
                )
            ],
            documents=[text],
            embeddings=[vector],
            metadatas=[metadata],
        )

    print(f"         {len(chunks)} chunks")

    return len(chunks), "indexed"


def remove_deleted_files(
    collection,
    disk_sources,
):
    stored_sources = indexed_sources(
        collection
    )

    deleted = (
        stored_sources - disk_sources
    )

    for source in sorted(deleted):

        print(f"DELETE   {source}")

        collection.delete(
            where={"source": source}
        )

    return len(deleted)


def main():

    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
    )

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME
    )

    files = sorted(
        CANON_ROOT.rglob("*.md")
    )

    disk_sources = {
        str(path.relative_to(CANON_ROOT))
        for path in files
    }

    print("\n=== STARFUR INGESTION ===\n")
    print(
        f"Found {len(files)} Markdown files.\n"
    )

    indexed = 0
    unchanged = 0
    generated_chunks = 0

    for path in files:

        chunks, status = ingest_file(
            collection,
            path,
        )

        if status == "unchanged":
            unchanged += 1

        else:
            indexed += 1
            generated_chunks += chunks

    deleted = remove_deleted_files(
        collection,
        disk_sources,
    )

    print("\n=== COMPLETE ===")
    print(
        f"Documents found:   {len(files)}"
    )
    print(
        f"Indexed/updated:   {indexed}"
    )
    print(
        f"Unchanged/skipped: {unchanged}"
    )
    print(
        f"Deleted:           {deleted}"
    )
    print(
        f"Chunks embedded:   {generated_chunks}"
    )
    print(
        f"Collection size:   {collection.count()}"
    )


if __name__ == "__main__":
    main()