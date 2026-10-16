# DevDocs AI 项目目录与阶段说明

当前状态：第一阶段已实现并验证，第二至六阶段的占位模块仍待实现。
已有蓝图保持原位。每阶段预算为 5–10 小时，开发清单见 docs/stages。

```text
devdocs-ai/
├── devdocs-ai-project-blueprint.md
├── README.md
├── .editorconfig
├── .gitignore
├── docker-compose.yml
├── apps/
│   ├── web/
│   │   ├── .env.example
│   │   ├── app/
│   │   │   ├── (auth)/{login,register}/
│   │   │   └── (workspace)/
│   │   │       ├── dashboard/
│   │   │       ├── knowledge-bases/
│   │   │       │   └── [id]/chat/
│   │   │       └── settings/
│   │   ├── components/{ui,auth,knowledge-bases,documents,chat,conversations}/
│   │   ├── lib/{api,auth,stream}.ts
│   │   ├── hooks/
│   │   ├── styles/
│   │   ├── public/
│   │   └── tests/e2e/
│   └── api/
│       ├── .env.example
│       ├── app/
│       │   ├── main.py
│       │   ├── core/{config,security,logging}.py
│       │   ├── api/{deps,routes_auth,routes_knowledge_bases,routes_documents,
│       │   │        routes_chat,routes_conversations}.py
│       │   ├── models/{user,knowledge_base,document,chunk,conversation,message}.py
│       │   ├── schemas/{auth,knowledge_base,document,chat,conversation}.py
│       │   ├── services/{auth_service,knowledge_base_service,document_service,
│       │   │             chat_service,conversation_service,usage_service}.py
│       │   ├── rag/{loaders,splitter,embeddings,retriever,prompts,chain}.py
│       │   ├── workers/document_worker.py
│       │   └── db/{base.py,session.py,migrations/versions/}
│       ├── tests/{unit,integration}/
│       └── storage/uploads/
├── packages/shared/types/{auth,knowledge-base,document,chat,conversation}.ts
├── docs/
│   ├── prd.md
│   ├── api.md
│   ├── rag.md
│   ├── implementation-plan.md
│   └── stages/
│       ├── 01-foundation.md
│       ├── 02-documents.md
│       ├── 03-embeddings.md
│       ├── 04-rag-chat.md
│       ├── 05-history.md
│       └── 06-release.md
├── infra/
│   ├── postgres/init/001-pgvector.sql
│   └── deploy/
├── evals/{datasets,fixtures,results}/
└── outputs/project-structure.md
```

树中的花括号是多个实际文件/目录的简写，不是字面路径。
各空目录用 README.md 或 .gitkeep 保留，Python 包有 __init__.py。

| 阶段 | 重点 | 交付验收 |
| --- | --- | --- |
| 1 | 工程初始化、认证和数据库 | 注册、登录、健康检查 |
| 2 | 知识库和 MD/TXT 上传 | 资源隔离、上传与状态 |
| 3 | PDF、分块、Embedding | 向量及定位元数据入库 |
| 4 | RAG 和流式引用问答 | 检索、引用、无依据拒答 |
| 5 | 历史和用量日志 | 刷新恢复、错误与用量追踪 |
| 6 | 部署和评测 | 完整流程、20–30 条评测、试用反馈 |

第 1 阶段已新增 package.json、Next.js 配置、Python pyproject.toml、依赖锁文件、
实际页面、认证 API、auth_sessions 模型和 0001_auth 迁移。上面的树为最初目录骨架，
当前启动和配置请查看同目录 stage-01-guide.md。
第 4 阶段先建立会话/消息基础表，以支持问答持久化；第 5 阶段补齐历史界面。
数据库 compose 使用蓝图中的 pgvector/pgvector:pg16，仅用于本地开发。
