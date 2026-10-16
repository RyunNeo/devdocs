import json
import os
import re
import tempfile
from pathlib import Path

RESULT_FIELDS = {
    "case_id",
    "status",
    "conversation_id",
    "request_id",
    "assistant_message_id",
    "answer",
    "citations",
    "usage",
    "elapsed_ms",
    "error_code",
    "model",
    "stream_verified",
    "attempted",
}
MANIFEST_FIELDS = {
    "schema_version",
    "run_id",
    "phase",
    "owner_id",
    "base_url",
    "dataset_version",
    "dataset_sha256",
    "documents",
    "kb_id",
    "started_at",
    "models",
    "dataset",
    "case_ids",
    "preparation_run_id",
    "error_code",
    "error_status",
}


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON 应为对象")
    return data


def create_run_dir(root: Path, run_id: str) -> Path:
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
    }
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", run_id) or run_id.upper() in reserved:
        raise ValueError("运行编号仅允许 1–48 位字母、数字、下划线和连字符，不能是系统保留名")
    root.mkdir(parents=True, exist_ok=True)
    directory = root / run_id
    try:
        directory.mkdir()
    except FileExistsError:
        raise ValueError("运行目录已存在，请使用新编号") from None
    return directory


def write_manifest(directory: Path, manifest: dict) -> None:
    if set(manifest) - MANIFEST_FIELDS:
        raise ValueError("清单含不允许字段")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, suffix=".tmp", delete=False
        ) as file:
            temporary = Path(file.name)
            json.dump(manifest, file, ensure_ascii=False, allow_nan=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, directory / "manifest.json")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def append_result(directory: Path, record: dict) -> None:
    if set(record) - RESULT_FIELDS:
        raise ValueError("结果含不允许字段")
    line = json.dumps(record, ensure_ascii=False, allow_nan=False)
    journals = journal_paths(directory)
    path = journals[-1] if journals else directory / "results.jsonl"
    separator = ""
    if path.exists():
        content = path.read_bytes()
        if content and not content.endswith(b"\n"):
            try:
                json.loads(content.split(b"\n")[-1].decode("utf-8"))
                separator = "\n"
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Preserve a torn append and continue in a new numbered journal.
                path = directory / f"results.{len(journals):04d}.jsonl"
    with path.open("a", encoding="utf-8") as file:
        file.write(separator)
        file.write(line + "\n")
        file.flush()
        os.fsync(file.fileno())


def journal_paths(directory: Path) -> list[Path]:
    base = directory / "results.jsonl"
    return ([base] if base.exists() else []) + sorted(
        directory.glob("results.[0-9][0-9][0-9][0-9].jsonl")
    )


def load_results(directory: Path) -> list[dict]:
    latest = {}
    for path in journal_paths(directory):
        lines = path.read_bytes().split(b"\n")
        if lines and not lines[-1]:
            lines.pop()
        for index, line in enumerate(lines):
            try:
                record = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                if index == len(lines) - 1:
                    break
                raise ValueError("结果文件中间存在损坏记录") from None
            if not isinstance(record, dict) or "case_id" not in record:
                raise ValueError("结果记录无题号")
            latest[record["case_id"]] = record
    return list(latest.values())
