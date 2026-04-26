"""FastAPI main application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import get_settings
from src.core.database import init_db
from src.api.auth import router as auth_router
from src.api.chat import router as chat_router

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Chatbot tư vấn Luật Lao Động Việt Nam sử dụng RAG + Gemini AI",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(chat_router)


@app.on_event("startup")
def on_startup():
    """Initialize database tables on startup."""
    init_db()


@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    from src.embeddings.vector_store import get_collection_info

    return {
        "status": "healthy",
        "app": settings.app_name,
        "vector_store": get_collection_info(),
    }
