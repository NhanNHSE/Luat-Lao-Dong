"""Chat endpoints with SSE streaming, caching, rate limiting, and auto-title."""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from sqlalchemy import or_

from src.core.database import get_db
from src.core.cache import get_cached_response, set_cached_response
from src.core.logging import get_logger
from src.database.models import User, Conversation, Message
from src.api.deps import get_current_user
from src.api.schemas import (
    ChatRequest,
    ConversationResponse,
    ConversationDetailResponse,
)
from src.rag.chain import ask, generate_title

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/stream")
@limiter.limit("10/minute")
def chat_stream(
    request_obj: Request,
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message and receive a streaming response via SSE.

    Rate limited to 10 requests per minute per IP.
    """
    logger.info("chat_request", user_id=user.id, message_preview=request.message[:50])

    # Get or create conversation
    if request.conversation_id:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == request.conversation_id,
                Conversation.user_id == user.id,
            )
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Cuộc trò chuyện không tồn tại")
    else:
        # Create new conversation - title will be auto-generated later
        conversation = Conversation(user_id=user.id, title="Cuộc trò chuyện mới")
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    is_new_conversation = conversation.title == "Cuộc trò chuyện mới"

    # Save user message
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
    )
    db.add(user_message)
    db.commit()

    # Get conversation history
    history = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
        .all()
    )

    # Check cache for non-conversational queries (first message only)
    cached = None
    if len(history) <= 1:
        cached = get_cached_response(request.message)

    def event_stream():
        full_response = []
        sources_data = []

        try:
            # Send conversation_id first
            yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conversation.id})}\n\n"

            if cached:
                # Use cached response
                cached_text, cached_docs = cached
                logger.info("using_cached_response", question=request.message[:50])

                # Stream cached response in chunks for natural feel
                chunk_size = 20
                for i in range(0, len(cached_text), chunk_size):
                    chunk = cached_text[i:i + chunk_size]
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
                full_response.append(cached_text)

                for doc in cached_docs[:5]:
                    meta = doc.get("metadata", {})
                    sources_data.append({
                        "article": meta.get("article", "N/A"),
                        "law_name": meta.get("law_name", "N/A"),
                        "content_preview": doc.get("text", "")[:150],
                    })
            else:
                # Generate fresh response
                response_gen, documents = ask(
                    question=request.message,
                    messages=history,
                    stream=True,
                )

                for chunk in response_gen:
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

                for doc in documents[:5]:
                    meta = doc.get("metadata", {})
                    sources_data.append({
                        "article": meta.get("article", "N/A"),
                        "law_name": meta.get("law_name", "N/A"),
                        "content_preview": doc.get("text", "")[:150],
                    })

                # Cache the response for future identical queries
                complete_text = "".join(full_response)
                if len(history) <= 1:
                    set_cached_response(request.message, complete_text, documents)

            # Send sources
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"

            # Save assistant message to DB
            complete_response = "".join(full_response)
            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=complete_response,
                sources=json.dumps(sources_data, ensure_ascii=False) if sources_data else None,
            )
            db.add(assistant_message)
            db.commit()

            # Auto-generate title for new conversations
            if is_new_conversation:
                try:
                    auto_title = generate_title(request.message, complete_response)
                    conversation.title = auto_title
                    db.commit()
                    yield f"data: {json.dumps({'type': 'title_update', 'title': auto_title})}\n\n"
                    logger.info("auto_title_generated", title=auto_title)
                except Exception as e:
                    logger.warning("auto_title_failed", error=str(e))
                    # Fallback to first 80 chars of question
                    conversation.title = request.message[:80] + ("..." if len(request.message) > 80 else "")
                    db.commit()

            # Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            logger.info("chat_response_complete", conversation_id=conversation.id)

        except Exception as e:
            logger.error("chat_stream_error", error=str(e), conversation_id=conversation.id)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=List[ConversationResponse])
def get_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None, description="Search conversations by title or message content"),
):
    """Get all conversations for the current user, with optional search."""
    query = db.query(Conversation).filter(Conversation.user_id == user.id)

    if search:
        search_term = f"%{search}%"
        # Search in conversation title and message content
        query = query.filter(
            or_(
                Conversation.title.ilike(search_term),
                Conversation.id.in_(
                    db.query(Message.conversation_id)
                    .filter(Message.content.ilike(search_term))
                    .subquery()
                ),
            )
        )

    conversations = query.order_by(Conversation.updated_at.desc()).all()
    return conversations


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a specific conversation with all messages."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Cuộc trò chuyện không tồn tại")
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Cuộc trò chuyện không tồn tại")

    db.delete(conversation)
    db.commit()
    logger.info("conversation_deleted", conversation_id=conversation_id, user_id=user.id)
