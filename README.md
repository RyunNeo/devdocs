# DevDocs AI

面向开发者的技术文档 AI 学习导师。
需求依据：[项目蓝图](./devdocs-ai-project-blueprint.md)。

## 当前进度

第一阶段已经实现：Next.js / TypeScript / Tailwind 前端、FastAPI 后端、
PostgreSQL + pgvector、本地迁移、注册登录、退出、会话保持及受保护控制台。
知识库、文档、问答、会话体验、个人用量与配额以及质量评测模块已通过用户验收；本机生产构建部署和成对备份隔离恢复已完成，公网部署与开发者试用待办。
当前不是完整 RAG MVP。

配置教学、启动命令、代码阅读路径和验收步骤见
[第一阶段指南](./outputs/stage-01-guide.md)。

## 本地启动

先启动 Docker Desktop，在根目录：

```powershell
docker compose up -d postgres
npm.cmd ci
```

后端终端：

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

前端终端，在根目录：

```powershell
npm.cmd run dev
```

前端为 http://127.0.0.1:3001，API 文档为 http://127.0.0.1:8000/docs。
重建 Python 环境的完整步骤见指南。本地开发默认配置可运行，无需模型 API Key。

## 目录

- apps/web：Next.js 页面、组件、请求和浏览器验收。
- apps/api：FastAPI、SQLAlchemy、Alembic、后端测试和后续 RAG 模块。
- packages/shared：后续共享类型位置。
- docs/stages：六阶段任务与验收项。
- infra：数据库初始化与后续部署位置。
- evals：后续评测集。
- outputs：用户可阅读的目录说明与配置指南。

## 六阶段状态

| 阶段 | 目标 | 状态 |
| --- | --- | --- |
| 1 | 工程、数据库、认证 | 已实现并验证 |
| 2 | 知识库、MD/TXT 上传 | 已通过用户验收 |
| 3 | PDF、分块、Embedding | 已通过用户验收 |
| 4 | 检索、流式引用问答 | 核心流程已通过用户验收；持续评测待后续阶段 |
| 5 | 会话历史、日志、用量 | 已通过用户验收 |
| 6 | 部署、评测、试用 | 评测模块已验收；本地部署与隔离恢复通过，公网部署及试用待办 |

每周 5–10 小时。先亲自完成第一阶段验收，再进入阶段 2。

第二阶段逐模块开发。本轮的知识库后端练习见
[模块 2.1 指南](./outputs/stage-02-module-01-guide.md)，用户执行迁移并验收后再推进页面。
当前页面练习：[模块 2.2 表格列表](./outputs/stage-02-module-02-list-guide.md)。
最新小步：[创建弹窗](./outputs/stage-02-module-02-create-guide.md)。
最新规则修正：[名称忽略所有空白](./outputs/knowledge-base-name-whitespace-guide.md)。
当前小步：[编辑弹窗](./outputs/stage-02-module-02-edit-guide.md)。

后续按完整流程划分模块，集中验收，不再逐项拆分回合。

当前流程：[MD/TXT 上传与解析](./docs/stages/02-upload-guide.md)。默认无需模型密钥。

第三阶段：[PDF 与向量索引配置](./docs/stages/03-indexing-guide.md)。使用硅基流动BAAI/bge-m3；密钥仅在后端。

第四阶段：[检索与流式问答](./docs/stages/04-rag-chat-guide.md)。回答使用deepseek-ai/DeepSeek-V4-Flash；复用后端密钥。

当前模块：[会话体验与历史恢复](./docs/stages/05-chat-experience-guide.md)。无需新迁移，未校验草稿不对外展示。

文档管理增强：[多文件上传与批量索引、删除](./docs/stages/document-batch-guide.md)。逐文件处理并汇总结果，无需新迁移。

已验收模块：[个人用量、日志与每日配额](./docs/stages/05-usage-guide.md)。迁移0007及后端重启已完成。

当前模块：[本地生产部署演练](./docs/stages/06-local-production-guide.md)。主入口 http://127.0.0.1:3100，独立恢复入口 http://127.0.0.1:3101；备份已实际还原并核对版本、业务表数量和原文件哈希，没有新增业务迁移或自动调用付费模型。

## 依赖与验证

前端使用 package-lock.json；后端使用 pyproject.toml 和 requirements.lock.txt。
后台开发服务不是部署。配置文件不提交 Git，生产需使用 HTTPS 和正式凭据。
