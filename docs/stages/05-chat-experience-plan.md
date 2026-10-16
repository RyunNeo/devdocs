# 会话体验优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for the user's inline execution method. Steps use checkbox syntax for tracking.

**Goal:** 完成键盘提问、校验后发布答案、会话历史入口和自动恢复的完整流程。

**Architecture:** 保留现有会话数据和 SSE 通道；服务端暂存模型草稿，校验并保存后才发布正文。
历史列表及消息游标分页复用现有表，前端通过知识库内导航进入历史并恢复同一会话 ID。

**Tech Stack:** Next.js 16.4、React 19.3、TypeScript、FastAPI、SQLAlchemy、PostgreSQL、Playwright、pytest。

**Spec:** `docs/stages/05-chat-experience-design.md`，用户于2026-10-15审核通过。

**执行状态:** 任务1–5已实现，自动化验证和独立审查记录见 `work/stage5-progress.md`；用户验收见 `05-chat-experience-guide.md`。

## Global Constraints

- Enter发送，Shift+Enter换行；isComposing、229、repeat、空问题和busy状态不误提交。
- 问题上限2000字符，不增加页面快捷键说明。
- 不额外开启深度思考，不增加第二次生成或审核模型调用，不展示reasoning_content。
- 服务端校验和保存完成前不发送任何正文token；status只包含retrieving/generating/validating。
- 失败和取消不保存新草稿；旧failed/cancelled的assistant正文和引用在读取时隐藏，不改写旧数据。
- 列表每页20，limit范围1–100，offset>=0；标题最多40字符、最近问题摘要最多80字符。
- 消息每页默认40，limit范围1–100，before_sequence>=1；按sequence升序返回并提供has_older。
- 默认恢复最近非空会话；new=1明确创建空白上下文；首次发送才创建记录。
- 保留所有已有数据、权限、检索与密钥配置，预计无新增迁移。
- 测试仅用假模型和隔离数据库，不调用真实付费模型，不执行用户数据库升级。
- 本轮不含会话改名、删除、搜索、配额、模型切换配置和部署。

## Review Focus

1. 生成了带有效引用的错误草稿，最后返回拒答：任何发布token及历史都不能出现该草稿（任务2）。
2. 输入法确认/按键长按：不会误发或重复创建消息和会话（任务3）。
3. 自动恢复请求迟到，用户已进入new=1或指定会话：旧响应不能覆盖当前状态（任务4）。
4. 旧失败消息含私有草稿/引用：详情和更早消息页都必须脱敏，而用户原问题保留（任务1）。
5. 数据保存与停止/断线同时发生：已完成答案可恢复，不自动重试，取消不覆盖completed（任务2、4）。

## 文件边界与命令

后端路径以 `apps/api/` 为前缀，命令从该目录使用 `.venv/Scripts/python.exe`。
前端沿用现有Playwright框架，先阅读 `apps/web/AGENTS.md` 和已安装Next相关指南。
本地npm入口若仍损坏，使用相同依赖的 `node ../../node_modules/...` 执行，不另装依赖。
保持测试服务8002/3002与用户服务8000/3001分开；输出及临时脚本放work目录。
执行前核对Git状态；若仍无Git仓库，不初始化或虚构提交，用本计划专属执行记录保存检查点。

## 任务1：历史列表、消息分页和安全读取

**Files:** 修改 `app/services/conversation_service.py`、`app/schemas/conversation.py`、
`app/api/routes_conversations.py`、`packages/shared/types/conversation.ts`；新增
`tests/integration/test_conversation_history.py`，补充现有PostgreSQL隔离测试。

**Interfaces:**
- `list_conversations(db: Session, user_id: UUID, kb_id: UUID, limit: int, offset: int) -> ConversationList`。
- `ConversationSummary`：id、knowledge_base_id、title、last_question、latest_status（可空）、created_at、updated_at。
- `ConversationList`：items、total、limit、offset。
- `read_conversation(db: Session, user_id: UUID, conversation_id: UUID, before_sequence: int | None = None, limit: int = 40) -> ConversationDetail`。
- `ConversationDetail`保持messages和has_older；所有assistant非completed消息的content/citations为空。

- [ ] 写 `test_owned_nonempty_history_is_sorted_and_bounded`：空会话不入列表；已有记录可读；title<=40、last_question<=80；updated_at降序、ID降序作为稳定次序。
- [ ] 写 `test_history_and_cursor_pages_are_owner_scoped`：匿名401、外国用户/外国知识库404；0 limit、负offset、0 before_sequence返回422。
- [ ] 写 `test_message_cursor_has_no_gaps_or_duplicates`：86条消息依次获取最新40、前40、前6；合并sequence为1–86且无重复。
- [ ] 写 `test_legacy_failed_drafts_are_not_returned`：failed/cancelled/streaming assistant草稿和引用均为空；user原文保留，DB原记录未改变。
- [ ] 运行新测试，确认因接口/新行为缺失而失败。
- [ ] 用SQL关联子查询派生第一条用户问题、最新用户问题及最新assistant状态；列表不加载完整消息、引用快照或文档正文。先校验KB所属，再分页和计数。
- [ ] 实现before_sequence严格小于边界的过滤，取limit+1判断has_older；复用来源状态刷新，仅对completed引用执行。
- [ ] 运行新测试、已有会话测试，预期全通过；在隔离PG核对列表和游标排序，无需修改表。

## 任务2：校验后发布与状态协议

**Files:** 修改 `app/services/chat_service.py`、`packages/shared/types/chat.ts`、
`apps/web/lib/stream.ts`；新增 `tests/integration/test_answer_publication.py`；
更新 `tests/integration/test_chat.py`、`test_chat_lifecycle.py` 和 `apps/web/tests/e2e/stream-parser.spec.ts`。

**Interfaces:**
- 新增 `ChatEvent` 联合成员 `{event:"status",data:{phase:"retrieving"|"generating"|"validating"}}`。
- `stream_chat(...)`、`finish_run(...)`的调用接口保留；事件顺序为meta、status*、token*、citations、done，或meta/status*/error。
- 普通done不重复整篇正文，保持分片大小和no-transform；固定拒答可继续使用done.content归一化。

- [ ] 写可控延迟假模型测试 `test_no_tokens_leave_before_validation_and_save`：生成部分内容后阻塞，已收事件只有meta/status；另一Session尚无completed正文。
- [ ] 写 `test_mixed_refusal_never_publishes_speculation`：模型先生成推测后给拒答标记，全部应用token拼接只等于中文固定拒答；引用为空。
- [ ] 写 `test_invalid_or_cancelled_answer_has_no_published_or_saved_draft`：非法编号、缺终态、取消均无正文token；持久化content/citations为空。
- [ ] 写读取协议测试：接受三个合法phase，未知phase/缺phase拒绝；原有中文分片与缺done测试保持通过。
- [ ] 运行新测试并观察预期失败，避免只改旧测试掩盖行为变化。
- [ ] 将生成token仅累积在服务端内存；检索前、生成前、校验前发送对应status，保留10秒心跳、现有时间/大小预算及取消能力。
- [ ] 正常校验并保存成功后，分片发送归一化后的answer.content、citations和done；不再发布生成过程草稿。
- [ ] failed/cancelled保存空正文及空引用；保留安全error_code和usage（如已收到），避免把草稿当历史。
- [ ] 更新旧“保存部分正文”的断言为新设计；补 `test_saved_completion_wins_over_late_cancel` 和断线后读取completed测试。
- [ ] 运行新发布测试、原chat/lifecycle测试和流解析测试，预期通过；provider请求仍enable_thinking=false且只调用一次。

## 任务3：键盘输入与问答状态

**Files:** 修改 `apps/web/components/chat/chat-composer.tsx`、`chat-workspace.tsx`、`message-list.tsx`，
新增 `apps/web/tests/e2e/chat-experience.spec.ts` 的输入/发布用例。

**Interfaces:**
- `ChatComposer`现有props保留；onSend经form.requestSubmit触发，与点击按钮共享验证和inFlight保护。
- `MessageList`接收当前run的phase，仅为streaming消息显示对应状态，不展示未完成assistant正文。
- 已完成正文继续使用现有安全纯文本和引用弹窗，不引入Markdown/HTML渲染。

- [ ] 写浏览器测试：Enter提交一次、Shift+Enter产生换行但请求计数不变、composition确认不发送、repeat不重复发送、空问题不发。
- [ ] 写延迟假回答测试：生成/校验过程中看不到原始草稿；最终拒答无内部标记，停止后无草稿。
- [ ] 运行新测试确认失败，再实现onKeyDown处理；检测nativeEvent.isComposing、keyCode=229和repeat，只有普通Enter preventDefault并提交。
- [ ] 处理status事件更新phase；失败/停止仅显示状态和安全原因；meta仍确认本轮用户问题已接收。
- [ ] 运行新测试及现有chat浏览器回归，预期通过。

## 任务4：知识库标签、历史页与恢复

**Files:** 新增 `apps/web/components/knowledge-bases/knowledge-base-tabs.tsx`、
`apps/web/components/conversations/conversation-history.tsx`、
`apps/web/app/(workspace)/knowledge-bases/[id]/conversations/page.tsx`；修改文档组件、问答page、
`chat-workspace.tsx`和styles/globals.css；补充chat-experience浏览器测试。

**Interfaces:**
- `KnowledgeBaseTabs({knowledgeBaseId,active,disabled})`：active为documents/chat/conversations；生成时禁用离开当前问答的标签。
- `ConversationHistory({knowledgeBaseId})`：读取任务1分页接口，点击项进入 `/knowledge-bases/{id}/chat?conversation={conversationId}`。
- `ChatWorkspace`新增 `startNew: boolean`；page解析conversation和new=1，显式conversation优先于new=1。
- `ChatWorkspace`保留当前唯一active请求和epoch/abort保护；历史加载不共享正在生成请求的controller。

- [ ] 写 `test_existing_history_is_reachable_and_continues_same_id`：预置旧会话，列表能看到；点击恢复后追问仍使用该ID，不创建新会话。
- [ ] 写 `test_default_latest_and_explicit_new_are_distinct`：无参数恢复最近非空会话；new=1刷新为空；首发才创建，URL替换为conversation参数。
- [ ] 写 `test_late_restore_cannot_overwrite_new_or_selected_conversation`：延迟列表/详情响应，切换目标后旧数据不能覆盖当前页面。
- [ ] 写历史分页、更早消息加载和不同知识库/用户隔离用例；无权限指定会话不能静默恢复其他会话。
- [ ] 运行新用例确认预期失败，再实现标签、历史列表和分页；每项包含title、last_question、时间、状态，不做卡片套卡片。
- [ ] 默认恢复查询list limit=1；显式new不查询恢复接口；会话选择参数改变时重置并取消旧加载，避免跨会话竞态。
- [ ] 加载更早消息使用当前最小sequence为游标，prepend并按消息ID去重，保留阅读位置；更新回复后历史按updated_at重新排序。
- [ ] busy期间禁止页面内切换/新建；离开时取消本页连接；保持completed后断线可从历史恢复，绝不自动重发问题。
- [ ] 运行历史/键盘/发布完整链路用例；截图1440x900与390x844，断言无横向溢出、输入区不遮挡消息、标签可达。

## 任务5：回归、审查和交付

**Files:** 新增 `docs/stages/05-chat-experience-guide.md`，更新 `docs/stages/05-history.md`、`docs/api.md`、
README和阶段4指南中已变化的实时草稿行为；执行记录放 `work/stage5-progress.md`。

- [ ] 逐项对照设计，确认旧数据未改写、已完成答案不自动重算、列表不泄露草稿、不需要新迁移。
- [ ] 后端运行 `python -m pytest tests -q -p no:cacheprovider --basetemp ../../work/stage5-suite`，报告通过/跳过原因；PG用例用独立随机库验证并清理。
- [ ] 运行Ruff、前端typecheck和独立构建目录build；隔离假模型8002/3002运行全部Playwright，禁止指向真实模型服务。
- [ ] 请求一次独立整体审查，聚焦未校验内容外泄、恢复竞态、IME和消息分页；修复具体问题后重跑相关及全量回归。
- [ ] 停止测试服务，清理生成配置中的临时目录引用，确认用户服务及数据库数据未被替换。
- [ ] 写整流程验收表：键盘发送→等待阶段状态→仅见最终答案→返回历史→继续原会话→新会话刷新。
- [ ] 协调重启已核对的用户后端并核验ready和新接口；前端通过现有开发服务更新。真实问答由用户主动提交。

## 审核与执行

沿用此前的当前会话直接实现方式，顺序完成上述紧密关联的任务，不逐项暂停请求确认。
本计划待用户审核；审核通过后开始业务代码实现，内部测试不要求用户每一步参与。
