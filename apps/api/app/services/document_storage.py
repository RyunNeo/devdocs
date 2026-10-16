import hashlib
import logging
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import safe_log
from app.models.document import StorageCleanupTask

logger = logging.getLogger(__name__)


def file_path(settings: Settings, key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}\.bin", key):
        raise ValueError("Invalid private storage key")
    root = settings.upload_dir.resolve()
    path = (root / key).resolve()
    if path.parent != root:
        raise ValueError("Storage path escapes configured directory")
    return path


def store_file(settings: Settings, upload: UploadFile) -> tuple[str, int, str]:
    key = f"{uuid.uuid4().hex}.bin"
    path = file_path(settings, key)
    temporary = path.with_suffix(".part")
    size = 0
    digest = hashlib.sha256()
    try:
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as target:
            while chunk := upload.file.read(64 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, "单个文件不能超过 10 MiB")
                digest.update(chunk)
                target.write(chunk)
        if size == 0:
            raise HTTPException(400, "文件为空，请选择有内容的文件")
        temporary.replace(path)
    except OSError:
        safe_log(logger, "storage_failed")
        raise HTTPException(503, "文件存储暂不可用，请检查存储目录权限和磁盘空间") from None
    finally:
        temporary.unlink(missing_ok=True)
    return key, size, digest.hexdigest()


def remove_file(settings: Settings, key: str) -> None:
    file_path(settings, key).unlink(missing_ok=True)


def drain_cleanup(db: Session, settings: Settings, keys: list[str] | None = None) -> int:
    query = select(StorageCleanupTask).order_by(StorageCleanupTask.created_at).limit(1000)
    if keys is not None:
        if not keys:
            return 0
        query = query.where(StorageCleanupTask.storage_key.in_(keys))
    tasks = db.scalars(query).all()
    removed = 0
    for task in tasks:
        try:
            remove_file(settings, task.storage_key)
        except (OSError, ValueError):
            safe_log(logger, "cleanup_deferred")
            continue
        db.delete(task)
        db.commit()
        removed += 1
    return removed
