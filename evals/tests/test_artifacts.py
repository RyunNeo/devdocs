import json

import pytest


def test_safe_artifacts(tmp_path):
    from evals.toolkit.artifacts import append_result, create_run_dir, write_manifest

    for name in ("../escape", "a/b", "CON", "bad.", ""):
        with pytest.raises(ValueError):
            create_run_dir(tmp_path, name)
    directory = create_run_dir(tmp_path, "trial-1")
    with pytest.raises(ValueError):
        create_run_dir(tmp_path, "trial-1")
    write_manifest(directory, {"run_id": "trial-1", "phase": "prepared"})
    append_result(directory, {"case_id": "fact-01", "answer": "中文"})
    assert json.loads((directory / "results.jsonl").read_text(encoding="utf-8"))["answer"] == "中文"
    with pytest.raises(ValueError):
        append_result(directory, {"password": "sentinel"})


def test_atomic_manifest(tmp_path):
    from evals.toolkit.artifacts import read_json, write_manifest

    write_manifest(tmp_path, {"phase": "starting"})
    write_manifest(tmp_path, {"phase": "prepared"})
    assert read_json(tmp_path / "manifest.json")["phase"] == "prepared"


@pytest.mark.parametrize("tail", [b'{"case_id": "broken', b'{"answer":"\xe4'])
def test_crash_tail_preserved_and_reconciliation_appendable(tmp_path, tail):
    from evals.toolkit.artifacts import append_result, load_results

    append_result(tmp_path, {"case_id": "fact-01", "status": "unknown"})
    path = tmp_path / "results.jsonl"
    with path.open("ab") as file:
        file.write(tail)
    original = path.read_bytes()
    assert load_results(tmp_path)[0]["status"] == "unknown"
    append_result(tmp_path, {"case_id": "fact-01", "status": "completed"})
    assert load_results(tmp_path)[0]["status"] == "completed"
    assert path.read_bytes() == original
