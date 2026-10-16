import hashlib
import importlib
import io
import tarfile

import pytest

from infra.deploy.archive import ArchiveError, create_upload_archive, inspect_upload_archive


def test_replacing_original_archive_after_validation_cannot_change_restored_content(
    tmp_path, monkeypatch
):
    module = importlib.import_module("infra.deploy.archive")
    root = tmp_path / "source"
    root.mkdir()
    key = "a" * 32 + ".bin"
    (root / key).write_bytes(b"approved content")
    original = tmp_path / "original.tar"
    approved = create_upload_archive(root, original)
    (root / key).write_bytes(b"replaced content")
    replacement = tmp_path / "replacement.tar"
    create_upload_archive(root, replacement)
    target = tmp_path / "target"
    target.mkdir()
    inspect = module.inspect_upload_archive

    def replace_after_inspection(path):
        result = inspect(path)
        original.write_bytes(replacement.read_bytes())
        return result

    monkeypatch.setattr(module, "inspect_upload_archive", replace_after_inspection)
    module.restore_upload_archive(original, target, expected_archive=approved["archive_sha256"])
    assert (target / key).read_bytes() == b"approved content"


def test_restore_validates_before_writing_and_refuses_existing_data(tmp_path):
    module = importlib.import_module("infra.deploy.archive")
    restore = getattr(module, "restore_upload_archive", None)
    assert callable(restore), "safe upload restoration is not implemented"
    root = tmp_path / "source"
    root.mkdir()
    key = "a" * 32 + ".bin"
    (root / key).write_bytes(b"restore fixture")
    archive = tmp_path / "uploads.tar"
    info = create_upload_archive(root, archive)
    target = tmp_path / "target"
    target.mkdir()
    with pytest.raises(ValueError):
        restore(archive, target, expected_archive="0" * 64)
    assert not list(target.iterdir())
    result = restore(archive, target, expected_archive=info["archive_sha256"])
    assert result == info
    assert (target / key).read_bytes() == b"restore fixture"
    with pytest.raises(ValueError):
        restore(archive, target, expected_archive=info["archive_sha256"])


def test_archive_roundtrip_matches_preflight_inventory(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    key, body = "a" * 32 + ".bin", b"fixture bytes"
    (root / key).write_bytes(body)
    archive = tmp_path / "uploads.tar"
    result = create_upload_archive(root, archive)
    expected = hashlib.sha256(key.encode() + hashlib.sha256(body).digest()).hexdigest()
    assert result["files"] == 1 and result["inventory_sha256"] == expected
    assert result == inspect_upload_archive(archive)
    assert key not in str(result) and "fixture bytes" not in str(result)
    before = archive.read_bytes()
    with pytest.raises(FileExistsError):
        create_upload_archive(root, archive)
    assert archive.read_bytes() == before


@pytest.mark.parametrize("name", ["../outside", "/absolute", "C:/file", "bad\\file", "note.part"])
def test_reject_unsafe_archive_names(tmp_path, name):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as target:
        item = tarfile.TarInfo(name)
        item.size = 1
        target.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(ArchiveError):
        inspect_upload_archive(archive)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE])
def test_reject_links_and_directories(tmp_path, kind):
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as target:
        item = tarfile.TarInfo("a" * 32 + ".bin")
        item.type = kind
        item.linkname = "outside"
        target.addfile(item)
    with pytest.raises(ArchiveError):
        inspect_upload_archive(archive)


def test_reject_duplicate_members(tmp_path):
    archive = tmp_path / "duplicate.tar"
    with tarfile.open(archive, "w") as target:
        for _ in range(2):
            item = tarfile.TarInfo("a" * 32 + ".bin")
            item.size = 1
            target.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(ArchiveError):
        inspect_upload_archive(archive)


def test_invalid_source_is_not_archived(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / "leftover.part").write_bytes(b"unfinished")
    archive = tmp_path / "uploads.tar"
    with pytest.raises(ArchiveError):
        create_upload_archive(root, archive)
    assert not archive.exists()


def test_truncated_archive_is_rejected(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (root / ("a" * 32 + ".bin")).write_bytes(b"data" * 1024)
    archive = tmp_path / "uploads.tar"
    create_upload_archive(root, archive)
    archive.write_bytes(archive.read_bytes()[:600])
    with pytest.raises(ArchiveError):
        inspect_upload_archive(archive)


def test_empty_source_is_supported_but_missing_root_is_not(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    assert create_upload_archive(root, tmp_path / "empty.tar")["files"] == 0
    with pytest.raises(ArchiveError):
        create_upload_archive(tmp_path / "missing", tmp_path / "missing.tar")
