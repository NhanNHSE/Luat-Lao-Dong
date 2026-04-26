"""Contract analysis service: analyze labor contracts against Vietnamese labor law."""

import json
from typing import Generator, List, Dict, Any

from google import genai
from google.genai.types import GenerateContentConfig

from src.core.config import get_settings
from src.core.logging import get_logger
from src.embeddings.embedding_service import embed_query
from src.embeddings.vector_store import search

settings = get_settings()
logger = get_logger(__name__)

_client = None


def _get_client() -> genai.Client:
    """Get or create the Gemini client."""
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


CONTRACT_ANALYSIS_PROMPT = """Bạn là một chuyên gia phân tích hợp đồng lao động Việt Nam.

Hãy phân tích hợp đồng lao động dưới đây và so sánh với các điều luật liên quan được cung cấp.

## NHIỆM VỤ:
1. **Tóm tắt hợp đồng**: Liệt kê các điều khoản chính (lương, thời gian, quyền lợi...)
2. **Vi phạm pháp luật**: Chỉ ra các điều khoản VI PHẠM luật lao động (nếu có), kèm trích dẫn điều luật cụ thể
3. **Thiếu quyền lợi**: Liệt kê các quyền lợi mà người lao động ĐÁNG LẼ PHẢI CÓ theo luật nhưng KHÔNG được đề cập trong hợp đồng
4. **Điều khoản bất lợi**: Các điều khoản hợp pháp nhưng BẤT LỢI cho người lao động
5. **Đề xuất**: Khuyến nghị cụ thể cho người lao động

## QUY TẮC:
- Trích dẫn cụ thể số Điều, Khoản, tên luật
- Đánh giá mức độ nghiêm trọng: 🔴 Nghiêm trọng | 🟡 Cần lưu ý | 🟢 Hợp lệ
- Nếu không chắc chắn, khuyên tham vấn luật sư
- Trả lời bằng tiếng Việt, sử dụng Markdown

## [NỘI DUNG HỢP ĐỒNG]
{contract_text}

## [CÁC ĐIỀU LUẬT LIÊN QUAN]
{legal_context}

## PHÂN TÍCH CHI TIẾT:"""


def retrieve_relevant_laws(contract_text: str, top_k: int = 15) -> List[Dict[str, Any]]:
    """Retrieve relevant labor law articles for contract analysis.

    Uses multiple search queries to cover different aspects of the contract.

    Args:
        contract_text: The extracted contract text.
        top_k: Number of documents per query.

    Returns:
        Deduplicated list of relevant legal documents.
    """
    # Generate multiple search queries to cover different contract aspects
    search_queries = [
        "hợp đồng lao động quy định bắt buộc",
        "thời giờ làm việc nghỉ ngơi",
        "tiền lương phụ cấp quyền lợi",
        "bảo hiểm xã hội bảo hiểm y tế",
        "chấm dứt hợp đồng sa thải bồi thường",
        "nghỉ phép năm thai sản",
    ]

    # Also search based on contract content keywords
    contract_preview = contract_text[:500].lower()
    if "thử việc" in contract_preview:
        search_queries.append("thời gian thử việc lương thử việc")
    if "làm thêm" in contract_preview or "tăng ca" in contract_preview:
        search_queries.append("làm thêm giờ tiền lương làm thêm")
    if "kỷ luật" in contract_preview:
        search_queries.append("kỷ luật lao động xử lý vi phạm")

    all_docs = {}
    for query in search_queries:
        try:
            query_embedding = embed_query(query)
            docs = search(query_embedding, top_k=5)
            for doc in docs:
                doc_id = doc.get("id")
                if doc_id not in all_docs:
                    all_docs[doc_id] = doc
        except Exception as e:
            logger.warning("search_query_failed", query=query, error=str(e))

    # Sort by relevance score and take top_k
    sorted_docs = sorted(all_docs.values(), key=lambda x: x.get("score", 0), reverse=True)
    return sorted_docs[:top_k]


def build_legal_context(documents: List[Dict[str, Any]]) -> str:
    """Build legal context string from retrieved documents.

    Args:
        documents: List of retrieved legal documents.

    Returns:
        Formatted legal context string.
    """
    if not documents:
        return "Không tìm thấy điều luật liên quan."

    parts = []
    for i, doc in enumerate(documents, 1):
        meta = doc.get("metadata", {})
        article = meta.get("article", "N/A")
        law_name = meta.get("law_name", "N/A")
        parts.append(f"[{i}] {article} — {law_name}\n{doc['text']}")

    return "\n\n".join(parts)


def analyze_contract_stream(contract_text: str) -> Generator[str, None, List[Dict[str, Any]]]:
    """Analyze a labor contract against labor law with streaming.

    Args:
        contract_text: The extracted contract text.

    Yields:
        Text chunks of the analysis.

    Returns:
        List of referenced legal documents (via generator return).
    """
    client = _get_client()

    # Retrieve relevant laws
    logger.info("retrieving_laws_for_analysis", text_length=len(contract_text))
    documents = retrieve_relevant_laws(contract_text)
    legal_context = build_legal_context(documents)

    # Truncate contract if too long (keep first 8000 chars)
    if len(contract_text) > 8000:
        contract_text = contract_text[:8000] + "\n\n[... nội dung đã được cắt bớt do quá dài ...]"

    prompt = CONTRACT_ANALYSIS_PROMPT.format(
        contract_text=contract_text,
        legal_context=legal_context,
    )

    logger.info("starting_contract_analysis", prompt_length=len(prompt))

    response_stream = client.models.generate_content_stream(
        model=settings.llm_model,
        contents=prompt,
        config=GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
        ),
    )

    for chunk in response_stream:
        if chunk.text:
            yield chunk.text

    return documents


def analyze_contract(contract_text: str) -> tuple:
    """Analyze a contract (non-streaming version).

    Args:
        contract_text: The extracted contract text.

    Returns:
        Tuple of (analysis_text, referenced_documents).
    """
    client = _get_client()

    documents = retrieve_relevant_laws(contract_text)
    legal_context = build_legal_context(documents)

    if len(contract_text) > 8000:
        contract_text = contract_text[:8000] + "\n\n[... nội dung đã được cắt bớt ...]"

    prompt = CONTRACT_ANALYSIS_PROMPT.format(
        contract_text=contract_text,
        legal_context=legal_context,
    )

    response = client.models.generate_content(
        model=settings.llm_model,
        contents=prompt,
        config=GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=4096,
        ),
    )

    return response.text, documents
