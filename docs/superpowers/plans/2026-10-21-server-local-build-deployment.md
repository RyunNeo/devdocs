# 服务器本机构建部署实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让宝塔从公开 GitHub 仓库获取源码，并在 ECS 本机构建和运行 DevDocs AI 的 API 与 Web。

**Architecture:** 生产 Compose 文件从克隆仓库的 `infra/deploy` 路径加载，使 API/Web 的 `../..` build context 指向仓库根目录。API migration 复用 API 本地镜像；PostgreSQL 仍使用 pgvector 镜像。移除 API/Web 发布 GHCR 的专用 workflow，不删除现有 GHCR 包。

**Tech Stack:** Docker Compose v2、Docker BuildKit、Python 3.14、Node.js 22、Next.js、FastAPI、宝塔面板、pytest/PyYAML。

**Spec:** `docs/superpowers/specs/2026-10-21-server-local-build-deployment-design.md`

## Global Constraints

- ECS 为 Ubuntu 24.04、2 vCPU、2 GiB RAM、40 GiB 系统盘。
- 服务器操作必须通过宝塔面板，不使用 SSH 命令行部署。
- 入口暂为 `http://47.106.71.228`，阿里云安全组 TCP 80 仅允许当前公网 IP `/32`。
- PostgreSQL 使用 `pgvector/pgvector:pg16`；API/Web 构建分别使用仓库现有 `infra/deploy/api.Dockerfile` 与 `infra/deploy/web.Dockerfile`。
- API Key 与数据库密码仅配置在宝塔运行时 `.env`，不作为 Docker build args。
- Compose 仅将 Web 的 `80:3000` 发布到主机；不公开 API `8000` 或数据库 `5432`。
- `postgres_data` 与 `uploads` 命名卷持久化；不得通过删除卷排障。
- 本机构建仍需 Docker 基础镜像与 npm/Python 包索引可访问；不能把本机构建当作绕开镜像仓库的手段。

## Review Focus

- Compose 文件从宝塔编辑框而非仓库路径加载时，相对 build context 会失效；测试与文档必须要求从仓库中的 Compose 文件路径运行。
- `migrate` 与 `api` 必须使用同一个本地构建镜像；避免迁移服务仍引用已移除的 GHCR 标签。
- 构建上下文不得包含 `.env`、上传内容、评测结果、虚拟环境或 node_modules；复用并回归 `.dockerignore` 合约。
- 2 GiB 内存下并行构建可能 OOM；面板构建能力与峰值资源需明确作为实机验收项。
- PostgreSQL、Python/Node 基础镜像和 npm/PyPI 仍需联网；Registry 或依赖源超时必须与应用健康故障区分。

---

### Task 1: Production Compose 本机构建

**Files:**
- Modify: `infra/deploy/compose.production.yml`
- Modify: `infra/deploy/production.env.example`
- Modify: `infra/deploy/tests/test_compose_contract.py`

**Interfaces:**
- `api` builds from context `../..` and Dockerfile `infra/deploy/api.Dockerfile`, with local image `devdocs-prod-api:local`.
- `migrate` consumes exactly the same local image as `api`.
- `web` builds from context `../..` and Dockerfile `infra/deploy/web.Dockerfile`, with local image `devdocs-prod-web:local`.
- Runtime configuration and service names remain unchanged except removal of `IMAGE_TAG`.

- [x] **Step 1: Add failing Compose contract tests**

Assert `api.build` and `web.build` have exact root context and Dockerfile paths; `api.image == migrate.image == devdocs-prod-api:local`; `web.image == devdocs-prod-web:local`; no production service references GHCR; `IMAGE_TAG` is absent from the env example; existing health dependencies, port exposure, volumes, cookie/origin and runtime-secret contracts remain intact.

- [x] **Step 2: Run focused tests and confirm expected failures**

Run: `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests/test_compose_contract.py -q`

Expected: new production-local-build assertions fail against current GHCR image references.

- [x] **Step 3: Change the production Compose and env template**

Set API/Web build configuration and local image names as specified above. Point `migrate.image` at the API local image. Remove only the now-unused `IMAGE_TAG` sample; retain all runtime values and volume definitions.

- [x] **Step 4: Re-run Compose contract tests and Docker Compose validation**

Run: `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests/test_compose_contract.py -q`

Run: `docker compose -f infra/deploy/compose.production.yml config --quiet`

Expected: all Compose tests pass and Compose returns exit code 0 with dummy, non-secret environment values.

- [x] **Step 5: Commit the Compose module**

Commit message: `deploy: build production app images on server`.

### Task 2: Remove GHCR application image publishing

**Files:**
- Delete: `.github/workflows/publish-container-images.yml`
- Delete: `infra/deploy/tests/test_image_publish_contract.py`
- Create: `infra/deploy/tests/test_ci_deployment_contract.py`

**Interfaces:**
- No workflow publishes API or Web runtime images to GHCR.
- Other existing GitHub workflows and already-created GHCR packages remain untouched.

- [x] **Step 1: Add a failing repository CI contract test**

Add `test_no_workflow_publishes_application_images_to_ghcr`, asserting no workflow publishes `ghcr.io/ryunneo/devdocs-api` or `ghcr.io/ryunneo/devdocs-web`.

- [x] **Step 2: Run the focused test and confirm it fails**

Run: `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests/test_ci_deployment_contract.py -q`

Expected: FAIL because the publishing workflow still exists.

- [x] **Step 3: Remove the obsolete publishing workflow and its dedicated tests**

Delete only the two named files. Do not delete registry packages or change package visibility.

- [x] **Step 4: Run focused deployment tests**

Run: `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests -q -k 'not finalize_and_revalidate_without_overwriting and not validate_rejects_incomplete_or_altered_manifest'`

Expected: suite passes; the two pre-existing hard-link tests remain deselected due the Windows sandbox restriction.

- [x] **Step 5: Commit the workflow module change**

Commit message: `ci: stop publishing app images to ghcr`.

### Task 3: Rewrite Baota source-build guide

**Files:**
- Modify: `infra/deploy/README-production.md`
- Modify: `infra/deploy/tests/test_production_guide_contract.py`

**Interfaces:**
- Guide steps cover public GitHub checkout or panel-supported archive download, Compose file selection from the repository, local API/Web builds, runtime `.env`, health checks, and upgrades.
- Guide explicitly states registry/npm/Python-index access remains necessary and calls out the 2 GiB build-memory constraint.

- [x] **Step 1: Add failing documentation contract assertions**

Assert instructions cover source acquisition via Baota UI, selecting the repository Compose file (not pasting it into editor-only mode), root-relative build context, local app builds, registry/base-image and package-index prerequisites, memory/OOM warning, no public API/database ports, persistent volumes, snapshot-before-upgrade, and HTTP/IP restrictions. Assert GHCR app publishing and `IMAGE_TAG` instructions are absent.

- [x] **Step 2: Run focused tests and confirm expected failures**

Run: `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests/test_production_guide_contract.py -q`

Expected: tests fail on the current GHCR-based guide.

- [x] **Step 3: Update the user-facing Baota guide**

Document the actual UI paths only where established by provided panel screenshots; mark Git checkout/file-source features as a panel-version verification. Provide a no-SSH fallback using a public GitHub source archive through the panel's file manager if supported. Do not invent a mirror hostname or tell the user to delete volumes.

- [x] **Step 4: Verify docs and full deployment suite**

Run focused guide tests, then all deployment tests with the two sandbox-blocked hard-link tests deselected. Run `git diff --check` and Docker Compose config validation.

Expected: all runnable deployment tests pass; Compose config is valid; no secret or stale GHCR instructions remain.

- [x] **Step 5: Commit documentation module**

Commit message: `docs: guide baota source-build deployment`.

### Task 4: Panel preflight and server acceptance handoff

> Pending live server acceptance. The implementation is prepared, but the remaining checks must be performed in the user's Baota panel; no SSH or panel session is available to this task. Keep these steps open until the user reports the results.

**Files:**
- Modify: `docs/superpowers/specs/2026-10-21-server-local-build-deployment-design.md` only if implementation reveals a confirmed panel constraint.

- [ ] **Step 1: Inspect Baota capabilities before creating containers**

In Docker → Container Orchestration, verify the panel can source a Compose file inside the GitHub checkout, resolve its relative build context, display build/pull logs, and recreate services without deleting volumes. If unavailable, stop and report the panel limitation before choosing a fallback.

- [ ] **Step 2: Verify registry and dependency access**

Use Baota's supported image-pull/build UI to confirm `pgvector/pgvector:pg16`, `python:3.14-slim`, and `node:22-slim` are reachable before starting the full stack. Do not proceed if pulls still time out; do not expose secrets while sharing logs.

- [ ] **Step 3: Build and start through Baota**

Use the `.env` with existing runtime variables, choose the intended GitHub commit, and create/update the compose stack while preserving `postgres_data` and `uploads`. Observe RAM and disk during builds. If memory pressure/OOM occurs, stop and reassess serial build support or ECS memory before retrying.

- [ ] **Step 4: Verify service chain and HTTP access**

Confirm PostgreSQL healthy, migration exits successfully, API ready, Web healthy, and `http://47.106.71.228` opens while TCP 80 remains restricted to the user's current IP `/32`. User reports each result; do not claim deployment complete before this real-server acceptance.
