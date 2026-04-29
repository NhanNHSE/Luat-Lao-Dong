"""Core configuration using pydantic-settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Chatbot Luật Lao Động"
    debug: bool = True

    # Gemini
    gemini_api_key: str = ""

    # PostgreSQL
    database_url: str = "postgresql://lawbot:lawbot_secret_2026@postgres:5432/lawbot_db"

    # Qdrant
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection: str = "labor_law"

    # JWT
    jwt_secret_key: str = "your-super-secret-jwt-key-change-this"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 1440  # 24 hours

    # RAG
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    llm_model: str = "gemini-2.5-flash"
    llm_fallback_model: str = "gemini-2.5-flash-lite"
    retrieval_top_k: int = 15        # Over-fetch from Qdrant
    rerank_top_k: int = 5            # Keep after rerank
    chunk_size: int = 3000
    chunk_overlap: int = 200

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
