# 模块 2.1：知识库后端与亲手验收

本次只完成知识库后端，页面和上传分别留到后续模块。
你选择的规则已落实：同一账号不允许重名，比较时忽略大小写和首尾空格。

## 当前交付

5 个 CRUD 接口、分页列表、参数校验、账号隔离及 0002_knowledge_bases 迁移。
新增 24 项 API 测试、1 项隔离 PostgreSQL 迁移测试，完整后端测试为 41 passed。
Ruff 检查通过，独立代码审查未发现本模块范围内的可操作问题。

开发数据库仍是 0001_auth。本轮没有替你执行开发库迁移，下面由你亲手处理。
测试使用独立的临时 PostgreSQL 数据库，测试结束后已清理。
不新增环境变量，不需要安装新依赖，沿用第一阶段配置。

## 任务 1：执行迁移（约 3 分钟）

先确保 Docker Desktop 正常运行，打开 PowerShell：

```powershell
cd C:\Users\nrx\Desktop\demo\devdocs-ai\apps\api
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
.\.venv\Scripts\python.exe -m alembic check
```

观察版本从 0001_auth 变为 0002_knowledge_bases (head)。最后应显示
No new upgrade operations detected，表示模型与数据库结构一致。
迁移只新增知识库表，已有账号和登录会话保留。不要执行 downgrade 或删库。
已经是 0002 时无需重复处理，upgrade head 会跳过已完成的版本。

迁移前知识库接口可能返回 503，提示数据库状态和迁移需要检查。
/health/ready 当前检查第一阶段认证表，不能替代本模块的迁移版本检查。
后端若仍在开发模式运行会自动加载代码；服务已关闭时按第一阶段指南启动。
本次后端已重启并显示新路由。下次建议从 apps/api 使用下面的开发命令，
只监听 app 目录，避免写测试文件触发重载，并限制退出等待时间：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --timeout-graceful-shutdown 5 --host 127.0.0.1 --port 8000 --no-access-log
```

## 任务 2：完成一次 CRUD（约 10 分钟）

打开 [接口文档](http://127.0.0.1:8000/docs)，展开接口，点击 Try it out，填写参数后 Execute。
保持使用 127.0.0.1，避免与 localhost 的 Cookie 混用。
采用 Cookie 登录，不需要点击 Authorize，也不要手填 token。

如果看到 403“请求来源未获允许”，检查后端 .env 的 ALLOWED_ORIGINS 是否包含
http://127.0.0.1:8000（接口文档地址）。配置模板和默认值已包含它，
已有 .env 会覆盖默认值，需要自行在数组中追加；改 .env 后重启后端。

1. 先调用 POST /auth/login，输入你第一阶段注册的邮箱和密码。成功为 200，
   浏览器自动保存 Cookie。GET /auth/me 应返回你的邮箱。
2. POST /knowledge-bases，输入下方 JSON，期望 201，记下返回的 id。
3. GET /knowledge-bases，默认 limit=20、offset=0，响应为 items、total、limit、offset。
   使用 GET /knowledge-bases/{knowledge_base_id} 查看刚创建的知识库，期望 200。
4. PATCH 同一个 id，提交下方改名 JSON，期望 200，描述应保留。
5. 再 PATCH 提交 description=null，期望 200，清空描述，名称应保留。
6. 再创建名称为 "  REACT 进阶学习  " 的知识库，期望 409：大小写和首尾空格不影响重名判定。
7. DELETE 原来的 id，期望 204、没有响应体；再 GET 原 id，期望 404。

创建示例：

```json
{
  "name": "React 学习",
  "description": "我的组件与状态学习笔记"
}
```

改名示例：

```json
{ "name": "React 进阶学习" }
```

清空描述：

```json
{ "description": null }
```

PATCH 表示只修改提供的字段，不需要提交完整知识库。
name=null 和空请求 {} 不合法；description=null 则表示清空。
列表按更新时间从新到旧排序，limit 为 1–100，offset 不小于 0。

## 任务 3：验证你决定的规则和权限

| 操作 | 预期状态 |
| --- | --- |
| 同账号创建重复名称，英文大小写不同或首尾有空格 | 409 |
| 换一个账号创建同名知识库 | 201 |
| 删除后重新使用原名称 | 201 |
| 名称仅为空格或超过 80 字符 | 422 |
| 描述超过 1000 字符 | 422 |
| 请求体自行提供 user_id | 422 |
| 退出后获取知识库列表 | 401 |
| 账号 B 查看、改名或删除账号 A 的知识库 id | 404 |
| 访问不存在的 UUID | 404 |
| id 格式不是 UUID | 422 |

规则已更新：展示时内部空格保留，但比较时忽略所有空白。
React 学习、React  学习和 React学习现在视为同名。
不要用敏感资料测试；无需把密码或 Cookie 发给导师。
当前没有文档、向量和学习会话表，删除关联数据的验证在对应模块补齐。

## 任务 4：读四个文件（约 5 分钟）

| 文件 | 找到这个逻辑 |
| --- | --- |
| [routes_knowledge_bases.py](../apps/api/app/api/routes_knowledge_bases.py) | URL 对应哪个函数，哪里取得当前账号 |
| [schemas/knowledge_base.py](../apps/api/app/schemas/knowledge_base.py) | 长度、空值及 PATCH 的字段约束 |
| [knowledge_base_service.py](../apps/api/app/services/knowledge_base_service.py) | 查询怎样限定 user_id，重名怎样回滚 |
| [models/knowledge_base.py](../apps/api/app/models/knowledge_base.py) | name、name_key 和联合唯一约束 |

请求经过：路由 → 登录依赖/参数校验 → service → 数据库 → 响应。
name 保存展示名称；name_key 保存去首尾空格、casefold 后的比较值。
数据库唯一约束防止两个同时到达的创建请求绕过重名规则。
user_id 从登录会话取得，不能交给前端指定；UUID 本身不等于访问权限。

## 回复验收结果

完成后按下面格式回复，我们确认本模块后再开始 2.2 知识库页面：

```text
迁移版本：
创建接口状态：
重复名称状态：
改名后描述是否保留：
退出后列表状态：
删除后详情状态：
我不理解的一个地方：
```

本轮没有前端页面变化。工作台原先的零计数仍是第一阶段空状态，
模块 2.2 再替换为真实知识库数据，不以当前空状态判断 API 是否成功。

## 可选：自己跑测试

```powershell
cd C:\Users\nrx\Desktop\demo\devdocs-ai\apps\api
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check app tests
```

没有设置 TEST_DATABASE_URL 时为 39 passed / 2 skipped。
包含真实 PostgreSQL 两项测试的本轮结果为 41 passed。
迁移测试创建 devdocs_kb_test_ 前缀的独立数据库并清理，需要测试账号有 CREATEDB 权限；
默认 Docker 开发账号具备该权限。普通 SQLite API 测试不修改开发数据。
