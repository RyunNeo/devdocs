# 日志、个人用量与每日配额 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有问答、索引链路中加入持久化次数配额、可追踪的用量记录、脱敏日志和个人用量页面。

**Architecture:** 受理事务原子占额并登记操作，供应商调用不持有数据库事务。独立操作记录不依赖文档或会话存活；阶段指标通过受控上下文传递，结束时幂等写入。前端使用只读个人接口展示次数与已知 Token，不作为账单。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、PostgreSQL/SQLite、Python logging/contextvars、Next.js/TypeScript、Playwright；不新增第三方平台或前端依赖。

**Spec:** `docs/superpowers/specs/2026-10-15-usage-observability-design.md`（已通过用户确认）。

**Execution:** 六个环节已实现。执行证据与两处审查修复见 `work/usage-observability-ledger.md`；用户真实数据库未迁移，下一步按 `docs/stages/05-usage-guide.md` 迁移和验收。

## Global Constraints

- `DAILY_CHAT_LIMIT=50`、`DAILY_INDEX_LIMIT=20`，均为每账号每日的逻辑任务次数，取值为正整数。
- 自然日采用固定 UTC+08:00，以受理时间归属当天；跨日完成不会扣第二天次数。
- 受理并提交占额后，即使失败、取消或断连也不退还次数。
- 空知识库本地完成的有效问答也占一次；复用索引、无权请求、重复 request_id 不重复占额。
- 缺失或部分未知的 Token 不记为 0，不按字符估算，不展示金额。
- 不记录正文、文件名、密码、密钥、Cookie、Authorization、连接串、查询参数或供应商原始响应。
- 不新增分布式任务系统或收费系统，不改变答案校验、打字机效果和批量任务规则。
- 不读取、输出或编辑真实 `.env` / `.env.example`；不迁移用户真实数据库，不调用真实模型。
- 当前目录不是 Git 仓库。不初始化仓库、不执行提交；各任务以测试证据作为检查点。
- 使用 apply_patch 手工编辑，遵循现有页面布局与图标约定，修改 Next.js 前查阅安装版本文档。

## Review Focus

1. 多 worker 同时争抢最后一次额度：只能一个受理，失败事务不得遗留占额（任务 1、2）。
2. 删除资源、过期恢复与晚到写入竞争：记录保留、结束只发生一次，不因资源消失返还配额（任务 2、3）。
3. 已有索引已完成或接口 HTTP 200 但业务失败：分别不重复扣次、不能误记成功（任务 3）。
4. 日志请求上下文跨并发请求、SSE 和线程泄漏：编号隔离、终态单独记录、敏感哨兵不出现（任务 4）。
5. Token 为 bool/负数/缺失或分批数据不完整：拒绝非法指标，只汇总已知值并保留未知范围（任务 1、3、5）。

## 文件与边界

- 数据及配额：`apps/api/app/models/usage.py`、现有 `services/usage_service.py`、`schemas/usage.py`。
- 测量上下文：`apps/api/app/core/usage_context.py`；不改变已有 provider factory 的函数签名。
- 链路接入：现有 `services/chat_service.py`、`services/indexing_service.py`、`rag/embeddings.py`、`rag/chat_model.py` 和对应路由。
- 脱敏日志：现有 `core/logging.py`、`main.py`；请求编号显式传入任务，不靠请求结束后仍存在的上下文。
- 查询与页面：新增 `api/routes_usage.py`、`packages/shared/types/usage.ts`、`apps/web/app/(workspace)/settings/usage/page.tsx`、`components/usage/usage-workspace.tsx`。
- 配置教学与验收：`docs/stages/05-usage-guide.md`、README、阶段状态、隔离测试夹具。

## 任务 1：持久化记录、原子占额与数据口径

**Files:**
- Create: `apps/api/app/models/usage.py`
- Create: `apps/api/app/db/migrations/versions/0007_usage_events_counters.py`
- Create: `apps/api/app/schemas/usage.py`
- Create: `apps/api/app/core/usage_context.py`（先定义 UsageMetrics；任务 2 扩展 recorder）
- Modify: `apps/api/app/models/__init__.py`、`apps/api/app/core/config.py`、`apps/api/app/services/usage_service.py`
- Test: `apps/api/tests/unit/test_usage_metrics.py`、`apps/api/tests/integration/test_usage_quota.py`、`apps/api/tests/integration/test_usage_postgres.py`

**Interfaces:**
- `usage_day(now: datetime) -> date`、`quota_reset_at(now: datetime) -> datetime`；结果采用 UTC+08:00 日界，reset_at 返回带时区 UTC 时间。
- `reserve_operation(db: Session, user_id: UUID, operation: Literal['chat','index'], run_id: UUID, request_id: str, settings: Settings, *, knowledge_base_id: UUID | None = None, conversation_id: UUID | None = None, document_id: UUID | None = None, now: datetime | None = None) -> UsageEvent`：只 flush、不 commit，由受理方提交或回滚。
- `finish_operation(factory, event_id: UUID, status: str, metrics: UsageMetrics, error_code: str | None = None, *, finished_at: datetime | None = None) -> bool`：独立短事务，仅更新 running，返回是否变更。
- `expire_usage_events(db: Session, user_id: UUID, now: datetime, settings: Settings) -> int`：只清理本账号；chat/index 窗口分别为 `chat_timeout_seconds + 180`、`indexing_timeout_seconds + 300` 秒。
- `UsageMetrics` 在 `core/usage_context.py` 先建立最小 dataclass；字段沿用任务 2 的 Interfaces，不在各链路复制。

- [ ] 编写失败测试：默认配额为 50/20、0 和负值配置失败；本地日期在 UTC 16:00 正确切换；limit=1 时第二次占额返回 429，`detail` 是字符串，包含 `code=daily_quota_exceeded`、`operation`、`reset_at`。
- [ ] 运行新测试，确认因新模型或服务缺失而失败，记录红灯证据。
- [ ] 建立 `UsageEvent` 和 `DailyUsageCounter`。事件字段为设计中的 ID/归属/状态/时间，指标采用 `durations_ms`、`models`、`attempts`、`token_usage` JSON；非适用指标为 null。只建立 user_id 的 CASCADE 外键，资源 ID 是可空 UUID 快照。operation/run_id 唯一，日计数 user/day/operation 唯一，加入非负与枚举约束。
- [ ] 实现 PostgreSQL/SQLite 方言安全的 insert-on-conflict-do-nothing，然后 `UPDATE ... WHERE used_count < limit`。额度检查、事件插入和现有受理失败必须一起回滚。不要通过 SUM(events) 或进程锁占额。
- [ ] 新增迁移 revision `0007_usage_events_counters`，down_revision 为 `0006_conversations_messages`；测试从 0006 升级保留消息、降回 0006 只删除新增表，并执行 alembic check。
- [ ] 定义 `normalize_token_usage(raw: object) -> dict[str, int | None]`，只接收实际整数（拒绝 bool）、非负值；不合计缺失项冒充完整 total，不同时合计 total 与 prompt/completion，保留 completeness。
- [ ] PostgreSQL 隔离数据库测试：两独立连接争抢最后一次额度，恰好一个成功；一个事务占额后抛出异常，回滚后仍可占额；重复唯一键失败不多扣；新建 App 后计数仍在。不在用户库运行测试。
- [ ] 验证：`python -m pytest tests/unit/test_usage_metrics.py tests/integration/test_usage_quota.py tests/integration/test_usage_postgres.py -v`；PostgreSQL 用既有 TEST_POSTGRES_ADMIN_URL 机制，未配置应明确 skip，不把 skip 当并发通过。

## 任务 2：问答受理、阶段测量与独立终态

**Files:**
- Modify: `apps/api/app/core/usage_context.py`
- Modify: `apps/api/app/services/chat_service.py`、`apps/api/app/services/conversation_service.py`、`apps/api/app/rag/chain.py`、`apps/api/app/api/routes_chat.py`
- Test: `apps/api/tests/integration/test_chat_usage.py`、既有 `test_chat_lifecycle.py`、`test_answer_publication.py`

**Interfaces:**
- `UsageMetrics`：`durations_ms: dict[str, int | None]`、`models: dict[str, str]`、`attempts: dict[str, int]`、`token_usage: dict[str, dict]`，阶段键固定为 query_embedding/chat/index_embedding，耗时另含 retrieval/validation/total/index_processing。
- `UsageRecorder(factory, event_id: UUID)`：`stage(name: str)` 同步计时上下文、`before_provider(phase: str, model: str) -> Awaitable[None]`、`observe_tokens(phase: str, raw: object) -> None`、`snapshot() -> UsageMetrics`。
- `bind_usage(recorder: UsageRecorder)` 上下文管理器和 `current_usage() -> UsageRecorder | None`，ContextVar 以 token/reset 实现，线程通过现有 anyio.to_thread 保留上下文。
- `ChatRun` 增加 `usage_event_id` 和 `request_id`；`claim_chat_run(..., settings, request_id: str | None = None)` 保留直接调用兼容性；API 总是传服务端请求编号。

- [ ] 先写测试：额度用完时无新 Message、无外部调用；有效空库问答占 1 次、事件 local_completed、attempts 全为 0；重复 request_id 不重复扣额；失败/取消不退次数。
- [ ] 运行新测试确认失败，再在现有 claim 的合法性/去重/配置检查之后、commit 之前调用 reserve_operation。受理冲突让整个事务回滚。
- [ ] 实现 UsageRecorder；`before_provider` 在实际外部 HTTP 请求前以独立短事务持久化阶段尝试数，仅允许更新 running 行；已过期/取消或数据库失败则抛出可映射的安全任务失效错误，不发送该请求。内存度量不要持有 Session。
- [ ] 在 stream_chat 的 producer 绑定 recorder，用 monotonic/perf_counter 计时检索、问题向量化、模型、校验和总处理；总耗时不包括前端打字动画。只有明确无供应商尝试才记录 local_completed。
- [ ] 保留现有 message 保存与发布顺序；在成功、失败和取消路径独立调用 finish_operation。取消时使用现有 shield；消息已删除/租约已失效仍应结束 usage，不能依靠 finish_run 的 True 才结束记录。
- [ ] 显式跨 worker 取消时同步终结匹配 running 用量记录；既有会话过期恢复也更新对应操作，不新增提交点破坏受理事务。重复取消、晚到完成只结束一次。
- [ ] 测试“删除 KB 后 producer 收尾”“取消后 late done”“过期记录后 late finish”、保存失败和阶段未完成耗时为 null；日志及用量不保存草稿。旧成功答案不回填账本。
- [ ] 验证新测试和既有聊天/发布/历史测试；模型全部使用 fake 或 httpx.MockTransport，保持原有不发布未校验草稿的断言。

## 任务 3：索引占额、供应商指标与批量兼容

**Files:**
- Modify: `apps/api/app/services/indexing_service.py`、`apps/api/app/rag/embeddings.py`、`apps/api/app/rag/chat_model.py`、`apps/api/app/api/routes_documents.py`
- Test: `apps/api/tests/integration/test_index_usage.py`、`apps/api/tests/unit/test_embeddings.py`、`apps/api/tests/unit/test_chat_components.py`

**Interfaces:**
- `index_document(..., doc_id, request_id: str | None = None)`，旧调用兼容；使用 index_run_id 作为 operation_run_id。
- 两个 provider factory 签名保持不变，真实 HTTP 客户端通过 current_usage 访问任务上下文；无 recorder 时行为与以前一致。
- provider 每批请求前 await `before_provider`；分批 Embedding 用量按已验证 total 累加，缺失一个批次即 incomplete。没有可靠元数据则未知，不能新增模型调用补统计。

- [ ] 写失败测试：索引复用零新扣次；未解析/正在处理/配置缺失不占额；HTTP 200 + index_status=failed 记录 failed；失败后额度不退；超额时不改文档状态、不访问供应商。
- [ ] 确认红灯后，在复用/状态/配置检查完成后，将 reserve_operation、indexing 状态及 run_id 一起提交；随后才进入分块和外部处理。
- [ ] 在绑定 recorder 的作用域中执行索引，分别记录 index_processing、实际 Embedding 批次及 token；成功、失败和文档已删除均独立关闭账本。原有失败原因和旧片段保留规则不变。
- [ ] 在 chat_model/embeddings 已存在的 HTTP 循环中接入 recorder；解析允许的 usage 字段，拒绝负数/bool/不一致字段。不要修改响应完成/引用验证要求，或泄露 provider 原始响应。
- [ ] MockTransport 测试：两 Embedding 批次分别返回 usage、仅一个返回、第二批超时、401/429，验证尝试数、已知合计、完整性和不会重试。问题向量化与对话使用不同 phase，不重复合计 token。
- [ ] 批量索引测试：设置只剩一次额度，选两份新文档，只开始第一份；第二份 429，队列停止，第三份不请求。复用索引不减少余额；HTTP 200 的供应商业务失败继续沿用批量暂停规则。
- [ ] 验证新测试、现有 indexing/embedding/chat 测试及 `batch-documents.spec.ts`。

## 任务 4：请求编号和白名单日志

**Files:**
- Modify: `apps/api/app/core/logging.py`、`apps/api/app/main.py`、问答/索引/文档服务现有 logger 调用
- Test: `apps/api/tests/integration/test_request_logging.py`

**Interfaces:**
- `configure_logging() -> None`：幂等安装项目 JSON 白名单 formatter；不重复注册 handler，不打开 SQL echo。
- `safe_log(logger, event: str, **fields) -> None`：event 和字段来自固定允许集合，拒绝正文和任意异常字符串。
- 服务端每请求生成 UUID request_id，存 request.state，添加 X-Request-ID；路由把它传给任务。HTTP 完成及 task finished 为不同事件。

- [ ] 先写敏感哨兵测试：问题/答案/文件名/密码/头/查询串/SQL 参数/异常消息中放唯一字符串，捕获完整输出，断言哨兵均不出现且合法请求编号存在。
- [ ] 确认失败后实现 ASGI 请求包装或等效可验证 middleware，覆盖普通响应、流式 response.start/response.body、异常和客户端取消。恢复 ContextVar，未知路由模板记常量，不退回原始 URL。
- [ ] HTTP 日志只记固定路由模板、状态、耗时；任务终态只记安全码、UUID、模型和度量。SQLAlchemy 错误只记异常类型，不格式化 exc_info；意外异常返回通用错误与请求编号，不把异常正文交给未脱敏应用 logger。
- [ ] 替换现有文档/index/chat 日志中的非白名单输出，不做无关重构。框架日志不被当成业务成功依据；指南明确用 `--no-access-log` 禁用 Uvicorn 原始 URL 访问日志。
- [ ] 测试两个并发请求和后台 SSE task 的编号不串、伪造入站 X-Request-ID 不被采用、校验/来源拒绝/503 都有安全日志和响应编号；stream start=200 后失败必须单独为 task failed。
- [ ] 验证 request_logging、认证、上传、聊天断连测试，确认编号传递未延长会话或连接生命周期。

## 任务 5：只读用量接口和个人页面

**Files:**
- Create: `apps/api/app/api/routes_usage.py`、`packages/shared/types/usage.ts`
- Create: `apps/web/app/(workspace)/settings/usage/page.tsx`、`apps/web/components/usage/usage-workspace.tsx`
- Modify: `apps/api/app/schemas/usage.py`、`services/usage_service.py`、`main.py`、`apps/web/components/ui/workspace-navigation.tsx`、`apps/web/styles/globals.css`
- Test: `apps/api/tests/integration/test_usage_api.py`、`apps/web/tests/e2e/usage.spec.ts`

**Interfaces:**
- `get_usage_summary(db, user_id, settings, now=None) -> UsageSummary`：today、reset_at、quota.chat/index 的 limit/used/remaining、recording_started_at（首条事件或 null）、recent。
- recent 含 total/ended/running/completed/local_completed/failed/cancelled/interrupted、success_rate（无 ended 时 null）、avg_duration_ms/sample_count、known_tokens、unknown_usage_count；unknown_usage_count 只统计已尝试供应商但任一阶段 usage 不完整的操作，本地明确未调用不算未知。remaining 为 max(0, limit-used)，降低配置后不返回负余额。7 日含今天及前 6 天，按 started_at 归属。
- `list_usage_events(db, user_id, *, operation=None, status=None, limit=20, offset=0) -> UsageEventList`：items/total/limit/offset，started_at DESC、id DESC，limit 1..100、offset >=0，筛选值为设计枚举。
- 查询前调用 expire_usage_events，仅结束本账号过期任务，提交后读取统计；成功率分母只含 ended；完整未知不被空值替换成 0。
- 只读路由 GET `/usage/summary`、GET `/usage/events`；响应 schemas 明确字段，无任意模型 dump 或正文 JSON。

- [ ] 写接口失败测试：401、两账号隔离、非法筛选/分页、同时间稳定排序、已知 token 不重复合计、空数据 success_rate 为 null、running 不入成功率分母、缺失 usage 计 unknown。
- [ ] 实现汇总及分页，按 events.user_id 过滤，不通过可被删除资源的 JOIN 限定归属；测试删除 KB/文档/会话后汇总不丢、quota 不恢复。
- [ ] 写浏览器失败测试：侧栏“用量”、今日额度、空状态、任务/结果筛选、分页重置、未知 token、局部失败重试、401 和 390/1440px 无外溢。
- [ ] 页面复用已有 apiRequest、表格和控制台样式；过滤使用 select，刷新使用 lucide 图标，加载请求可取消，旧响应不得覆盖新筛选。配额页面只读，不新增价格、账单或充值入口。
- [ ] 前端 HTTP 429 detail 包含可读重置时间；如现有通用错误丢掉结构，扩展 ApiError 的可选 code/reset_at，不破坏已有 status。问答保留未提交输入，索引不创建假成功结果。
- [ ] 浏览器验收配额耗尽、已有任务跨日完成、批量队列停止、改筛选时延迟返回、失效登录；截图检查手机和桌面，没有卡片嵌套或跳动。

## 任务 6：迁移教学、端到端回归与交付

**Files:**
- Create: `docs/stages/05-usage-guide.md`、`work/stage5_usage_test_api.py`
- Modify: `README.md`、`docs/stages/05-history.md`、`docs/api.md`，涉及启动命令的现有指南
- Test: 所有后端/前端测试与隔离 PostgreSQL 并发/迁移测试

- [ ] 新建仅测试用的独立 SQLite 数据库与上传目录，fake chat/embedding；清空测试密钥继承，配置小额度生成验收场景，不使用已有 work 测试库中的累计用量。
- [ ] 只更新受到新增默认额度影响的旧测试夹具，避免共用账号累计触顶；不放宽生产配额或删除已有断言。所有真实 PostgreSQL 操作仅针对明确创建的唯一测试数据库，清理前核验名字。
- [ ] 指南写明新迁移 head=0007_usage_events_counters、两项非敏感配置、后端重启，以及配额次数不是账单；历史 usage 不回填、删除不返额、Token 缺失含义和日志安全启动方式。
- [ ] 用户教学命令（不是助手对真实库执行）：在 apps/api 下 `.\.venv\Scripts\python.exe -m alembic upgrade head`、`.\.venv\Scripts\python.exe -m alembic current`，再 `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log`。
- [ ] 运行下述检查，读取完成退出码和真实通过/跳过数；遇到权限或缺失 PostgreSQL 测试环境明确报告，不以推测补充证据。

```powershell
# apps/api：隔离临时目录，禁止读取真实模型密钥
.\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider --basetemp ../../work/stage5-usage-pytest
.\.venv\Scripts\python.exe -m ruff check app tests

# apps/web：直接使用仓库工具，避免本机 npm 包装器问题
node ../../node_modules/typescript/bin/tsc --noEmit
node ../../node_modules/@playwright/test/cli.js test --reporter=line

# 仓库根：独立构建目录
$env:NEXT_DIST_DIR='.next-build-check'
node node_modules/next/dist/bin/next build apps/web
```

- [ ] Playwright 仅连接模拟 API/前端端口（如 8002/3002）；启动进程隐藏窗口，避让原来的 8000/3001。结束后核验进程命令，仅停止本次测试进程，恢复 Next 自动添加的测试类型路径。
- [ ] 完成后独立代码审查整个模块，修复重要发现并重跑相关测试；最终确认没有修改真实环境文件或迁移用户数据库。
- [ ] 交付修改摘要、验收指南和迁移教学；标记“实现/测试通过、待用户迁移和验收”，不要提前声称用户真实环境已可用。

## 实施顺序与执行方式

顺序：任务 1 → 任务 2 → 任务 3 → 任务 4 → 任务 5 → 任务 6。
这是一条相互依赖的完整链路，前端验收基于真实接口，受理/配额/结束依赖同一套事务契约。
推荐由当前会话顺序实现，完成后进行一次独立整体审查，减少接口分工产生的重复调整；也可选择逐任务子代理实现与审查。
业务实现前，用户需审阅本计划并确认执行方式。
