from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from evals.toolkit.artifacts import (
    append_result,
    create_run_dir,
    load_results,
    read_json,
    write_manifest,
)
from evals.toolkit.client import EvaluationError
from evals.toolkit.dataset import Dataset, select_cases


def check_quota(client, operation: str, needed: int):
    try:
        remaining = client.summary()["quota"][operation]["remaining"]
    except (KeyError, TypeError):
        raise EvaluationError("invalid_quota_response") from None
    if type(remaining) is not int or remaining < needed:
        raise EvaluationError("insufficient_quota")


def new_manifest(client, dataset, run_id, owner_id):
    return {
        "schema_version": 1,
        "run_id": run_id,
        "phase": "preparing",
        "owner_id": owner_id,
        "base_url": client.base_url,
        "dataset_version": dataset.version,
        "dataset_sha256": dataset.dataset_sha256,
        "dataset": dataset.model_dump(mode="json", exclude={"fixtures_root"}),
        "documents": [],
        "kb_id": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "models": {"chat": None, "embedding": None},
    }


def prepare(client, dataset: Dataset, output_root: Path, run_id: str) -> Path:
    owner = client.me()["id"]
    check_quota(client, "index", len(dataset.documents))
    directory = create_run_dir(output_root, run_id)
    manifest = new_manifest(client, dataset, run_id, owner)
    write_manifest(directory, manifest)
    try:
        manifest["kb_id"] = client.create_kb(f"评测-CedarDesk-{run_id}")["id"]
        write_manifest(directory, manifest)
        for name in dataset.documents:
            doc = client.upload(manifest["kb_id"], dataset.fixtures_root / name)
            entry = {"filename": name, "sha256": dataset.document_hashes[name], "id": doc["id"]}
            manifest["documents"].append(entry)
            write_manifest(directory, manifest)
            if doc.get("status") != "parsed":
                raise EvaluationError("parse_failed")
            indexed = client.index(doc["id"])
            if indexed.get("index_status") != "completed":
                raise EvaluationError("index_failed")
            entry["updated_at"] = indexed.get("updated_at")
            write_manifest(directory, manifest)
        manifest["phase"] = "prepared"
        write_manifest(directory, manifest)
    except (EvaluationError, KeyboardInterrupt) as exc:
        manifest["phase"] = "prepare_failed"
        manifest["error_code"] = exc.code if isinstance(exc, EvaluationError) else "interrupted"
        if isinstance(exc, EvaluationError):
            manifest["error_status"] = exc.status
        write_manifest(directory, manifest)
        raise
    return directory / "manifest.json"


def verify_manifest(client, dataset, manifest):
    if manifest.get("phase") in {"preparing", "prepare_failed"}:
        raise EvaluationError("preparation_incomplete")
    if (
        manifest.get("schema_version") != 1
        or manifest.get("phase") not in {"prepared", "run"}
        or manifest.get("owner_id") != client.me().get("id")
        or manifest.get("base_url") != client.base_url
        or manifest.get("dataset_sha256") != dataset.dataset_sha256
        or manifest.get("dataset_version") != dataset.version
        or manifest.get("dataset") != dataset.model_dump(mode="json", exclude={"fixtures_root"})
    ):
        raise EvaluationError("manifest_mismatch")
    entries = manifest.get("documents", [])
    if (
        len(entries) != len(dataset.documents)
        or {e["filename"]: e["sha256"] for e in entries} != dataset.document_hashes
    ):
        raise EvaluationError("document_hash_mismatch")
    docs = client.list_documents(manifest["kb_id"])
    if len(docs) != len(entries) or {d["id"] for d in docs} != {e["id"] for e in entries}:
        raise EvaluationError("document_set_mismatch")
    for entry in entries:
        doc = next(d for d in docs if d["id"] == entry["id"])
        if (
            doc.get("filename") != entry["filename"]
            or doc.get("status") != "parsed"
            or doc.get("index_status") != "completed"
            or doc.get("knowledge_base_id") != manifest["kb_id"]
            or (entry.get("updated_at") and doc.get("updated_at") != entry["updated_at"])
        ):
            raise EvaluationError("document_state_mismatch")


def safe_usage(usage):
    if not isinstance(usage, dict):
        return None
    keys = ("prompt_tokens", "completion_tokens", "total_tokens")
    result = {k: usage[k] for k in keys if type(usage.get(k)) is int and 0 <= usage[k] <= 2**53 - 1}
    if all(k in result for k in keys) and (
        result["total_tokens"] != result["prompt_tokens"] + result["completion_tokens"]
    ):
        return None
    return result or None


def safe_citations(citations):
    keys = {
        "number",
        "document_id",
        "chunk_id",
        "chunk_index",
        "filename",
        "content",
        "source_status",
        "index_fingerprint",
    }
    if not isinstance(citations, list) or any(not isinstance(c, dict) for c in citations):
        raise EvaluationError("invalid_citations")
    return [{k: v for k, v in c.items() if k in keys} for c in citations]


def persisted_message(client, record):
    detail = client.read_conversation(record["conversation_id"])
    matches = [
        m
        for m in detail.get("messages", [])
        if m.get("role") == "assistant" and m.get("run_id") == record["request_id"]
    ]
    if len(matches) != 1:
        return None
    message = matches[0]
    if record.get("assistant_message_id") and message.get("id") != record["assistant_message_id"]:
        return None
    return message


def apply_message(record, message):
    record["assistant_message_id"] = message["id"]
    if message.get("status") == "completed" and isinstance(message.get("content"), str):
        record.update(
            status="completed",
            answer=message["content"],
            citations=safe_citations(message.get("citations", [])),
            usage=safe_usage(message.get("usage")),
            model=message.get("model"),
        )
    elif message.get("status") in {"failed", "cancelled", "interrupted"}:
        record.update(status="failed", error_code="persisted_task_failed")


def run_cases(
    client,
    dataset: Dataset,
    manifest_path: Path,
    output_root: Path,
    run_id: str,
    case_ids: list[str] | None = None,
) -> Path:
    cases = select_cases(dataset, case_ids)
    original = read_json(manifest_path)
    verify_manifest(client, dataset, original)
    check_quota(client, "chat", len(cases))
    directory = create_run_dir(output_root, run_id)
    manifest = dict(
        original,
        run_id=run_id,
        phase="run",
        case_ids=[c.id for c in cases],
        preparation_run_id=original["run_id"],
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    write_manifest(directory, manifest)
    groups, blocked = {}, set()
    stopped = False
    for case in cases:
        record = {
            "case_id": case.id,
            "status": "not_attempted",
            "attempted": False,
            "conversation_id": None,
            "request_id": str(uuid4()),
            "assistant_message_id": None,
            "answer": "",
            "citations": [],
            "usage": None,
            "elapsed_ms": None,
            "error_code": None,
            "model": None,
            "stream_verified": False,
        }
        if case.conversation_group in blocked:
            record["status"] = "blocked"
        elif not stopped:
            stream = None
            try:
                group = case.conversation_group
                cid = groups.get(group) if group else None
                if cid is None:
                    cid = client.create_conversation(manifest["kb_id"])["id"]
                    if group:
                        groups[group] = cid
                record.update(conversation_id=cid, status="unknown", attempted=True)
                # Persist request identity before the chargeable submission, even on Ctrl+C.
                append_result(directory, record)
                stream = client.stream_answer(cid, case.question, record["request_id"])
                record["assistant_message_id"] = stream.meta.get("assistant_message_id")
                message = persisted_message(client, record)
                matches = (
                    message
                    and stream.meta.get("run_id") == record["request_id"]
                    and stream.meta.get("conversation_id") == cid
                    and stream.done.get("message_id") == message.get("id")
                    and stream.done.get("status") == "completed"
                    and stream.answer == message.get("content")
                    and stream.citations == message.get("citations")
                )
                if matches:
                    apply_message(record, message)
                    record["stream_verified"] = record["status"] == "completed"
                    record["elapsed_ms"] = stream.elapsed_ms
                else:
                    record["error_code"] = "persistence_mismatch"
            except EvaluationError as exc:
                record["error_code"] = exc.code
                if record["attempted"]:
                    try:
                        message = persisted_message(client, record)
                        if message:
                            apply_message(record, message)
                    except EvaluationError:
                        pass
                if exc.status and exc.status < 500:
                    if record["status"] != "completed":
                        record["status"] = "failed"
                stopped = exc.code in {"network_error", "login_required", "quota_or_rate_limit"}
                stopped = stopped or (exc.status is not None and exc.status >= 500)
            except KeyboardInterrupt:
                record["error_code"] = "interrupted"
                append_result(directory, record)
                raise
        if case.conversation_group and record["status"] != "completed":
            blocked.add(case.conversation_group)
        append_result(directory, record)
    return directory


def reconcile(client, result_directory: Path) -> None:
    manifest = read_json(result_directory / "manifest.json")
    if (
        manifest.get("owner_id") != client.me().get("id")
        or manifest.get("base_url") != client.base_url
        or manifest.get("phase") != "run"
    ):
        raise EvaluationError("manifest_mismatch")
    for record in load_results(result_directory):
        if record["status"] == "unknown" and record.get("conversation_id"):
            message = persisted_message(client, record)
            if message:
                apply_message(record, message)
                append_result(result_directory, record)
