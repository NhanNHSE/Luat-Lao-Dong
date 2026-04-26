"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, EmailStr, Field


# --- Auth Schemas ---
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# --- Chat Schemas ---
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: Optional[str] = None


class SourceInfo(BaseModel):
    article: str
    law_name: str
    content_preview: str


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    sources: List[SourceInfo] = []


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    sources: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    messages: List[MessageResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}
