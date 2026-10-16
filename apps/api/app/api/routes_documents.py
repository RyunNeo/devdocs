from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, Request, Response, UploadFile

from app.api.deps import CurrentUser, Database
from app.schemas.document import DocumentDetail, DocumentList, DocumentRead
from app.services import document_service as service
from app.services import indexing_service

router = APIRouter(tags=["documents"])


@router.post("/knowledge-bases/{kb_id}/documents", response_model=DocumentRead, status_code=201)
def upload(
    kb_id: UUID,
    request: Request,
    user: CurrentUser,
    db: Database,
    file: Annotated[UploadFile, File()],
):
    try:
        return service.upload_document(db, request.app.state.settings, user.id, kb_id, file)
    finally:
        file.file.close()


@router.get("/knowledge-bases/{kb_id}/documents", response_model=DocumentList)
def list_all(
    kb_id: UUID,
    user: CurrentUser,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list_documents(db, user.id, kb_id, limit, offset)


@router.get("/documents/summary")
def summary(user: CurrentUser, db: Database):
    return service.summary(db, user.id)


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def detail(doc_id: UUID, user: CurrentUser, db: Database):
    return service.detail(db, user.id, doc_id)


@router.post("/documents/{doc_id}/retry", response_model=DocumentRead)
def retry(doc_id: UUID, request: Request, user: CurrentUser, db: Database):
    return service.process_document(db, request.app.state.settings, user.id, doc_id)


@router.delete("/documents/{doc_id}", status_code=204)
def delete(doc_id: UUID, request: Request, user: CurrentUser, db: Database):
    service.delete_document(db, request.app.state.settings, user.id, doc_id)
    return Response(status_code=204)


@router.post("/documents/{doc_id}/index", response_model=DocumentRead)
def index(doc_id: UUID, request: Request, user: CurrentUser, db: Database):
    return indexing_service.index_document(
        db, request.app.state.settings, user.id, doc_id, getattr(request.state, "request_id", None)
    )


@router.get("/documents/{doc_id}/chunks")
def chunks(
    doc_id: UUID,
    user: CurrentUser,
    db: Database,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return indexing_service.list_chunks(db, user.id, doc_id, limit, offset)
