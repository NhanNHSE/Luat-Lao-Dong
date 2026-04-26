"""Embedding service using Gemini text-embedding-004."""

from typing import List
from google import genai

from src.core.config import get_settings

settings = get_settings()

_client = None


def _get_client() -> genai.Client:
    """Get or create the Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using Gemini embedding model.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors.
    """
    client = _get_client()
    embeddings = []

    # Process in batches of 100 (Gemini API limit)
    batch_size = 100
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        result = client.models.embed_content(
            model=settings.embedding_model,
            contents=batch,
        )
        for embedding in result.embeddings:
            embeddings.append(embedding.values)

    return embeddings


def embed_query(query: str) -> List[float]:
    """Embed a single query text.

    Args:
        query: The query string to embed.

    Returns:
        Embedding vector.
    """
    client = _get_client()
    result = client.models.embed_content(
        model=settings.embedding_model,
        contents=[query],
    )
    return result.embeddings[0].values
