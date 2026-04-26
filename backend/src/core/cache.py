"""Response caching for RAG queries to reduce API calls."""

import hashlib
import json
from typing import Optional, Tuple, List, Dict, Any
from cachetools import TTLCache

from src.core.logging import get_logger

logger = get_logger(__name__)

# Cache with max 500 entries, TTL of 1 hour
_response_cache: TTLCache = TTLCache(maxsize=500, ttl=3600)


def _make_cache_key(question: str, conversation_context: str = "") -> str:
    """Create a deterministic cache key from the question and context.

    Args:
        question: The user's question.
        conversation_context: Serialized recent conversation history.

    Returns:
        An MD5 hash string as the cache key.
    """
    raw = f"{question.strip().lower()}|{conversation_context}"
    return hashlib.md5(raw.encode()).hexdigest()


def get_cached_response(question: str, conversation_context: str = "") -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """Try to get a cached response for a question.

    Args:
        question: The user's question.
        conversation_context: Serialized recent conversation history.

    Returns:
        Tuple of (response_text, documents) if cached, None otherwise.
    """
    key = _make_cache_key(question, conversation_context)
    result = _response_cache.get(key)
    if result:
        logger.info("cache_hit", question=question[:50])
    return result


def set_cached_response(
    question: str,
    response: str,
    documents: List[Dict[str, Any]],
    conversation_context: str = "",
):
    """Cache a response for a question.

    Args:
        question: The user's question.
        response: The generated response text.
        documents: The retrieved documents.
        conversation_context: Serialized recent conversation history.
    """
    key = _make_cache_key(question, conversation_context)
    _response_cache[key] = (response, documents)
    logger.info("cache_set", question=question[:50], cache_size=len(_response_cache))


def clear_cache():
    """Clear all cached responses."""
    _response_cache.clear()
    logger.info("cache_cleared")


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics.

    Returns:
        Dict with current size, max size, and TTL.
    """
    return {
        "current_size": len(_response_cache),
        "max_size": _response_cache.maxsize,
        "ttl_seconds": int(_response_cache.ttl),
    }
