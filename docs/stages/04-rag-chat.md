# 阶段 4：检索与流式问答

预算：每周 5–10 小时。状态：链路已实现，待用户0006迁移和真实问答验收。
配置与验收见 `04-rag-chat-guide.md`，已确认设计和实施计划见同目录对应文档。

## 主要位置

- `apps/web/app/(workspace)/knowledge-bases/[id]/chat`
- `apps/web/components/chat`
- `apps/web/lib/stream.ts`
- `apps/api/app/api/routes_chat.py`
- `apps/api/app/services/chat_service.py`
- `apps/api/app/rag/retriever.py`
- `apps/api/app/rag/prompts.py`
- `apps/api/app/rag/chain.py`
- `apps/api/app/models/conversation.py`
- `apps/api/app/models/message.py`

## 开发任务

- [x] 创建会话和消息表基础，支持第一次问答；历史列表与体验在阶段 5 完成。
- [x] 实现按用户和知识库过滤的查询向量检索；样本阈值校准留待用户验收。
- [x] 实现依据不足提示、基础多轮处理、来源编号和实际引用校验。
- [x] 实现 fetch POST 流式协议、meta/token/citations/done/error 事件和前端完整帧缓冲。

## 功能验收

- [ ] 基于上传文档流式回答，引用可定位原文。
- [ ] 无依据时拒答；跨用户资源不可访问；流中断可识别失败。
