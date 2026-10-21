# DevDocs AI 宝塔临时部署（公网 IP）

> 本指南用于短期验收，不是开放公网的安全配置。当前通过 `http://47.106.71.228` 使用明文 HTTP；登录密码和会话 Cookie 没有传输加密保护。仅在阿里云安全组把 TCP 80 来源限制为你当前公网 IP `/32` 后使用。不要在公共 Wi-Fi 登录，不要上传敏感或真实用户资料。

服务器是 2 vCPU / 2 GiB RAM。镜像在 GitHub Actions 构建，ECS 只拉取镜像；低并发试用期间留意宝塔资源监控和容器重启情况。若内存持续紧张，先停止额外任务并扩容，不要通过删除数据卷排障。

## 发布镜像

1. 将本部署配置提交到公开仓库的 `main` 分支。`Publish container images` 工作流会为 API 和 Web 各构建一个镜像，标签为 `sha-<完整提交 SHA>`。
2. 在 GitHub 仓库的 **Actions** 中打开最新一次 `Publish container images` 运行。确认 `publish` 的 API、Web 两个矩阵任务均成功，并记录触发该运行的完整提交 SHA。
3. 首次发布会在 GitHub Packages 创建 `devdocs-api`、`devdocs-web` 两个镜像包，默认可见性为私有。ECS 无凭据拉取需要改为 Public：在包页面进入 **Package settings → Change visibility → Public**。

**重要：GitHub 说明，包一旦改为 Public，就不能再改回 Private。** 公开后任何人都可以拉取镜像；本项目镜像只包含应用代码，不应包含 `.env`、API Key、数据库密码、上传文件或用户数据。请确认接受公开镜像后再执行可见性更改。参考 [GitHub Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry) 与 [包可见性说明](https://docs.github.com/en/packages/learn-github-packages/configuring-a-packages-access-control-and-visibility)。

首次发布包仍为私有时，先不要创建服务器编排。公开仓库不会自动令 GHCR 包公开。

## 宝塔首次创建

### 创建前检查

- 阿里云安全组 TCP 80 的来源是你当前公网 IP `/32`，不是 ECS 自己的公网 IP；网络切换后要更新来源地址。
- 宝塔 Docker 已安装。Compose 中只有 Web 使用宿主机 80；不要额外开放 3000、8000 或 5432。
- 准备好本地仓库里的 `infra/deploy/compose.production.yml` 和 `infra/deploy/production.env.example`。前者复制到 Compose 编辑框；后者仅作模板，必须替换占位符后再放入 `.env` 内容框。
- 在密码管理器中生成唯一的 64 位十六进制数据库密码。不要将真实密码或 SiliconFlow Key 放进 GitHub、Compose YAML 或聊天截图。

### 填写容器编排

1. 宝塔左侧打开 **Docker → 容器编排 → 添加容器编排 → 常规创建**。
2. 编排名称填 `devdocs-ai-prod`。
3. 来源保持 **编辑**。把 `compose.production.yml` 的完整内容粘贴到 Compose 内容编辑区。
4. 把 `production.env.example` 的内容粘贴到 `.env` 内容编辑区，并替换以下值：
   - `IMAGE_TAG`：填 `sha-` 加上刚才成功的 GitHub Actions 提交 SHA。
   - `POSTGRES_PASSWORD`：填刚生成的 64 位十六进制密码；只填十六进制字符，避免 URL 编码和 Compose 插值问题。
   - `PUBLIC_ORIGIN`：当前为 `http://47.106.71.228`，必须与浏览器地址完全一致，不带结尾斜杠。
   - `SILICONFLOW_API_KEY`：填你自己的硅基流动 Key。若暂时只验收注册登录，可留空；文档索引与 AI 问答需要配置它。
   - `CHAT_MODEL` 初始为 `deepseek-ai/DeepSeek-V4-Flash`，可按已有模型方案调整。
5. 再核对 Compose 只发布 `80:3000`；`.env` 中没有 `REPLACE_WITH...` 残留，数据库密码和 API Key 均未放入 Compose 编辑区。
6. 点击 **确定** 创建并启动。首次启动顺序是 PostgreSQL 健康检查、Alembic 迁移、API 健康检查、Web 启动。`migrate` 容器正常完成后会显示退出状态；退出码应为成功。不要因为它已退出就删除容器或卷。

### 首次验收

1. 在宝塔 Docker 的容器页面确认 `postgres`、`api`、`web` 健康运行。`migrate` 应成功退出。
2. 用浏览器打开 [http://47.106.71.228](http://47.106.71.228)，检查登录页可加载。
3. 注册一个仅用于验收的账号并登录。确认成功后再测试知识库创建；只有设置了 `SILICONFLOW_API_KEY` 才测试文档索引和 AI 问答。
4. 若页面打不开，先查看宝塔中 `web`、`api`、`migrate` 的容器日志和健康状态；回报错误时遮住密码、Key、Cookie 和个人信息。不要删除卷，也不要运行清理卷的操作。

## 数据与升级

- PostgreSQL 数据保存在 `postgres_data` 命名卷，上传文件保存在 `uploads` 命名卷。重建容器不应删除这两个卷。
- 升级前先在宝塔停止该编排中的应用容器，再到阿里云 ECS 控制台为**系统盘**创建手动快照；当前 Docker 命名卷位于服务器系统盘。快照可能产生费用，且普通磁盘快照不等同于数据库一致性备份。确认快照完成后再启动原编排并升级。参考[创建云盘快照](https://help.aliyun.com/zh/ecs/user-guide/create-a-snapshot)。
- 升级时在 `.env` 中把 `IMAGE_TAG` 改为新成功运行对应的 `sha-<完整 SHA>`，在宝塔保存并更新/重建服务，确认数据库迁移、API 和 Web 健康后再验收。
- 保留上一个已验收的 SHA。若新版本有问题，只有确认数据库迁移向后兼容时才可仅改回旧 SHA；若迁移已改变数据库结构，单改镜像标签不一定能回滚数据库。需要恢复快照时会覆盖快照之后写入的数据，先停止服务并核对快照时间、磁盘目标和数据损失范围；不要在没有确认时执行磁盘回滚或删除卷。
- 本指南不配置自动或异地备份。正式长期使用前需要 HTTPS、Secure Cookie、可靠的数据库/上传文件备份以及恢复演练。

## 结束临时 IP 验收

申请并完成域名备案、配置可信 HTTPS 之后，把 `PUBLIC_ORIGIN` 改为 HTTPS 域名，并将 API 的 `COOKIE_SECURE` 改为 `true`，重新发布/更新服务并完整验收后，再把 HTTP 80 重定向到 HTTPS。不要在仍使用 HTTP 时启用 `COOKIE_SECURE=true`，否则登录 Cookie 不会通过 HTTP 发送。

