"""Prompt templates for the legal chatbot."""

SYSTEM_PROMPT = """Bạn là một chuyên gia tư vấn pháp luật Việt Nam, chuyên về Luật Lao Động.
Hãy trả lời câu hỏi dựa HOÀN TOÀN vào các điều luật được cung cấp trong phần [Ngữ cảnh] bên dưới.

Quy tắc bắt buộc:
1. Chỉ trả lời dựa trên thông tin có trong ngữ cảnh. Nếu không tìm thấy thông tin liên quan, hãy nói rõ: "Tôi không tìm thấy thông tin liên quan trong cơ sở dữ liệu."
2. Luôn trích dẫn cụ thể: số Điều, Khoản, tên luật, năm ban hành.
3. Giải thích bằng ngôn ngữ dễ hiểu cho người không chuyên luật.
4. Nếu có nhiều điều luật liên quan, liệt kê và giải thích từng điều.
5. Nếu câu hỏi phức tạp hoặc cần phân tích sâu, khuyên người dùng tham vấn luật sư chuyên nghiệp.
6. Trả lời bằng tiếng Việt.
7. Sử dụng Markdown để định dạng câu trả lời cho dễ đọc."""

RAG_PROMPT_TEMPLATE = """{system_prompt}

[Ngữ cảnh - Các điều luật liên quan]
{context}

[Lịch sử hội thoại]
{chat_history}

[Câu hỏi của người dùng]
{question}

Hãy trả lời câu hỏi dựa trên ngữ cảnh được cung cấp. Trích dẫn cụ thể các điều luật liên quan."""


def build_context(documents: list) -> str:
    """Build context string from retrieved documents.

    Args:
        documents: List of retrieved document dicts with text and metadata.

    Returns:
        Formatted context string.
    """
    if not documents:
        return "Không tìm thấy điều luật liên quan."

    context_parts = []
    for i, doc in enumerate(documents, 1):
        meta = doc.get("metadata", {})
        article = meta.get("article", "N/A")
        law_name = meta.get("law_name", "N/A")
        chapter = meta.get("chapter", "")

        header = f"--- Nguồn {i}: {article} - {law_name}"
        if chapter:
            header += f" ({chapter})"
        header += " ---"

        context_parts.append(f"{header}\n{doc['text']}")

    return "\n\n".join(context_parts)


def build_chat_history(messages: list, max_messages: int = 10) -> str:
    """Build chat history string from recent messages.

    Args:
        messages: List of message objects with role and content.
        max_messages: Maximum number of recent messages to include.

    Returns:
        Formatted chat history string.
    """
    if not messages:
        return "Chưa có lịch sử hội thoại."

    recent = messages[-max_messages:]
    history_parts = []
    for msg in recent:
        role = "Người dùng" if msg.role == "user" else "Trợ lý"
        history_parts.append(f"{role}: {msg.content}")

    return "\n".join(history_parts)


def build_rag_prompt(question: str, documents: list, messages: list = None) -> str:
    """Build the complete RAG prompt.

    Args:
        question: The user's question.
        documents: Retrieved legal documents.
        messages: Previous conversation messages.

    Returns:
        Complete prompt string ready for the LLM.
    """
    context = build_context(documents)
    chat_history = build_chat_history(messages or [])

    return RAG_PROMPT_TEMPLATE.format(
        system_prompt=SYSTEM_PROMPT,
        context=context,
        chat_history=chat_history,
        question=question,
    )
