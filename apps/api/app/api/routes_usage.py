from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.deps import CurrentUser, Database
from app.schemas.usage import Operation, UsageEventList, UsageStatus, UsageSummary
from app.services.usage_service import (
    expire_usage_events,
    get_usage_summary,
    list_usage_events,
    utc_now,
)

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("/summary", response_model=UsageSummary)
def summary(request: Request, user: CurrentUser, db: Database):
    return get_usage_summary(db, user.id, request.app.state.settings)


@router.get("/events", response_model=UsageEventList)
def events(
    request: Request,
    user: CurrentUser,
    db: Database,
    operation: Operation | None = None,
    status: UsageStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    expire_usage_events(db, user.id, utc_now(), request.app.state.settings)
    db.commit()
    return list_usage_events(
        db, user.id, operation=operation, status=status, limit=limit, offset=offset
    )
