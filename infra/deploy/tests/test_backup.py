import copy
import importlib
import json

import pytest

from infra.deploy.archive import create_upload_archive, file_hash


def fixture_backup(tmp_path):
    root = tmp_path / "backup-001"
    root.mkdir()
    (root / "database.dump").write_bytes(b"PGDMP\x00test-only-dump")
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / ("a" * 32 + ".bin")).write_bytes(b"fixture")
    inventory = create_upload_archive(uploads, root / "uploads.tar")
    metadata = {
        "postgres_version": "16.15",
        "pgvector_version": "0.8.7",
        "alembic_revision": "0007_usage_events_counters",
        "table_counts": {
            name: 0
            for name in (
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
            )
        },
        "images": {name: "sha256:" + "a" * 64 for name in ("postgres", "api", "web")},
    }
    metadata["table_counts"]["documents"] = 1
    return root, metadata, inventory


def test_finalize_and_revalidate_without_overwriting(tmp_path):
    module = importlib.import_module("infra.deploy.backup")
    root, metadata, inventory = fixture_backup(tmp_path)
    manifest = module.finalize_backup(
        root,
        metadata,
        expected_dump=file_hash(root / "database.dump"),
        expected_inventory=inventory["inventory_sha256"],
    )
    assert manifest["complete"] is True
    assert manifest["restore_verified"] is False
    assert module.validate_backup(root) == manifest
    before = (root / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        module.finalize_backup(
            root,
            metadata,
            expected_dump=file_hash(root / "database.dump"),
            expected_inventory=inventory["inventory_sha256"],
        )
    assert (root / "manifest.json").read_bytes() == before
    (root / "database.dump").write_bytes(b"PGDMPtampered")
    with pytest.raises(ValueError):
        module.validate_backup(root)


@pytest.mark.parametrize("fault", ["hash", "count", "revision", "image", "secret", "negative"])
def test_invalid_backups_have_no_complete_manifest(tmp_path, fault):
    module = importlib.import_module("infra.deploy.backup")
    root, metadata, inventory = fixture_backup(tmp_path)
    expected = file_hash(root / "database.dump")
    if fault == "hash":
        expected = "0" * 64
    elif fault == "count":
        metadata["table_counts"]["documents"] = 2
    elif fault == "revision":
        metadata["alembic_revision"] = "unknown"
    elif fault == "image":
        metadata["images"]["api"] = "floating:tag"
    elif fault == "secret":
        metadata["password"] = "never-serialize-this"
    else:
        metadata["table_counts"]["users"] = -1
    with pytest.raises(ValueError):
        module.finalize_backup(
            root, metadata, expected_dump=expected, expected_inventory=inventory["inventory_sha256"]
        )
    assert not (root / "manifest.json").exists()


def test_validate_rejects_incomplete_or_altered_manifest(tmp_path):
    module = importlib.import_module("infra.deploy.backup")
    root, metadata, inventory = fixture_backup(tmp_path)
    original = module.finalize_backup(
        root,
        metadata,
        expected_dump=file_hash(root / "database.dump"),
        expected_inventory=inventory["inventory_sha256"],
    )
    for change in ({"complete": False}, {"format_version": 2}, {"source_project": "development"}):
        invalid = copy.deepcopy(original)
        invalid.update(change)
        (root / "manifest.json").write_text(json.dumps(invalid))
        with pytest.raises(ValueError):
            module.validate_backup(root)
