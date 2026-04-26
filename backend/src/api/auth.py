"""Authentication endpoints: register, login with rate limiting and logging."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.core.security import hash_password, verify_password, create_access_token
from src.core.logging import get_logger
from src.database.models import User
from src.api.schemas import UserRegister, UserLogin, TokenResponse, UserResponse

logger = get_logger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(request: Request, data: UserRegister, db: Session = Depends(get_db)):
    """Register a new user account. Rate limited to 5/minute."""
    logger.info("register_attempt", username=data.username)

    # Check if username or email already exists
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="Tên đăng nhập đã tồn tại")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email đã được sử dụng")

    # Create user
    user = User(
        username=data.username,
        email=data.email,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate token
    token = create_access_token({"sub": user.id, "username": user.username})
    logger.info("register_success", user_id=user.id, username=user.username)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, data: UserLogin, db: Session = Depends(get_db)):
    """Login with username and password. Rate limited to 10/minute."""
    logger.info("login_attempt", username=data.username)

    user = db.query(User).filter(User.username == data.username).first()
    if not user or not verify_password(data.password, user.hashed_password):
        logger.warning("login_failed", username=data.username)
        raise HTTPException(status_code=401, detail="Tên đăng nhập hoặc mật khẩu không đúng")

    token = create_access_token({"sub": user.id, "username": user.username})
    logger.info("login_success", user_id=user.id, username=user.username)

    return TokenResponse(
        access_token=token,
        user=UserResponse.model_validate(user),
    )
