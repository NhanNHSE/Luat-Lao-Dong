"""Contract analysis API: upload file, extract text, analyze against labor law."""

import json
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.logging import get_logger
from src.database.models import User, Conversation, Message
from src.api.deps import get_current_user
from src.services.document_processor import extract_text, validate_file, SUPPORTED_EXTENSIONS
from src.services.contract_analyzer import analyze_contract_stream

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/contract", tags=["Contract Analysis"])


@router.post("/analyze")
@limiter.limit("5/minute")
async def analyze_contract_endpoint(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a contract file and analyze it against labor law.

    Supports: PDF, DOCX, PNG, JPG, WEBP, BMP, TIFF.
    Uses OCR for scanned documents and images.
    Rate limited to 5 requests per minute.
    """
    logger.info(
        "contract_upload",
        user_id=user.id,
        filename=file.filename,
        content_type=file.content_type,
    )

    # Validate file
    file_bytes = await file.read()
    error = validate_file(file.filename, len(file_bytes))
    if error:
        raise HTTPException(status_code=400, detail=error)

    # Extract text from file
    try:
        extracted_text = extract_text(file.filename, file_bytes)
    except Exception as e:
        logger.error("text_extraction_failed", error=str(e), filename=file.filename)
        raise HTTPException(
            status_code=422,
            detail=f"Không thể đọc file: {str(e)}"
        )

    if not extracted_text or len(extracted_text.strip()) < 50:
        raise HTTPException(
            status_code=422,
            detail="Không thể trích xuất nội dung từ file. Vui lòng kiểm tra file có nội dung rõ ràng."
        )

    logger.info("text_extracted", chars=len(extracted_text), filename=file.filename)

    # Create a conversation for this analysis
    title = f"📋 Phân tích: {file.filename}"
    if len(title) > 80:
        title = title[:77] + "..."
    conversation = Conversation(user_id=user.id, title=title)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)

    # Save the uploaded content as a user message
    user_message_content = f"[Tải lên file: {file.filename}]\n\nNội dung trích xuất:\n{extracted_text[:2000]}{'...' if len(extracted_text) > 2000 else ''}"
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        content=user_message_content,
    )
    db.add(user_message)
    db.commit()

    # Streaming analysis
    def event_stream():
        full_response = []
        sources_data = []

        try:
            # Send meta
            yield f"data: {json.dumps({'type': 'meta', 'conversation_id': conversation.id, 'extracted_length': len(extracted_text)})}\n\n"

            # Send extracted text preview
            yield f"data: {json.dumps({'type': 'extracted_text', 'preview': extracted_text[:500], 'total_chars': len(extracted_text)})}\n\n"

            # Stream analysis
            gen = analyze_contract_stream(extracted_text)
            documents = []

            try:
                while True:
                    chunk = next(gen)
                    full_response.append(chunk)
                    yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
            except StopIteration as e:
                # Generator return value contains documents
                documents = e.value if e.value else []

            # Prepare sources
            for doc in (documents or [])[:5]:
                meta = doc.get("metadata", {})
                sources_data.append({
                    "article": meta.get("article", "N/A"),
                    "law_name": meta.get("law_name", "N/A"),
                    "content_preview": doc.get("text", "")[:150],
                })

            yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data})}\n\n"

            # Save analysis to DB
            complete_response = "".join(full_response)
            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=complete_response,
                sources=json.dumps(sources_data, ensure_ascii=False) if sources_data else None,
            )
            db.add(assistant_message)
            db.commit()

            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            logger.info("contract_analysis_complete", conversation_id=conversation.id)

        except Exception as e:
            logger.error("contract_analysis_error", error=str(e))
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


@router.get("/supported-formats")
def get_supported_formats():
    """Get list of supported file formats."""
    return {
        "formats": list(SUPPORTED_EXTENSIONS.keys()),
        "max_size_mb": 20,
        "description": "Hỗ trợ PDF, DOCX, và ảnh (PNG, JPG, WEBP, BMP, TIFF). File scan/ảnh sẽ được OCR tự động.",
    }
