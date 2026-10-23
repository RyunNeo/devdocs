# DevDocs AI 宝塔源码构建部署（公网 IP）

> 当前仅用于受限验收：访问地址为 `http://47.106.71.228`，使用明文 HTTP，登录密码和会话 Cookie 没有传输加密保护。阿里云安全组 TCP 80 仅允许你当前公网 IP `/32`。不要在公共 Wi-Fi 登录，也不要上传敏感或真实用户资料。

本方案由宝塔取得公开 GitHub 源码，并在 ECS 上本机构建 API/Web 镜像。ECS 仍需下载 Docker 基础镜像，并访问 npm 与 PyPI 依赖源；本机构建不会绕过镜像仓库网络。当前生产 Compose 的 PostgreSQL 镜像为 `pgvector/pgvector:pg16`，API/Web 构建基础镜像分别为 `python:3.14-slim`、`node:22-slim`。

Compose 会直接本地构建 API/Web，并让迁移服务复用 API 本地镜像，不从远端仓库拉取应用镜像。PostgreSQL 和 Dockerfile 中的 Python/Node 基础镜像仍必须能够从镜像仓库获取。

服务器为 2 vCPU / 2 GiB RAM。Next.js 构建和 Python 依赖安装可能占用较多内存；若系统或构建容器出现 OOM、持续内存不足或面板无响应，先停止构建并评估串行构建能力或升级内存，不要反复重建。40 GiB 系统盘还要容纳源码、构建缓存、镜像、数据库和上传文件。

## 获取源码

本仓库公开地址为 [RyunNeo/devdocs](https://github.com/RyunNeo/devdocs)。在宝塔 Docker 插件开始创建编排前，先把源码放到服务器固定目录，例如 `/www/wwwroot/devdocs`。

- 如果当前宝塔已安装 Git/源码管理功能，可用它检出仓库的 `main` 分支。
- 如果没有 Git 检出功能，可在本地浏览器打开 GitHub 仓库，下载 `main` 的 ZIP；再通过宝塔 **文件** 页面上传并解压到 `/www/wwwroot/devdocs`。解压后应能看到 `apps`、`packages`、`infra`、`.dockerignore` 等仓库根目录内容。

部署前确认源码版本；更新时也要记录所用提交。不要将运行时 `.env` 放进仓库目录。`.dockerignore` 会排除环境文件、上传资料、本地依赖和评测结果，但仍应遵守密钥只放宝塔运行时配置的规则。

## 创建编排

### 创建前检查

- 确认安全组 TCP 80 来源为你当前公网 IP `/32`，不是 ECS 自身公网 IP；网络切换后需更新来源地址。
- 确认宝塔 Docker 插件可选择服务器上的 Compose 文件，并按 Compose 文件路径解析相对构建上下文。当前 Compose 的 API/Web 构建上下文是 `../..`，必须从仓库中的 `infra/deploy/compose.production.yml` 加载。
- Compose 的“编辑”模式只接收文本，无法可靠解析源码树中的相对构建上下文，不适合本方案。
- 先确认 Docker 能拉取 `pgvector/pgvector:pg16`、`python:3.14-slim` 和 `node:22-slim`，且 ECS 可访问 npm 与 Python 包索引。若仍遇到 `registry-1.docker.io` 超时，先解决 Registry 网络；本机构建不会绕过这一依赖。不要使用来源不明的镜像地址。
- 如果宝塔只允许粘贴 Compose 文本，先暂停并回报面板版本/界面；纯编辑模式下文件相对路径可能解析到宝塔临时目录，无法找到 Dockerfile。

### 填写容器编排

1. 宝塔左侧打开 **Docker → 容器编排 → 添加容器编排 → 常规创建**。
2. 编排名称填 `devdocs-ai-prod`。
3. 在“来源”选择 **文件**，选择 `/www/wwwroot/devdocs/infra/deploy/compose.production.yml`。不要选择“编辑”后粘贴 Compose 文本。
4. 把 `infra/deploy/production.env.example` 的内容填入宝塔的 `.env` 内容框，并设置：
   - `POSTGRES_PASSWORD`：在密码管理器中生成唯一的 64 位十六进制密码，只替换占位符。
   - `PUBLIC_ORIGIN`：`http://47.106.71.228`，与浏览器地址一致且不带结尾斜杠。
   - `SILICONFLOW_API_KEY`：填写硅基流动 Key。若暂时只验收注册登录可留空；索引和问答需要配置。
   - `CHAT_MODEL`：初始为 `deepseek-ai/DeepSeek-V4-Flash`，可按已有模型方案调整。
5. 确认 `.env` 中没有 `REPLACE_WITH...` 残留，真实密码和 Key 只出现在宝塔的运行时 `.env` 中，不要发到聊天或截图里。
6. Web 按需映射到主机 `80:3000`（或宝塔中实际使用的主机端口）；PostgreSQL 的 `127.0.0.1:5432:5432` 仅供服务器本机和 SSH 隧道使用。不要将 API `8000` 或 PostgreSQL `5432` 绑定到公网地址，也不要在阿里云安全组开放 5432。
7. 点击创建/启动后观察拉取与构建日志、系统内存和磁盘。预期顺序是 PostgreSQL 健康、Alembic 迁移成功、API 健康、Web 启动。`migrate` 成功后会正常退出；检查其退出码，不要因其退出就删除容器或卷。

## 首次验收

1. 宝塔 Docker 容器列表中，`postgres`、`api`、`web` 应健康运行；`migrate` 应成功退出。
2. 打开 [http://47.106.71.228](http://47.106.71.228)，确认登录页可加载。
3. 注册一个仅用于验收的账号并登录，再测试知识库创建。只有配置 `SILICONFLOW_API_KEY` 后才测试文档索引和 AI 问答。
4. 若容器列表为空，检查编排日志是否在拉取数据库/基础镜像时失败；若 PostgreSQL 已运行但 API 不健康，查看 `migrate` 和 `api` 日志。分享日志时遮住密码、Key、Cookie 和个人信息。不要删除数据卷或运行清理卷操作。

## 使用 Navicat Premium 连接 PostgreSQL

数据库不对公网开放。Compose 通过 `127.0.0.1:5432:5432` 将容器端口绑定到服务器回环地址，再由 Navicat SSH 隧道转发；不要把映射改为 `0.0.0.0:5432:5432`，也不要添加云安全组 5432 入方向规则。

1. 更新源码后，在宝塔更新/重建编排中的 `postgres` 服务，使新的回环端口映射生效。保留 `postgres_data` 数据卷；此操作会短暂重启数据库。
2. 在阿里云安全组确认 TCP 22 入方向仅允许你当前电脑的公网 IP `/32`。若 IP 已变化，先更新 SSH 规则。
3. Navicat 新建 PostgreSQL 连接。在“常规”页填写主机 `127.0.0.1`、端口 `5432`、数据库名 `POSTGRES_DB`、用户名 `POSTGRES_USER` 和密码 `POSTGRES_PASSWORD`；这些值从宝塔编排 `.env` 中读取，不要发送到聊天或截图。
4. 在“SSH”页启用 SSH 隧道：SSH 主机填写 ECS 公网 IP `47.106.71.228`、端口 `22`、服务器 SSH 用户名，并选择你已有的 SSH 密码或私钥认证方式。Navicat Premium 支持 SSH 隧道连接；隧道目标数据库仍填写 `127.0.0.1:5432`。
5. 点击“测试连接”。若 SSH 连接失败，先检查 22 入方向来源 IP 和认证方式；若 SSH 成功但数据库失败，确认 `postgres` 正在运行、回环端口映射已生效，以及数据库名/账号/密码填写正确。

## 更新与数据保护

- PostgreSQL 数据位于 `postgres_data` 命名卷，上传文件位于 `uploads` 命名卷。重建服务应保留这两个卷。
- 更新前在宝塔停止该编排的应用服务，再到阿里云 ECS 控制台为**系统盘**创建手动快照；当前 Docker 命名卷位于系统盘。快照可能产生费用，且普通磁盘快照不等同于数据库一致性备份。确认快照完成后再继续。参考[创建云盘快照](https://help.aliyun.com/zh/ecs/user-guide/create-a-snapshot)。
- 通过宝塔 Git/源码管理更新到目标提交；若使用 ZIP，则从 GitHub 下载目标版本并通过宝塔文件管理器更新源码。记录提交号，然后在宝塔用仓库内 Compose 文件重建 API/Web。
- 检查数据库、迁移、API、Web 状态后再验收。保留上一个已验收的源码提交和快照记录。若迁移改变数据库结构，只回退应用代码未必能恢复兼容；恢复磁盘快照会覆盖快照之后的数据，先核对时间、磁盘目标与数据损失范围。
- 可清理无用的构建缓存以释放空间，但只在宝塔明确显示为未使用镜像/构建缓存时操作。不要选择删除 volumes、清理数据卷或重置编排存储。
- GitHub 上以前发布的 GHCR 镜像包不再用于此方案；本次修改不会自动删除旧包或调整其可见性。

## 结束临时 IP 验收

申请并完成域名备案、配置可信 HTTPS 之后，将 `PUBLIC_ORIGIN` 改为 HTTPS 域名，并把 API 的 `COOKIE_SECURE` 改为 `true`，重新构建/更新并完整验收后，再把 HTTP 80 重定向到 HTTPS。不要在仍使用 HTTP 时启用 `COOKIE_SECURE=true`，否则登录 Cookie 不会通过 HTTP 发送。
