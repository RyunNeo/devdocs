from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/publish-container-images.yml"


def _workflow():
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_publish_workflow_is_main_and_manual_only():
    events = _workflow()["on"]
    assert events["push"]["branches"] == ["main"]
    assert "workflow_dispatch" in events
    assert set(events) == {"push", "workflow_dispatch"}


def test_publish_workflow_uses_minimal_permissions():
    assert _workflow()["permissions"] == {
        "contents": "read",
        "packages": "write",
    }


def test_publish_workflow_builds_api_and_web_sha_images():
    workflow = _workflow()
    matrix = workflow["jobs"]["publish"]["strategy"]["matrix"]["include"]
    expected = {
        "api": ("ghcr.io/ryunneo/devdocs-api", "infra/deploy/api.Dockerfile"),
        "web": ("ghcr.io/ryunneo/devdocs-web", "infra/deploy/web.Dockerfile"),
    }
    assert {
        row["service"]: (row["image"], row["dockerfile"])
        for row in matrix
    } == expected

    build_step = next(
        step
        for step in workflow["jobs"]["publish"]["steps"]
        if step.get("uses", "").startswith("docker/build-push-action@")
    )
    assert build_step["with"]["context"] == "."
    assert build_step["with"]["file"] == "${{ matrix.dockerfile }}"
    assert build_step["with"]["push"] == "true"
    assert build_step["with"]["tags"] == "${{ matrix.image }}:sha-${{ github.sha }}"


def test_publish_workflow_does_not_inject_runtime_secrets():
    text = WORKFLOW.read_text(encoding="utf-8").lower()
    for secret in ("siliconflow_api_key", "postgres_password", "env_file"):
        assert secret not in text
    assert "secrets.github_token" in text
