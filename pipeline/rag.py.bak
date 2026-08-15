import chromadb
import ollama


CHROMA_HOST = "localhost"
CHROMA_PORT = 8000

COLLECTION_NAME = "starfur_canon"
EMBED_MODEL = "nomic-embed-text"
CHAT_MODEL = "qwen3:8b"

TOP_K = 3


def embed(text: str):
    response = ollama.embed(
        model=EMBED_MODEL,
        input=text,
    )
    return response["embeddings"][0]


def retrieve(question: str):
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
    )

    collection = client.get_collection(
        name=COLLECTION_NAME
    )

    result = collection.query(
        query_embeddings=[embed(question)],
        n_results=min(TOP_K, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    return result


def build_context(results):
    passages = []

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    for i, document in enumerate(documents):
        metadata = metadatas[i]

        passages.append(
            f"""[SOURCE {i + 1}]
File: {metadata['filename']}
Chunk: {metadata['chunk_index']}

{document}"""
        )

    return "\n\n".join(passages)


def ask_starfur(question: str):
    results = retrieve(question)
    context = build_context(results)

    print("\n=== RETRIEVED CANON ===\n")

    for i, document in enumerate(results["documents"][0]):
        distance = results["distances"][0][i]
        metadata = results["metadatas"][0][i]

        print(
            f"[{i + 1}] {metadata['filename']} "
            f"chunk {metadata['chunk_index']} "
            f"distance={distance:.4f}"
        )
        print(document)
        print()

    system_prompt = """You are StarFur, an assistant for a fictional universe.

Answer questions using ONLY the supplied canon context.

Rules:
- Treat supplied context as authoritative canon.
- Do not invent facts that are absent from the context.
- If the context does not contain enough information, say so.
- Distinguish explicitly stated facts from reasonable inference.
- Do not silently fill gaps using general world knowledge.
"""

    user_prompt = f"""CANON CONTEXT:

{context}

QUESTION:

{question}
"""

    response = ollama.chat(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
    )

    print("\n=== STARFUR ===\n")
    print(response["message"]["content"])


if __name__ == "__main__":
    question = input("Ask StarFur: ")
    ask_starfur(question)
