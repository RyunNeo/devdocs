# RAG 质量评测闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用独立测试资料完成可重复运行、可人工核对的 24 题 RAG 评测闭环。

**Architecture:** 独立 Python 工具通过现有认证、文档、会话和 SSE API 执行评测，不调用内部 RAG 服务。离线校验和报告与在线执行分离；每次执行独立留档，收费操作必须显式启用。

**Tech Stack:** Python 3.12+、现有 httpx / Pydantic / pytest、标准库 argparse / csv / json / hashlib。

**Spec:** `docs/superpowers/specs/2026-10-15-rag-evaluation-design.md`，用户已确认。

## Global Constraints

- 不修改现有业务接口，不增加数据库表或迁移，不自动访问真实模型或修改密钥。
- 不包含生产部署、评测管理页面、学习卡片、Agent 或模型自动裁判。
- 首批 4 份原创文档、24 题：8 单文档、4 跨文档、4 拒答、6 多轮、2 干扰题。
- 密码隐藏输入；不接收或保存模型密钥、Cookie、密码及完整请求头。
- 不自动重试收费请求，不自动清理用户数据，不覆盖已有运行目录。
- 只报告期望引用来源覆盖，不声称得到 Recall@K、MRR 或未公开检索分数。
- 缺失 Token 为未知；关键词命中不是正确率；人工未评分不算通过。
- 本地文件手动编辑用 apply_patch；工作区没有 Git 仓库，不初始化或创建提交。

## Review Focus

1. 多轮子集跳过前置题：选择阶段拒绝不完整依赖，或显式包含所需前置题，不能当作独立题执行（任务 4）。
2. 服务端已受理但客户端断流：保留请求身份，只读核对，不重发或误判为拒答（任务 2、4）。
3. 清单来源被替换或跨账号复用：验证账号、地址、哈希、文档集合与状态，不运行在错误知识库（任务 3、4）。
4. CSV 参考资料或答案以公式开头：导出电子表格安全文本，导入只信任稳定题号和评分列（任务 5）。
5. 所有题失败或全部未评分：统计使用空值及明确分母，不生成 NaN、不输出虚假 100%（任务 5）。

## 文件划分

- `evals/__init__.py`、`evals/run.py`：模块入口与命令参数，不包含业务编排细节。
- `evals/toolkit/{__init__,dataset,client,sse,artifacts,runner,report}.py`：分别负责资料、HTTP、事件解析、落盘、流程、统计。
- `evals/fixtures/{product,frontend,api,release}.md`：虚构项目 CedarDesk 的原创规范。
- `evals/datasets/cedardesk-v1.json`：版本化问题集。
- `evals/tests/{test_dataset,test_client,test_artifacts,test_runner,test_report,test_cli}.py`：独立测试，不依赖真实供应商。
- 修改 `.gitignore`、`evals/README.md`、`README.md`、`docs/stages/{05-history,06-release}.md`。
- 新增 `docs/stages/06-evaluation-guide.md`：用户操作和评分教学。

测试命令均从项目根目录执行：`apps/api/.venv/Scripts/python.exe -m pytest evals/tests/... -q -p no:cacheprovider`。
命令入口统一为 `apps/api/.venv/Scripts/python.exe -m evals.run`。

### Task 1: 资料与数据集校验

**Files:** `evals/fixtures/*.md`、`evals/datasets/cedardesk-v1.json`、`evals/toolkit/dataset.py`、包初始化文件、`evals/tests/test_dataset.py`。

**Interfaces:**
- `load_dataset(path: Path, fixtures_root: Path) -> Dataset`，Pydantic 严格模型，拒绝未知字段。
- `Dataset` 包含 version、documents、cases、dataset_sha256；`Case` 包含 id、category、question、expected_behavior、reference_answer、required_facts、forbidden_facts、expected_sources、evidence、conversation_group、turn。
- `select_cases(dataset: Dataset, ids: list[str] | None) -> list[Case]` 保持数据集顺序，拒绝未知或重复 ID、不完整多轮依赖。

- [x] 先写 `test_dataset.py`：总数 24、分类为 8/4/4/6/2、3 组两轮；重复 ID、路径越界、失效证据、非法分组次序均抛可读错误。3 题试跑选 1 单文档、1 拒答、1 跨文档，不破坏多轮依赖。
- [x] 运行该文件确认新增能力缺失导致失败，不接受配置错误或导入路径错误作为红灯证据。
- [x] 编写四份原创资料和问题集、模型与校验。证据逐字核验，文件路径解析后限制在 fixtures 根内，文档及数据集计算 SHA-256。
- [x] 重跑该文件全部通过；人工核对参考事实、跨文档必要性和注入题不含真实秘密。

### Task 2: 认证 HTTP 与 SSE 客户端

**Files:** `evals/toolkit/client.py`、`evals/toolkit/sse.py`、`evals/tests/test_client.py`。

**Interfaces:**
- `EvaluationClient(base_url: str, *, allow_remote: bool = False, transport=None)`，同步上下文管理器，内部复用 httpx.Client；不设置重试，follow_redirects=False。
- 方法：`login(email, password) -> dict`、`summary() -> dict`、`create_kb(name) -> dict`、`upload(kb_id, path) -> dict`、`index(doc_id) -> dict`、`list_documents(kb_id) -> list[dict]`、`create_conversation(kb_id) -> dict`、`read_conversation(conversation_id) -> dict`、`stream_answer(conversation_id, question, request_id) -> StreamResult`。
- `StreamResult` 包含 meta、answer、citations、done、elapsed_ms；`iter_sse(lines: Iterable[str]) -> Iterator[SSEEvent]` 支持多行 data，空行结束事件，忽略注释和未知事件，限制单事件最大 1 MiB。
- `EvaluationError` 仅携带固定 code、HTTP status、request_id 和可安全展示的说明，不打印原始请求或响应正文。

- [x] 写测试：未显式允许远程、非本地 HTTP、URL 用户信息/query/fragment 均拒绝；远程仅 HTTPS；重定向不跟随；无自动重试；401/429、业务索引失败正确分类。
- [x] 写测试：中文 UTF-8 任意字节分包、CRLF、心跳、多行 data、缺失 done、畸形 JSON、超长事件、超时；meta/done/引用正确组装，不能将 token 事件当完成。
- [x] 运行 `test_client.py` 确认失败，再实现客户端。使用 httpx 的增量 UTF-8 行解码，连接超时 10 秒、读超时 30 秒、整条问答总时限 180 秒；total deadline 在心跳处也检查。
- [x] 请求路径严格复用当前 API；GET 文档分页读全，登录 Cookie 仅内存；HTTP 200 索引响应必须检查 index_status=completed。
- [x] 重跑测试全部通过，检查异常路径不会输出包含哨兵密码/Cookie 的原始异常。

### Task 3: 独立留档与准备流程

**Files:** `evals/toolkit/artifacts.py`、`evals/toolkit/runner.py`、`evals/tests/test_artifacts.py`、`evals/tests/test_runner.py`、`.gitignore`。

**Interfaces:**
- `create_run_dir(root: Path, run_id: str) -> Path`：只接受字母数字下划线连字符，原子创建，目录存在即失败。
- `write_manifest(directory: Path, manifest: dict) -> None`：同目录临时文件加原子替换；`append_result(directory: Path, record: dict) -> None`：JSONL 每题 flush。
- `prepare(client, dataset: Dataset, output_root: Path, run_id: str) -> Path`：返回准备清单路径。
- 清单字段 schema_version、run_id、phase、owner_id、base_url、dataset_version/hash、documents（文件相对路径/hash/id）、kb_id、started_at、模型未知字段及非敏感备注；错误后保留已知资源 ID。

- [x] 写测试：目录越界/重名拒绝、中文结果往返、落盘中断保留前题、不写凭据；额度低于 4 时在创建资源前拒绝。
- [x] 写测试：上传/解析/索引任一失败及 429 后停止后续操作，保留已有资源映射，200+index_status=failed 不能继续。
- [x] 运行相关测试确认失败，再实现目录管理与 prepare：认证后用 `/auth/me` 身份、检查配额，创建 `评测-CedarDesk-<run-id>` 知识库，4 份资料逐个上传索引，每步更新清单。
- [x] `.gitignore` 加 `evals/results/*` 并保留 `.gitkeep`；实现只白名单字段落盘，不序列化整个客户端或响应对象。
- [x] 重跑 `test_artifacts.py` 与 prepare 测试全部通过，确认无删除 API 调用。

### Task 4: 问答编排与结果核对

**Files:** `evals/toolkit/runner.py`、`evals/tests/test_runner.py`。

**Interfaces:**
- `run_cases(client, dataset: Dataset, manifest_path: Path, output_root: Path, run_id: str, case_ids: list[str] | None) -> Path`。
- 逐题记录 case_id、status、conversation_id、request_id、assistant_message_id、answer、citations、usage、elapsed_ms、error_code；状态 completed/failed/unknown/blocked/not_attempted。
- `reconcile(client, result_directory: Path) -> None` 只读查询既有会话，追加核对记录；报告按 case_id 使用最近的有效结果，保留原始执行耗时与首次尝试身份。

- [x] 写测试：清单账号/地址/哈希不一致、额外/缺失文档、文档未索引均在问答前拒绝；额度小于所选题量时零问答提交。
- [x] 写测试：独立题会话不同，多轮组共享会话，失败前置使后续 blocked；子集仅选第二轮报错；参考答案和预期事实不出现在提问请求中。
- [x] 写测试：done 与持久化消息 ID/run_id/状态/答案不一致不能通过；断流后只读核对；成功恢复后无重复提交；401/429/服务不可达停止批次并保存未尝试题。
- [x] 运行 `test_runner.py` 确认失败，实现校验、串行执行、逐题落盘和只读 reconcile。当前接口所有 24 次提交算配额，即使最终本地拒答也算；不以预计模型调用数替代额度检查。
- [x] 每题使用 UUID 请求标识；从 meta 获取助手消息 ID，历史用 run_id/ID 定位，不简单取最后一条消息。缺少持久化完成证据时标 unknown。
- [x] 重跑全部 runner 测试；用带完整响应协议的假后端跑完整 24 题，验证调用次数与会话分组。

### Task 5: 人工评分与离线报告

**Files:** `evals/toolkit/report.py`、`evals/tests/test_report.py`。

**Interfaces:**
- `export_scores(dataset: Dataset, result_directory: Path) -> Path`：生成 UTF-8 BOM CSV，不覆盖已有评分。
- `load_scores(path: Path, dataset: Dataset) -> dict[str, Score]`：仅读取题号、正确性、引用支持性、拒答判定、多轮判定、备注评分列；验证唯一 ID 和字段适用性。
- `build_report(dataset: Dataset, result_directory: Path, scores_path: Path | None) -> Path`：生成 report.md；重新生成需显式允许覆盖该派生报告，不能覆盖原始结果或 CSV。

- [x] 写测试：完成率 2/3、期望来源 1/2、逐题全覆盖、无样本空值、Token 缺失未知、未评分不计通过；P95 用排序后 nearest-rank `ceil(0.95*n)`，中位数用 statistics.median。
- [x] 写测试：未知/重复 ID、非法分值、跨类型适用性冲突报错；CSV 单元格公式前缀中和；引用条目与编号异常提示，不计为事实错误定论。
- [x] 写测试：参考拒答题无期望来源不进入覆盖分母；正确性 2 且支持性 2 才作为可回答题通过，拒答题以人工拒答通过为准，多轮与注入单列警示。
- [x] 运行 `test_report.py` 确认失败，再实现结果加载、辅助事实匹配、评分与报告。报告注明这是引用来源覆盖不是检索召回；只报告本次实际返回 usage，不查询账号用量差。
- [x] 重跑测试通过；报告区分尝试/完成/未知/阻塞/未尝试、人工已评分/全部题、索引与问答消耗未知项，不承诺模拟测试代表真实质量。

### Task 6: 命令入口、指导与回归

**Files:** `evals/run.py`、`evals/tests/test_cli.py`、`evals/README.md`、`docs/stages/06-evaluation-guide.md`、`docs/stages/05-history.md`、`docs/stages/06-release.md`、`README.md`。

**CLI Contract:**
- `validate --dataset <path>`：默认使用 cedardesk-v1，完全离线。
- `prepare --base-url http://127.0.0.1:8000 --email <email> --run-id <id> --allow-paid-calls`：隐藏询问密码，显式打印将开始的索引数量；远程还需 `--allow-remote`。
- `run --manifest <path> --email <email> --run-id <new-id> --cases fact-01,refusal-01,cross-01 --allow-paid-calls`：省略 cases 为 24 题，收费开关缺失时退出且不登录、不写库。
- `reconcile --results <directory> --email <email>`：只读核对，无收费开关，基础地址从清单读取，远程仍需显式允许。
- `report --results <directory> [--scores <csv>] [--overwrite-report]`：离线生成报告，首次同时创建评分模板。
- `--dataset`、`--output-root` 为准备/运行的可选通用参数；所有运行目录默认位于 evals/results。

- [x] 写测试：help/validate/report 不联网，收费开关缺失时无请求；密码不进入参数或文件；CLI 失败码 1，参数错误 2，成功 0；错误输出无原始敏感正文。
- [x] 运行 `test_cli.py` 确认失败，实现 argparse 路由、getpass、安全错误展示；不读取项目 .env 或 .env.example，模型配置始终由现有后端负责。
- [x] 编写中文指南：推荐独立测试账号、4 次索引+24 次问答额度提示、3 题试跑与人工评分示例、补跑新目录、断流只读核对、评分后重生成报告、手动清理与不返额度。
- [x] 同步阶段记录：第五阶段已验收；第六阶段评测工具实现后待用户真实试跑；部署和试用仍待办，不宣称线上已发布。
- [x] 执行 `apps/api/.venv/Scripts/python.exe -m pytest evals/tests -q -p no:cacheprovider`，预期全部通过；执行离线 validate，预期 4 份文档与 24 题校验通过。
- [x] 在 apps/api 运行后端 pytest 全量回归，记录通过数与跳过原因；从项目根运行后端虚拟环境的 `ruff check evals apps/api/app apps/api/tests`，预期无错误。
- [x] 进行一次独立代码审查，修复后重跑相关测试；将测试证据记录到 work/rag-evaluation-ledger.md。不启动真实评测，不改变当前服务启动方式。
- [x] 向用户交付指南、离线验证结果及下一步 3 题试跑命令；明确真实答案质量仍需用户运行与评分。

## 执行与参与方式

建议采用当前会话内直接实施：任务间接口依赖紧密，由同一实现者完成后统一独立审查，减少交接。
用户在实现完成后参与真实调用与人工评分；助手测试全程使用假响应或隔离服务。
计划审阅确认后才进入实现，不把设计确认当成对尚未存在计划的批准。
