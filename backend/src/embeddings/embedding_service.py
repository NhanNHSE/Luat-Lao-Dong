"""Embedding service using local fastembed model.

Uses 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2' which
supports Vietnamese well and produces 384-dimensional embeddings.
Tries GPU (CUDA) first, falls back to CPU if unavailable.
"""

from typing import List
from fastembed import TextEmbedding

_model = None

# Multilingual model with good Vietnamese support (384 dims)
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_SIZE = 384


def _get_model() -> TextEmbedding:
    """Get or create the embedding model (lazy loading).

    Tries CUDA GPU first, falls back to CPU.
    """
    global _model
    if _model is None:
        try:
            print(f"🔄 Loading embedding model: {MODEL_NAME} (trying GPU)...")
            _model = TextEmbedding(
                MODEL_NAME,
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            print("✅ Embedding model loaded with GPU!")
        except Exception as e:
            print(f"⚠️ GPU not available ({e}), using CPU...")
            _model = TextEmbedding(MODEL_NAME)
            print("✅ Embedding model loaded on CPU.")
    return _model


def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of texts using local model.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (384 dimensions each).
    """
    model = _get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def embed_query(query: str) -> List[float]:
    """Embed a single query text.

    Args:
        query: The query string to embed.

    Returns:
        Embedding vector (384 dimensions).
    """
    model = _get_model()
    embeddings = list(model.embed([query]))
    return embeddings[0].tolist()
