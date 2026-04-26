"""RAG chain: Retrieve → Build Prompt → LLM → Stream Response."""

from typing import Generator, List, Dict, Any
import json

from google import genai
from google.genai.types import GenerateContentConfig

from src.core.config import get_settings
from src.embeddings.embedding_service import embed_query
from src.embeddings.vector_store import search
from src.rag.prompts import build_rag_prompt

settings = get_settings()

_client = None


def _get_client() -> genai.Client:
    """Get or create the Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def retrieve(query: str, top_k: int = None) -> List[Dict[str, Any]]:
    """Retrieve relevant legal documents for a query.

    Args:
        query: User's question.
        top_k: Number of documents to retrieve.

    Returns:
        List of relevant documents with metadata.
    """
    if top_k is None:
        top_k = settings.retrieval_top_k

    # Embed the query
    query_embedding = embed_query(query)

    # Search in vector store
    documents = search(query_embedding, top_k=top_k)

    return documents


def generate_response(
    question: str,
    documents: List[Dict[str, Any]],
    messages: list = None,
) -> str:
    """Generate a complete response (non-streaming).

    Args:
        question: User's question.
        documents: Retrieved documents.
        messages: Previous conversation messages.

    Returns:
        Complete response text.
    """
    client = _get_client()
    prompt = build_rag_prompt(question, documents, messages)

    response = client.models.generate_content(
        model=settings.llm_model,
        contents=prompt,
        config=GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )

    return response.text


def generate_response_stream(
    question: str,
    documents: List[Dict[str, Any]],
    messages: list = None,
) -> Generator[str, None, None]:
    """Generate a streaming response.

    Args:
        question: User's question.
        documents: Retrieved documents.
        messages: Previous conversation messages.

    Yields:
        Text chunks as they are generated.
    """
    client = _get_client()
    prompt = build_rag_prompt(question, documents, messages)

    response_stream = client.models.generate_content_stream(
        model=settings.llm_model,
        contents=prompt,
        config=GenerateContentConfig(
            temperature=0.3,
            max_output_tokens=2048,
        ),
    )

    for chunk in response_stream:
        if chunk.text:
            yield chunk.text


def ask(question: str, messages: list = None, stream: bool = True):
    """Main entry point: retrieve documents and generate answer.

    Args:
        question: User's question.
        messages: Previous conversation messages.
        stream: If True, return a generator; otherwise return complete text.

    Returns:
        Tuple of (response_or_generator, retrieved_documents).
    """
    # Step 1: Retrieve relevant documents
    documents = retrieve(question)

    # Step 2: Generate response
    if stream:
        return generate_response_stream(question, documents, messages), documents
    else:
        return generate_response(question, documents, messages), documents


def generate_title(question: str, answer: str) -> str:
    """Generate a concise conversation title using LLM.

    Args:
        question: The user's first question.
        answer: The assistant's first answer.

    Returns:
        A short title string (max 60 chars).
    """
    client = _get_client()
    prompt = f"""Tạo một tiêu đề ngắn gọn (tối đa 50 ký tự) cho cuộc hội thoại pháp luật sau.
Chỉ trả về tiêu đề, không giải thích.

Câu hỏi: {question[:200]}
Trả lời: {answer[:200]}

Tiêu đề:"""

    response = client.models.generate_content(
        model=settings.llm_model,
        contents=prompt,
        config=GenerateContentConfig(
            temperature=0.5,
            max_output_tokens=60,
        ),
    )

    title = response.text.strip().strip('"').strip("'")
    # Ensure max length
    if len(title) > 60:
        title = title[:57] + "..."
    return title

