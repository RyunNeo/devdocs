# 第一阶段实施记录

依据：项目蓝图和 01-foundation.md。用户已授权直接实现，并希望自行学习配置。

## 设计决定

- Next.js App Router，前端浏览器请求 /api，通过 rewrite 转发到 FastAPI。
- 后端 SQLAlchemy + psycopg；Alembic 管理 users 和 auth_sessions 两表。
- 使用随机会话凭据与 HttpOnly / SameSite=Lax Cookie；数据库只存 SHA-256 摘要。
  不采用 localStorage 保存登录凭据。退出删除数据库会话，旧凭据立即失效。
- Cookie 默认为本地 HTTP；生产必须开启 Secure、使用 HTTPS 并明确允许来源。
- SQLite 只用于隔离自动化测试；实际开发数据库仍为 PostgreSQL + pgvector。
- 不新增 AI 接口或要求 API Key；本轮范围为第一阶段。

## 任务与证据

- [x] 后端依赖与测试：注册、重复邮箱、密码哈希、身份隔离、过期、退出撤销、来源检查。
- [x] 实现 API、配置与迁移；先运行失败测试，再实现并运行完整测试。
- [x] 实现登录/注册、受保护控制台、退出和后端不可用时的错误状态。
- [x] 安装并锁定依赖，执行类型检查、构建、页面和端到端验收。
- [x] 整理 Windows 本地配置教学，标注 Docker / PostgreSQL 实际验证状态。

## 当前环境

Node.js 22.21.0、Python 3.14.6 已安装；Docker CLI 已安装，但首次检查时引擎未运行。
保持现有目录直接开发：当前没有 Git 仓库，不创建或提交分支。

## 结果与处理记录

- Docker 后续启动成功，compose 数据库 healthy，pgvector 0.8.7，迁移 0001_auth。
- 本机 localhost 数据库连接等待，127.0.0.1 验证成功；默认与示例统一使用 IPv4。
- 3000 已被其他服务占用，前端使用空闲 3001 并加入允许来源。
- 认证测试从未实现的应用入口断言失败开始，完成后 15 项隔离测试通过。
- 真实 PostgreSQL 时区测试先暴露过期会话仍返回 200；保留带时区时间后恢复 401。
  全部 16 项后端测试通过，Ruff 检查通过。
- 4 项 Playwright 测试通过，包含 1440px 和 390px 下的页面截图与溢出检查。
- TypeScript 检查与 Next.js 生产构建通过；依赖记录在前后端锁文件。
- 独立代码审查未发现本阶段范围内的可操作问题。
- 配置教学交付于 outputs/stage-01-guide.md；代码完成不代替用户自行完成配置练习。
