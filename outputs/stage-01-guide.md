# 第一阶段：本地配置与验收指南

日期：2026-10-12。项目位置：`C:\Users\nrx\Desktop\demo\devdocs-ai`。

## 本阶段交付

已实现 Next.js / TypeScript / Tailwind 前端、FastAPI 后端、注册、登录、退出、
登录态保持和受保护控制台。数据库使用 PostgreSQL + pgvector，Alembic 迁移版本
为 `0001_auth`。知识库、上传、问答与历史属于后续阶段。

当前电脑已经安装依赖并启动服务。先完成下方“亲自验收”，不用重复安装。
3000 端口已有其他服务，因此本项目使用 3001，不关闭原有服务。

- 前端：[http://127.0.0.1:3001](http://127.0.0.1:3001)
- 后端接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 存活检查：[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
- 数据库就绪：[http://127.0.0.1:8000/health/ready](http://127.0.0.1:8000/health/ready)

服务只监听本机，不是线上部署。如果重启电脑，请按“以后如何启动”启动。

## 亲自验收

1. 打开前端，用测试邮箱注册，密码为 10–128 个字符；不要求邮箱收到验证邮件。
2. 注册成功应进入工作台，显示你刚才输入的邮箱。
3. 刷新页面，仍应保持登录。
4. 点击退出，再直接访问 /dashboard，应回到登录页。
5. 用错误密码登录，看到“邮箱或密码错误”；用正确密码重新登录。
6. 重复注册同一个邮箱，应提示邮箱已经注册。
7. 打开 /health/ready，看到 status=ready、database=postgresql 和 pgvector 版本。

控制台的知识库、文档、会话当前为空，知识库入口尚未启用，这是本阶段的范围。
自动化验收账号留在本地数据库中，属于测试数据，不会成为你的登录凭据。

## 配置练习：理解两个环境文件

在项目根目录打开 PowerShell。以下复制命令只在目标文件不存在时执行；已经有文件时
编辑现有文件，避免覆盖你配置的内容。

```powershell
Copy-Item apps/api/.env.example apps/api/.env
Copy-Item apps/web/.env.example apps/web/.env.local
```

这两份 .env 文件不提交 Git。模板是开发示例，本阶段不需要填写任何模型密钥。
修改配置后要重启对应服务。

### 后端 apps/api/.env

```dotenv
DATABASE_URL=postgresql+psycopg://devdocs:devdocs@127.0.0.1:5432/devdocs_ai
ALLOWED_ORIGINS=["http://localhost:3001","http://127.0.0.1:3001","http://localhost:8000","http://127.0.0.1:8000"]
COOKIE_NAME=devdocs_session
COOKIE_SECURE=false
SESSION_DAYS=7
```

- DATABASE_URL：驱动 + 用户名 + 密码 + 主机 + 端口 + 数据库名称。与 docker-compose.yml 一致。
- ALLOWED_ORIGINS：允许发起浏览器请求的网站地址，必须使用 JSON 数组格式。
  3001 是前端，8000 是接口文档；在 Swagger 操作也需要允许 8000。换端口时同步修改。
- COOKIE_NAME：登录 Cookie 的名称，与前端 SESSION_COOKIE_NAME 保持一致。
- COOKIE_SECURE：本地 HTTP 使用 false；正式 HTTPS 部署使用 true。
- SESSION_DAYS：登录有效期，范围 1–30 天，默认 7 天。

开发账号 devdocs/devdocs 来自 compose 的本地配置。不要用于正式部署。
你这台机器验证过 127.0.0.1 能正常连接；localhost 曾出现连接等待，因此使用明确的 IPv4 地址。
默认配置已经能运行，但显式环境文件更便于你学习和调整配置。

### 前端 apps/web/.env.local

```dotenv
API_BASE_URL=http://127.0.0.1:8000
SESSION_COOKIE_NAME=devdocs_session
```

API_BASE_URL 供 Next.js 服务端访问后端。浏览器请求 /api/auth/...，Next.js 代理到
FastAPI 的 /auth/...，因此浏览器不直接处理后端跨域地址。
它没有 NEXT_PUBLIC 前缀；模型密钥以后仍只放后端。

Cookie 不限定端口。验收时始终使用 127.0.0.1:3001，避免和其他 localhost 项目的
登录 Cookie 混用。以后同时运行多个项目可设置不同 COOKIE_NAME。

## 以后如何启动

需要三个运行中的部分：Docker 数据库、后端、前端。首次依赖已经安装。
以下步骤用于下次启动；当前后台服务运行时不要再启动相同端口。

### 1. 数据库

打开 Docker Desktop，等待引擎运行。在项目根目录执行：

```powershell
docker compose up -d postgres
docker compose ps
```

看到 postgres 为 healthy，说明 PostgreSQL 已准备好。
数据保存在 Docker volume，停止容器不会删除账号。

### 2. 后端和迁移

另开 PowerShell：

```powershell
cd C:\Users\nrx\Desktop\demo\devdocs-ai\apps\api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

upgrade head 按版本创建/更新表，多次执行不会重复建表。
current 应显示 0001_auth (head)。
后端启动后保持这个终端打开，Ctrl+C 停止它。
--reload 会在修改 Python 文件后自动重启，仅用于开发。

这里直接调用 .venv 内的 Python，不需要改 PowerShell 执行策略或激活脚本。

### 3. 前端

再开一个 PowerShell：

```powershell
cd C:\Users\nrx\Desktop\demo\devdocs-ai
npm.cmd run dev
```

看到 Ready 后打开 127.0.0.1:3001。终端保持打开，Ctrl+C 停止前端。
根目录的 dev 命令默认使用 3001；如果改端口，也要改允许来源和测试地址。

当前这次启动是后台进程，日志在 work 目录。需要切换到自己启动的终端服务时，
先通过任务管理器核对对应进程的命令行与端口，再只停止本项目的进程；不要结束其他项目。

## 换电脑或重建开发环境

已在 Node.js 22.21.0、Python 3.14.6 上验证。建议沿用这些版本，
Python 的项目最低版本是 3.12，其他版本需重新验证依赖兼容性。

在项目根目录：

```powershell
npm.cmd ci
python -m venv apps/api/.venv
apps/api/.venv/Scripts/python.exe -m pip install -r apps/api/requirements.lock.txt
apps/api/.venv/Scripts/python.exe -m pip install --no-deps -e apps/api
```

npm ci 从 package-lock.json 安装已锁定的前端依赖。
requirements.lock.txt 包含当前验证过的后端及测试依赖；随后 editable 安装将本地 app
注册为可导入包。pyproject.toml 定义直接依赖范围，锁文件定义本次可复现版本。
数据库配置和启动步骤仍按上一节执行。

## 代码阅读顺序

1. [前端认证表单](../apps/web/components/auth/auth-form.tsx)：表单校验、提交、加载和错误处理。
2. [前端请求](../apps/web/lib/api.ts)：发送 JSON，通过 /api 访问后端。
3. [后端认证路由](../apps/api/app/api/routes_auth.py)：请求入口和 Cookie 写入。
4. [认证服务](../apps/api/app/services/auth_service.py)：注册、密码检查、创建/撤销会话。
5. [用户模型](../apps/api/app/models/user.py)和[会话模型](../apps/api/app/models/session.py)：实际持久化的数据。
6. [服务端身份读取](../apps/web/lib/auth.ts)和[工作台布局](../apps/web/app/(workspace)/layout.tsx)：页面权限检查。
7. [数据库迁移](../apps/api/app/db/migrations/versions/0001_auth.py)：建立用户与会话表。

### 注册与登录如何工作

浏览器提交邮箱密码 → Next.js 代理 → FastAPI 校验 → 数据库保存用户/会话 →
后端设置 HttpOnly Cookie → 前端跳转工作台。

密码用 Argon2 哈希保存，数据库不存明文。
登录凭据是随机字符串，数据库只存 SHA-256 摘要。
HttpOnly 表示前端 JavaScript 不能读取这个 Cookie，浏览器会自动发送它。
读取工作台时，服务端向 /auth/me 确认身份，不能只看 Cookie 是否存在。
退出会删除当前数据库会话并清除 Cookie；复制出来的旧 Cookie 也不能继续访问。
这是可撤销的服务端会话方案，与蓝图中“会话或 token”的认证范围一致，本阶段没有 JWT。

上传、知识库和消息接口后续还需要逐资源校验 user_id；
第一阶段只有账号资源，因此现在验证的是不同账号的身份隔离。

## 自己运行验证

后端测试不依赖运行中的 API，默认用临时 SQLite 数据库隔离：

```powershell
cd C:\Users\nrx\Desktop\demo\devdocs-ai\apps\api
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check app tests
```

默认结果为 15 passed、1 skipped；跳过项需要真实 PostgreSQL：

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://devdocs:devdocs@127.0.0.1:5432/devdocs_ai"
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

此时应为 16 passed。真实数据库测试创建临时账号，测试后删除该账号。
其中一项用 Asia/Shanghai 数据库时区验证过期会话，防止时区偏移导致过期判断错误。

在根目录验证前端：

```powershell
npm.cmd run typecheck
npm.cmd run build
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD/work/browsers"
npm.cmd exec --workspace @devdocs/web -- playwright install chromium
npm.cmd run test:e2e
```

浏览器测试需要前后端和数据库都在运行。测试在本地数据库创建示例账号。
已下载的浏览器可重复使用。前端构建时先停止同一项目的 dev 服务，
防止二者同时写 .next；构建完成后再次启动 dev。

## 常见配置问题

| 现象 | 优先检查 |
| --- | --- |
| docker compose 无法连接 | Docker Desktop 是否显示引擎运行 |
| 5432 端口占用 | 其他数据库是否占用；修改 compose 映射端口和 DATABASE_URL |
| 登录提示数据库暂不可用 | 数据库是否 healthy，是否执行 alembic upgrade head |
| /health 正常但 /health/ready 失败 | health 仅代表进程存活；ready 检查数据库、vector 扩展及表 |
| 请求来源未获允许 | 前端实际协议、主机和端口是否在 ALLOWED_ORIGINS |
| 登录后立即回到登录页 | COOKIE_SECURE 本地是否为 false；前后端 Cookie 名称是否一致 |
| 修改 .env 后未生效 | 重启后端；修改 .env.local 后重启前端 |
| 提示该邮箱已注册 | 使用登录页或换测试邮箱 |
| 3001/8000 已被占用 | 可能已有本项目服务，无需重复启动 |
| 本地能登录但线上不能 | 检查 HTTPS、Secure、同源代理、来源列表和生产持久数据库 |

不要为了连接失败删除 Docker volume；不要使用 docker compose down -v 来解决一般问题。
本地数据库不包含生产数据，当前开发凭据仅用于本地。

## 当前验证记录

- 16 项后端测试通过，覆盖真实 PostgreSQL 时区及隔离 SQLite 认证流程。
- 4 项浏览器测试通过：受保护页面跳转、注册/刷新/退出/登录、密码确认、桌面/手机布局。
- TypeScript 检查、Next.js 生产构建、Ruff 检查通过。
- 数据库就绪返回 postgresql / pgvector 0.8.7，迁移为 0001_auth。
- 桌面 1440px、手机 390px 截图已人工检查，无横向溢出。
- 本阶段未实现邮箱验证、密码找回及线上认证限流，这些需在公开试用前补齐。

## 下一阶段

相关官方资料：[Next.js 项目初始化](https://nextjs.org/docs/app/getting-started/installation)、
[FastAPI 密码哈希教学](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)、
[Starlette Cookie 与中间件说明](https://www.starlette.io/middleware/)。
密码哈希资料可帮助理解 Argon2；该教程中的 JWT 与本项目的数据库会话是两种认证方案。

你完成亲自验收后，阶段 2 将增加知识库 CRUD、Markdown/TXT 上传、私有存储及处理状态，
并沿用本阶段认证依赖来做资源级权限隔离。
