# 阶段 5：历史、日志与体验

预算：每周 5–10 小时。状态：会话与文档管理体验、日志、个人用量与配额均已通过用户验收。
真实数据库已迁移至 `0007_usage_events_counters`，后端已重启并加载用量接口。

## 主要位置

- `apps/web/components/conversations`
- `apps/web/app/(workspace)/settings`
- `apps/api/app/api/routes_conversations.py`
- `apps/api/app/services/conversation_service.py`
- `apps/api/app/services/usage_service.py`
- `apps/api/app/core/logging.py`

## 开发任务

- [x] 补齐会话列表、恢复消息、多轮追问与刷新恢复。
- [x] Enter发送/Shift+Enter换行、输入法保护、校验后发布、处理阶段和旧草稿隐藏。
- [x] 记录已知 token、检索和模型耗时，缺失用量保留未知，日志脱敏并关联请求。
- [x] 实现配额检查，补齐空状态、加载态和可重试失败态。
- [x] 明确流式失败或用户断开时消息持久化规则，不把半截回答标记完成。

## 功能验收

- [x] 刷新、切换会话能恢复消息与引用。
- [x] 用户看懂失败原因；日志可定位错误且不含密码、密钥和完整私有文档。
