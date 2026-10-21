# 阿里云宝塔 IP 部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为公开 GitHub 仓库建立 GHCR 镜像发布流程，并提供宝塔可用的 IP 临时验收 Compose 与操作指南。

**Architecture:** GitHub Actions 在 `main` 更新时构建并发布带提交 SHA 标签的 API/Web 镜像。宝塔 Compose 只拉取镜像，启动 PostgreSQL/pgvector、初始化/迁移任务、API 与 Web；仅 Web 映射 HTTP 80，持久化数据留在命名卷。

**Tech Stack:** GitHub Actions、Docker Buildx、GHCR、Docker Compose、Python/PyYAML/pytest、宝塔面板。

**Spec:** `docs/superpowers/specs/2026-10-21-aliyun-bt-ip-deployment-design.md`

## Global Constraints

- 用户在宝塔面板执行服务器操作，不要求 SSH 命令行安装或部署。
- IP 临时访问使用 `http://47.106.71.228`，安全组来源仅允许用户当前公网 IP `/32`。
- 仅 Web 发布宿主机 80；API 8000 与 PostgreSQL 5432 不得映射宿主机端口。
- 镜像仅通过 GHCR 按提交 SHA 拉取；应用密钥和数据库凭据不得进入 Git、镜像或 CI 日志。
- Alembic `0001_auth` 创建 pgvector 扩展；API 仅在数据库健康且迁移成功后启动，Compose 不依赖服务器上的仓库 bind mount。
- IP HTTP 仅用于受限的短期验收；正式开放必须切换可信 HTTPS 并启用 Secure Cookie。
- 不删除现存 Docker 卷，不迁移本地 rehearsal 数据。

## Review Focus

- 公共 GHCR 包可匿名拉取，且 SHA 标签精确对应触发构建的提交。
- 构建上下文不包含 `.env`、上传资料、评测产物或本地依赖目录。
- 首次启动及后续更换 SHA 标签时迁移依赖顺序正确，不会跳过失败的迁移。
- Compose 项目重建或服务更新不会丢失数据库与上传文件命名卷。
- 临时 IP Origin、API/Web 会话 Cookie 名称、HTTP Cookie 行为一致。

---

### Task 1: GHCR 镜像发布流程

**Files:**
- Create: `.github/workflows/publish-container-images.yml`
- Create: `infra/deploy/tests/test_image_publish_contract.py`

**Interfaces:**
- Workflow input: push to `main` and manual dispatch.
- Workflow output: public `ghcr.io/ryunneo/devdocs-api:sha-<commit>` and `ghcr.io/ryunneo/devdocs-web:sha-<commit>`.
- Required token permissions: `contents: read`, `packages: write`; no application secrets.

- [x] Add `test_publish_workflow_is_main_and_manual_only`, `test_publish_workflow_uses_minimal_permissions`, `test_publish_workflow_builds_api_and_web_sha_images`, and `test_publish_workflow_does_not_inject_runtime_secrets`; assert `main`/manual triggers, `contents: read`, `packages: write`, exact GHCR names and commit-SHA tags, root build context, both Dockerfiles, and no application secret references.
- [x] Run `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests/test_image_publish_contract.py -q`; confirm the missing-workflow assertions fail.
- [x] Add a Buildx workflow using `docker/login-action` with `GITHUB_TOKEN` and `docker/build-push-action`, building both images from repository root context.
- [x] Re-run the focused test and the full deployment test suite; expected: all pass except two existing backup tests blocked by sandbox hard-link restrictions.
- [x] Review GitHub package visibility instructions for first publication and document the one-time public visibility setting in Task 3.

### Task 2: Production Compose contract

**Files:**
- Create: `infra/deploy/compose.production.yml`
- Create: `infra/deploy/production.env.example`
- Modify: `infra/deploy/tests/test_compose_contract.py`

**Interfaces:**
- Compose image variables: `IMAGE_TAG`, used by the API and Web GHCR image references.
- Runtime variables: PostgreSQL credentials, `SILICONFLOW_API_KEY`, `CHAT_MODEL`, `PUBLIC_ORIGIN`, and daily usage limits.
- Services: `postgres`, `migrate`, `api`, `web`; named volumes for PostgreSQL data and uploads.

- [x] Add failing contract tests `test_production_images_are_sha_tagged_ghcr_references`, `test_production_database_has_pgvector_and_no_public_port`, `test_production_api_is_private_and_waits_for_migration`, `test_production_web_is_the_only_public_http_service`, `test_production_volumes_persist_database_and_uploads`, and `test_production_env_contract_matches_cookie_and_origin_settings`; assert no `build:` directives, no API/DB `ports`, the `0001_auth` migration creates the vector extension, no server-side init-file bind mount, `migrate` completion before API start, only `80:3000` published, named volumes, API/Web cookie agreement, HTTP `PUBLIC_ORIGIN`, and no literal credentials/API keys.
- [x] Run the focused production Compose tests; confirm the expected missing-file failures.
- [x] Implement Compose with externalized env values, PostgreSQL health gating, a one-shot Alembic migration dependency, API health gating, Web publication on `80:3000`, and named persistent volumes.
- [x] Add an env example with placeholders/comments only; specify a generated high-entropy database password and keep provider key blank.
- [x] Re-run focused tests and the full deployment test suite; expected: all pass except the same two environment-blocked backup tests.

### Task 3: Baota deployment and operations guide

**Files:**
- Create: `infra/deploy/README-production.md`
- Create: `infra/deploy/tests/test_production_guide_contract.py`

**Interfaces:**
- User workflow: publish image -> set first GHCR package visibility to public -> create Compose in Baota -> paste Compose and `.env` -> start -> verify health and HTTP IP access.
- Upgrade workflow: create ECS disk snapshot in Alibaba Cloud -> select a new SHA tag -> update/recreate in Baota -> verify -> retain prior tag for rollback.
- Safety workflow: keep 80 limited to the user IP, never expose 5432/8000, explain HTTP risks and HTTPS migration boundary.

- [x] Add `test_production_guide_covers_baota_first_deploy`, `test_production_guide_warns_about_http_and_security_group`, `test_production_guide_documents_backup_and_rollback`, and `test_production_guide_never_embeds_real_secrets`; assert the documented Compose/`.env` workflow, `http://47.106.71.228`, IP allowlisting, HTTPS/Secure-Cookie boundary, health verification, GHCR package visibility, ECS snapshot-before-upgrade, rollback tag, and placeholder-only credentials.
- [x] Run the focused documentation tests; confirm expected missing-guide failures.
- [x] Write UI-oriented Baota steps matching the Compose editor and `.env` fields; include first-run migration behavior and public GHCR setting.
- [x] Run all deployment tests, `git diff --check`, and a Compose YAML parse/contract check; expected: no failures.
- [x] Inspect the final diff for accidental secrets, destructive volume commands, public database/API ports, or rehearsal-only settings.
