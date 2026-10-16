import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from app.core.config import Settings
    from app.db.base import Base
    from app.main import create_app

    application = create_app(Settings(database_url=f"sqlite:///{tmp_path / 'knowledge.db'}"))
    Base.metadata.create_all(application.state.engine)
    with TestClient(application) as test_client:
        yield test_client


def sign_in(client, email="knowledge@example.com"):
    client.cookies.clear()
    assert (
        client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "Study-safe-2026!",
            },
        ).status_code
        == 201
    )


def create(client, **fields):
    return client.post("/knowledge-bases", json={"name": "React 学习", **fields})


def test_create_read_edit_and_delete_owned_knowledge_base(client):
    sign_in(client)
    response = create(client, name="  React 学习  ", description="组件与状态")
    assert response.status_code == 201
    knowledge = response.json()
    assert knowledge["name"] == "React 学习"
    assert knowledge["description"] == "组件与状态"
    assert "created_at" in knowledge and "updated_at" in knowledge
    resource = f"/knowledge-bases/{knowledge['id']}"
    assert client.get(resource).json()["id"] == knowledge["id"]
    renamed = client.patch(resource, json={"name": "Next.js 学习"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Next.js 学习"
    assert renamed.json()["description"] == "组件与状态"
    cleared = client.patch(resource, json={"description": None})
    assert cleared.json()["description"] is None
    assert client.delete(resource).status_code == 204
    assert client.get(resource).status_code == 404


def test_list_includes_only_current_user_and_supports_pagination(client):
    sign_in(client)
    first_id = create(client).json()["id"]
    second_id = create(client, name="Python 学习").json()["id"]
    result = client.get("/knowledge-bases", params={"limit": 1, "offset": 0}).json()
    assert result["total"] == 2
    assert len(result["items"]) == 1
    next_result = client.get("/knowledge-bases", params={"limit": 1, "offset": 1}).json()
    assert {result["items"][0]["id"], next_result["items"][0]["id"]} == {first_id, second_id}
    sign_in(client, "other@example.com")
    assert client.get("/knowledge-bases").json()["items"] == []


def test_other_user_cannot_read_edit_or_delete_resource(client):
    sign_in(client)
    knowledge_id = create(client).json()["id"]
    sign_in(client, "other@example.com")
    resource = f"/knowledge-bases/{knowledge_id}"
    assert client.get(resource).status_code == 404
    assert client.patch(resource, json={"name": "stolen"}).status_code == 404
    assert client.delete(resource).status_code == 404
    client.post("/auth/logout")
    assert (
        client.post(
            "/auth/login",
            json={
                "email": "knowledge@example.com",
                "password": "Study-safe-2026!",
            },
        ).status_code
        == 200
    )
    assert client.get(resource).json()["name"] == "React 学习"


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/knowledge-bases", None),
        ("POST", "/knowledge-bases", {"name": "React"}),
        ("GET", "/knowledge-bases/00000000-0000-0000-0000-000000000001", None),
        ("PATCH", "/knowledge-bases/00000000-0000-0000-0000-000000000001", {"name": "React"}),
        ("DELETE", "/knowledge-bases/00000000-0000-0000-0000-000000000001", None),
    ],
)
def test_all_knowledge_routes_require_login(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "  "},
        {"name": "x" * 81},
        {"name": "React", "description": "x" * 1001},
        {"name": "React", "user_id": "00000000-0000-0000-0000-000000000001"},
    ],
)
def test_invalid_create_is_rejected(client, payload):
    sign_in(client)
    result = client.post("/knowledge-bases", json=payload)
    assert result.status_code == 422
    assert "邮箱" not in result.json()["detail"]
    assert client.get("/knowledge-bases").json()["total"] == 0


@pytest.mark.parametrize(
    "payload", [{}, {"name": None}, {"name": "  "}, {"description": "x" * 1001}]
)
def test_invalid_patch_preserves_resource(client, payload):
    sign_in(client)
    knowledge_id = create(client).json()["id"]
    resource = f"/knowledge-bases/{knowledge_id}"
    assert client.patch(resource, json=payload).status_code == 422
    assert client.get(resource).json()["name"] == "React 学习"


def test_pagination_parameters_are_bounded(client):
    sign_in(client)
    for params in [{"limit": 0}, {"limit": 101}, {"offset": -1}]:
        assert client.get("/knowledge-bases", params=params).status_code == 422


def test_unknown_resource_and_invalid_identifier(client):
    sign_in(client)
    assert client.get("/knowledge-bases/00000000-0000-0000-0000-000000000001").status_code == 404
    assert client.get("/knowledge-bases/not-a-uuid").status_code == 422


def test_duplicate_name_ignores_case_and_outer_whitespace(client):
    sign_in(client)
    assert create(client, name="  React  ").status_code == 201
    assert create(client, name="react").status_code == 409
    assert client.get("/knowledge-bases").json()["total"] == 1
    sign_in(client, "other@example.com")
    assert create(client, name="REACT").status_code == 201


def test_duplicate_rename_leaves_original_values_unchanged(client):
    sign_in(client)
    create(client, name="React")
    second = create(client, name="Python", description="保留这段描述").json()
    resource = f"/knowledge-bases/{second['id']}"
    response = client.patch(resource, json={"name": " REACT ", "description": "不能保存"})
    assert response.status_code == 409
    current = client.get(resource).json()
    assert current["name"] == "Python"
    assert current["description"] == "保留这段描述"
    assert client.patch(resource, json={"name": " PYTHON "}).status_code == 200


def test_name_can_be_reused_after_deletion(client):
    sign_in(client)
    first_id = create(client, name="React").json()["id"]
    assert client.delete(f"/knowledge-bases/{first_id}").status_code == 204
    assert create(client, name="react").status_code == 201


def test_cross_origin_patch_and_delete_are_rejected(client):
    sign_in(client)
    resource = f"/knowledge-bases/{create(client).json()['id']}"
    headers = {"Origin": "https://evil.example"}
    assert client.patch(resource, json={"name": "bad"}, headers=headers).status_code == 403
    assert client.delete(resource, headers=headers).status_code == 403
    assert client.get(resource).status_code == 200


def test_direct_browser_cors_allows_patch_and_delete(client):
    for method in ["PATCH", "DELETE"]:
        response = client.options(
            "/knowledge-bases",
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": method,
            },
        )
        assert response.status_code == 200


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8000", "http://localhost:8000"])
def test_local_api_docs_can_login_create_edit_and_delete(client, origin):
    sign_in(client)
    headers = {"Origin": origin}
    login = client.post(
        "/auth/login",
        headers=headers,
        json={"email": "knowledge@example.com", "password": "Study-safe-2026!"},
    )
    assert login.status_code == 200
    created = client.post("/knowledge-bases", headers=headers, json={"name": "Swagger 验收"})
    assert created.status_code == 201
    resource = f"/knowledge-bases/{created.json()['id']}"
    assert client.patch(resource, headers=headers, json={"name": "Swagger 更新"}).status_code == 200
    assert client.delete(resource, headers=headers).status_code == 204


def test_local_docs_address_as_subdomain_does_not_bypass_origin_guard(client):
    sign_in(client)
    response = client.post(
        "/knowledge-bases",
        headers={"Origin": "http://127.0.0.1:8000.evil.example"},
        json={"name": "Should not be created"},
    )
    assert response.status_code == 403
    assert client.get("/knowledge-bases").json()["total"] == 0


@pytest.mark.parametrize(
    "name", ["Python学习", "P y t h o n 学习", "Python\t学习", "Python\u3000学习"]
)
def test_duplicate_name_ignores_internal_whitespace(client, name):
    sign_in(client)
    original = create(client, name="Python 学习").json()
    assert original["name"] == "Python 学习"
    assert create(client, name=name).status_code == 409
    assert client.get("/knowledge-bases").json()["total"] == 1


def test_rename_ignores_internal_whitespace_and_preserves_display_name(client):
    sign_in(client)
    original = create(client, name="Python 学习").json()
    second = create(client, name="React 学习").json()
    resource = f"/knowledge-bases/{second['id']}"
    assert client.patch(resource, json={"name": "Python学习"}).status_code == 409
    assert client.get(resource).json()["name"] == "React 学习"
    assert (
        client.patch(
            f"/knowledge-bases/{original['id']}", json={"name": "Python  学习"}
        ).status_code
        == 200
    )


def test_new_rule_detects_legacy_key_before_data_migration(client):
    sign_in(client)
    original = create(client, name="Python 学习").json()
    from uuid import UUID

    from app.models.knowledge_base import KnowledgeBase

    with client.app.state.session_factory() as db:
        knowledge = db.get(KnowledgeBase, UUID(original["id"]))
        knowledge.name_key = "python 学习"
        db.commit()
    assert create(client, name="Python学习").status_code == 409
    sign_in(client, "other-whitespace@example.com")
    assert create(client, name="Python学习").status_code == 201
