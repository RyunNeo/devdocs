# 阶段 2：知识库与上传

预算：每周 5–10 小时。状态：知识库CRUD、MD/TXT上传与解析链路已通过用户验收。

本阶段改为逐模块推进，详见 docs/stages/02-modules.md（项目根目录）。
2.1 知识库 API → 2.2 知识库页面 → 2.3 MD/TXT 上传 → 2.4 文档处理状态。
2.2 已实现列表、创建、编辑与删除确认。后续按完整流程交付，集中验收。
2.3–2.4 已合并实现 MD/TXT 上传与解析状态链路，配置及集中验收见02-upload-guide.md。
下面的阶段总验收等待用户执行迁移与上传实测，不以自动化替代用户验收。

## 主要位置

- `apps/web/app/(workspace)/knowledge-bases`
- `apps/web/components/knowledge-bases`
- `apps/web/components/documents`
- `apps/api/app/api/routes_knowledge_bases.py`
- `apps/api/app/api/routes_documents.py`
- `apps/api/app/services/document_service.py`
- `apps/api/app/rag/loaders.py`
- `apps/api/app/workers/document_worker.py`

## 开发任务

- [x] 实现知识库 CRUD、所属校验、模型迁移和对应页面。
- [x] 实现 MD/TXT 上传、10 MiB 校验、内容哈希、私有存储和文档状态。
- [x] 当前采用请求内同步解析并记录失败，不作为生产可靠队列。
- [x] 解析状态parsed与未来向量就绪completed区分。

## 功能验收

- [x] 用户可创建知识库并上传 MD/TXT，看到真实处理状态。
- [x] 错误类型、超限文件有提示；另一用户无法读取或删除资源。
