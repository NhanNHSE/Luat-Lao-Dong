"""Qdrant vector store wrapper for legal document storage and retrieval."""

from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)

from src.core.config import get_settings

settings = get_settings()

_client = None


def _get_client() -> QdrantClient:
    """Get or create the Qdrant client."""
    global _client
    if _client is None:
        _client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    return _client


def create_collection(vector_size: int = 768):
    """Create the law collection in Qdrant if it doesn't exist.

    Args:
        vector_size: Dimension of the embedding vectors (768 for Gemini text-embedding-004).
    """
    client = _get_client()
    collections = [c.name for c in client.get_collections().collections]

    if settings.qdrant_collection not in collections:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
        print(f"Created collection: {settings.qdrant_collection}")
    else:
        print(f"Collection '{settings.qdrant_collection}' already exists.")


def upsert_documents(
    ids: List[str],
    embeddings: List[List[float]],
    documents: List[str],
    metadatas: List[Dict[str, Any]],
):
    """Insert or update documents in the vector store.

    Args:
        ids: Unique identifiers for each document.
        embeddings: Embedding vectors.
        documents: Original text content.
        metadatas: Metadata dicts for each document.
    """
    client = _get_client()
    points = []
    for i, (doc_id, embedding, doc, meta) in enumerate(
        zip(ids, embeddings, documents, metadatas)
    ):
        payload = {**meta, "text": doc}
        points.append(
            PointStruct(
                id=i if not isinstance(doc_id, int) else doc_id,
                vector=embedding,
                payload=payload,
            )
        )

    # Upsert in batches of 100
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(
            collection_name=settings.qdrant_collection,
            points=batch,
        )


def search(
    query_embedding: List[float],
    top_k: int = 8,
    law_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search for similar documents in the vector store.

    Args:
        query_embedding: The query embedding vector.
        top_k: Number of results to return.
        law_filter: Optional filter by law name.

    Returns:
        List of matching documents with scores and metadata.
    """
    client = _get_client()

    search_filter = None
    if law_filter:
        search_filter = Filter(
            must=[
                FieldCondition(
                    key="law_name",
                    match=MatchValue(value=law_filter),
                )
            ]
        )

    results = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_embedding,
        limit=top_k,
        query_filter=search_filter,
        with_payload=True,
    )

    documents = []
    for point in results.points:
        documents.append(
            {
                "id": point.id,
                "score": point.score,
                "text": point.payload.get("text", ""),
                "metadata": {
                    k: v for k, v in point.payload.items() if k != "text"
                },
            }
        )

    return documents


def get_collection_info() -> Dict[str, Any]:
    """Get information about the law collection."""
    client = _get_client()
    try:
        info = client.get_collection(settings.qdrant_collection)
        return {
            "name": settings.qdrant_collection,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
        }
    except Exception:
        return {"name": settings.qdrant_collection, "status": "not_found"}
