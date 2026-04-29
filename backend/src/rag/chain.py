"""RAG chain: Retrieve → Build Prompt → LLM → Stream Response."""

import time
import json
from typing import Generator, List, Dict, Any

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
    """Retrieve relevant legal documents for a query with reranking.

    Args:
        query: User's question.
        top_k: Number of documents to retrieve from Qdrant.

    Returns:
        List of relevant documents with metadata, reranked by Gemini.
    """
    if top_k is None:
        top_k = settings.retrieval_top_k

    # Embed the query
    query_embedding = embed_query(query)

    # Over-fetch from vector store
    documents = search(query_embedding, top_k=top_k)

    # Rerank with Gemini
    if len(documents) > settings.rerank_top_k:
        documents = rerank(query, documents, settings.rerank_top_k)

    return documents


def rerank(query: str, documents: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """Rerank documents using Gemini LLM for better relevance.

    Args:
        query: User's question.
        documents: Candidate documents from vector search.
        top_k: Number of documents to keep after reranking.

    Returns:
        Top-k most relevant documents.
    """
    client = _get_client()

    # Build rerank prompt
    doc_list = ""
    for i, doc in enumerate(documents):
        preview = doc["text"][:300].replace("\n", " ")
        doc_list += f"[{i}] {preview}\n\n"

    prompt = f"""Bạn là chuyên gia pháp luật lao động Việt Nam.
Cho câu hỏi: "{query}"

Dưới đây là {len(documents)} đoạn văn bản pháp luật. Hãy chọn {top_k} đoạn LIÊN QUAN NHẤT đến câu hỏi.
Trả về CHỈ các số thứ tự (index), cách nhau bởi dấu phẩy, theo thứ tự liên quan giảm dần.
Ví dụ: 2,0,5,3,7

Các đoạn văn:
{doc_list}

Các index liên quan nhất (chỉ trả về số, không giải thích):"""

    try:
        response = client.models.generate_content(
            model=settings.llm_model,
            contents=prompt,
            config=GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=100,
            ),
        )

        # Parse indices from response
        indices_text = response.text.strip()
        indices = []
        for part in indices_text.replace(" ", "").split(","):
            try:
                idx = int(part.strip())
                if 0 <= idx < len(documents) and idx not in indices:
                    indices.append(idx)
            except ValueError:
                continue

        if indices:
            return [documents[i] for i in indices[:top_k]]
    except Exception as e:
        print(f"⚠️ Rerank failed, using original order: {e}")

    # Fallback: return top_k by original score
    return documents[:top_k]


MAX_RETRIES = 5


def generate_response(
    question: str,
    documents: List[Dict[str, Any]],
    messages: list = None,
) -> str:
    """Generate a complete response (non-streaming) with retry.

    Args:
        question: User's question.
        documents: Retrieved documents.
        messages: Previous conversation messages.

    Returns:
        Complete response text.
    """
    client = _get_client()
    prompt = build_rag_prompt(question, documents, messages)

    for attempt in range(MAX_RETRIES):
        model = settings.llm_model if attempt < MAX_RETRIES - 1 else settings.llm_fallback_model
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )
            return response.text
        except (Exception, json.JSONDecodeError) as e:
            err_str = str(e)
            if ('503' in err_str or '429' in err_str or 'double quotes' in err_str) and attempt < MAX_RETRIES - 1:
                wait = 2 ** (attempt + 1)
                next_model = settings.llm_model if attempt + 1 < MAX_RETRIES - 1 else settings.llm_fallback_model
                print(f"⏳ {model} failed, retrying with {next_model} in {wait}s ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise


def generate_response_stream(
    question: str,
    documents: List[Dict[str, Any]],
    messages: list = None,
) -> Generator[str, None, None]:
    """Generate a streaming response with retry on 503.

    Args:
        question: User's question.
        documents: Retrieved documents.
        messages: Previous conversation messages.

    Yields:
        Text chunks as they are generated.
    """
    client = _get_client()
    prompt = build_rag_prompt(question, documents, messages)

    for attempt in range(MAX_RETRIES):
        model = settings.llm_model if attempt < MAX_RETRIES - 1 else settings.llm_fallback_model
        try:
            response_stream = client.models.generate_content_stream(
                model=model,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=8192,
                ),
            )

            for chunk in response_stream:
                if chunk.text:
                    yield chunk.text
            return  # Success, exit retry loop
        except (Exception, json.JSONDecodeError) as e:
            err_str = str(e)
            if ('503' in err_str or '429' in err_str or 'double quotes' in err_str) and attempt < MAX_RETRIES - 1:
                wait = 2 ** (attempt + 1)
                next_model = settings.llm_model if attempt + 1 < MAX_RETRIES - 1 else settings.llm_fallback_model
                print(f"⏳ {model} failed, retrying with {next_model} in {wait}s ({attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise


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

    for attempt in range(MAX_RETRIES):
        model = settings.llm_model if attempt < MAX_RETRIES - 1 else settings.llm_fallback_model
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.5,
                    max_output_tokens=60,
                ),
            )
            title = response.text.strip().strip('"').strip("'")
            if len(title) > 60:
                title = title[:57] + "..."
            return title
        except (Exception, json.JSONDecodeError) as e:
            err_str = str(e)
            if ('503' in err_str or '429' in err_str or 'double quotes' in err_str) and attempt < MAX_RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
            else:
                raise

