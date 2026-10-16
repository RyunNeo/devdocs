"""Validate paired local artifacts and publish a no-clobber backup manifest.

The caller must first stop writers and verify pg_restore --list against the
source dump. This module never connects to Docker or reads environment files.
"""

import argparse
import json
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from infra.deploy.archive import file_hash, inspect_upload_archive

TABLES = {
    "users",
    "auth_sessions",
    "knowledge_bases",
    "documents",
    "storage_cleanup_tasks",
    "document_chunks",
    "conversations",
    "messages",
    "usage_events",
    "daily_usage_counters",
}
REVISION = "0007_usage_events_counters"
METADATA_KEYS = {
    "postgres_version",
    "pgvector_version",
    "alembic_revision",
    "table_counts",
    "images",
}


def validate_metadata(metadata: dict) -> None:
    if set(metadata) != METADATA_KEYS:
        raise ValueError("invalid_metadata_fields")
    if not re.fullmatch(r"16(?:\.[0-9]+)?(?: .*)?", metadata["postgres_version"]):
        raise ValueError("unsupported_postgres")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", metadata["pgvector_version"]):
        raise ValueError("invalid_vector_version")
    if metadata["alembic_revision"] != REVISION:
        raise ValueError("revision_mismatch")
    counts = metadata["table_counts"]
    if set(counts) != TABLES or any(type(v) is not int or v < 0 for v in counts.values()):
        raise ValueError("invalid_table_counts")
    images = metadata["images"]
    if set(images) != {"postgres", "api", "web"} or any(
        not re.fullmatch(r"sha256:[0-9a-f]{64}", image) for image in images.values()
    ):
        raise ValueError("invalid_images")


def artifact_info(root: Path) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid_backup_directory")
    result = {}
    for name in ("database.dump", "uploads.tar"):
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("invalid_artifact")
        result[name] = {"size_bytes": path.stat().st_size, "sha256": file_hash(path)}
    with (root / "database.dump").open("rb") as source:
        if source.read(5) != b"PGDMP" or result["database.dump"]["size_bytes"] <= 5:
            raise ValueError("invalid_dump_format")
    return result


def write_json_once(path: Path, value: dict) -> None:
    """Publish complete JSON atomically; an existing destination is never replaced."""
    descriptor, name = tempfile.mkstemp(prefix=".manifest-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            json.dump(value, target, indent=2, ensure_ascii=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def finalize_backup(
    root: Path, metadata: dict, *, expected_dump: str, expected_inventory: str
) -> dict:
    if (root / "manifest.json").exists():
        raise FileExistsError("manifest_exists")
    validate_metadata(metadata)
    artifacts = artifact_info(root)
    uploads = inspect_upload_archive(root / "uploads.tar")
    if (
        artifacts["database.dump"]["sha256"] != expected_dump.lower()
        or uploads["inventory_sha256"] != expected_inventory.lower()
        or uploads["files"] != metadata["table_counts"]["documents"]
    ):
        raise ValueError("artifact_mismatch")
    manifest = {
        "format_version": 1,
        "complete": True,
        "restore_verified": False,
        "source_project": "devdocs-rehearsal",
        "created_at": datetime.now(UTC).isoformat(),
        "postgres_major": 16,
        **metadata,
        "upload_inventory": uploads,
        "artifacts": artifacts,
    }
    write_json_once(root / "manifest.json", manifest)
    return manifest


def validate_backup(root: Path) -> dict:
    path = root / "manifest.json"
    if path.is_symlink():
        raise ValueError("invalid_manifest_file")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("format_version") != 1
        or manifest.get("complete") is not True
        or manifest.get("source_project") != "devdocs-rehearsal"
        or manifest.get("postgres_major") != 16
    ):
        raise ValueError("incomplete_or_unsupported_backup")
    validate_metadata({key: manifest[key] for key in METADATA_KEYS})
    if (
        artifact_info(root) != manifest["artifacts"]
        or inspect_upload_archive(root / "uploads.tar") != manifest["upload_inventory"]
        or manifest["upload_inventory"]["files"] != manifest["table_counts"]["documents"]
    ):
        raise ValueError("artifact_mismatch")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate paired backup files; no Docker operations"
    )
    parser.add_argument("command", choices=["finalize", "validate"])
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--expected-dump")
    parser.add_argument("--expected-inventory")
    args = parser.parse_args(argv)
    try:
        if args.command == "finalize":
            if not (args.metadata and args.expected_dump and args.expected_inventory):
                raise ValueError("missing_finalization_inputs")
            finalize_backup(
                args.directory,
                json.loads(args.metadata.read_text(encoding="utf-8-sig")),
                expected_dump=args.expected_dump,
                expected_inventory=args.expected_inventory,
            )
        result = validate_backup(args.directory)
        print(
            json.dumps(
                {
                    "complete": result["complete"],
                    "files": result["upload_inventory"]["files"],
                    "restore_verified": result["restore_verified"],
                }
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"status": "failed", "reason": "invalid_or_existing_backup"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
