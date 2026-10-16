# 本地生产环境演练：逐步操作记录

本模块按用户要求改为教学式推进：助手编写当前步骤的代码与说明，用户亲自执行配置、Docker、迁移、备份和恢复；每步确认结果后再继续。
尚未完成全部演练，不能将本指南视为已经上线的部署结果。

## 第一步：Docker 环境（用户已确认）

Docker version 同时有 Client/Server，Docker Compose 为 v2 或以上，docker info 的 OSType 为 linux。
这一步不启动项目、不修改数据。

## 第二步：独立演练配置（用户已确认）

从项目根目录执行：

```powershell
.\apps\api\.venv\Scripts\python.exe -m infra.deploy.config
```

预期提示已生成 infra/deploy/.env.rehearsal，数据库密码随机生成且不显示；模型密钥保持空，未启动容器、未连接数据库。
文件已存在时保留原配置，不覆盖或重新生成密码。

配置含义：

| 配置项 | 用途 |
| --- | --- |
| REHEARSAL_PORT=3100 | 后续本机演练入口，与开发页面 3001 分开；现在尚未启动 |
| POSTGRES_USER / POSTGRES_DB | 独立演练数据库账号与库名 |
| POSTGRES_PASSWORD | 随机密码，不能改成开发默认密码，不要发到聊天 |
| SILICONFLOW_API_KEY | 当前留空，暂不执行收费模型调用 |
| CHAT_MODEL | 仅设置模型名，不代表会调用模型 |
| DAILY_CHAT_LIMIT / DAILY_INDEX_LIMIT | 演练账号的每日业务配额 |

仅检查文件是否存在，不输出内容：

```powershell
Test-Path .\infra\deploy\.env.rehearsal
```

预期 True。不需要手动填写或复制开发密钥，不要将真实配置内容粘贴到聊天。
现有 .gitignore 排除 .env.*；本项目暂时没有 Git 仓库，后续若引入版本控制仍需核对凭据未被跟踪。
这份配置不是加密保险箱，本机有权限的用户仍可能读取；Windows 下文件访问权限由系统 ACL 决定。

## 第三步：编写并校验数据库 Compose（用户已确认退出码 0）

已添加 infra/deploy/compose.rehearsal.yml，目前只有 postgres 服务，前后端将在后续步骤逐步加入。
不要修改根目录开发用 docker-compose.yml。

- image：沿用支持 pgvector 的 PostgreSQL 16 镜像。
- environment：密码等值来自独立演练配置；缺少配置会报错，而不是回退到开发默认密码。
- volumes：postgres_data 保存数据库文件，Compose 项目名前缀用于隔离；../postgres/init 只读挂载初始化 SQL，安装 vector 扩展。
- healthcheck：检查数据库是否接受连接，不等于业务表已迁移或功能验收完成。
- 不设置 ports：不占用宿主机 5432，后端将通过容器网络访问 postgres:5432。

先只检查配置，不拉取镜像、不创建容器或数据卷：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml config --quiet
```

紧接着检查上一条命令退出码：

```powershell
$LASTEXITCODE
```

预期首条无输出，退出码为 0。--quiet 避免展开数据库密码；不要去掉该参数后将完整配置发到聊天。
当前命令只是语法/配置解析检查，不证明数据库已经运行。确认本步结果后，再指导实际创建独立数据库。

## 第四步：用户启动独立数据库（已确认 healthy）

先确认 Docker 指向本机：

```powershell
docker context inspect --format '{{.Endpoints.docker.Host}}'
```

Docker Desktop 下通常输出 npipe:// 开头的本机命名管道，或 unix:// 开头的本地 socket。若是 ssh://、tcp:// 或执行失败，先停止并反馈，不启动项目。
检查会覆盖配置或目标的终端变量，只显示变量名、不显示值：

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -in @('DOCKER_HOST', 'DOCKER_CONTEXT', 'POSTGRES_USER', 'POSTGRES_DB', 'POSTGRES_PASSWORD', 'COMPOSE_PROFILES') } | Select-Object -ExpandProperty Name
```

预期无输出。有变量名时先反馈，不自行清空全局环境变量或继续启动。显式 -p/-f/--env-file 限定项目与文件，但环境变量仍可能覆盖 dotenv 值。

以上检查满足条件后，由用户执行：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml up -d --wait --wait-timeout 120 postgres
```

首次可能联网下载镜像。命令将创建 devdocs-rehearsal 项目专属网络、数据库数据卷和 postgres 容器，等待数据库健康；不启动前端、后端，不执行业务迁移，不调用模型。
此时可产生数据库初始化文件，但不连接开发数据库，也不占用宿主机 5432。

然后检查状态：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml ps
```

预期 postgres 为 Up / healthy，PORTS 可能显示 5432/tcp（容器内端口），但不能出现 0.0.0.0:5432-> 或 127.0.0.1:5432-> 宿主机映射。
若下载失败、超时或 unhealthy，停在此步并反馈错误，不使用 down -v 或删除卷重试。不要修改已初始化数据库的密码来尝试修复连接。
健康状态仅证明数据库就绪；vector 扩展和业务迁移将在后续步骤分别核对。

## 第五步：核对数据库身份与向量扩展（用户已确认）

从项目根目录执行只读 SQL：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml exec -T postgres psql -U devdocs_rehearsal -d devdocs_rehearsal -c "SELECT current_database() AS database_name, current_user AS user_name, extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

预期一行：database_name 与 user_name 均为 devdocs_rehearsal，extname 为 vector，extversion 为已安装的实际版本，不要求固定版本号。
这能确认查询的是独立演练库，且首次初始化 SQL 已安装 pgvector；healthy 本身不能证明扩展存在。
查询通过容器内 psql 执行，不需要开放宿主机数据库端口或显示密码。
如返回 0 rows 或连接失败，保留容器和数据卷并反馈，不手动删卷或修改数据库密码。
此时还没有通过 Alembic 创建业务表，用户/知识库等业务表将在后端镜像准备后由用户执行迁移。

## 第六步：只构建后端镜像（用户已确认）

已准备 api.Dockerfile、根目录 .dockerignore 和 Compose 的 api 服务定义；本步不启动 api、不初始化业务表。
Dockerfile 先安装锁定 Python 依赖，再复制业务代码及 Alembic 文件；运行阶段采用 UID/GID 10001 的非 root 用户、单 Uvicorn worker，不启用热重载，不在启动命令中自动迁移。
镜像不包含开发 .env、虚拟环境、原上传文件、work 或评测结果。运行配置通过 Compose 在启动容器时注入，不通过构建参数放入镜像。
容器里的数据库地址是 postgres:5432，指向同一演练网络的服务，不是宿主机上的 127.0.0.1:5432。

先由用户重新校验配置：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml config --quiet
```

紧接着查看 $LASTEXITCODE，只有为 0 时才继续：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml build api
```

首次需要联网下载 Python 基础镜像和锁定依赖，可能耗时几分钟；失败时反馈错误，不手动更新依赖版本绕过。
成功通常显示 devdocs-rehearsal-api:local 已构建。可检查镜像存在：

```powershell
docker image inspect devdocs-rehearsal-api:local --format '{{.Id}} {{.Config.User}}'
```

预期为 sha256:... 和 10001:10001。这条只取镜像 ID 与运行用户，不输出环境配置。
本步成功仅表示镜像能构建且运行用户符合配置，不代表后端业务启动/数据库认证/上传卷权限已经验收。
不要执行 up api 或不带服务名的 up；后续还要显式初始化上传存储卷并执行一次性迁移。
已有演练 postgres 和开发服务不需要停止。助手不会替用户构建、启动容器或读取真实配置。

## 第七步：初始化上传卷与迁移演练库（用户已确认）

镜像 ID 已由用户检查，运行用户为 10001:10001。本步仅修改演练栈的新卷/数据库，不启动 API。
新增两个 maintenance profile 的一次性任务；无需重新构建后端镜像。
storage-init 暂以 root 执行固定目录的属主与权限设置，只有 uploads 卷可写且无网络；业务进程仍是非 root。
migrate 继承镜像非 root 用户，只传演练 DATABASE_URL，不传模型密钥或挂载上传资料。
profiles 使维护任务不会随普通 up 自动运行；需要明确指定任务。

先校验本次 Compose 修改：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml --profile maintenance config --quiet
```

检查 $LASTEXITCODE 为 0 后，初始化上传目录：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml --profile maintenance run --rm --no-deps storage-init
```

预期 uploads initialized 且 $LASTEXITCODE 为 0。--rm 只清理这次临时任务容器，命名 uploads 数据卷保留；--no-deps 不启动其他服务。
只处理 /data/uploads 目录本身，不递归改动文件或删除数据。

成功后由用户执行一次性迁移：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml --profile maintenance run --rm --no-deps migrate
```

预期退出码 0，演练库升级到当前 head；SQL 初始化扩展与业务迁移是两件不同的事情。
最后读取迁移版本（覆盖此次临时任务命令，不再执行 upgrade）：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml --profile maintenance run --rm --no-deps migrate python -m alembic current
```

当前预期 0007_usage_events_counters (head)。迁移命令会创建演练业务表，但不迁移/读取开发库资料，不调用模型。
每条命令成功后才继续；失败先反馈错误，不修改密码、不删卷、不强行 downgrade。
本步仅适用于本次全新演练库。未来有真实演练数据后的版本升级要先备份，不能以此跳过备份流程。

## 第八步：启动后端并检查就绪（用户已确认）

用户已确认 uploads initialized 和 0007_usage_events_counters (head)，现在可以启动 api。
从项目根执行，复用已构建镜像，不重建、不启动依赖，不重新迁移：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml up -d --no-deps --no-build --wait --wait-timeout 120 api
```

仅在原有 postgres 仍健康运行的情况下执行；失败先反馈，不开放 8000 或改用开发数据库。
随后检查状态：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml ps
```

预期 api 与 postgres 均 healthy。8000/tcp 和 5432/tcp 仅表示容器内端口，不应出现宿主机映射。
通过容器内请求核对就绪状态与非 root 上传权限：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml exec -T api python -c "import json, os, urllib.request; result = json.load(urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5)); result['runtime_uid'] = os.getuid(); result['uploads_writable'] = os.access('/data/uploads', os.W_OK); print(json.dumps(result))"
```

预期 status=ready、database=postgresql、pgvector 有版本值、runtime_uid=10001、uploads_writable=true。
os.access 仅检查权限，不代替后续真实上传验证，也不验证磁盘剩余空间。
本步只运行服务与只读健康检查，不调用真实模型；此时尚无演练网页入口，不能访问开发用 8000/3001 来代替验收。
如启动失败或 uploads_writable=false，保留现场反馈，不以 root 运行业务进程或递归修改宿主机目录。

## 第九步：只构建前端生产镜像（用户已确认）

后端已由用户确认 ready、pgvector=0.8.7、UID=10001、上传目录可写。接下来准备网页入口，但先只构建，不启动。
新增 web.Dockerfile 和 web 服务，使用 Node 22、多阶段构建与 Next.js standalone。
构建时启用 DEPLOY_STANDALONE=1；日常开发未设置该变量，保持原有行为。
standalone 的追踪根为项目根，包含 monorepo 运行依赖，另外显式复制 static 和 public。最终镜像不复制整个开发目录。

需要注意两种配置：

- API_BASE_URL=http://api:8000：容器内请求及 /api 代理指向同网络的 api，不是开发后端；rewrites 在构建时固化，更换代理目标后需要重新构建。
- SESSION_COOKIE_NAME=devdocs_rehearsal_session：与演练后端 COOKIE_NAME 对齐，否则登录后服务端仍可能认为未登录。恢复环境未来需两端一起设置新的名称。

先校验配置并检查 $LASTEXITCODE 为 0：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml config --quiet
```

然后只构建前端镜像：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml build web
```

首次会下载 Node 基础镜像及 npm 锁定依赖，并执行生产构建；需要网络和磁盘空间。构建阶段保留 TypeScript/Tailwind 等开发依赖供编译，最终阶段只复制追踪出的运行产物。
本步骤不重启正在运行的 api/postgres，不迁移数据库，不调用真实模型，不把模型密钥提供给前端。
成功后检查镜像：

```powershell
docker image inspect devdocs-rehearsal-web:local --format '{{.Id}} {{.Config.User}}'
```

预期 sha256:... 10001:10001。镜像构建成功不等于网页登录、SSE 和代理全部通过，实际验收在启动后进行。
先不要执行 up web 或直接浏览 3100；下一步将先检查端口，再由用户启动网页入口。

## 第十步：启动网页入口并验证登录（用户已确认）

确认原有演练 api/postgres 仍正常。先只读检查默认入口端口是否被占用：

```powershell
Get-NetTCPConnection -LocalPort 3100 -State Listen -ErrorAction SilentlyContinue
```

预期无监听记录。如有记录，先反馈，不停止占用进程、不直接覆盖已有服务；若配置中自行修改过 REHEARSAL_PORT，应检查对应端口。
确认空闲后，由用户执行：

```powershell
docker compose --project-name devdocs-rehearsal --env-file .\infra\deploy\.env.rehearsal --file .\infra\deploy\compose.rehearsal.yml up -d --no-deps --no-build --wait --wait-timeout 120 web
```

复用现有镜像，只启动 web，不重建、不迁移、不启动依赖。随后运行同一 Compose 命令的 ps，预期 web/api/postgres 全部 healthy。
web 的宿主机端口应为 127.0.0.1:3100->3000/tcp，不是 0.0.0.0:3100；api/postgres 仍不发布端口。
通过网页入口检查代理，不能用开发后端地址代替：

```powershell
Invoke-RestMethod http://127.0.0.1:3100/api/health/ready
```

预期 status=ready、database=postgresql，pgvector 有版本值。此检查不需要登录且不调用模型。
浏览器打开 http://127.0.0.1:3100，在演练环境注册测试账号，登录后刷新，验证能保持登录且无循环跳转。
开发数据库的账号/知识库不会自动出现在演练环境；这是预期隔离，不要因此导入开发库。
不用发送密码、Cookie 或真实配置，只反馈服务状态、代理检查结果和能否完成注册/登录。
如果端口占用、网页错误、注册 403 或登录后跳回登录页，保留容器和数据卷并反馈，不改为 root、不关闭来源检查、不删除卷。
本机 HTTP 和环回绑定仅适合本地演练，尚未完成 HTTPS、公网访问控制或后续备份恢复验收。

## 第十一步：无模型业务链路验收（用户已确认）

仍使用 http://127.0.0.1:3100，不切换到开发页面 3001。
此步留下一组后续重启与备份恢复要核对的测试记录，不代表已经验证有依据 RAG 回答质量。

1. 创建名为“部署演练验收”的全新知识库，描述填写“用于重启和恢复验证”。
2. 暂不上传资料，先在该空库提问“这个知识库有哪些资料？”。预期显示没有足够文档依据的本地回复，而不是 500、一直生成或凭空编造。
3. 切换“历史会话”，重新打开本次会话，再刷新页面，预期问题与完整回复仍可恢复。
4. 在该知识库上传项目现有 evals/fixtures/product.md。预期成功解析且预览可读；不要点击建立索引或批量索引。
5. 访问“个人用量”，预期能看到这次问答记录，问答次数增加 1；空库本地回复不调用 Embedding 或对话供应商，但仍占本站问答配额。
6. 退出后重新登录，确认知识库、文档和历史仍存在。暂不删除这些验收资料，后续用于持久化和恢复核对。

本步无需填写模型密钥，不产生模型费用。上传解析与建立向量索引是不同操作，解析成功不代表已经可以基于该文档回答。
异常反馈只需页面现象或错误编号，不要发送密码、Cookie、密钥或非测试私有文档。
确认本步后再进入重启演练，当前不要自行 down -v、删卷或清理 Docker 项目。

## 第十二步：重建容器并核对持久化

本步由用户执行，会短暂停止演练网页。先等待所有上传与问答结束，期间不操作页面。
使用相同的已有镜像和配置，不重新生成密码、不更新镜像、不迁移数据库。
和单纯 restart 相比，force-recreate 会替换容器，更适合检查业务数据是否确实保存在命名卷中。
只针对本次演练测试数据，不操作开发项目；实际生产更新应另走备份与升级流程。

为减少重复输入，在项目根目录的同一个 PowerShell 会话定义参数数组（本身不执行 Docker）：

```powershell
$dc = @('compose', '--project-name', 'devdocs-rehearsal', '--env-file', '.\infra\deploy\.env.rehearsal', '--file', '.\infra\deploy\compose.rehearsal.yml')
```

先读取上传文件数量和汇总校验值，不显示文件正文：

```powershell
docker @dc exec -T api python -c "import hashlib, json; from pathlib import Path; files = sorted(Path('/data/uploads').glob('*.bin')); print(json.dumps({'files': len(files), 'sha256': hashlib.sha256(b''.join(p.name.encode() + hashlib.sha256(p.read_bytes()).digest() for p in files)).hexdigest()}))"
```

记录结果，files 应至少为 1；如为 0，停下检查上一步上传，不继续重建。
随后优雅停止三项演练服务（web/api 先于数据库停止）：

```powershell
docker @dc stop web api postgres
```

只有停止成功才继续，以相同镜像重建容器并等待健康：

```powershell
docker @dc up -d --no-build --pull never --force-recreate --wait --wait-timeout 120 postgres api web
```

命名 postgres_data 和 uploads 数据卷保留，不使用 down -v 或任何卷删除命令。
若失败，停下反馈，不通过删卷或重新初始化密码排障；演练页面此时可能暂不可用。
成功后重复上面的文件数量与汇总校验命令，预期 files 和 sha256 均与重建前完全一致。
再执行：

```powershell
Invoke-RestMethod http://127.0.0.1:3100/api/health/ready
```

预期 ready。浏览器刷新，必要时重新登录，核对“部署演练验收”知识库、文档预览、历史问答和已有用量记录仍存在，不需要再提问或建立索引。
检查已有用量记录而非强制比较“今日剩余额度”，因为跨日额度按既定规则重置。
本步通过不等于备份已完成：命名卷仍只在本机，误删卷或磁盘故障仍会丢数据，下一步必须学习成对备份。

### files=0 时先定位，不继续重建

用户反馈首次文件校验 files=0。尚未确认发生在重建前还是重建后，不能将其判断为容器重建导致文件丢失。
先暂停重建、重新上传、删除和清理，仅检查演练 API 的实际上传目录与演练数据库文档计数：

```powershell
docker @dc exec -T api python -c "import json; from app.core.config import Settings; p = Settings().upload_dir; print(json.dumps({'upload_dir': str(p), 'exists': p.exists(), 'files': sum(1 for f in p.iterdir() if f.is_file()) if p.is_dir() else 0, 'bin_files': len(list(p.glob('*.bin')))}))"
```

```powershell
docker @dc exec -T postgres psql -U devdocs_rehearsal -d devdocs_rehearsal -c "SELECT count(*) AS documents_count, count(*) FILTER (WHERE status = 'parsed') AS parsed_count FROM documents;"
```

这两条不显示文档正文、文件名、密码或连接串，也不修改数据。若为新 PowerShell 会话，先重新定义本步的 $dc 数组。
反馈两项结果及是否已执行过 stop/force-recreate；不要以重新上传使计数变正来替代定位已有数据去向。

## 第十三步：成对备份前的一致性检查（用户已确认）

用户随后反馈当前已恢复正常并希望继续。已知此前用户/知识库/会话/消息计数为 1/1/1/2；未收到重建前后哈希对比或零文档原因，不能额外认定持久化演练完整通过。
继续备份准备前，先用 preflight.py 将数据库文档元数据与实际原文件逐一核对，不仅比较数量。
脚本只读数据库与上传卷，不打印文档名、正文、存储键、密码或连接串；不调用模型、不修复或删除数据。
在项目根目录、已定义 $dc 的 PowerShell 窗口执行：

```powershell
Get-Content -Raw .\infra\deploy\preflight.py | docker @dc exec -T api python -
```

此处只通过标准输入传入 ASCII Python 源码，不传输备份二进制；无需重建镜像或复制脚本到持久化目录。
若是新窗口，先定义：

```powershell
$dc = @('compose', '--project-name', 'devdocs-rehearsal', '--env-file', '.\infra\deploy\.env.rehearsal', '--file', '.\infra\deploy\compose.rehearsal.yml')
```

预期 documents 与 stored_files 至少为 1，各错误计数为 0，consistent=true 且 fixture_ready=true。
inventory_sha256 是可比较的原文件汇总校验值，不是备份完成标志。
如果为 0、文件缺失、哈希不符、有孤立文件或读取失败，先反馈结果，不继续备份、不自动删除“孤立”文件。
执行期间不要上传、删除或建立索引，避免并发修改造成检查结果过时；正式备份仍会先停止写入服务并重新采集清单。
本步只为备份准备；实际导出、完整备份标记及恢复尚未执行。

## 第十四步：停止写入并导出数据库

一致性检查已通过：documents=stored_files=1，各错误计数为 0，consistent/fixture_ready=true；inventory_sha256=14181424922b002a8b3e7f6a77b0d5db5ded3222e0c56174f46f4297e1e6d7c6。
开始成对停机备份，当前先导出数据库，下一步备份上传原文件并核验。数据库文件单独不算完整备份。
以下均由用户执行，助手不操作 Docker。保持同一 PowerShell 会话与 $dc 定义，操作期间不使用网页、上传、提问或运行其他维护任务。
本轮原有 web/api 正常运行；停止后演练页面会暂时不可用，postgres 保持运行。

先创建全新备份子目录：

```powershell
New-Item -ItemType Directory -Path .\infra\deploy\backups\backup-001 -ErrorAction Stop
```

已存在时先停下，不添加 -Force、不覆盖旧备份。此处保留备份批次名称，后续上传归档使用同一目录。
备份目录已排除 Git 提交和 Docker 构建上下文；转储仍是未加密的敏感数据，不能上传到公开仓库或聊天。

停止写入入口和后台业务进程：

```powershell
docker @dc stop web api
```

确认两个服务都已退出，不再有后台任务继续写入：

```powershell
docker @dc ps --all web api
```

预期两项均 Exited；若仍在运行或停止失败，不继续导出。不要在此时启动迁移、其他 API 容器或直接写数据库。
在 postgres 容器内生成二进制自定义格式转储：

```powershell
docker @dc exec -T postgres sh -c 'test ! -e /tmp/devdocs-backup-001.dump && umask 077 && exec pg_dump -U devdocs_rehearsal -d devdocs_rehearsal --format=custom --no-owner --no-acl --file=/tmp/devdocs-backup-001.dump'
```

立刻检查 $LASTEXITCODE，必须为 0；输出文件已存在时命令拒绝覆盖。其他失败也停下反馈，不删除卷或修改密码。
不使用 PowerShell > 或文本管道传递数据库二进制。
成功后从容器复制转储到本机：

```powershell
docker @dc cp postgres:/tmp/devdocs-backup-001.dump .\infra\deploy\backups\backup-001\database.dump
```

检查复制命令退出码为 0，再检查非空文件与本机 SHA-256：

```powershell
Get-Item .\infra\deploy\backups\backup-001\database.dump | Select-Object Name,Length
Get-FileHash .\infra\deploy\backups\backup-001\database.dump -Algorithm SHA256
```

这两项只查看本机导出文件，不显示转储正文。反馈文件长度与校验值即可，不发送 database.dump。
数据库转储包含账号信息、密码哈希、会话记录等敏感数据，需要本地妥善保管，不等于加密备份。
目前仍缺上传文件归档、目录/校验验证和完整备份清单，不能视为备份成功。
保持 web/api 停止，直到下一步成对备份完成再恢复；如果希望中断演练，应先说明，再恢复原有服务并使用新批次重新备份，不继续拼接发生变动的数据。

## 第十五步：备份并检查上传原文件

用户提供 database.dump 的 SHA-256 为 90DB32507A30A69EC800C025B971AC528D2E13AE7FEFF88CF0E51CF5449CCC12。
此时尚未完成数据库转储目录可读性及完整备份清单验证，不能只凭该哈希宣称备份可恢复。
继续保持 web/api 停止，postgres 运行；不要提问、上传、迁移或运行其他写数据库操作。
本步新增 backup-files 一次性任务，复用现有 API 镜像，非 root，无网络或数据库凭据，仅只读挂载 uploads 卷。
归档写入临时容器的 /tmp，临时容器需要保留到复制完成，因此本次 run 不使用 --rm。

先校验新配置，确认 $LASTEXITCODE 为 0：

```powershell
docker @dc --profile maintenance config --quiet
```

将本地 ASCII 检查/打包脚本通过标准输入交给临时容器执行：

```powershell
Get-Content -Raw .\infra\deploy\archive.py | docker @dc --profile maintenance run -T --no-deps --name devdocs-rehearsal-backup-files-001 backup-files
```

这里管道传输的是 Python 源码，不是二进制备份。脚本会拒绝非管理文件、链接或大小异常项，并在容器内自检；预期输出 files=1、inventory_sha256 与第十三步一致，退出码 0。
默认上限为单文件 10 MiB、10,000 个文件、总原文件 10 GiB，超出停止，不静默漏备。
任务成功会退出但保留容器；如果名称已存在，不删除或覆盖它，先反馈。
复制二进制归档到本次备份目录：

```powershell
docker cp devdocs-rehearsal-backup-files-001:/tmp/uploads.tar .\infra\deploy\backups\backup-001\uploads.tar
```

首次执行目标应不存在，若已有 uploads.tar 则先停下，不覆盖原文件。
复制成功后在本机做安全结构与内容校验，不解压、不读取真实配置或启动容器：

```powershell
.\apps\api\.venv\Scripts\python.exe -m infra.deploy.archive inspect --archive .\infra\deploy\backups\backup-001\uploads.tar --expected-inventory 14181424922b002a8b3e7f6a77b0d5db5ded3222e0c56174f46f4297e1e6d7c6
```

预期 files=1、matches_expected=true；归档哈希 archive_sha256 与原文件汇总 inventory_sha256 是不同口径，不应相互比较。
校验拒绝路径穿越、链接、重复成员、非普通文件、过大和截断归档，不输出原文件名、存储键或正文。
如失败，保留容器与归档现场，不删除源数据；回报固定错误或校验 JSON。
此时仍暂不启动 web/api，下一步核验数据库转储与源状态元数据，生成完整备份标记后恢复原有服务。
即便原文件已归档，本机未加密备份仍需保密；不要发送归档或转储文件到聊天。

### 第十五步验收记录

用户反馈本机归档检查结果：files=1、total_bytes=622、size_bytes=10240、matches_expected=true。
inventory_sha256=14181424922b002a8b3e7f6a77b0d5db5ded3222e0c56174f46f4297e1e6d7c6，与备份前一致。
archive_sha256=8383cdabffe9fafe12302f59ca332a941a100c5964912fd4ccd7cc98b93126d1。
这证明上传归档通过当前结构和内容检查，不代表数据库已验证或恢复演练通过。

## 第十六步：检查数据库转储可读性与复制一致性

以下仅由用户执行；助手不访问实际备份、不操作 Docker。继续保持 web/api 停止、postgres 运行，不执行其他写入或维护任务。
在项目根目录、已定义 $dc 的同一 PowerShell 会话先检查服务状态：

```powershell
docker @dc ps --all web api postgres
```

预期 web/api 为 Exited，postgres 为 Up/healthy。若不符合，先停下反馈，不继续拼接这批备份。
随后检查容器内原始转储的目录能否读取，再计算该转储的哈希：

```powershell
docker @dc exec -T postgres sh -c 'pg_restore --list /tmp/devdocs-backup-001.dump > /dev/null && sha256sum /tmp/devdocs-backup-001.dump'
$LASTEXITCODE
```

这里的重定向发生在 Linux 容器内，仅丢弃目录列表文本，不传输或修改备份二进制。
成功时退出码为 0，输出 SHA-256 应为 90db32507a30a69ec800c025b971ac528d2e13ae7feff88cf0e51cf5449ccc12，与此前本机 database.dump 哈希一致；大小写不影响比较。
失败或哈希不同则保留现场，不删除源文件、不覆盖本机备份，反馈错误即可。不要发送转储正文或备份文件。
本检查只能证明转储目录可读取及复制哈希一致，不能证明全部数据可恢复；下一步仍需收集源版本/计数并生成备份清单，之后恢复原服务，再进行隔离恢复验收。

### 第十六步验收记录

用户反馈容器内转储 SHA-256 为 90db32507a30a69ec800c025b971ac528d2e13ae7feff88cf0e51cf5449ccc12，与此前本机值一致。
由于命令用 && 连接 pg_restore --list 与 sha256sum，出现该哈希也说明前面的目录读取命令成功。尚未执行完整恢复验证。

## 第十七步：记录源数据库与镜像基准

仍由用户执行，保持 web/api 停止、postgres 运行，期间不要执行其他写入任务。
下列查询在只读事务内获取版本与所有业务表计数，不显示用户资料、文档正文或凭据。
在项目根目录、已有 $dc 定义的 PowerShell 窗口执行：

```powershell
$metadataSql = @'
BEGIN TRANSACTION READ ONLY;
SELECT json_build_object(
  'postgres_version', current_setting('server_version'),
  'pgvector_version', (SELECT extversion FROM pg_extension WHERE extname = 'vector'),
  'alembic_revision', (SELECT version_num FROM alembic_version),
  'table_counts', json_build_object(
    'users', (SELECT count(*) FROM users),
    'auth_sessions', (SELECT count(*) FROM auth_sessions),
    'knowledge_bases', (SELECT count(*) FROM knowledge_bases),
    'documents', (SELECT count(*) FROM documents),
    'storage_cleanup_tasks', (SELECT count(*) FROM storage_cleanup_tasks),
    'document_chunks', (SELECT count(*) FROM document_chunks),
    'conversations', (SELECT count(*) FROM conversations),
    'messages', (SELECT count(*) FROM messages),
    'usage_events', (SELECT count(*) FROM usage_events),
    'daily_usage_counters', (SELECT count(*) FROM daily_usage_counters)
  )
);
COMMIT;
'@
$metadataSql | docker @dc exec -T postgres psql -X -qAt -v ON_ERROR_STOP=1 -U devdocs_rehearsal -d devdocs_rehearsal
$LASTEXITCODE
```

预期输出一行 JSON，退出码 0；迁移版本应为 0007_usage_events_counters，documents 应为 1，其他计数以实际结果为准。
再只读取三个源服务容器的名字与实际镜像 ID，不读取完整 inspect 或环境变量：

```powershell
docker inspect --format '{{.Name}} {{.Image}}' devdocs-rehearsal-postgres-1 devdocs-rehearsal-api-1 devdocs-rehearsal-web-1
$LASTEXITCODE
```

反馈 JSON、三行镜像编号及退出码即可，不发送实际配置或转储文件。版本与计数尚未写入完整备份清单；不要在此时恢复写入。
后续将这些基准写入本批次备份清单，再恢复原服务。恢复演练必须到全新项目；清理恢复库登录会话后的 auth_sessions 数量允许与源库不同，其他业务表及原文件仍需逐项核对。

## 接管部署与验收记录（2026-10-16）

用户提供第十七步基准后，明确授权助手接管后续操作。本节之后不再要求用户逐条执行；此前教学记录保留作为操作依据。

### 实际完成

- 核对本地 Docker npipe 上下文、无相关环境变量覆盖，源服务标签和命名卷归属正确。
- 复核数据库转储目录可读、30304 字节、SHA-256 与用户提供值一致；原文件归档 10240 字节，包含 1 个 622 字节文件。
- 生成备份目录内 manifest.json，记录真实镜像、版本、计数及两份文件校验；原子发布且不覆盖旧文件。
- 恢复原演练 api/web，使用原镜像，无构建、拉取、自动迁移或删除数据卷；3100 代理就绪检查通过。
- 确认 devdocs-restore-001 项目、命名卷及 3101 端口不存在/未占用，生成新随机密码配置 .env.restore-001，不复制或显示开发密钥。
- 使用备份记录的三个固定镜像 ID，创建独立恢复数据库；通过 docker cp 传递二进制转储，pg_restore 使用单事务和遇错退出。
- 无网络辅助容器仅挂载恢复 uploads 卷。恢复过程遇到目录权限初始化及移交顺序问题，已修正配置与测试；实际文件内容未被重复覆盖，恢复卷权限收尾后以应用用户核对成功。
- 恢复库版本、全部十张表的数量与基准一致；随后仅清除恢复库 2 条旧 auth_sessions，其他九张表保持一致，原库会话不变。
- 恢复文件与数据库逐条比对：documents=stored_files=1，各错误数为 0，inventory_sha256 与备份前一致。
- 启动恢复 api/web；3100 与 3101 登录页均 200，健康接口均 ready/pgvector0.8.7。API 和数据库无宿主机端口映射。
- 浏览器测试仅针对恢复端口，用新测试账号完成注册登录、上传/预览/重复防护、移动布局和空库本地问答用量，七项全部通过，无付费模型调用。
- 浏览器测试前已完成恢复基准对比；测试会增加恢复库专用账号和资料，因此测试后的库总数不再等于原备份计数。源环境复核仍为 users1/sessions2/KB1/docs1/conversations1/messages2/events1/counters1，原文件哈希未变。

### 使用入口与边界

主入口为 http://127.0.0.1:3100，继续使用原演练账号。
独立恢复入口为 http://127.0.0.1:3101，可用原账号密码重新登录；旧会话不会被复制为有效登录。助手没有获取原密码，因此未代替用户登录原账号检查私有正文。
两个环境均保留运行，数据与 Cookie 独立。辅助任务容器已退出，不删除其现场、备份或数据卷。

备份文件与报告位于 infra/deploy/backups/backup-001；报告 restore-001-report.json 独立记录恢复验收，原 manifest.json 的 restore_verified=false 保持原样，表示创建备份时尚未验收恢复，不是当前恢复失败。
恢复覆盖文件 compose.restore-001.yml 只用于该批次，严禁套用到 devdocs-rehearsal。该配置现在对应已有数据，不可重复运行恢复任务或强制覆盖；后续恢复应使用全新项目编号。
归档恢复发生磁盘故障等错误时可能留下部分文件；不会自动删除或重试覆盖，应保留现场并使用新恢复目标，不将其视为完整恢复。

部署与评测工具回归 115 项通过，后端 146 项通过/5 项跳过，前端类型检查通过。独立安全审查发现的归档替换风险以私有快照修复，并补充回归；目录初始化和所有权移交顺序亦有回归测试。
浏览器初次因缺少匹配的测试浏览器而未启动，安装 Playwright 对应无头组件后重新运行七项全部通过。
本轮没有重新构建已验证镜像，没有证明此前缺少对照记录的强制重建持久化步骤，也未验证真实模型、正式域名、HTTPS、公网访问或离机加密备份。
通用启动/升级/自动备份恢复 CLI 仍是后续工具化任务，本次实际部署与隔离恢复不能替代这些尚未实现的自动化接口。
