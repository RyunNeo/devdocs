# 第四阶段检索与流式问答实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 完成知识库提问、检索、流式回答、引用查看和会话内追问的完整链路。

**Architecture:** 沿用同步 SQLAlchemy 短事务，在异步模型调用期间不持有数据库连接或锁。
模型客户端、检索器、引用校验和流式持久化各自独立；前端通过现有 Next.js 代理读取 POST SSE。

**Tech Stack:** Next.js 16.4 / React 19.3 / TypeScript / FastAPI / Python / HTTPX / LangChain Embeddings / PostgreSQL / pgvector。

**Spec:** `docs/stages/04-rag-chat-design.md`，用户于 2026-10-14 确认通过。

## Global Constraints

- 回答模型 `deepseek-ai/DeepSeek-V4-Flash`；Embedding `BAAI/bge-m3`、1024 维。
- 复用 `SILICONFLOW_API_KEY`，不打印密钥，不覆盖已有 `.env`。
- 本轮问题 1–2000 字符；top_k=5（1–8）；最低相似度 0.35（0–1）。
- 检索上下文最多 12000 UTF-8 字节；最近 3 个 completed 问答对、最多 6000 字符。
- 检索问题最多 4000 字符；输出初值 1024 tokens。
- 外部调用总预算 90 秒；连接 5 秒、空闲读取 20 秒；前端 110 秒、代理 120 秒。
- 供应商单帧 64 KiB、总流 1 MiB；无自动重试；本地单进程最多 2 个生成请求。
- 同会话单活跃 run，180 秒过期；单会话读取最新 40 条消息，含 has_older。
- 无匹配分块时不调用回答模型；停止/失败/无终态不能冒充完成。
- 自动化使用假模型和隔离数据库；用户执行真实数据库迁移和付费模型验收。
- 不改变已验收的分块、上传、认证及名称规则；不实现历史列表和 Agent。
- 本目录暂无 Git 仓库，不自行初始化仓库或创建提交；每项用测试结果记录检查点。

## Review Focus

1. 中文字符被网络分片截断、CRLF 或多行 data：不得乱码、漏帧或重复输出（任务 3、5）。
2. 停止恰好与成功结束竞争：只有一个持久化终态，取消不得覆盖已完成答案（任务 4）。
3. 文档/知识库在生成期间删除或重建：不复活记录、不将旧快照冒充当前版本（任务 2、4）。
4. 供应商返回 HTTP 200 但流内报错/截断/只有推理字段：显示安全失败，不生成 done（任务 3、4）。
5. 前端断线但服务端已保存成功：刷新通过读取会话恢复真实状态，不自动重复收费（任务 4、5）。

## 文件与模块边界

- 模型和迁移：`models/conversation.py`、`models/message.py`、`app/db/migrations/versions/0006_conversations_messages.py`。
- 会话短事务：`services/conversation_service.py`；检索：`rag/retriever.py`。
- 提示词：`rag/prompts.py`；引用：新增 `rag/citations.py`；供应商：新增 `rag/chat_model.py`。
- 供应商和应用 SSE 编解码：新增 `rag/stream_protocol.py`。
- 链路：`rag/chain.py`；运行生命周期：`services/chat_service.py`；路由：已有 chat/conversations 占位文件。
- 前端：`components/chat/` 下拆分 Workspace、Composer、MessageList、CitationDialog。
- 共享契约：`packages/shared/types/chat.ts`、`conversation.ts`；前端解码：`apps/web/lib/stream.ts`。
- 新增测试位于现有 unit/integration/e2e 目录，不添加第二套测试框架。

以下后端路径以 `apps/api/app/` 为前缀；后端命令从 `apps/api` 执行并使用 `.venv/Scripts/python.exe`。
前端命令从仓库根目录执行。每项按先失败测试、最小实现、通过测试的顺序完成。

## 任务 1：会话数据和安全读取

**Files:** 模型、迁移、`schemas/conversation.py`、`services/conversation_service.py`、
`api/routes_conversations.py`、`main.py`、`app/db/migrations/env.py`，新增
`tests/integration/test_conversations.py`、`test_chat_migration.py`。

**Interfaces:**
- `create_conversation(db: Session, user_id: UUID, kb_id: UUID) -> Conversation`。
- `read_conversation(db: Session, user_id: UUID, conversation_id: UUID) -> ConversationDetail`。
- `ConversationDetail`：id、knowledge_base_id、时间、messages、has_older。
- `MessageRead`：id、role、content、status、run_id、sequence、citations、model、usage、error_code、时间。

- [ ] 添加失败测试 `test_create_read_owned_conversation`：创建 201、读取 200、空 messages；匿名 401、非所属 404。
- [ ] 添加 `test_read_latest_40_messages`：42 条返回序号 3–42、has_older=true；少于 40 条为 false。
- [ ] 运行 `python -m pytest tests/integration/test_conversations.py -q`，确认因业务缺失而失败。
- [ ] 实现两个模型、role/status CHECK、sequence 唯一约束和级联外键，创建 0006 迁移；最新 40 条先倒序取再升序展示。
- [ ] 实现创建/读取接口；读取超过 180 秒的 streaming 消息时清理为 failed/interrupted 并释放同 run 租约。
- [ ] 在隔离 PostgreSQL 测试 0005 → 0006 → 0005：旧文档保留，新增表可升降级；同时验证知识库级联删除。
- [ ] 运行两个新测试文件，预期全通过；记录检查点，不执行用户库迁移。

## 任务 2：检索、上下文和引用

**Files:** `rag/retriever.py`、`rag/prompts.py`、新增 `rag/citations.py`、`core/config.py`、
`tests/unit/test_retrieval_context.py`、`tests/integration/test_chat_retrieval.py`。

**Interfaces:**
- `RetrievedSource` dataclass：number、document_id、chunk_id、chunk_index、filename、content、metadata、similarity。
- `retrieve_sources(db: Session, user_id: UUID, kb_id: UUID, vector: list[float], settings: Settings) -> list[RetrievedSource]`。
- `build_retrieval_query(question: str, history: list[MessageRead]) -> str`。
- `build_prompt_messages(question: str, history: list[MessageRead], sources: list[RetrievedSource]) -> list[dict[str, str]]`。
- `validate_answer(text: str, sources: list[RetrievedSource]) -> ValidatedAnswer`，含 content、citations、insufficient；非法引用抛 `CitationError`。

- [ ] 添加 `test_only_current_owned_completed_index_is_retrieved`：放入外国用户、其他库、failed 索引和旧指纹分块，结果均不包含它们。
- [ ] 添加真实 PG cosine 排序/分数并列稳定排序测试；相似度 0.34 被排除，0.35 被保留。
- [ ] 添加上下文测试：UTF-8 字节 <=12000、完整分块、历史最多 3 对/6000 字符、failed/cancelled 不入提示词。
- [ ] 添加引用测试：`[1]` 对应真实来源；`[99]` 和实质答案无引用抛异常；仅约定标记 `[[INSUFFICIENT_EVIDENCE]]` 转固定拒答。
- [ ] 运行新测试，确认预期失败，再实现过滤 JOIN、指纹校验、上下文预算和结构化来源；相似度用 `1 - cosine_distance`。
- [ ] 实现提示词不可信资料边界和固定拒答规则，引用校验只证明编号存在，不声称事实验证。
- [ ] 添加 `test_rebuilt_document_does_not_relabel_old_snapshot`，确保编号和正文绑定检索时快照。
- [ ] 运行两个新测试文件，预期全通过；PG 测试必须在随机隔离库执行。

## 任务 3：硅基流动流解析和预算

**Files:** 新增 `rag/chat_model.py`、`rag/stream_protocol.py`，修改 `core/config.py` 和安全模板，
新增 `tests/unit/test_chat_model.py`、`test_stream_protocol.py`。

**Interfaces:**
- `ProviderEvent` dataclass：kind 为 token/finish/usage，data 为 dict。
- `SiliconFlowChatModel(settings: Settings, transport: httpx.AsyncBaseTransport | None = None)`。
- `astream(messages: list[dict[str, str]], deadline: float) -> AsyncIterator[ProviderEvent]`。
- `encode_sse(event: str, payload: dict) -> bytes`；供应商解码器支持 UTF-8 增量读取和完整帧缓冲。
- `ChatModelError(code: str, message: str)`，消息仅使用安全中文文案。

- [ ] 添加 MockTransport 测试，断言固定地址、用户指定模型、stream=true、输出上限 1024、无自动重试。
- [ ] 测试任意字节分片、中文跨片、CRLF、多行 data、注释、usage；reasoning_content 不变成 token。
- [ ] 测试只有 reasoning、HTTP 200 内 error、finish_reason=length、缺成功终态、畸形 JSON、超大帧/总流均安全失败。
- [ ] 运行新单元测试，确认预期失败。
- [ ] 核对硅基流动官方当前请求字段；实现固定 URL、SecretStr 内部取值、trust_env=false、follow_redirects=false。
- [ ] 实现共享绝对 deadline，连接 5 秒、空闲读取 20 秒、单帧 64 KiB/总流 1 MiB；取消时关闭 HTTP 流。
- [ ] 在配置和 `.env.example` 增加非敏感默认值，不读出/覆盖实际密钥；API 请求只发送答案所需消息。
- [ ] 运行新单元测试；断言错误响应不包含测试密钥和供应商原文。

## 任务 4：完整问答运行和持久化

**Files:** `rag/chain.py`、`services/chat_service.py`、会话服务、chat 路由及 schema、main、
`services/knowledge_base_service.py`，新增 `tests/integration/test_chat.py`、`test_chat_postgres.py`。

**Interfaces:**
- `ChatRuntime`：本地并发槽（2）、run_id 对应取消 Event 和心跳控制，不保存数据库 Session。
- `claim_chat_run(db: Session, user_id: UUID, conversation_id: UUID, question: str, request_id: UUID) -> ChatRun`。
- `ChatRun`：run_id、conversation_id、assistant_message_id、knowledge_base_id、user_id、question。
- `stream_chat(run: ChatRun, session_factory: sessionmaker, settings: Settings, runtime: ChatRuntime) -> AsyncIterator[bytes]`。
- `cancel_chat_run(db: Session, user_id: UUID, conversation_id: UUID, run_id: UUID, runtime: ChatRuntime) -> None`。

- [ ] 测试登录/所属/无配置前置错误、同会话并发 409、request_id 重复 409、全局槽超限 429。
- [ ] 测试无可检索分块的固定拒答：回答客户端调用次数为 0；确认未索引库连 Embedding 也不调用。
- [ ] 测试正常事件 `meta → token* → citations → done`，done 前已在另一 DB Session 读到 completed。
- [ ] 测试错误/引用非法/缺终态只发 error、不发 done；部分正文保存为 failed，usage 可空。
- [ ] 运行新集成测试，确认预期失败。
- [ ] 实现短事务 claim、顺序消息写入、180 秒租约恢复、固定 request_id/run_id，网络调用期间关闭数据库 Session。
- [ ] 实现总预算 90 秒（Embedding 和生成共享），定时 10 秒心跳；持久化终态使用 run_id 条件更新。
- [ ] 实现停止接口、断线取消和 KB 删除通知；取消只能更新该 run 的 streaming 消息。
- [ ] 添加取消/完成竞争、KB 删除/迟到结果、同 run 超时清理后新 run 不被覆盖测试，预期唯一终态且无复活。
- [ ] 添加故障恢复测试：done 发送失败但 DB 已 completed，读取仍返回 completed；不得自动重试模型。
- [ ] 添加日志捕获测试，确认日志无问题/正文/密钥；补充请求 ID、耗时、数量和安全错误码。
- [ ] 运行 API 和 PG 集成测试，预期全通过；健康 ready 增加新表检查。

## 任务 5：流式问答页面和引用交互

**Files:** `apps/web/app/(workspace)/knowledge-bases/[id]/chat/page.tsx`、该库详情页面、
新增 `components/chat/chat-workspace.tsx`、`chat-composer.tsx`、`message-list.tsx`、`citation-dialog.tsx`，
`lib/stream.ts`、共享 chat/conversation 类型，新增 `tests/e2e/chat.spec.ts`、`stream-parser.spec.ts`。

**Interfaces:**
- `ChatEvent` 为 meta/token/citations/done/error 判别联合，字段与任务 4 保持一致。
- `readChatStream(response: Response, onEvent: (event: ChatEvent) => void, signal: AbortSignal) -> Promise<void>`。
- `ChatWorkspace({ knowledgeBaseId }: { knowledgeBaseId: string })`；会话 ID 使用 URL query `conversation`。
- CitationDialog 只展示当前用户会话中的服务端快照，原文删除/重建时显示状态提示。

- [ ] 阅读 `apps/web/AGENTS.md` 及本地 Next 文档的路由/query/代理相关指南后再写前端代码。
- [ ] 使用 Playwright 测试流解析器：中文每字节切片仍等于原文；CRLF/多行 data/缺 done/非法帧有明确结果。
- [ ] 添加页面测试：首次进入不创建会话、首次发送只创建一次、URL 保存 ID、重复发送被禁用。
- [ ] 运行两个新测试文件，确认因页面/解析器缺失而失败。
- [ ] 实现 110 秒等待和 AbortController、纯文本草稿、完成状态、错误/结果未知；仅 done 标记成功。
- [ ] 实现停止同时 abort 和独立取消请求；先收到 done 的 completed 不被取消回调覆盖。
- [ ] 实现单会话刷新恢复、最近消息 has_older 提示但不加历史分页，401 返回登录、404 显示不可访问。
- [ ] 实现编号点击快照弹窗、标题/页码、删除/重建提示；只为校验通过来源提供交互。
- [ ] 测试停止、断线后刷新、引用非法、纯文本 XSS、空库提示和追问，模型使用隔离假服务。
- [ ] 在 1440x900 和 390x844 截图检查：输入/按钮/正文/弹窗不重叠、不横向溢出，移动端能关闭引用。
- [ ] 运行 `npm run typecheck` 和新浏览器测试，预期全通过。

## 任务 6：回归与用户验收交付

**Files:** 新增 `docs/stages/04-rag-chat-guide.md`，更新阶段入口、`docs/api.md`、`README.md`。
测试辅助脚本置于 `work/`，沿用隔离 API 8002、前端 3002，不替换用户 8000/3001 服务。

- [ ] 自审设计覆盖：API、租约、输入限额、取消、引用、安全、数据删除和配置逐项对应实际测试。
- [ ] 在隔离库运行 `python -m pytest tests -q`；对 PG 专项设置临时库连接，任何遗留用例不可指向用户库。
- [ ] 运行 `python -m ruff check app tests`、`npm run typecheck`、`npm run build`，预期退出码均为 0。
- [ ] 启动隔离假模型服务，使用 `E2E_BASE_URL` 运行 `npm run test:e2e`；报告通过数量和真实跳过原因。
- [ ] 停止隔离测试服务、关闭测试浏览器，确认无遗留测试数据库；保留用户服务不动。
- [ ] 写配置指南：现有密钥可复用、CHAT_MODEL 默认指定模型、0006 升级命令和重启时机；不声称账号权限已验证。
- [ ] 写验收表：5 个有据问题、3 个无关问题、2 组追问、停止、刷新恢复、Markdown/PDF 引用。
- [ ] 交付说明注明真实费用、取消不保证零费用、阈值非置信度、无事实验证/生产分布式限流。
- [ ] 等用户迁移和配置确认后，再核对并重启所属后端；真实问答由用户主动提交，不自行调用。

## 执行与参与方式

内部按上面 6 项推进，但对用户作为一个完整问答模块交付，不要求逐个小步骤回复。
建议助手在当前会话直接执行，顺序完成紧密依赖的接口和前后端集成；可用的独立审查工具只用于最终审查。
计划审核通过前不开始业务代码实现。下一次用户确认后，保留其选择的执行方式，不再重复询问模块范围。
