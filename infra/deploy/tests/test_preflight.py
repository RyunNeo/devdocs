import hashlib

from infra.deploy.preflight import inspect_uploads


def document(key, body):
    return {"storage_key": key, "content_hash": hashlib.sha256(body).hexdigest()}


def test_matching_documents_and_files_are_consistent(tmp_path):
    key = "a" * 32 + ".bin"
    body = b"rehearsal fixture"
    (tmp_path / key).write_bytes(body)
    result = inspect_uploads(tmp_path, [document(key, body)])
    assert result["consistent"] is True
    assert result["documents"] == result["stored_files"] == 1
    assert len(result["inventory_sha256"]) == 64
    assert key not in str(result)


def test_missing_and_corrupted_files_are_reported(tmp_path):
    good_key, missing_key = (c * 32 + ".bin" for c in "ab")
    (tmp_path / good_key).write_bytes(b"changed")
    result = inspect_uploads(
        tmp_path, [document(good_key, b"expected"), document(missing_key, b"missing")]
    )
    assert result["consistent"] is False
    assert result["hash_mismatches"] == result["missing_files"] == 1


def test_outside_paths_and_orphans_are_not_silently_accepted(tmp_path):
    orphan = "a" * 32 + ".bin"
    (tmp_path / orphan).write_bytes(b"orphan")
    result = inspect_uploads(tmp_path, [document("../outside.bin", b"invalid")])
    assert result["consistent"] is False
    assert result["invalid_keys"] == result["orphan_files"] == 1


def test_empty_dataset_is_distinguished_from_inconsistency(tmp_path):
    result = inspect_uploads(tmp_path, [])
    assert result["consistent"] is True
    assert result["documents"] == result["stored_files"] == 0


def test_missing_root_is_not_a_valid_empty_volume(tmp_path):
    assert inspect_uploads(tmp_path / "missing", [])["consistent"] is False
