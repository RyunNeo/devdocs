import json
from copy import deepcopy
from uuid import uuid4

import pytest

from evals.toolkit.client import EvaluationError, StreamResult
from evals.toolkit.dataset import DEFAULT_DATASET, load_dataset


class FakeClient:
    base_url = "http://127.0.0.1:8000"

    def __init__(self):
        self.docs, self.messages, self.calls = [], {}, []
        self.remaining = 50
        self.fail_index = False
        self.chat_error = None
        self.owner = "owner"
        self.persist = True
        self.bad_done = False

    def me(self):
        return {"id": self.owner}

    def summary(self):
        return {"quota": {k: {"remaining": self.remaining} for k in ("chat", "index")}}

    def create_kb(self, name):
        self.calls.append(("kb", name))
        return {"id": "kb"}

    def upload(self, kb, path):
        item = {
            "id": str(uuid4()),
            "filename": path.name,
            "status": "parsed",
            "index_status": "pending",
            "knowledge_base_id": kb,
        }
        self.docs.append(item)
        return item

    def index(self, doc):
        self.calls.append(("index", doc))
        if self.fail_index:
            raise EvaluationError("index_failed")
        item = next(d for d in self.docs if d["id"] == doc)
        item["index_status"] = "completed"
        return item

    def list_documents(self, kb):
        return deepcopy(self.docs)

    def create_conversation(self, kb):
        cid = str(uuid4())
        self.messages[cid] = []
        return {"id": cid}

    def stream_answer(self, cid, question, request_id):
        self.calls.append(("chat", cid, question))
        mid = str(uuid4())
        citations = [
            {
                "number": 1,
                "document_id": self.docs[0]["id"],
                "filename": self.docs[0]["filename"],
                "content": "资料",
            }
        ]
        msg = {
            "id": mid,
            "run_id": request_id,
            "role": "assistant",
            "status": "completed",
            "content": "回答[1]",
            "citations": citations,
            "usage": None,
            "model": "fake",
        }
        if self.persist:
            self.messages[cid].append(msg)
        if self.chat_error:
            raise self.chat_error
        return StreamResult(
            meta={"run_id": request_id, "assistant_message_id": mid, "conversation_id": cid},
            answer=msg["content"],
            citations=citations,
            done={"message_id": "wrong" if self.bad_done else mid, "status": "completed"},
            elapsed_ms=12,
        )

    def read_conversation(self, cid):
        return {"messages": self.messages[cid]}


def setup_run(tmp_path):
    from evals.toolkit.runner import prepare

    client = FakeClient()
    dataset = load_dataset(DEFAULT_DATASET)
    path = prepare(client, dataset, tmp_path, "prepare")
    return client, dataset, path


def records(path):
    from evals.toolkit.artifacts import load_results

    return load_results(path)


def test_prepare_and_quota(tmp_path):
    from evals.toolkit.runner import prepare

    client = FakeClient()
    dataset = load_dataset(DEFAULT_DATASET)
    client.remaining = 3
    with pytest.raises(EvaluationError, match="insufficient_quota"):
        prepare(client, dataset, tmp_path, "small")
    assert not client.calls
    client.remaining = 50
    client.fail_index = True
    with pytest.raises(EvaluationError):
        prepare(client, dataset, tmp_path, "failed")
    manifest = json.loads((tmp_path / "failed/manifest.json").read_text(encoding="utf-8"))
    assert manifest["kb_id"] == "kb" and len(manifest["documents"]) == 1
    assert len([c for c in client.calls if c[0] == "index"]) == 1


def test_failed_preparation_has_specific_error_without_submissions(tmp_path):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    raw.update(phase="prepare_failed", documents=[], kb_id=None, error_code="http_error")
    manifest.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(EvaluationError, match="preparation_incomplete") as exc:
        run_cases(client, dataset, manifest, tmp_path, "trial", ["fact-01"])
    assert "准备" in str(exc.value)
    assert not [c for c in client.calls if c[0] == "chat"]
    assert not (tmp_path / "trial").exists()


def test_prepare_keeps_safe_http_failure_status(tmp_path):
    from evals.toolkit.runner import prepare

    client = FakeClient()
    def conflict(name):
        raise EvaluationError("knowledge_base_name_conflict", 409)
    client.create_kb = conflict
    with pytest.raises(EvaluationError):
        prepare(client, load_dataset(DEFAULT_DATASET), tmp_path, "conflict")
    manifest = json.loads((tmp_path / "conflict/manifest.json").read_text(encoding="utf-8"))
    assert manifest["error_status"] == 409


def test_full_run_groups_and_no_answers_in_questions(tmp_path):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    path = run_cases(client, dataset, manifest, tmp_path, "full", None)
    results = records(path)
    assert len(results) == 24 and all(r["status"] == "completed" for r in results)
    chats = [c for c in client.calls if c[0] == "chat"]
    assert len(chats) == 24 and len({c[1] for c in chats}) == 21
    assert [c[2] for c in chats] == [c.question for c in dataset.cases]


@pytest.mark.parametrize("change", ["owner", "docs", "state", "hash", "quota", "snapshot"])
def test_invalid_preflight(tmp_path, change):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    if change == "owner":
        client.owner = "other"
    elif change == "docs":
        client.docs.append(dict(client.docs[0], id="extra"))
    elif change == "state":
        client.docs[0]["index_status"] = "failed"
    elif change == "hash":
        dataset.dataset_sha256 = "wrong"
    elif change == "snapshot":
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        raw["dataset"]["cases"][0]["question"] = "a different question"
        manifest.write_text(json.dumps(raw), encoding="utf-8")
    else:
        client.remaining = 0
    with pytest.raises(EvaluationError):
        run_cases(client, dataset, manifest, tmp_path, "bad", ["fact-01"])
    assert not [c for c in client.calls if c[0] == "chat"]


def test_disconnect_reconcile_never_resubmits(tmp_path):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    client.chat_error = EvaluationError("network_error")
    path = run_cases(client, dataset, manifest, tmp_path, "broken", ["fact-01", "fact-02"])
    result = records(path)
    assert result[0]["status"] == "completed" and result[0]["elapsed_ms"] is None
    assert result[1]["status"] == "not_attempted"
    assert len([c for c in client.calls if c[0] == "chat"]) == 1


def test_mismatch_and_dependency_block(tmp_path):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    client.bad_done = True
    path = run_cases(client, dataset, manifest, tmp_path, "mismatch", ["multi-01", "multi-02"])
    result = records(path)
    assert result[0]["status"] == "unknown"
    assert result[1]["status"] == "blocked"


def test_explicit_reconcile_only_reads(tmp_path):
    from evals.toolkit.runner import reconcile, run_cases

    client, dataset, manifest = setup_run(tmp_path)
    client.persist = False
    path = run_cases(client, dataset, manifest, tmp_path, "unknown", ["fact-01"])
    result = records(path)[0]
    assert result["status"] == "unknown"
    client.messages[result["conversation_id"]].append(
        {
            "id": result["assistant_message_id"],
            "role": "assistant",
            "status": "completed",
            "run_id": result["request_id"],
            "content": "回答[1]",
            "citations": [],
            "usage": None,
        }
    )
    count = len(client.calls)
    reconcile(client, path)
    assert len(client.calls) == count
    assert records(path)[-1]["status"] == "completed"


@pytest.mark.parametrize("status", [401, 429, 503])
def test_stop_after_rejected_submission(tmp_path, status):
    from evals.toolkit.runner import run_cases

    client, dataset, manifest = setup_run(tmp_path)
    client.persist = False
    client.chat_error = EvaluationError(
        {401: "login_required", 429: "quota_or_rate_limit", 503: "http_error"}[status], status
    )
    path = run_cases(client, dataset, manifest, tmp_path, "rejected", ["fact-01", "fact-02"])
    rows = records(path)
    assert rows[1]["status"] == "not_attempted"
    assert len([c for c in client.calls if c[0] == "chat"]) == 1


def test_api_transport_full_chain(tmp_path):
    import httpx

    from evals.toolkit.client import EvaluationClient
    from evals.toolkit.runner import prepare, run_cases

    fake = FakeClient()

    def handler(req):
        path = req.url.path
        if path == "/auth/login":
            return httpx.Response(
                200,
                json={"user": fake.me()},
                headers={"set-cookie": "session=fake; HttpOnly; Path=/"},
            )
        assert req.headers.get("cookie") == "session=fake"
        if path == "/auth/me":
            payload = fake.me()
        elif path == "/usage/summary":
            payload = fake.summary()
        elif path == "/knowledge-bases":
            payload = fake.create_kb(json.loads(req.content)["name"])
        elif path.endswith("/documents"):
            if req.method == "POST":
                name = next(
                    n for n in load_dataset(DEFAULT_DATASET).documents if n.encode() in req.content
                )
                payload = fake.upload("kb", DEFAULT_DATASET.parent.parent / "fixtures" / name)
            else:
                payload = {"items": fake.docs, "total": len(fake.docs)}
        elif path.endswith("/index"):
            payload = fake.index(path.split("/")[2])
        elif path.endswith("/conversations"):
            payload = fake.create_conversation("kb")
        elif path.endswith("/chat/stream"):
            data = json.loads(req.content)
            result = fake.stream_answer(path.split("/")[2], data["question"], data["request_id"])
            events = [
                ("meta", result.meta),
                ("token", {"delta": result.answer}),
                ("citations", {"items": result.citations}),
                ("done", result.done),
            ]
            body = "".join(
                f"event: {name}\ndata: {json.dumps(value)}\n\n" for name, value in events
            )
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)
        else:
            payload = fake.read_conversation(path.split("/")[2])
        return httpx.Response(200, json=payload)

    with EvaluationClient(fake.base_url, transport=httpx.MockTransport(handler)) as client:
        client.login("test@example.com", "sentinel-password")
        dataset = load_dataset(DEFAULT_DATASET)
        manifest = prepare(client, dataset, tmp_path, "http-prepare")
        directory = run_cases(client, dataset, manifest, tmp_path, "http-run")
        assert len(records(directory)) == 24
        assert all(r["status"] == "completed" for r in records(directory))
    for path in tmp_path.rglob("*.json*"):
        text = path.read_text(encoding="utf-8")
        assert "sentinel-password" not in text and "session=fake" not in text
