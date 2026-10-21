# 阿里云宝塔 IP 临时部署设计

## 目标

通过 GitHub Actions 在仓库更新时构建并发布 DevDocs AI 容器镜像到 GitHub Container Registry（GHCR），再由阿里云宝塔 Docker Compose 拉取镜像并运行服务。初期通过公网 IP 临时验收，不要求先购买域名；访问范围由阿里云安全组限制为用户当前公网 IP。

## 已确认的约束

- 服务器：阿里云 ECS，Ubuntu 24.04，2 vCPU、2 GiB RAM、40 GiB 系统盘。
- 仓库：公开 GitHub 仓库 `RyunNeo/devdocs`。
- 操作：用户通过宝塔面板完成容器编排操作；不要求用户在服务器 SSH 命令行安装或部署。
- 入口：暂用 `http://47.106.71.228`；安全组 HTTP 80 来源限制为用户当前公网地址 `/32`。
- 暂不处理域名、ICP 备案或 HTTPS。443 规则可能保留，但本阶段不依赖它。
- 现有演练 Compose 仅用于本地验证，不可直接复制到公网服务器。

## 方案

GitHub Actions 使用仓库中的 API/Web Dockerfile 构建 Linux 容器镜像，并将镜像发布到 GHCR。标签至少包含 Git commit SHA，保证服务器部署使用可追溯的不可变版本；可以额外发布 `latest` 供面板操作方便，但部署说明优先推荐 SHA 标签。因为仓库公开，部署镜像应配置为公开可拉取，不在 GitHub Actions 或镜像中注入应用运行密钥。

生产 Compose 仅拉取已构建镜像，不在 2 GiB ECS 上编译。Compose 管理 PostgreSQL/pgvector、迁移、FastAPI、Next.js；仅 Web 的 HTTP 端口映射到宿主机 80。PostgreSQL 与 API 只在 Compose 内网通信。PostgreSQL 数据与上传文件使用独立命名卷持久化。

运行参数与密钥通过宝塔编排页面的 `.env` 内容设置，不写入公开仓库。`SILICONFLOW_API_KEY` 留在 API 容器环境中；数据库密码使用随机强值。IP 临时 HTTP 模式允许非 Secure 会话 Cookie，因此仅允许安全组白名单来源进行短期验收，不承诺可用于开放公网或传输敏感资料。

首次启动应先等待数据库健康，再执行 Alembic 迁移，最后启动 API 与 Web。仓库的 `0001_auth` 迁移负责 `CREATE EXTENSION IF NOT EXISTS vector`；宝塔粘贴 Compose 时服务器没有仓库工作目录，因此生产 Compose 不绑定挂载仓库内的初始化 SQL 文件。应用升级时使用新的 SHA 镜像标签，并在升级前通过阿里云 ECS 磁盘快照备份；本设计包含明确的宝塔更新与旧 SHA 回滚说明，不自动删除卷或既有数据。

## 组件与文件

- `.github/workflows/publish-container-images.yml`：构建并发布 API、Web 镜像到 GHCR；限制触发条件并使用最小必要的 `GITHUB_TOKEN` 权限。
- `infra/deploy/compose.production.yml`：服务器 Compose，使用 GHCR 镜像引用和外置变量，不包含口令或 API Key。
- `infra/deploy/production.env.example`：变量清单与安全注释，不含真实凭据。
- `infra/deploy/README-production.md`：宝塔逐步操作、标签选择、启动顺序、健康检查、升级及备份/回滚说明。
- `infra/deploy/tests/`：Compose 合约测试及 Workflow/镜像引用测试，防止端口暴露、硬编码密钥、缺少持久卷或不安全配置回归。

## 安全与运维验收

1. GHCR 镜像不包含 `.env`、SiliconFlow Key、数据库凭据或用户上传数据。
2. Compose 中只有 Web 服务映射宿主机端口 80；PostgreSQL 5432 和 API 8000 无宿主机端口映射。
3. API CORS/Origin 仅允许配置的 HTTP 公网 IP Origin；生产 Cookie 名称在 API/Web 一致。
4. 数据库和上传目录均为持久化卷；迁移需在 API 启动前成功完成。
5. README 明确：IP HTTP 仅用于白名单下短期验收，换网络时更新来源 IP；登录凭据与会话不具备传输加密保护。正式开放前必须切换为可信 HTTPS，并启用 Secure Cookie。
6. CI 成功只能证明镜像构建和合约检查通过；真实服务器验收仍需用户逐步在宝塔操作并回报结果。

## 不包含

- 域名购买、ICP 备案、TLS/HTTPS 部署。
- 自动将 GitHub 更新推送到 ECS；部署由用户在宝塔面板手动选择镜像标签并更新。
- 云端对象存储、自动异地备份、监控告警或高可用架构。
- 把本地演练数据迁移到生产实例。

