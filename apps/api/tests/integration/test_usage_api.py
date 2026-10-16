from uuid import uuid4

from test_usage_quota import usage_app as usage_app


def test_usage_summary_scope_and_pagination(usage_app):
    _, client = usage_app
    response = client.get("/usage/summary")
    assert response.status_code == 200
    assert response.json()["quota"]["chat"]["remaining"] == 1
    assert response.json()["recent"]["success_rate"] is None
    kb = client.post("/knowledge-bases", json={"name": "Private sentinel name"}).json()["id"]
    conv = client.post(f"/knowledge-bases/{kb}/conversations", json={}).json()["id"]
    client.post(
        f"/conversations/{conv}/chat/stream",
        json={"question": "SECRET_QUESTION_SENTINEL", "request_id": str(uuid4())},
    )
    summary = client.get("/usage/summary").json()
    assert summary["quota"]["chat"]["remaining"] == 0
    assert summary["recent"]["local_completed"] == 1
    assert summary["recent"]["success_rate"] == 1
    rows = client.get("/usage/events").json()
    assert rows["total"] == 1 and rows["items"][0]["status"] == "local_completed"
    assert "SECRET_" not in str(rows) and "Private sentinel" not in str(rows)
    assert client.get("/usage/events?limit=0").status_code == 422
    assert client.get("/usage/events?status=not-a-status").status_code == 422
    client.post("/auth/logout")
    assert client.get("/usage/summary").status_code == 401
    client.post(
        "/auth/register", json={"email": "other@example.com", "password": "Study-safe-2026!"}
    )
    assert client.get("/usage/events").json()["total"] == 0


def test_request_id_and_safe_logs(usage_app, caplog):
    import logging

    _, client = usage_app
    with caplog.at_level(logging.INFO, logger="app"):
        response = client.get(
            "/usage/summary?token=SECRET_QUERY_SENTINEL", headers={"X-Request-ID": "SECRET_FAKE_ID"}
        )
    assert response.status_code == 200
    assert response.headers.get("x-request-id")
    assert response.headers["x-request-id"] != "SECRET_FAKE_ID"
    assert "SECRET_" not in caplog.text


def test_exception_validation_and_context_logs_never_echo_input(usage_app, caplog):
    import json
    import logging

    app, client = usage_app

    @app.get("/test-safe-error")
    def fail():
        raise RuntimeError("SECRET_EXCEPTION_SENTINEL")

    with caplog.at_level(logging.INFO, logger="app"):
        failed = client.get("/test-safe-error?token=SECRET_QUERY_SENTINEL")
        invalid = client.post(
            "/auth/login", json={"email": [], "password": "SECRET_PASSWORD_SENTINEL"}
        )
    assert failed.status_code == 500
    assert invalid.status_code == 422
    assert failed.headers["x-request-id"] != invalid.headers["x-request-id"]
    records = [record for record in caplog.records if record.name.startswith("app.")]
    assert records
    assert all("SECRET_" not in record.getMessage() for record in records)
    payloads = [json.loads(record.getMessage()) for record in records]
    assert {item["request_id"] for item in payloads} == {
        failed.headers["x-request-id"],
        invalid.headers["x-request-id"],
    }
    from app.core.logging import request_id_context

    assert request_id_context.get() is None
