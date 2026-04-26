"""Chat endpoints with SSE streaming support."""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.database.models import User, Conversation, Message
from src.api.deps import get_current_user
from src.api.schemas import (
    ChatRequest,
    ConversationResponse,
    ConversationDetailResponse,
    MessageResponse,
)
from src.rag.chain import ask

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/stream")
def chat_stream(
    request: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message and receive a streaming response via SSE."""
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
        # Create new conversation with first message as title
        title = request.message[:80] + ("..." if len(request.message) > 80 else "")
        conversation = Conversation(user_id=user.id, title=title)
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

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

    # Generate streaming response
    def event_stream():
        full_response = []
        sources_data = []

        try:
            response_gen, documents = ask(
                question=request.message,
                messages=history,
                stream=True,
            )

            # Send conversation_id first
            yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conversation.id})}\n\n"

            # Stream response chunks
            for chunk in response_gen:
                full_response.append(chunk)
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # Prepare sources
            for doc in documents[:5]:
                meta = doc.get("metadata", {})
                sources_data.append({
                    "article": meta.get("article", "N/A"),
                    "law_name": meta.get("law_name", "N/A"),
                    "content_preview": doc.get("text", "")[:150],
                })

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

            # Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as e:
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
):
    """Get all conversations for the current user."""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
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
