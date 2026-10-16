import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import dummy_hash, hash_password, hash_token, verify_password
from app.models.session import AuthSession
from app.models.user import User
from app.schemas.auth import Credentials, Registration


def create_session(db: Session, user: User, settings: Settings) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.session_days),
        )
    )
    return token


def register_user(db: Session, data: Registration, settings: Settings) -> tuple[User, str]:
    user = User(email=str(data.email), password_hash=hash_password(data.password))
    db.add(user)
    try:
        db.flush()
        token = create_session(db, user, settings)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "该邮箱已注册，请直接登录") from None
    return user, token


def login_user(db: Session, data: Credentials, settings: Settings) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == str(data.email)))
    valid = verify_password(data.password, user.password_hash if user else dummy_hash)
    if user is None or not valid:
        raise HTTPException(401, "邮箱或密码错误")
    token = create_session(db, user, settings)
    db.commit()
    return user, token


def resolve_user(db: Session, token: str | None) -> User:
    if not token or len(token) > 128:
        raise HTTPException(401, "请先登录")
    session = db.get(AuthSession, hash_token(token))
    if session is None:
        raise HTTPException(401, "登录已失效，请重新登录")
    expiry = session.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        raise HTTPException(401, "登录已失效，请重新登录")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "登录已失效，请重新登录")
    return user


def revoke_session(db: Session, token: str | None) -> None:
    if token and len(token) <= 128:
        db.execute(delete(AuthSession).where(AuthSession.token_hash == hash_token(token)))
        db.commit()
