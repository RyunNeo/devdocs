# 第三阶段：PDF与可检索索引链路

用户已验收第二阶段，指定硅基流动 BAAI/bge-m3。导师写代码，用户自行配置后端密钥和执行迁移。

## 范围与接口

- MD/TXT保留已有流程，增加文本PDF；扫描件、加密或损坏PDF失败，不引入OCR。
- pypdf在独立子进程解析，限制页数/解压流/提取文本与时间；正文及页码范围存数据库。
- LangChain结构分块，UTF-8字节上限2000、重叠200，最多200块。字节预算是保守输入限制，
  不是BGE tokenizer计数；不伪称精确token数。超大片段和代码可能跨块，保留正文和结构元数据。
- 硅基流动 /v1/embeddings，固定BAAI/bge-m3、1024维稠密float向量；批次16，单次网络超时，
  总耗时预算60秒。验证维度、数量、索引、有限数值和非零向量，不盲重试。
- 新增独立index_status，解析parsed保持不变；索引completed才显示可检索。
- POST /documents/{id}/index：显式触发；相同指纹且已完成则幂等、不重复调用。
- GET /documents/{id}/chunks：分页查看文本、页码/标题、模型及维度，不返回原向量。
- 无密钥给出配置错误。索引失败安全提示，允许重试；不能显示部分成功。
- 005迁移：索引状态/运行令牌/时间/指纹/块数与来源元数据，document_chunks VECTOR(1024)。
- 删除文档或知识库连同chunks清理；不增加聊天、SSE、Agent、OCR、ANN索引或生产队列。

## 事务与费用

Claim阶段短事务锁知识库，提交索引中与随机run_id；外部调用不持有数据库行锁。
发布前重新检查所属、run_id和文档存在，事务替换全部chunks后标记completed。
失败不写入部分向量；旧chunks保留但failed不宣称可检索。删除中的文档不能被迟到请求复活。
活跃运行重复请求409；超过安全租期可重试，旧运行令牌无法覆盖新运行。
chunk指纹包含原始内容哈希、模型、分块版本，模型/参数变化需重建。
显式点击建立索引会将文档片段发送到硅基流动；用户应先使用无敏感信息样本文档。
本轮测试只使用测试替身/本地传输，不自动调用真实服务、不读取或输出密钥。

## 实施和验收

1. PDF/分块/provider/索引所有权和幂等测试先失败再实现。
2. 锁定pypdf、langchain-text-splitters/core、pgvector、httpx及其新增依赖。
3. 用隔离PostgreSQL验证005 upgrade/check/downgrade、1024维约束、原子发布和删除。
4. 页面PDF选择、索引确认与状态、片段预览、失败重试；旧上传/CRUD测试保持通过。
5. 独立审查，完整后端/浏览器回归、构建和桌面/手机截图。
6. 用户执行迁移和填写SILICONFLOW_API_KEY；真实Embedding调用由用户自行验收。

## 实施记录

所有主要链路已实现，用户开发库只读确认0004；0005和密钥仍由用户配置。
99项后端、35项浏览器测试通过（1项Windows符号链接测试权限跳过），Ruff/构建/类型检查通过。
独立审查的三个问题先通过失败回归复现，再修正；测试不调用真实硅基流动服务。

## 技术依据

[硅基流动接口](https://siliconflow.readme.io/reference/createembedding)、
[BGE-M3模型卡](https://huggingface.co/BAAI/bge-m3)、
[pypdf提取说明](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)。
依赖和Next转发超时对照本地版本实现。
