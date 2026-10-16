# 阶段 3：分块与向量入库

预算：每周 5–10 小时。状态：用户已完成0005迁移、密钥配置和真实链路验收。
模型选择：硅基流动BAAI/bge-m3、1024维稠密向量。配置与流程见03-indexing-guide.md。

## 主要位置

- `apps/api/app/rag/loaders.py`
- `apps/api/app/rag/splitter.py`
- `apps/api/app/rag/embeddings.py`
- `apps/api/app/models/chunk.py`
- `apps/api/app/db/migrations/versions`

## 开发任务

- [x] 增加文本 PDF 提取和页码元数据，扫描 PDF 返回明确失败。
- [x] LangChain结构分块，保留正文/缩进与标题；使用UTF-8字节预算，不伪称精确token计数。
- [x] 确定模型、1024维、批次16、网络及总请求超时，添加向量表迁移。
- [x] 写入chunks后独立index_status=completed；失败可重试、原子发布、幂等复用；用PostgreSQL精确余弦验证。

## 功能验收

- [x] MD/TXT/PDF 产生可检索 chunks、向量和定位信息。
- [x] 向量维度一致；无密钥时清晰报配置错误；失败文档不伪装成功。
