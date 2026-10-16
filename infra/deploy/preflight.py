"""Read-only upload consistency check; stream into the API container with python -."""

import hashlib
import json
import re
from pathlib import Path


def inspect_uploads(root: Path, documents: list[dict]) -> dict:
    available = root.is_dir() and not root.is_symlink()
    result = {
        "documents": len(documents),
        "directory_available": available,
        "stored_files": 0,
        "missing_files": 0,
        "hash_mismatches": 0,
        "invalid_keys": 0,
        "unreadable_files": 0,
        "orphan_files": 0,
        "inventory_sha256": None,
    }
    expected, actual = {}, {}
    for row in documents:
        key, digest = row.get("storage_key"), row.get("content_hash")
        if (
            not isinstance(key, str)
            or not re.fullmatch(r"[0-9a-f]{32}\.bin", key)
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or key in expected
        ):
            result["invalid_keys"] += 1
            continue
        expected[key] = digest
    candidates = sorted(root.glob("*.bin")) if available else []
    for path in candidates:
        if (
            path.is_symlink()
            or not path.is_file()
            or not re.fullmatch(r"[0-9a-f]{32}\.bin", path.name)
        ):
            result["invalid_keys"] += 1
            continue
        result["stored_files"] += 1
        try:
            with path.open("rb") as file:
                actual[path.name] = hashlib.file_digest(file, "sha256").hexdigest()
        except OSError:
            result["unreadable_files"] += 1
    result["missing_files"] = len(expected.keys() - actual.keys())
    result["hash_mismatches"] = sum(
        expected[key] != actual[key] for key in expected.keys() & actual.keys()
    )
    result["orphan_files"] = len(actual.keys() - expected.keys())
    result["inventory_sha256"] = hashlib.sha256(
        b"".join(name.encode() + bytes.fromhex(actual[name]) for name in sorted(actual))
    ).hexdigest()
    result["consistent"] = available and not any(
        result[key]
        for key in (
            "missing_files",
            "hash_mismatches",
            "invalid_keys",
            "unreadable_files",
            "orphan_files",
        )
    )
    return result


def main() -> int:
    engine = None
    try:
        from app.core.config import Settings
        from app.db.session import make_database
        from sqlalchemy import text

        settings = Settings()
        engine, _ = make_database(settings)
        with engine.connect() as connection:
            rows = [
                dict(row)
                for row in connection.execute(
                    text("SELECT storage_key, content_hash FROM documents")
                ).mappings()
            ]
        result = inspect_uploads(settings.upload_dir, rows)
        result["fixture_ready"] = result["consistent"] and result["documents"] > 0
        print(json.dumps(result))
        return 0 if result["fixture_ready"] else 1
    except Exception:
        print(json.dumps({"check": "failed", "reason": "database_or_storage_unavailable"}))
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
