# RAG 质量评测（阶段 6）

4 份原创 CedarDesk 虚构项目资料、24 题，以及 HTTP/SSE 评测、人工评分与离线报告工具。
完整操作见 [评测指南](../docs/stages/06-evaluation-guide.md)。

从项目根目录无费用校验：

```powershell
.\apps\api\.venv\Scripts\python.exe -m evals.run validate
.\apps\api\.venv\Scripts\python.exe -m evals.run --help
```

`prepare` 和 `run` 需要显式 `--allow-paid-calls`，会消耗配额与模型费用。
`validate`、`report` 完全离线，`reconcile` 仅只读核对既有任务，不重新调用模型。
不新增迁移、不直接读取模型密钥、不自动删除资源或重试收费操作。

- datasets：版本化问题、参考答案、原文证据。
- fixtures：可公开的原创中文资料，不代表 DevDocs AI 产品行为。
- toolkit：数据校验、HTTP/SSE、执行、留档与报告。
- results：本地运行产物与人工评分，排除提交，不保存登录凭据。
- tests：独立离线测试；执行时建议将 pytest basetemp 指向 work 下的新目录。

引用来源覆盖不是检索召回率；真实答案正确性与引用支持性需要人工评分。
