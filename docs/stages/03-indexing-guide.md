# 第三阶段：配置硅基流动与集中验收

## 本轮交付

文本PDF提取（页码定位）→ LangChain结构分块 → 硅基流动 BAAI/bge-m3 → VECTOR(1024)入库
→ 可检索状态 → 片段查看、失败重试与删除。此阶段还没有聊天界面或回答生成。

旧MD/TXT无需重新上传，解析状态parsed保持不变。建立索引是显式操作；上传本身不调用Embedding。
只有全部片段写入成功才index_status=completed，页面显示“可检索”。

## 你来配置

导师没有读取/输出/写入你的密钥，也没有对真实硅基流动服务发起请求。
当前环境依赖已安装，仍列出命令便于你独立重现配置；开发数据库迁移由你执行。

在项目根目录终端执行：

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

预期版本 `0005_document_chunks (head)`。迁移添加向量表与索引状态，旧文档默认为未建索引。
不要为了排错downgrade；回滚会删除向量和索引状态。

保留 apps/api/.env 的原有配置，追加或更新下面的键，只在本地填入真实值：

```dotenv
SILICONFLOW_API_KEY=<你的硅基流动密钥>
EMBEDDING_BATCH_SIZE=16
INDEXING_TIMEOUT_SECONDS=60
```

如果.env不存在，可参考同目录.env.example创建；不要覆盖已有数据库/来源/会话配置。
不要把密钥发到聊天里、写进前端.env、使用NEXT_PUBLIC_或提交Git。
固定使用 https://api.siliconflow.cn/v1/embeddings 与 BAAI/bge-m3，输出1024维稠密向量。
不使用稀疏/ColBERT输出，也不自动切换其他模型或Pro模型。
SILICONFLOW_API_KEY变化需要重启后端；迁移本身不替代重启。

完成两项后告诉导师“迁移和密钥配置已完成”，导师可重启当前后台8000服务，避免重复占用端口。
若后端本来由你自己的终端运行，停止旧进程后在apps/api自行启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

导师后台更新的新版本在未完成迁移时ready/文档接口会返回503；这不是模型密钥已经被验证。
重启后健康就绪检查 http://127.0.0.1:8000/health/ready 应返回ready，它只检查本地数据库结构，
不会付费调用模型或验证模型权限。模型权限在你实际点击建立索引时验证。

## 完整流程验收

先用没有敏感信息的小文档。确认索引会将片段发送到硅基流动，可能产生服务调用费用；
不要用公司内部资料做首次测试，也不要假设该模型永久免费。
前端 http://127.0.0.1:3001。

| 操作 | 预期 |
| --- | --- |
| 进入已有MD/TXT文档知识库 | 已解析保持不变，新增“未建索引” |
| 点击数据库图标并取消 | 未建索引不变，不发送Embedding请求 |
| 再次确认建立索引 | 等待后显示可检索与真实片段数量 |
| 点击层叠图标查看片段 | 模型BAAI/bge-m3、1024维、正文及标题路径 |
| 再次确认相同文档索引 | 相同指纹直接复用，数量/片段ID不重复 |
| 上传可复制文本PDF并建立索引 | 解析成功，片段显示原PDF的1-based页码 |
| 上传扫描/加密/损坏PDF | 明确解析失败，不伪装成可检索 |
| 删除测试文档/知识库 | 文档、chunks、向量不可访问，正常文件清理仍执行 |

部分PDF页面无文本时显示警告，仅有文本页面进入索引。完全无文本PDF不支持OCR。
PDF排版、表格、数学公式提取可能不准确；本轮不能承诺恢复原始阅读顺序或复杂布局。
缺密钥、无权限、429、超时、异常向量和并发删除由自动化覆盖；不需要你故意泄露密钥或制造网络故障。

## 分块和限制

- 使用langchain-text-splitters 1.1.3；Markdown保留代码缩进与标题元数据，PDF按页分块。
- 片段2000个UTF-8字节、最多重叠200字节；这不是精确的BGE tokenizer计数。
- 最多200个片段，超限在模型调用前失败；请拆分文档，而不是无限增大免费额度。
- 无法保证超长代码块始终完整地放在一个片段；正文保留，长代码可能跨片段。
- 未闭合Markdown代码围栏采用保留全文的回退，不丢弃末尾代码。
- 单文件10MiB；PDF最多100页、提取文本最多200万字符、解析子进程20秒超时。
- pypdf配置每个主要解压流4MiB及复杂度边界；Linux子进程另有512MiB地址空间/CPU限制，
  Windows本轮没有硬内存额度，仍不应把它当作生产级恶意PDF沙箱。
- Embedding每批最多16，响应数量/顺序/1024维/有限非零数值全部检查，并单位归一化。
- 模型请求总预算默认60秒（5–90秒可配），不含分块和数据库耗时；前端转发/等待120秒。
- 不自动重试429或网络失败，不自动调用聊天模型，也不引入模型下载或GPU配置。

## 故障和恢复

索引中重复请求409；模型错误保存为index_status=failed，解析文本仍保留。
失败不会写入部分向量；重建失败时旧chunks保留供诊断，但failed不显示为可检索。
片段弹窗会说明旧片段状态，未来检索必须只选择completed索引。
断网/前端超时先刷新确认结果；进程崩溃留在索引中时，超过5分钟可再次建立索引。
新的run_id会阻止迟到旧请求覆盖新结果；请求期间删除文档不会被模型返回结果复活。
向量发布使用一次事务全部替换，删除沿用第二阶段的私有文件清理任务机制。

当前采用请求内索引，不是生产可靠队列。外部请求期间不持有数据库行锁，但同步HTTP仍占一个工作线程。
数据库和私有上传目录需要一起备份；更换模型/维度属于数据兼容性变更，不随意改成其他维度。
迁移固定VECTOR(1024)，此阶段只验证精确余弦查询，不添加HNSW/IVFFlat。

## 代码阅读

- app/rag/loaders.py、pdf_worker.py：PDF子进程、时间与内容限制、页码范围。
- app/rag/splitter.py：LangChain结构分块与保守字节预算。
- app/rag/embeddings.py：LangChain Embeddings接口、硅基流动请求、绝对超时与安全错误。
- app/services/indexing_service.py：短事务claim、外部调用、run_id校验及原子发布。
- app/models/chunk.py、0005_document_chunks.py：1024维向量、所属信息和迁移。
- 前端index-dialog.tsx、chunks-dialog.tsx：索引确认、费用/数据外发提示、片段预览。

## 验证记录

2026-10-13：99项后端测试通过，1项Windows符号链接权限测试跳过；35项浏览器测试通过。
包含隔离PostgreSQL 0004旧文档回填、005 upgrade/check/downgrade、错误维度约束、精确余弦查询、
并发claim/删除和迟到失败令牌校验。PDF控制字符、页数/解压/文本限制及超时子进程回收已验证。
独立审查发现的Markdown末尾丢失、PDF NUL持久化与模型EOF超时问题均已通过失败复现并修复。
浏览器中的成功索引仅使用隔离测试替身；没有把假向量写进开发数据库。
类型检查、Ruff和生产构建通过，手机截图已检查；开发库仍停在0004，未自动执行005或真实模型调用。

## 官方依据

[硅基流动Embedding接口](https://siliconflow.readme.io/reference/createembedding)、
[BGE-M3模型卡](https://huggingface.co/BAAI/bge-m3)、
[LangChain分块文档](https://reference.langchain.com/python/langchain-text-splitters/langchain_text_splitters)、
[pypdf文本提取边界](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。
