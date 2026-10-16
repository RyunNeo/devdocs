# 数据库迁移

Alembic 已初始化。阶段 1 的 0001_auth 创建 users 与 auth_sessions，
并在 PostgreSQL 中确保 vector 扩展存在。

从 apps/api 执行 python -m alembic upgrade head、python -m alembic current。
数据库地址通过 app.core.config.Settings 读取，不把密码写入 alembic.ini。
后续阶段追加迁移，不重写已经运行的版本。

downgrade 会删除对应表和数据，仅在确认目标数据库及备份后操作。
