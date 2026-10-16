# MD/TXT 上传与解析：配置和集中验收

## 本轮已实现

知识库名称入口 → 文档列表 → 单文件上传 → SHA-256 去重 → 私有存储 → UTF-8 文本提取
→ 纯文本预览 / 失败原因 → 重新解析 / 删除 → 首页真实文档数量。
解析完成表示 parsed，不表示可检索；PDF、分块、Embedding 和问答留在后续阶段。

## 用户配置

这一轮新增 python-multipart 和 0004_documents 迁移；导师仅迁移了隔离测试库，未迁移开发库。
API 的默认存储在 apps/api/storage/uploads，目录会在首次上传时创建，不需要填写模型密钥。
相对 UPLOAD_DIR 总是按 apps/api 解析，不随终端工作目录变化。

在项目根目录打开 PowerShell：

```powershell
cd apps/api
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

预期迁移版本为 `0004_documents (head)`。不要执行 downgrade 来解决配置问题，回滚会移除文档表。
安装步骤在导师当前环境中已执行，保留该命令是为了你能独立复现环境。

导师已更新此前后台启动的8000后端，当前只需完成迁移，无需重复启动。
将来若自己的终端仍在运行旧后端，停止该终端的服务并重新启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
```

不要同时启动两个8000服务。若当前服务由导师后台启动并已更新，只需执行迁移，无需再启动。
前端为 http://127.0.0.1:3001；API就绪检查 http://127.0.0.1:8000/health/ready 必须返回 ready。
health 仅证明进程存活；ready 会检查包括文档表在内的实际数据库结构。

可选自定义配置，添加到 apps/api/.env，而不是前端：

```dotenv
UPLOAD_DIR=storage/uploads
MAX_UPLOAD_BYTES=10485760
```

上传目录不能放在 apps/web/public、网站静态目录或共享可公开读取位置。
MAX_UPLOAD_BYTES 只能降低，当前最大支持 10485760 字节（10 MiB）。
浏览器和前端转发按10 MiB配置；后端根据实际设置拒绝更小的上限。
服务账号需要该目录的创建、读取、写入及删除权限。无需手动建立文档UUID文件。

## 一次性验收

用新建的“上传流程验收”知识库，不删除现有学习资料。
项目 examples/uploads 中准备了 React Markdown、Python TXT、空文件与不支持的 JSON 示例。

| 场景 | 操作 | 预期 |
| --- | --- | --- |
| 正常上传 | 点击知识库名称，分别上传两个 UTF-8 示例 | 文档数2；均为已解析，显示字符数 |
| 内容核对 | 点预览 | 中文、标题与代码文本保留；不会执行代码或HTML |
| 持久化 | 刷新页面，侧栏进入概览 | 文档仍在，首页文档总数增加2 |
| 内容去重 | 同一文件改名后再次上传 | 同内容提示，数量不变；不是按文件名去重 |
| 无效文件 | 上传空文件或JSON/PDF | 拒绝，数量不变；PDF本轮未支持 |
| 失败原因 | 上传非UTF-8或只有空白的TXT | 原文件保存，状态解析失败，有修正提示 |
| 重新解析 | 对失败记录点重新解析 | 更新结果，不新建一条记录；坏编码不因重试自动变成UTF-8 |
| 删除 | 删除一个测试文档，再删除测试知识库 | 记录和总数一致；正常情况下原文件也清理 |
| 小屏 | 缩窄窗口，打开预览 | 上传区域不溢出，关键状态在文档名下可见，表格可横向滚动 |

超限边界、并发重复上传、跨账号权限、请求断线和文件清理失败由自动化覆盖，
不要求手工构造10 MiB文件。失败编码可通过编辑器“以编码保存”准备，文件修正后删除旧记录再上传。
重试不向用户宣称自动转码，也不引入模型调用。

## 状态与恢复

- pending：原文件与记录已保存，解析还未提交。进程中断时可能留下，可重新解析。
- processing：服务正在提取；当前同步请求在页面显示“上传并解析中”，不会保证用户看到持久化中间态。
- parsed：已提取文本，尚未向量化。
- failed：编码/空白/二进制内容或存储读取失败；列表显示具体安全错误，不暴露路径。

上传/解析/删除超时或断网时，先刷新列表确认最终结果，再决定重试；请求超时不等于服务端没有保存。
正常UTF-8文本保留段落/Markdown代码和标题；换行统一为LF。预览最多20000字符，完整文本留在数据库。
同一知识库、相同原始字节才去重；不同换行/BOM或不同知识库可分别存储。

## 私有文件清理与备份

数据库与磁盘不能原子删除。删除文档/知识库时先事务提交清理任务，随后删除私有原文件。
若磁盘拒绝删除，记录已不可访问，清理任务仍保留；原文件仍可能占磁盘空间，不宣称已经物理删除。
修好权限后在 apps/api 运行：

```powershell
.\.venv\Scripts\python.exe -m scripts.cleanup_document_files
```

每轮最多处理1000个清理任务；pending非零时查看权限/磁盘并再次运行。
该脚本只删除数据库已提交的UUID清理任务，不扫描并猜测删除任意文件。
若进程在文件落盘但记录/清理任务提交前崩溃，或数据库与文件清理同时不可用，可能留下孤立文件，
需后续维护审计；当前没有自动扫描孤立文件，以免误删仍在上传的资料。
备份需要同时保存数据库和UPLOAD_DIR，且保持同一份配置；更换目录不会自动迁移旧文件。

## 代码阅读路径

- apps/web/components/documents/upload-form.tsx：选择文件、FormData、请求状态。
- apps/web/components/documents/document-workspace.tsx：真实列表、分页、错误、重试与刷新。
- apps/web/components/documents/document-dialog.tsx：纯文本预览和删除确认。
- apps/api/app/api/routes_documents.py：接口与认证入口。
- apps/api/app/services/document_service.py：所属检查、去重、解析生命周期与数据库事务。
- apps/api/app/services/document_storage.py：UUID路径、流式写入上限、清理任务。
- apps/api/app/rag/loaders.py：UTF-8 BOM、换行、非法内容检查。
- apps/api/app/db/migrations/versions/0004_documents.py：模型迁移。

开发服务器不是生产部署：公网还需要HTTPS、反向代理限流、总存储配额、任务队列和备份策略。

## 自动化记录

2026-10-13：67项后端测试通过（包括隔离PostgreSQL迁移、alembic check、并发去重及级联清理）；
1项Windows符号链接创建测试因权限跳过，路径遍历检查仍运行通过。
30项浏览器测试在独立8002/3002环境通过，类型检查、Ruff及生产构建通过，桌面/手机截图已检查。
未执行开发库0004；后台开发服务已加载新代码，缺少迁移时ready或文档接口会返回503。
独立审查指出并修复了前端转发10MiB边界、列表正文加载及回滚文件持久清理任务的问题。
精确10MiB上传、SQL不读取列表正文、磁盘清理失败可恢复都已加入回归测试。
