import requests

OLLAMA_URL = "http://localhost:11434/api/embeddings"
MODEL_NAME = "embeddinggemma:latest"

def _embed_raw(text: str) -> list[float]:
    """
    Internal helper: sends raw text to Ollama and returns the embedding vector.
    """
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL_NAME, "prompt": text}
    )
    response.raise_for_status()
    return response.json()["embedding"]

def get_document_embedding(text: str) -> list[float]:
    """
    Use this when embedding data to STORE (e.g. order records).
    embeddinggemma expects documents prefixed this way for best retrieval quality.
    """
    prefixed = f"title: none | text: {text}"
    return _embed_raw(prefixed)

def get_query_embedding(text: str) -> list[float]:
    """
    Use this when embedding a QUESTION being searched for.
    embeddinggemma expects queries prefixed this way for best retrieval quality.
    """
    prefixed = f"task: search result | query: {text}"
    return _embed_raw(prefixed)