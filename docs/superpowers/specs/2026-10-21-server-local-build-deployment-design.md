# 服务器本机构建部署设计

## 目标

调整 DevDocs AI 生产部署流程：阿里云 ECS 通过宝塔获取公开 GitHub 仓库源码，并在服务器上构建 API 和 Web 应用镜像。应用运行镜像不再依赖 GHCR 发布；用户仍通过宝塔完成服务器侧操作，不使用 SSH 命令行。

## 当前问题

宝塔编排创建时，`pgvector/pgvector:pg16` 从 Docker Hub 拉取超时，导致容器列表为空，应用服务尚未启动。已有 GHCR API/Web 镜像构建成功，但生产 Compose 仍有 Docker Hub 的数据库镜像依赖。

## 已确认约束

- 服务器为 Ubuntu 24.04、2 vCPU、2 GiB RAM、40 GiB 系统盘。
- 项目仓库公开，ECS 通过宝塔获取源码；服务器操作保持面板方式。
- 临时访问地址为 `http://47.106.71.228`；TCP 80 安全组只允许用户当前公网 IP `/32`。
- 暂不配置域名、备案或 HTTPS。
- API 和 Web 使用仓库现有 Dockerfile 多阶段构建；Compose 文件必须从克隆仓库中的 `infra/deploy` 路径加载，以使 `../..` 构建上下文解析至仓库根目录。
- API Key、数据库密码只在宝塔运行时环境中配置，不作为构建参数，不进入源码、镜像或构建日志。
- PostgreSQL 和上传文件继续使用独立命名卷；不得删除既有卷作为排障手段。

## 方案

1. 在宝塔支持的 Git/源码管理界面将公开仓库检出到固定目录，并选择一个明确的分支或提交。
2. 在宝塔容器编排中使用仓库内的 `infra/deploy/compose.production.yml` 文件来源，而非只粘贴 Compose 文本。API 和 Web 服务使用 `build.context: ../..` 与仓库现有 Dockerfile；迁移服务复用 API 本地构建镜像。
3. 构建并运行 API、Web。Compose 的宿主机端口仍只有 `80:3000`；API `8000` 与 PostgreSQL `5432` 不公开。
4. PostgreSQL 继续使用 `pgvector/pgvector:pg16` 镜像，数据卷和启动顺序维持不变。开始完整构建前，先在宝塔确认 Docker 能取得数据库镜像及 `python:3.14-slim`、`node:22-slim` 基础镜像，并确认 ECS 构建网络可以访问 npm 与 Python 包索引。若 Docker Hub 或依赖源在 ECS 上仍超时，应先解决镜像/网络来源，不把本机构建误当作绕开 Registry 的手段。
5. 移除用于发布 API/Web 应用镜像到 GHCR 的 GitHub Actions workflow 与对应的镜像发布合约测试；保留其余 CI 与代码测试。已有 GHCR 包不自动删除、不改可见性。

## 资源约束与构建方式

Web Dockerfile 在 BuildKit 中执行 `npm ci` 和 Next.js production build，API Dockerfile 安装锁定的 Python 依赖。ECS 可用内存只有 2 GiB，若宝塔同时构建两个服务可能耗尽内存并导致 Docker 或系统进程被 OOM Killer 终止。实施时需要验证宝塔是否支持单服务构建/串行构建；若不支持，应先评估扩容到至少 4 GiB，再进行首次本机构建。不得通过删除数据库卷或降低安全配置来处理构建内存问题。

磁盘剩余空间需覆盖源码、Docker build cache、镜像层和 PostgreSQL/上传数据。部署文档应区分清理无用构建缓存与清理数据卷；绝不提供带卷删除选项的清理步骤。

## 发布与升级流程

- 初次部署：宝塔获取指定 GitHub 提交 -> 使用仓库内 Compose 文件 -> 填写运行时 `.env` -> 取得基础镜像 -> 按资源能力构建 API/Web -> 数据库健康 -> Alembic 迁移 -> API/Web 健康检查。
- 升级：先停止服务并创建 ECS 系统盘快照；宝塔将仓库更新到目标提交，再重建 API/Web 并启动。保留当前已验证提交和快照信息。迁移不兼容时不得只回退应用代码并假设数据库自动恢复。
- 暂时继续通过 `http://47.106.71.228` 验收。明文 HTTP 只适合受安全组 `/32` 限制的短期测试；正式开放前需 HTTPS 并启用 Secure Cookie。

## 宝塔能力验证项

实施前或分阶段验收时，必须确认当前 Docker 插件可以：

1. 从公开 GitHub 获取源码到服务器文件目录；若当前面板没有 Git 检出功能，确认宝塔文件管理器能否直接下载并解压 GitHub 仓库归档。
2. 以仓库内 Compose 文件路径运行，而不是把文本粘贴到无源码上下文的编辑框。
3. 从该 Compose 文件相对目录解析 `../..` build context。
4. 观察 build 输出、单独重试失败的镜像拉取，并查看容器健康状态。
5. 保留原命名卷执行更新/重建，不选择删除 volumes。

若面板版本不提供其中任一关键能力，再决定使用面板文件管理下载源码归档或调整操作步骤；不得未经确认退回服务器 SSH 命令行方案。

## 验收标准

- 生产 Compose 的 API/Web 使用本地 `build` 配置，API migration 复用同一 API 镜像，不引用 GHCR 应用镜像。
- 数据库仍是 pgvector/PostgreSQL 16，且镜像拉取可用性作为部署前置条件明确记录。
- API、Web Docker build context 是仓库根目录；`.dockerignore` 排除环境密钥、上传资料、评测结果和本地依赖。
- 生产 Compose 中只有 Web 映射 `80:3000`，迁移完成后 API 才启动，API 健康后 Web 才启动。
- 数据库和上传卷持久化；升级和故障说明不要求删除卷。
- GitHub 不再对应用镜像执行 GHCR 发布；不会自动更改旧 GHCR 包权限或删除旧包。
- 在当前 2 GiB ECS 上至少完成一次面板构建试验；记录构建峰值资源或 OOM 结果。若构建失败，不得宣称本机构建部署已验收。

## 不包含

- 服务器命令行部署或 SSH 自动化。
- 域名、ICP 备案、HTTPS/TLS。
- 自动部署、自动回滚、异地备份或高可用。
- 迁移本地 rehearsal 数据。
- 删除既有 GHCR 包、Docker 命名卷或生产数据。
