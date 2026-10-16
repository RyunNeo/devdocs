# API 约定

完整请求和响应示例见项目蓝图第 12 节。阶段 1 后由 FastAPI OpenAPI 补充实际契约。

## 第一阶段实际认证契约（2026-10-12）

- POST /auth/register：JSON 邮箱/密码，成功 201，响应为 {user: ...} 并写入 Cookie。
- POST /auth/login：JSON 邮箱/密码，成功 200，响应为 {user: ...} 并写入 Cookie。
- GET /auth/me：成功 200，返回当前用户；未登录、过期或撤销返回 401。
- POST /auth/logout：成功 204，撤销当前数据库会话并清除 Cookie，可重复调用。
- GET /health：进程存活，返回 status=ok；不代表数据库已准备好。
- GET /health/ready：数据库、vector 扩展和认证表就绪返回 200，否则 503。

采用蓝图允许的会话方案，实际接口不返回 access_token。Cookie 是 HttpOnly / SameSite=Lax，
数据库保存会话摘要。浏览器使用 Next.js 的 /api 代理前缀。请求格式错误为 422，
重复注册为 409，来源未允许为 403，数据库不可用为 503。密码不出现在错误响应中。
前后端默认都使用 devdocs_session，注册密码范围 10–128 字符。

## 模块 2.1 知识库契约

POST /knowledge-bases 成功 201，GET 列表/详情与 PATCH 成功 200，DELETE 成功 204。
返回资源包含 id、name、description、created_at、updated_at，不暴露 name_key。
列表返回 items、total、limit、offset，默认 limit=20、offset=0；limit 为 1–100。
POST 名称为 1–80 字符，描述最大 1000 字符，可省略或为 null。
PATCH 只改明确提交的字段；description=null 清空，name=null 和空对象均为 422。
同账号名称去除全部空白并 casefold 后重复返回 409，不同账号允许同名。
展示名称仍保留内部空格；0003_name_whitespace 为旧记录重算 name_key，冲突时先停下。
所有接口要求登录；别人的资源与不存在的资源均为 404。
所属账号由会话取得，请求体指定 user_id 被拒绝。
启用前由用户执行 0002_knowledge_bases 迁移，练习见 outputs/stage-02-module-01-guide.md。

| 模块 | 路由文件 | 开发阶段 |
| --- | --- | --- |
| 健康检查 | app/main.py | 1 |
| /auth/register、/auth/login | api/routes_auth.py | 1 |
| /knowledge-bases | api/routes_knowledge_bases.py | 2 |
| 知识库文档上传、列表、文档详情与删除 | api/routes_documents.py | 2–3 |
| POST /conversations/{id}/chat/stream | api/routes_chat.py | 4 |
| 知识库会话列表、创建、历史消息 | api/routes_conversations.py | 4–5 |

路径中的资源 ID 不能代替授权检查。通过认证取得用户 ID，服务层校验资源所属用户。
流式 POST 使用 fetch 读取 text/event-stream；浏览器原生 EventSource 不支持 POST。
沿用蓝图的 token / citations / done 事件，阶段 4 补充 error 事件和断线处理规则。

## 第四阶段实际契约

- POST `/knowledge-bases/{id}/conversations`：空对象，201 创建所属会话。
- GET `/conversations/{id}`：200，所属会话和最新40条消息（sequence升序）、has_older；不返回用户ID。
- POST `/conversations/{id}/chat/stream`：question（去首尾空白后1–2000字符）、request_id（UUID）。
- POST `/conversations/{id}/chat/cancel`：run_id（UUID），204；取消只影响当前所属会话匹配的活跃run。

流建立前：未登录401、非所属404、重复request_id/活跃会话409、并发超限429、缺配置503。
流建立后：meta（接收确认）→status*→token（校验保存后）→citations→done；失败以error结束，缺终态不能判定完成。
done仅在DB保存后发送，包含message_id/status/finish_reason/usage；content仅用于替换固定拒答，正常正文由token拼接。
citations只含实际引用的检索来源和正文快照，source_status标记current/changed/deleted。
未知引用或有实质答案却无有效引用标记failed/citation_invalid；编号校验不是事实真实性判断。
回答状态streaming/completed/failed/cancelled；180秒过期租约在读取/发送时恢复。
SSE响应Cache-Control=no-store,no-transform和X-Accel-Buffering=no；不压缩缓冲流。
知识库删除清理全部会话和引用快照；文档删除不清理历史快照，读取显示原文已删除。
## 会话体验模块更新（2026-10-15）

GET `/knowledge-bases/{id}/conversations`：所属非空会话分页，默认limit20/offset0，limit1–100。
返回items/total/limit/offset；摘要含id、knowledge_base_id、title（首问题前40字符）、last_question（最近问题前80字符）、latest_status和时间，不含消息正文或引用。
GET `/conversations/{id}` 支持before_sequence>=1、limit1–100（默认40）；消息严格早于游标，升序返回，has_older表示还有更早记录。
非completed的assistant正文和引用在读取时为空，旧数据库内容不被批量改写。
SSE增加status事件，phase为retrieving/generating/validating；meta可附user_sequence用于页面正确维护消息游标。
正文token仅在引用校验、来源状态核对及保存成功后发布，失败/取消不发布草稿；provider调用次数和thinking配置不变。
历史默认updated_at降序/ID降序，空创建记录不进列表；new=1是前端显式新会话状态，不是后端自动创建命令。
无新增迁移，仍使用0006结构；切换本模块需前后端一起更新并重启后端。

## 用量、日志与配额（0007）

GET `/usage/summary`：所属账号今日 chat/index 配额、UTC+08:00 重置时间、近七日统计及最早记录时间。
GET `/usage/events`：所属操作分页，operation=chat/index、status=running/completed/local_completed/failed/cancelled/interrupted，默认 limit20/offset0，limit1–100。
响应不包含问题、回答、文件名或原始供应商响应。Token 仅汇总已知值，不完整阶段明确标注。
每次受理问答占一次，每份实际索引占一次；复用索引不多扣。失败/取消不返额，删除资源不清账本。
超额在调用前返回429，JSON附 code=daily_quota_exceeded、operation、reset_at，保留字符串detail。
请求返回服务端生成的 X-Request-ID；安全日志以固定路由模板关联请求与任务结果。
新增迁移0007_usage_events_counters，配置和验收见 docs/stages/05-usage-guide.md。

## 文档上传与解析（阶段2–3）

阶段3新增 POST `/documents/{id}/index`（200，索引结果）；GET `/documents/{id}/chunks`（limit/offset分页）。
解析status保持parsed/failed；独立index_status为pending/indexing/completed/failed，completed才可检索。
同指纹已完成的索引幂等复用；活跃索引409、缺密钥503、外部服务失败200并返回failed安全原因。
chunks接口不返回原始向量，仍强制资源所属；删除文档/知识库级联清理chunks。
增加文本PDF上传、页码来源及部分无文本页面警告；配置见docs/stages/03-indexing-guide.md。

新增 multipart POST `/knowledge-bases/{id}/documents`（201），GET同路径返回分页元数据。
GET `/documents/summary` 返回当前用户文档总数；GET `/documents/{id}` 返回安全状态和最多20000字符纯文本预览。
POST `/documents/{id}/retry` 重试pending/failed（parsed幂等返回）；DELETE文档或知识库安排事务性私有文件清理。
格式400、超限413、重复409、未登录401、非所属/不存在404、数据库或文件写入不可用503。
UTF-8文本解析失败仍返回201和failed，因为原文件和记录已成功保存；不将此状态称为向量就绪。
同步解析无队列ID，也不需要状态轮询。详情不返回user_id、storage_key、content_hash或完整正文。
约定与配置见 docs/stages/02-upload-guide.md。原有知识库重名规则保持不变。

