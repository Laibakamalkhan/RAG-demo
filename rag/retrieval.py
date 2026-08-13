# Handles retrieval from vector database
import os
import chromadb
from dotenv import load_dotenv
from rag.embeddings import get_query_embedding

load_dotenv()

CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
COLLECTION_NAME = "orders"

def search(question: str, tenant_id: str, n_results: int = 5) -> list[dict]:
    """
    Given a natural-language question, returns the most relevant order records
    for the given tenant, ranked by semantic similarity.
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(COLLECTION_NAME)

    query_vector = get_query_embedding(question)

    results = collection.query(
        query_embeddings=[query_vector],
        n_results=n_results,
        where={"tenant_id": tenant_id}
    )

    output = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        output.append({
            "text": doc,
            "metadata": meta,
            "similarity_distance": dist
        })

    return output


if __name__ == "__main__":
    results = search("Why are customers unhappy with their orders?", tenant_id="shop_demo_001")
    for r in results:
        print("-" * 50)
        print(r["text"])
        print("Rating:", r["metadata"].get("rating"))
        print("Distance:", r["similarity_distance"])