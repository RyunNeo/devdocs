# API 后端

第一阶段已实现 FastAPI / SQLAlchemy / Alembic / Argon2 / 数据库 Cookie 会话。
RAG、文档、知识库、会话历史模块仍为后续占位。

从本目录：
```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

配置文件固定读取本目录 .env，参考 .env.example。
health 是存活检查，health/ready 检查数据库、pgvector 和认证表。
不要在应用启动时使用 create_all 创建生产表；表结构通过迁移管理。

实际数据库：PostgreSQL + psycopg。默认测试使用 SQLite，真实时区测试通过
TEST_DATABASE_URL 启用。其测试账号使用随机邮箱并在结束时清理。
登录凭据在数据库仅保存哈希摘要，退出撤销当前会话。

完整配置教学见根目录 outputs/stage-01-guide.md。
