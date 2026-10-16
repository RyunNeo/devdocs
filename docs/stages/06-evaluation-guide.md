# 第六阶段模块一：RAG 质量评测

## 这次你参与什么

代码、独立测试资料和评测工具已经提供。你负责用自己的模型服务跑一次小批问答，阅读答案，再填写人工评分。
目标不是让工具宣布“全部正确”，而是获得一份可以追踪到题目、原文、回答和错误的质量基线。

本模块不需要数据库迁移、前端重启或新密钥；仍使用后端现有硅基流动配置。
不需要将任何密码或密钥发给助手，也不要把密码放到命令参数里。

## 1. 准备

在项目根目录 `C:\Users\nrx\Desktop\demo\devdocs-ai` 打开 PowerShell，保持现有前后端与数据库运行。
建议在页面注册一个独立测试账号，避免测试记录与自己的知识库混在一起。

以下全部命令都在项目根目录执行，使用现有后端虚拟环境，不需要安装新依赖。
先执行完全离线、无费用的资料校验：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run validate
```

预期：`校验通过：4 份文档，24 题。`

资料是原创虚构项目 CedarDesk 的产品、前端、API 与发布规范，不是 DevDocs AI 的真实功能说明。
问题包括 8 个单文档、4 个跨文档、4 个拒答、6 个多轮和 2 个干扰场景。
可以直接阅读 `evals/fixtures` 和 `evals/datasets/cedardesk-v1.json`，每题都有参考事实与证据原文。

## 2. 创建专用测试知识库

**从这一步开始会调用真实 Embedding 服务，消耗测试账号配额，并可能产生供应商费用。**
准备流程最多索引 4 份资料。工具通过已有后端调用模型，不直接读取密钥。

将邮箱替换为你的测试账号，运行：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run prepare --email your-test@example.com --run-id cedar-prep-01 --allow-paid-calls
```

按提示输入测试账号密码，输入不显示。不要使用无法隐藏输入的非交互终端。
成功后会创建 `评测-CedarDesk-cedar-prep-01` 知识库，并留下：

```text
evals/results/cedar-prep-01/manifest.json
```

清单保留账号 ID、知识库/文档 ID、资料哈希和步骤进度，不保存登录 Cookie 或密码。
准备失败时已有知识库不会自动删除；不要覆盖原目录。先检查失败原因和页面文档状态，必要时使用新运行编号重做，重新索引会另占额度。

## 3. 先试跑三题

**本步骤最多受理 3 次问答，会消耗配额，且可能调用真实 Embedding 和对话模型。无依据回复也占问答次数。**

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run run --manifest evals/results/cedar-prep-01/manifest.json --email your-test@example.com --run-id cedar-trial-01 --cases fact-01,refusal-01,cross-01 --allow-paid-calls
```

三题分别核对产品定位、无资料的订阅价格和跨文档的两种限额。
执行前会核对账号、地址、资料哈希、知识库文档集合、索引状态和剩余额度。
不要往测试知识库添加其他文档，或在准备后重建索引；这些变动会使清单校验不通过。
更换资料或模型后建议使用新编号留档。公共接口未暴露的模型配置和检索参数会保持未知，可另写非敏感实验备注。

结果目录：

```text
evals/results/cedar-trial-01/
  manifest.json
  results.jsonl
```

`results.jsonl` 是追加日志：同一题可出现“准备提交”和“最终结果”两条记录，报告按题号读取最新状态，不是重复提问。
若写入被意外中断，后续核对可生成 `results.0001.jsonl` 等续写文件，原始残留记录不覆盖。

## 4. 生成报告与评分表

本步骤完全离线，无模型费用：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run report --results evals/results/cedar-trial-01
```

得到 `report.md` 与 `scores.csv`。先读报告中的实际答案、参考答案、引用原文及错误编号，再编辑评分表。
CSV 使用 UTF-8 BOM，便于中文表格软件打开；保持 CSV 格式与原有列名、题号。
仅编辑这些评分列，其余列是阅读辅助，修改不会改变本地参考答案：

| 列名 | 如何填写 |
| --- | --- |
| correctness | 可回答题：0 错误、1 部分正确、2 正确 |
| support | 可回答题：0 引用不支持、1 部分支持、2 充分支持 |
| refusal | 仅应拒答题：通过/未通过，也接受 pass/fail |
| multi | 仅多轮题：通过/未通过，判断指代与上下文是否一致 |
| notes | 写下遗漏、错误事实、无依据扩展等 |

例如：`fact-01` 完整说出目标用户和定位，且引用原文确实支持，可填 correctness=2、support=2。
`refusal-01` 明确说没有定价依据且没有编造价格，填 refusal=通过；support 留空或填“不适用”。
未检查的评分项保持空白，不要预填 0。非拒答题的 refusal、非多轮题的 multi 留空。
三题试跑中，fact-01 和 cross-01 只填 correctness、support 与 notes；refusal-01 主要填 refusal 与 notes，support 和 multi 留空。
评分表出现题型冲突时，工具会提示题号和列名。不要将 pass/通过 填满所有判定列。
可回答题必须正确性和引用支持性都为 2 才算答案通过；多轮一致性另列，不会被答案分数掩盖。
只回答“可能是某价格”仍是编造，不因为语气谨慎就算拒答通过。

完成评分后关闭表格文件，再重生成报告：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run report --results evals/results/cedar-trial-01 --scores evals/results/cedar-trial-01/scores.csv --overwrite-report
```

只覆盖派生的报告，不覆盖原始回答或你的评分表。
若只读核对后答案发生更新，已有 CSV 不自动覆盖，请以新报告为准重新检查评分和备注。

## 5. 执行剩余题目

三题流程确认后，可继续剩余 21 题（总计本次资料 24 题、不重复试跑题）：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run run --manifest evals/results/cedar-prep-01/manifest.json --email your-test@example.com --run-id cedar-rest-01 --cases fact-02,fact-03,fact-04,fact-05,fact-06,fact-07,fact-08,cross-02,cross-03,cross-04,refusal-02,refusal-03,refusal-04,multi-01,multi-02,multi-03,multi-04,multi-05,multi-06,adversarial-01,adversarial-02 --allow-paid-calls
```

为新目录生成报告、填写评分、重新生成报告，操作与上一步相同。
不同目录报告分别保留，不静默合并为一次全量结果。
若需要单份 24 题基线报告，可省略 `--cases`，使用新运行编号完整跑一轮；会额外受理 24 次问答。
试跑 3 题再完整 24 题共占 27 次问答，并非 24 次。务必先看“用量”页面。

## 6. 异常怎么处理

- `login_required`：检查账号密码、登录有效性和基础地址；401 后停止后续题。
- `insufficient_quota`：整批开始前配额不足，缩小题目子集或等次日重置；多轮第二题不能脱离前置题单跑。
- `quota_or_rate_limit`：可能是本站配额或上游限流，停止后续题，不自动重发。
- `document_*_mismatch` / `manifest_mismatch`：账号、地址或资料与准备清单不一致。不要直接手改清单来绕过校验。
- `preparation_incomplete`：清单仍为 preparing 或 prepare_failed，尚不能提问。检查准备步骤的错误，只有 prepare 成功结束后才能运行问答。
- `knowledge_base_name_conflict`：已有同名测试知识库（HTTP 409）。使用新的准备运行编号，例如 cedar-prep-02；后续 run 的 --manifest 也改为该新目录。重新准备会索引新资料并消耗额度；已有知识库和文件不会被自动删除或复用。
- `index_failed` / `parse_failed`：先在文档页面查看失败状态，准备流程不会继续索引后续文件。
- `unknown` / `persistence_mismatch` / `network_error`：不能确认原任务结果，不代表拒答或无费用。先只读核对原会话：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run reconcile --results evals/results/cedar-trial-01 --email your-test@example.com
```

核对只读取原会话，不重新问、不收费；仍无法确认则保留 unknown，再次核对需你显式执行。
生成新报告时带 `--overwrite-report`；若仍需重问，用新运行编号明确发起，会另占额度。
工具不会自动删除测试知识库或会话，你可以在现有页面手动清理；删除不退还配额。

默认只允许本机地址。未来访问远程测试后端时，必须使用 HTTPS 和 `--allow-remote`，且仅指向你信任的服务。

## 7. 如何读指标

- 执行完成率是业务链路完成，不是答案正确率。
- 期望引用来源覆盖按准备清单中的文档 ID 核对，不仅比较同名文件；不是检索召回率。
- 引用结构检查只验证编号与条目对应，不证明引用支持答案。
- 必需/禁止事实按字面匹配，可能受表达方式影响，只用来提醒人工检查。
- 耗时是完整响应接收时间，恢复的断流结果没有完整耗时样本，不是模型首 Token 延迟。
- 已知 Token 仅来自问答返回的可靠字段，缺失或不完整会明确标识；不含完整索引/检索用量，不是供应商账单。
- 未评分不算通过，也不算零分。建议全量人工评分至少 80% 通过，拒答与注入无严重编造，再进入试用；不是上线保证。

## 8. 代码阅读路径

先看 `evals/run.py` 的命令入口，再看 `toolkit/runner.py` 的 prepare/run_cases/reconcile。
`dataset.py` 做资料校验，`client.py` 和 `sse.py` 处理 HTTP 与流式协议，`artifacts.py` 负责留档，`report.py` 负责评分与报告。
自动测试全部使用假响应，不调用你的真实模型。真实答案质量要靠这次亲自试跑确认。
