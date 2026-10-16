# 阶段 1：骨架与认证

预算：每周 5–10 小时。状态：代码已实现并通过本地验收（2026-10-12）。

## 主要位置

- `apps/web/app/(auth)/login`
- `apps/web/app/(auth)/register`
- `apps/web/app/(workspace)/dashboard`
- `apps/web/lib/auth.ts`
- `apps/api/app/main.py`
- `apps/api/app/core/config.py`
- `apps/api/app/core/security.py`
- `apps/api/app/api/routes_auth.py`
- `apps/api/app/models/user.py`
- `apps/api/app/db/session.py`
- `apps/api/app/db/migrations`
- `docker-compose.yml`

## 开发任务

- [x] 初始化 Next.js / TypeScript / Tailwind，补齐 package.json、tsconfig 和 App Router 根 layout。
- [x] 建立 Python pyproject.toml 与依赖锁定，初始化 FastAPI、配置、数据库会话和 Alembic。
- [x] 启动本地 PostgreSQL，验证 vector 扩展，创建用户表。
- [x] 实现密码哈希、注册登录、当前用户、退出及受保护页面；确定登录凭据存储策略。

## 功能验收

- [x] 注册、登录、退出完整可用。
- [x] 后端健康检查、数据库连接和迁移通过。
- [x] 未登录用户不能读取受保护资源。

配置教学见 outputs/stage-01-guide.md（项目根目录）。用户自行完成该指南的亲自验收。
