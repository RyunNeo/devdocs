# 上传与解析流程实施方案

日期：2026-10-13。依据既有蓝图与用户要求，导师实现代码，用户完成开发数据库迁移并集中验收。

## 范围

- 从知识库名称进入文档页，单文件 MD/TXT 上传、列表分页、解析文本预览、失败重试和删除。
- 单文件 <= 10 MiB；UTF-8/UTF-8 BOM；保留 Markdown 原始标题与代码，不执行、不渲染 HTML。
- 原文件用服务生成的 UUID 存在 API 私有目录；SHA-256 在同一知识库去重。
- 当前采用同步解析，上传按钮在请求内显示上传/解析中；API 返回 parsed 或 failed。
  parsed 仅表示提取文本，不代表 completed/可检索。pending 记录用于中断后的恢复。
- 不引入队列、PDF、分块、Embedding、模型密钥、RAG 或生产配额系统。
- 数据库删除与磁盘删除无法原子提交，使用事务内清理任务表；提交后清理，失败保留任务供维护脚本重试。

## 数据与接口

- 0004_documents：documents 与 storage_cleanup_tasks；知识库外键级联。
- 文档存 id、knowledge_base_id、user_id、filename、file_type、size_bytes、content_hash、storage_key、
  status、error_message、extracted_text、character_count 与时间戳。列表不返回文本或文件路径。
- POST /knowledge-bases/{id}/documents：multipart file，201；非法格式400，超限413，重复409。
- GET /knowledge-bases/{id}/documents：limit/offset 分页。
- GET /documents/{id}：状态和最多20000字符预览，附 truncated 标识。
- POST /documents/{id}/retry：恢复 pending/failed，200；parsed 幂等返回。
- DELETE /documents/{id}：204；删除知识库同样安排全部原文件清理。
- GET /documents/summary：当前用户文档总数。
- 每个入口强制当前用户所属检查；外用户资源统一404。原文件不挂载静态路由。

## 实施与验证

1. 先添加真实 API 测试：上传/去重/解析失败/重试/分页/越权/清理，观察缺失路由失败。
2. 增加模型、0004迁移、路径安全存储、UTF-8 loader、清理任务与服务；锁知识库避免上传和删除竞态。
3. 安装并锁定 python-multipart；采用现有 Starlette 请求体限制器，覆盖无 Content-Length 的请求。
4. 在独立测试数据库验证 upgrade/check/downgrade，不代替用户执行开发数据库迁移。
5. 先写浏览器链路测试，再实现文档页、选择文件/提交、列表、预览弹窗、重试与删除确认，接真实首页文档数量。
6. 独立代码审查、后端回归、前端类型检查/构建与桌面/手机截图检查。
7. 提供一次配置清单及完整流程验收表；不自动进入下一阶段。

## 已知边界

同步解析适用于当前小文件/个人练习，不是生产可靠任务队列，不会伪造处理百分比。
同一知识库操作用 PostgreSQL 行锁串行化；SQLite 仅用于测试，不作为生产并发方案。
失败文档保留原文件便于诊断与重试；编码错误需要删除后上传 UTF-8 修正版。
清理任务可能因磁盘权限失败留存，维护脚本可重试；备份必须同时包含数据库和私有存储。
当前仅请求体大小限制，不宣称完整抵御恶意流量，公网部署还需反向代理限流/超时与总存储配额。

## 实施记录

- API缺失时上传测试404失败，补全后通过；浏览器缺少知识库链接时失败，补全后通过。
- 独立审查发现三个边界，逐一通过失败回归复现并修正；恰好10MiB的multipart前端转发实际验证。
- 67项后端与30项浏览器测试通过，1项Windows符号链接测试权限跳过；构建/Ruff/类型检查通过。
- 开发数据库未迁移，留给用户执行0004。测试数据库与私有文件均在隔离环境。

## 技术依据

[FastAPI 上传文档](https://fastapi.tiangolo.com/tutorial/request-files/)
与 [Starlette 请求体限制](https://www.starlette.io/middleware/)；实际实现对照本地安装版本。
