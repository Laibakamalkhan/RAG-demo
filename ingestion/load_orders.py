# Loads rag_ready_orders.json into Chroma (embeds each rag_document via Ollama)
import json
import os
import chromadb
from pathlib import Path
from dotenv import load_dotenv
from rag.embeddings import get_document_embedding

load_dotenv()

DATA_PATH = Path(__file__).parent.parent / "data" / "rag_ready_orders.json"
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_data")
COLLECTION_NAME = "orders"

def clean_metadata(metadata: dict) -> dict:
    """
    Chroma doesn't allow None values in metadata.
    Replace any None with a safe default so filtering still works.
    """
    cleaned = {}
    for key, value in metadata.items():
        if value is None:
            cleaned[key] = "none"
        else:
            cleaned[key] = value
    return cleaned

def load_orders():
    # 1. Read the JSON file
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data["records"] if isinstance(data, dict) and "records" in data else data

    # 2. Connect to (or create) the local Chroma database
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    ids, documents, embeddings, metadatas = [], [], [], []

    # 3. Loop through every record, embed it, and prepare it for storage
    for record in records:
        order_id = record["order_id"]
        rag_text = record["rag_document"]
        metadata = clean_metadata(record["metadata"])

        print(f"Embedding order {order_id}...")
        vector = get_document_embedding(rag_text)

        ids.append(order_id)
        documents.append(rag_text)
        embeddings.append(vector)
        metadatas.append(metadata)

    # 4. Store everything in Chroma in one batch call
    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )

    print(f"\nDone. Loaded {len(ids)} records into Chroma collection '{COLLECTION_NAME}'.")

if __name__ == "__main__":
    load_orders()