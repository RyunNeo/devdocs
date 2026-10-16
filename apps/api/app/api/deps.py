from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.services.auth_service import resolve_user

Database = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: Database) -> User:
    return resolve_user(db, request.cookies.get(request.app.state.settings.cookie_name))


CurrentUser = Annotated[User, Depends(get_current_user)]
