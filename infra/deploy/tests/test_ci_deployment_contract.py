from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_no_workflow_publishes_application_images_to_ghcr():
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / ".github/workflows").glob("*.y*ml")
    )
    assert "ghcr.io/ryunneo/devdocs-api" not in workflow_text
    assert "ghcr.io/ryunneo/devdocs-web" not in workflow_text
