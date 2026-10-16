# DevDocs AI 分阶段目录实施计划

本文件记录 2026-10-10 的目录生成工作。2026-10-12 第一阶段已实现，当前代码与配置
以 docs/stages/01-implementation.md 和 outputs/stage-01-guide.md 为准。

需求依据：根目录 devdocs-ai-project-blueprint.md 第 10、18 节和本次用户请求。
本轮目标是生成可继续开发的目录和模块位置；六阶段功能实施另行逐步完成。

## 本轮交付检查

- 创建 apps/web、apps/api、packages/shared 和 docs。
- 按路由预留前端页面目录，按蓝图预留后端模块。
- 为模块注明开发阶段和职责。
- 添加本地数据库 compose、pgvector 初始化和无密钥环境示例。
- 为六阶段列出开发位置、任务和验收标准。
- 验证目录完整、JSON/脚本占位无伪业务逻辑，保留原始蓝图。

## 阶段导航

- [阶段 1：骨架与认证](./stages/01-foundation.md)
- [阶段 2：知识库与上传](./stages/02-documents.md)
- [阶段 3：分块与向量入库](./stages/03-embeddings.md)
- [阶段 4：检索与流式问答](./stages/04-rag-chat.md)
- [阶段 5：历史、日志与体验](./stages/05-history.md)
- [阶段 6：部署、评测与试用](./stages/06-release.md)

## 约束

页面、认证、上传、模型请求等尚未实现；不能运行完整应用。
先在阶段 1 确定依赖版本并生成锁文件，不写虚构依赖版本。
本轮不安装依赖、不调用模型 API、不部署或提交 Git。
