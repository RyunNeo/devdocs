from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPOSE = ROOT / "infra/deploy/compose.rehearsal.yml"


def test_database_uses_required_dedicated_settings():
    content = COMPOSE.read_text(encoding="utf-8")
    assert "image: pgvector/pgvector:pg16" in content
    for key in ("POSTGRES_USER", "POSTGRES_DB", "POSTGRES_PASSWORD"):
        assert f"{key}: ${{{key}:?" in content


def test_no_database_host_port_or_external_development_volume():
    content = COMPOSE.read_text(encoding="utf-8")
    services = yaml.safe_load(content)["services"]
    assert "ports" not in services["postgres"]
    assert "container_name:" not in content
    assert "external:" not in content
    assert "name: postgres_data" not in content
    assert "name: devdocs" not in content
    assert "postgres_data:/var/lib/postgresql/data" in content


def test_initialization_is_readonly_and_healthcheck_contains_no_password():
    content = COMPOSE.read_text(encoding="utf-8")
    assert "../postgres/init:/docker-entrypoint-initdb.d:ro" in content
    health = str(yaml.safe_load(content)["services"]["postgres"]["healthcheck"])
    assert "pg_isready" in health
    assert "$$POSTGRES_USER" in health and "$$POSTGRES_DB" in health
    assert "PASSWORD" not in health


def test_api_build_uses_root_context_and_isolated_runtime():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    api = services["api"]
    assert api["build"] == {"context": "../..", "dockerfile": "infra/deploy/api.Dockerfile"}
    assert api["image"] == "devdocs-rehearsal-api:local"
    assert not api.get("ports")
    assert api["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert api["environment"]["UPLOAD_DIR"] == "/data/uploads"
    assert api["environment"]["COOKIE_NAME"] == "devdocs_rehearsal_session"
    assert api["environment"]["COOKIE_SECURE"] == "false"
    assert "@postgres:5432/" in api["environment"]["DATABASE_URL"]
    assert "127.0.0.1:5432" not in api["environment"]["DATABASE_URL"]
    assert api["volumes"] == ["uploads:/data/uploads"]


def test_backend_image_has_locked_dependencies_nonroot_and_no_auto_migration():
    content = (ROOT / "infra/deploy/api.Dockerfile").read_text(encoding="utf-8")
    assert "python:3.14-slim" in content
    assert "requirements.lock.txt" in content
    assert "USER 10001:10001" in content
    assert '"--workers", "1"' in content
    assert '"--no-access-log"' in content
    assert '"--reload"' not in content
    assert "upgrade head" not in content
    assert "COPY . ." not in content
    assert "COPY apps/api/.env" not in content


def test_dockerignore_excludes_local_credentials_and_artifacts():
    patterns = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    for pattern in [
        "**/.env",
        "**/.env.*",
        "**/*.env.*",
        "work/",
        "evals/results/",
        "apps/api/storage/uploads/",
        "infra/deploy/backups/",
        "**/.venv/",
        "**/node_modules/",
        "**/.next*",
    ]:
        assert pattern in patterns


def test_storage_initializer_is_offline_and_only_touches_upload_volume():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    init = services["storage-init"]
    assert init["image"] == services["api"]["image"]
    assert init["profiles"] == ["maintenance"]
    assert init["user"] == "0:0"
    assert init["network_mode"] == "none"
    assert init["read_only"] is True
    assert init["volumes"] == ["uploads:/data/uploads"]
    assert not init.get("environment")
    assert "os.chown(path, 10001, 10001)" in init["command"][2]
    assert "os.chmod(path, 0o750)" in init["command"][2]
    assert "remove" not in init["command"][2]


def test_migration_job_is_explicit_and_only_uses_rehearsal_database():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    migrate = services["migrate"]
    assert migrate["profiles"] == ["maintenance"]
    assert migrate["image"] == services["api"]["image"]
    assert migrate["command"] == ["python", "-m", "alembic", "upgrade", "head"]
    assert migrate["environment"] == {
        "DATABASE_URL": services["api"]["environment"]["DATABASE_URL"]
    }
    assert not migrate.get("volumes")
    assert not migrate.get("ports")
    assert "user" not in migrate
    assert migrate["read_only"] is True


def test_web_is_the_only_loopback_entry_and_matches_api_cookie():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    web = services["web"]
    assert web["build"] == {"context": "../..", "dockerfile": "infra/deploy/web.Dockerfile"}
    assert web["image"] == "devdocs-rehearsal-web:local"
    assert web["ports"] == ["127.0.0.1:${REHEARSAL_PORT:?Run the config initializer}:3000"]
    assert web["environment"]["API_BASE_URL"] == "http://api:8000"
    assert (
        web["environment"]["SESSION_COOKIE_NAME"] == services["api"]["environment"]["COOKIE_NAME"]
    )
    assert "SILICONFLOW_API_KEY" not in web["environment"]
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert all(not svc.get("ports") for name, svc in services.items() if name != "web")


def test_web_image_uses_standalone_runtime_and_includes_static_assets():
    content = (ROOT / "infra/deploy/web.Dockerfile").read_text(encoding="utf-8")
    assert "node:22-slim" in content
    assert "npm ci" in content
    assert "DEPLOY_STANDALONE=1" in content
    assert "API_BASE_URL=http://api:8000" in content
    assert "COPY packages/shared/" in content
    assert "/app/apps/web/.next/standalone" in content
    assert "/app/apps/web/.next/static" in content
    assert "/app/apps/web/public" in content
    assert "USER 10001:10001" in content
    assert 'CMD ["node", "apps/web/server.js"]' in content
    assert "COPY . ." not in content
    assert "SILICONFLOW_API_KEY" not in content


def test_backup_files_job_is_readonly_offline_and_without_credentials():
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    job = services["backup-files"]
    assert job["image"] == services["api"]["image"]
    assert job["profiles"] == ["maintenance"]
    assert job["network_mode"] == "none"
    assert job["volumes"] == ["uploads:/data/uploads:ro"]
    assert not job.get("environment") and not job.get("user")
    assert not job.get("ports")
    assert job["command"] == [
        "python",
        "-",
        "create",
        "--source",
        "/data/uploads",
        "--output",
        "/tmp/uploads.tar",
    ]


def test_restore_override_pins_images_and_isolates_cookie():
    from pathlib import Path

    import yaml

    path = Path(__file__).resolve().parents[1] / "compose.restore-001.yml"
    assert path.exists(), "isolated recovery configuration is missing"
    services = yaml.safe_load(path.read_text())["services"]
    for name in ("postgres", "api", "web"):
        assert services[name]["image"].startswith("sha256:")
    assert services["api"]["environment"]["COOKIE_NAME"] == "devdocs_restore_001_session"
    assert services["web"]["environment"]["SESSION_COOKIE_NAME"] == "devdocs_restore_001_session"
    job = services["restore-files"]
    assert job["network_mode"] == "none"
    assert job["volumes"] == ["uploads:/data/uploads"]
    assert job["cap_drop"] == ["ALL"]
    assert not job.get("environment")
    script = job["command"][-1]
    assert script.index("os.chown(root, 0, 0)") < script.index("result = tools[")
    assert script.index("os.chown(root, 0, 0)") < script.index("any(root.iterdir())")
    assert script.index("for path in root.iterdir():") < script.index(
        "os.chown(root, 10001, 10001)"
    )


def _production_compose():
    return yaml.safe_load((ROOT / "infra/deploy/compose.production.yml").read_text(encoding="utf-8"))


def test_production_images_are_built_locally_from_repository_root():
    services = _production_compose()["services"]
    assert services["api"]["build"] == {
        "context": "../..",
        "dockerfile": "infra/deploy/api.Dockerfile",
    }
    assert services["api"]["image"] == "devdocs-prod-api:local"
    assert services["api"]["pull_policy"] == "build"
    assert services["migrate"]["image"] == services["api"]["image"]
    assert services["migrate"]["pull_policy"] == "never"
    assert services["web"]["build"] == {
        "context": "../..",
        "dockerfile": "infra/deploy/web.Dockerfile",
    }
    assert services["web"]["image"] == "devdocs-prod-web:local"
    assert services["web"]["pull_policy"] == "build"
    assert all("ghcr.io/" not in service.get("image", "") for service in services.values())


def test_production_database_has_pgvector_and_no_public_port():
    compose = _production_compose()
    services = compose["services"]
    postgres = services["postgres"]
    assert postgres["image"] == "pgvector/pgvector:pg16"
    assert not postgres.get("ports")
    assert postgres["healthcheck"]["test"][0] == "CMD-SHELL"
    assert "pg_isready" in postgres["healthcheck"]["test"][1]
    assert "postgres_data:/var/lib/postgresql/data" in postgres["volumes"]
    assert "001-pgvector.sql" not in str(postgres.get("volumes", []))

    migration = ROOT / "apps/api/app/db/migrations/versions/0001_auth.py"
    assert "CREATE EXTENSION IF NOT EXISTS vector" in migration.read_text(encoding="utf-8")


def test_production_api_is_private_and_waits_for_migration():
    services = _production_compose()["services"]
    migrate = services["migrate"]
    api = services["api"]
    assert migrate["command"] == ["python", "-m", "alembic", "upgrade", "head"]
    assert migrate["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert api["depends_on"]["migrate"]["condition"] == "service_completed_successfully"
    assert not api.get("ports") and not migrate.get("ports")
    assert "uploads:/data/uploads" in api["volumes"]
    assert "DATABASE_URL" in api["environment"]
    assert "@postgres:5432/" in api["environment"]["DATABASE_URL"]


def test_production_web_is_the_only_public_http_service():
    services = _production_compose()["services"]
    web = services["web"]
    assert web["ports"] == ["80:3000"]
    assert web["environment"]["API_BASE_URL"] == "http://api:8000"
    assert web["depends_on"]["api"]["condition"] == "service_healthy"
    assert all(not service.get("ports") for name, service in services.items() if name != "web")


def test_production_volumes_persist_database_and_uploads():
    compose = _production_compose()
    assert set(compose["volumes"]) == {"postgres_data", "uploads"}
    assert "postgres_data:/var/lib/postgresql/data" in compose["services"]["postgres"]["volumes"]
    assert "uploads:/data/uploads" in compose["services"]["api"]["volumes"]


def test_production_env_contract_matches_cookie_and_origin_settings():
    services = _production_compose()["services"]
    api_env = services["api"]["environment"]
    web_env = services["web"]["environment"]
    assert api_env["COOKIE_NAME"] == web_env["SESSION_COOKIE_NAME"]
    assert api_env["COOKIE_SECURE"] == "false"
    assert '${PUBLIC_ORIGIN:?' in api_env["ALLOWED_ORIGINS"]
    assert api_env["SILICONFLOW_API_KEY"] == "${SILICONFLOW_API_KEY:-}"

    env_example = (ROOT / "infra/deploy/production.env.example").read_text(encoding="utf-8")
    for key in ("POSTGRES_PASSWORD", "SILICONFLOW_API_KEY", "PUBLIC_ORIGIN"):
        assert f"{key}=" in env_example
    assert "REPLACE_WITH" in env_example
    assert "POSTGRES_PASSWORD=REPLACE_WITH_64_HEX_CHARACTERS" in env_example
    assert "SILICONFLOW_API_KEY=" in env_example
    assert "SILICONFLOW_API_KEY=\n" in env_example
def test_production_env_no_longer_requires_a_prebuilt_image_tag():
    env_example = (ROOT / "infra/deploy/production.env.example").read_text(encoding="utf-8")
    assert "IMAGE_TAG" not in env_example
