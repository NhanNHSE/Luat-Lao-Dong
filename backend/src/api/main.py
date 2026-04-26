"""FastAPI main application with rate limiting, logging, and caching."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.core.config import get_settings
from src.core.database import init_db
from src.core.logging import setup_logging, get_logger
from src.api.auth import router as auth_router
from src.api.chat import router as chat_router
from src.api.contract import router as contract_router

settings = get_settings()

# Setup structured logging
setup_logging(debug=settings.debug)
logger = get_logger("main")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title=settings.app_name,
    description="Chatbot tư vấn Luật Lao Động Việt Nam sử dụng RAG + Gemini AI",
    version="1.0.0",
)

# Attach limiter to app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
app.include_router(contract_router)


@app.on_event("startup")
def on_startup():
    """Initialize database tables on startup."""
    logger.info("app_startup", app_name=settings.app_name)
    init_db()
    logger.info("database_initialized")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client=request.client.host if request.client else "unknown",
    )
    response = await call_next(request)
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
    )
    return response


@app.get("/api/health")
def health_check():
    """Health check endpoint with cache stats."""
    from src.embeddings.vector_store import get_collection_info
    from src.core.cache import get_cache_stats

    return {
        "status": "healthy",
        "app": settings.app_name,
        "vector_store": get_collection_info(),
        "cache": get_cache_stats(),
    }
