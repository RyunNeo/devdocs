from fastapi import APIRouter, Request, Response

from app.api.deps import CurrentUser, Database
from app.schemas.auth import AuthResponse, Credentials, Registration, UserRead
from app.services.auth_service import login_user, register_user, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])


def set_session_cookie(request: Request, response: Response, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(data: Registration, request: Request, response: Response, db: Database):
    user, token = register_user(db, data, request.app.state.settings)
    set_session_cookie(request, response, token)
    return {"user": user}


@router.post("/login", response_model=AuthResponse)
def login(data: Credentials, request: Request, response: Response, db: Database):
    user, token = login_user(db, data, request.app.state.settings)
    set_session_cookie(request, response, token)
    return {"user": user}


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser):
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, db: Database):
    settings = request.app.state.settings
    revoke_session(db, request.cookies.get(settings.cookie_name))
    response = Response(status_code=204)
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return response
