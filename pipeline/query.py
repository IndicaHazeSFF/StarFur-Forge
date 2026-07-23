import chromadb
import ollama


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


def search(query: str, results: int = 3):
    client = chromadb.HttpClient(
        host=CHROMA_HOST,
        port=CHROMA_PORT,
    )

    collection = client.get_collection(
        name=COLLECTION_NAME
    )

    query_vector = embed(query)

    result = collection.query(
        query_embeddings=[query_vector],
        n_results=min(results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    return result


if __name__ == "__main__":
    question = input("Search StarFur: ")

    results = search(question)

    print()

    for i, document in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][i]
        distance = results["distances"][0][i]

        print(f"--- RESULT {i + 1} ---")
        print(f"Source: {metadata['filename']}")
        print(f"Chunk: {metadata['chunk_index']}")
        print(f"Distance: {distance:.4f}")
        print()
        print(document)
        print()
