"""Create and inspect managed upload tar files without extracting their contents."""

import argparse
import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

MAX_FILES = 10_000
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024 * 1024
MAX_ARCHIVE_BYTES = MAX_TOTAL_BYTES + MAX_FILES * 1024 + 10240
KEY_PATTERN = re.compile(r"[0-9a-f]{32}\.bin")


class ArchiveError(ValueError):
    pass


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def inspect_upload_archive(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ArchiveError("invalid_archive_file")
    size = path.stat().st_size
    if size < 1024 or size % 512 or size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("invalid_archive_size")
    with path.open("rb") as source:
        source.seek(-1024, os.SEEK_END)
        if source.read() != b"\x00" * 1024:
            raise ArchiveError("incomplete_archive")
    inventory, total = {}, 0
    try:
        with tarfile.open(path, mode="r:") as archive:
            for member in archive:
                if (
                    not member.isfile()
                    or not KEY_PATTERN.fullmatch(member.name)
                    or member.name in inventory
                    or member.size <= 0
                    or member.size > MAX_FILE_BYTES
                    or len(inventory) >= MAX_FILES
                ):
                    raise ArchiveError("unsafe_archive_member")
                total += member.size
                if total > MAX_TOTAL_BYTES:
                    raise ArchiveError("archive_content_limit")
                with archive.extractfile(member) as source:
                    inventory[member.name] = hashlib.file_digest(source, "sha256").hexdigest()
    except (tarfile.TarError, EOFError):
        raise ArchiveError("unreadable_archive") from None
    digest = hashlib.sha256(
        b"".join(name.encode() + bytes.fromhex(inventory[name]) for name in sorted(inventory))
    ).hexdigest()
    return {
        "files": len(inventory),
        "total_bytes": total,
        "inventory_sha256": digest,
        "archive_sha256": file_hash(path),
        "size_bytes": size,
    }


def create_upload_archive(root: Path, output: Path) -> dict:
    if root.is_symlink() or not root.is_dir() or output.resolve().is_relative_to(root.resolve()):
        raise ArchiveError("invalid_archive_source_or_target")
    files, total = sorted(root.iterdir()), 0
    if len(files) > MAX_FILES:
        raise ArchiveError("archive_file_limit")
    for path in files:
        if path.is_symlink() or not path.is_file() or not KEY_PATTERN.fullmatch(path.name):
            raise ArchiveError("invalid_source_entry")
        size = path.stat().st_size
        total += size
        if not 0 < size <= MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ArchiveError("source_size_limit")
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        with tarfile.open(fileobj=target, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for path in files:
                info = tarfile.TarInfo(path.name)
                info.size = path.stat().st_size
                info.mtime = int(path.stat().st_mtime)
                info.uid = info.gid = 10001
                info.mode = 0o640
                with path.open("rb") as source:
                    archive.addfile(info, source)
        target.flush()
        os.fsync(target.fileno())
    return inspect_upload_archive(output)


def restore_upload_archive(path: Path, target: Path, *, expected_archive: str) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("invalid_archive_file")
    # A private snapshot binds validation and extraction to the same bytes.
    with tempfile.TemporaryDirectory(prefix="devdocs-restore-") as directory:
        snapshot = Path(directory) / "uploads.tar"
        total = 0
        with path.open("rb") as source, snapshot.open("xb") as output:
            while block := source.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    raise ArchiveError("archive_content_limit")
                output.write(block)
        return _restore_snapshot(snapshot, target, expected_archive=expected_archive)


def _restore_snapshot(path: Path, target: Path, *, expected_archive: str) -> dict:
    info = inspect_upload_archive(path)
    if info["archive_sha256"] != expected_archive:
        raise ArchiveError("archive_hash_mismatch")
    if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
        raise ArchiveError("restore_target_not_empty")
    # No extractall: only validated flat storage keys can become new files.
    with tarfile.open(path, "r:") as archive:
        for member in archive:
            if not member.isfile() or not KEY_PATTERN.fullmatch(member.name):
                raise ArchiveError("unsafe_archive_member")
            descriptor = os.open(target / member.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
            with os.fdopen(descriptor, "wb") as output, archive.extractfile(member) as source:
                shutil.copyfileobj(source, output)
                output.flush()
                os.fsync(output.fileno())
            if file_hash(target / member.name) != file_hash_from_member(archive, member):
                raise ArchiveError("restored_file_mismatch")
    return info


def file_hash_from_member(archive, member) -> str:
    with archive.extractfile(member) as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Managed upload archive creation and validation")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--source", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--archive", required=True, type=Path)
    inspect.add_argument("--expected-inventory")
    restore = commands.add_parser("restore")
    restore.add_argument("--archive", required=True, type=Path)
    restore.add_argument("--target", required=True, type=Path)
    restore.add_argument("--expected-archive", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            result = create_upload_archive(args.source, args.output)
        elif args.command == "restore":
            result = restore_upload_archive(
                args.archive, args.target, expected_archive=args.expected_archive
            )
        else:
            expected = args.expected_inventory
            if expected and not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
                raise ArchiveError("invalid_expected_inventory")
            result = inspect_upload_archive(args.archive)
            if expected:
                result["matches_expected"] = result["inventory_sha256"] == expected.lower()
                if not result["matches_expected"]:
                    print(json.dumps(result))
                    return 1
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, tarfile.TarError):
        print(json.dumps({"check": "failed", "reason": "archive_invalid_or_unavailable"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
