# 本地生产环境演练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for inline execution or superpowers:subagent-driven-development when explicitly selected. Execute task-by-task with test-first steps and a final independent review.

**Goal:** 在不影响开发服务与数据的前提下，交付可本机启动、成对备份和全新隔离恢复的生产构建演练环境。

**Architecture:** 独立 Compose 栈运行 Next.js standalone、单进程 FastAPI 和 PostgreSQL/pgvector。PowerShell 薄入口调用使用标准库的 Python 操作模块，统一执行配置检查、Docker 命令、停机备份与恢复；容器内维护模块负责数据库及文件核验。

**Tech Stack:** Docker Compose v2、Node 22、Python 3.14、pgvector/pgvector:pg16、现有锁定依赖、pytest、Playwright。

**Spec:** `docs/superpowers/specs/2026-10-16-local-production-rehearsal-design.md`。用户通过“实施计划”请求进入本阶段；本计划仍需审阅后才实施。

## Global Constraints

- 不购买资源、不公开服务、不配置真实域名或证书、不迁移开发数据。
- 保留根目录 docker-compose.yml 和现有开发启动方式；无 Git 仓库，不初始化、不提交。
- 演练项目 devdocs-rehearsal，恢复项目 devdocs-restore-<编号>；拒绝连接开发项目或开发数据卷。
- 唯一宿主机映射为 web 的 127.0.0.1:3100，恢复默认 3101；api/postgres 不发布端口。
- 单 Uvicorn worker、无 reload、无原始 access log；web/api 非 root，上传初始化任务除外。
- 不读取或复制现有 .env 密钥，不在日志、Docker build ARG、镜像层中保存凭据。
- 实际配置 infra/deploy/.env.rehearsal；默认模型密钥为空，不自动调用真实供应商。
- COOKIE_SECURE=false 仅用于本机 HTTP，不能宣称公网生产就绪。
- 停止保留数据卷；不实现 down -v、prune、自动 downgrade、原栈覆盖恢复或强制删除。
- 数据库与上传文件成对停机备份；二进制文件通过容器文件生成和 Docker cp 传递，不经过 PowerShell 文本重定向。
- 所有测试和迁移仅针对新建演练/测试环境；未实际运行的构建或恢复不得宣称通过。

## Review Focus

1. 父进程 COMPOSE_*、端口或数据库环境变量覆盖配置：命令必须显式限定项目/文件，过滤相关环境覆盖（任务 1、3）。
2. Docker 指向远程 daemon：doctor 拒绝 SSH/TCP 远程上下文，不能把“本机演练”操作发到服务器（任务 1）。
3. 两个操作并发导致备份期间迁移或重启：每栈独占操作锁，锁冲突时拒绝；源栈与恢复目标均受保护（任务 3、4、5）。
4. 备份成功但 finally 恢复原应用失败：不能返回完全成功，保留可用备份并明确需手工恢复服务（任务 4）。
5. 恢复后密码哈希/会话和源库同源：仅清理恢复库 auth_sessions；其他记录和文件计数校验不能因会话删除误报失败（任务 5）。

## 文件与接口

- `infra/__init__.py`、`infra/deploy/__init__.py`：Python 包，不影响现有 postgres 初始化目录。
- `infra/deploy/rehearsal.ps1`：从任意当前目录定位项目根，使用现有后端虚拟环境运行 `python -m infra.deploy.cli`，透传退出码。
- `infra/deploy/{cli,config,docker,stack,backup,restore,archive}.py`：命令入口、配置、受控 Docker 执行、栈生命周期、备份、恢复、归档校验。
- `infra/deploy/container_ops.py`：复制到 API 镜像中的维护入口，只提供固定子命令，不执行任意 SQL/脚本参数。
- `infra/deploy/{web.Dockerfile,api.Dockerfile,compose.rehearsal.yml,rehearsal.env.example}`：镜像与声明式配置。
- `infra/deploy/tests/test_{config,docker,stack,archive,backup,restore,cli}.py`：pytest 使用假执行器，不要求安装 Pester。
- `apps/web/tests/e2e/production-rehearsal.spec.ts`：生产入口验收；使用 E2E_BASE_URL，默认测试不执行付费索引。
- 修改 `.dockerignore`、`.gitignore`、`apps/web/next.config.ts`、README、阶段记录；新增用户指南。

统一类型：`DeployError(code: str)` 仅显示固定错误说明；`RehearsalConfig` 负责秘密字段 repr 隐藏。
`DockerRunner.run(args: list[str], *, timeout: int = 120) -> str`：无 shell，失败不回显原始 argv/stdout/stderr；只允许调用本模块构造的命令。
`StackContext` 包含 cfg、project、config_path、runner、compose_file；所有操作函数接收它，不自行探测或猜测开发项目。
`BackupManifest`：format_version=1、complete=true、source_project、created_at、postgres_major=16、pgvector_version、alembic_revision、images、table_counts、upload_inventory、artifacts（路径/大小/SHA-256）。

全部 Python 单测从项目根使用后端虚拟环境运行，pytest basetemp 使用 work 下全新目录。代码检查对 deploy 使用 apps/api/pyproject.toml 配置，后端在 apps/api 内单独检查，避免导入分类误差。

### Task 1: 安全配置与命令入口

**Files:** 包初始化、rehearsal.ps1、cli.py、config.py、docker.py、rehearsal.env.example、test_config.py、test_docker.py、test_cli.py、.gitignore。

**Interfaces:** `init_config(path: Path, *, port: int = 3100, restore_id: str | None = None) -> RehearsalConfig`；`load_config(path: Path) -> RehearsalConfig`；`doctor(runner: DockerRunner, cfg: RehearsalConfig) -> dict`。

- [ ] 写失败测试：配置已存在不覆盖；生成密码不少于 32 字节随机熵且 URL 安全；端口仅 1024–65535；恢复编号限定小写字母数字/连字符且不超过 24 字符；Windows 保留名、目录穿越、换行、配置未知键均拒绝。
- [ ] 写失败测试：模型字段默认空；秘密不进入 repr、异常或命令输出；宿主 COMPOSE_FILE/COMPOSE_PROJECT_NAME/COMPOSE_PROFILES 和本模块配置同名变量不改变目标；远程 Docker endpoint 拒绝。
- [ ] 运行三个测试文件，确认失败来自能力缺失，再实现初始化、受限配置读取、错误类型和 Docker 执行器。配置只接受本模块字段，不执行 shell、不读取项目其他 .env；凭据文件排除提交，禁止覆盖。
- [ ] 固定配置字段：REHEARSAL_PORT、POSTGRES_USER、POSTGRES_DB、POSTGRES_PASSWORD、SILICONFLOW_API_KEY、CHAT_MODEL、DAILY_CHAT_LIMIT、DAILY_INDEX_LIMIT。用户/库名分别 devdocs_rehearsal，密码生成；模型默认沿用当前默认名称。API DSN、Origin、Cookie 名由目标栈推导，不允许随意提供开发 DSN。
- [ ] 为配置文件及生成密码限制可用字符，避免 Compose 的 `$` 插值和 dotenv 多行歧义；模型密钥不允许控制字符，不把它作为命令行参数。清理相关父进程变量后显式指定 --env-file、--file、--project-name。
- [ ] 实现 doctor：Docker Compose v2 可用、daemon 为 Linux、本地 unix/npipe 上下文、目标端口空闲；不打印配置或完整 inspect。已有本栈运行时 check 不把它自身端口视为外部冲突。
- [ ] 重跑测试通过；PowerShell wrapper 验证帮助命令退出码与工作目录定位，未安装/未启动 Docker 返回可操作说明，不自动安装或启动桌面程序。

### Task 2: 生产镜像与隔离 Compose

**Files:** Dockerfile 两份、compose.rehearsal.yml、.dockerignore、apps/web/next.config.ts、test_stack.py。

**Interfaces:** Compose 服务 web/api/postgres、profile=maintenance 的 migrate/storage-init/backup-files；数据卷 postgres_data/uploads 均由 Compose 项目前缀命名，不设置外部卷或固定 container_name。

- [ ] 写失败测试：实际 Compose JSON 中仅 web 发布环回端口；无开发卷、源码 bind mount、Docker socket、真实 env 构建参数；应用非 root、api 单 worker，数据卷命名按项目隔离。
- [ ] 运行测试确认失败。编写 api 多阶段镜像，Python 3.14 slim，安装 requirements.lock.txt；COPY 明确的 app、alembic.ini 与 container_ops.py，不 COPY .env。若锁定包不支持镜像平台，记录阻塞，不静默升级。
- [ ] 编写 web 多阶段镜像，Node 22 slim，npm ci、生产 build；构建期 API_BASE_URL=http://api:8000，NODE_ENV=production；standalone 追踪根设为 monorepo 根，正确复制 apps/web 对应 standalone/server.js、static 和可选 public。
- [ ] 先阅读已安装 Next.js output/self-hosting 文档；仅在 `DEPLOY_STANDALONE=1` 时启用 standalone，保留普通开发构建行为及 NEXT_DIST_DIR 约定，避免 Windows symlink 改变日常开发。
- [ ] 编写 .dockerignore，排除所有 .env/凭据、work、evals/results、上传、备份、node_modules、.venv、.next*、测试产物；示例文件可保留但不含秘密。禁止用 COPY . . 把整个项目带入最终运行层。
- [ ] postgres 使用 pgvector/pgvector:pg16 与现有初始化 SQL；api 使用 /data/uploads、独立 Cookie/Origin，环境通过 Compose 引用专用配置，不发布 8000/5432。storage-init 只为当前 uploads 卷设置 UID/GID 权限，不递归处理宿主机目录。
- [ ] 健康检查：postgres pg_isready；api 用标准库访问 /health/ready；web 请求 /login。应用 log 配置限制轮转大小；无访问 URL 原文日志。缺失配置在启动前失败。
- [ ] 运行静态测试；使用 Docker Compose config 的 JSON 在进程内断言而不回显（其内容含秘密），再真实构建两镜像，记录镜像 ID 和 Linux 兼容结果。镜像内容检查确认无真实配置和测试数据。

### Task 3: 启动、迁移、检查与停止

**Files:** stack.py、container_ops.py、cli.py、test_stack.py、test_cli.py。

**Interfaces:** `start_stack(ctx: StackContext) -> dict`、`check_stack(ctx) -> dict`、`stop_stack(ctx) -> None`、`stack_lock(project: str)`；`container_ops inventory` 输出白名单 JSON（revision/table_counts/upload_inventory/版本）。

- [ ] 写失败测试：数据库未就绪、迁移非零、端口冲突时不启动应用；已有栈重新启动不删除卷；锁冲突拒绝；inspect 只查询本项目标签，不能误操作开发容器。
- [ ] 运行相关单测确认失败，实现显式生命周期：up postgres → 有界就绪等待 → storage-init → migrate `alembic upgrade head` → up api/web → 180 秒内就绪；迁移超时 180 秒，容器停止宽限 30 秒。失败只输出固定阶段编号。
- [ ] 使用非阻塞 OS 文件锁（Windows msvcrt，Unix fcntl）对同一 project 串行化操作，记录进度到被忽略的操作目录；不使用自动删除 stale 文件判定锁归属。
- [ ] start 仅供首次创建或相同镜像重启；已有栈镜像/迁移版本将变化时，要求用户先通过 backup，并显式使用 upgrade 子命令及匹配的备份编号，避免重启隐式升级。
- [ ] 提供 upgrade 的受控更新路径：确认完整备份匹配当前源 revision/清单，停止应用后迁移并启动；失败保留数据与备份，不自动回滚数据库。镜像更新前旧镜像 ID 留档。
- [ ] 实现 inventory：仅输出预定业务表计数、Alembic revision、PostgreSQL 主版本、vector 版本、上传相对文件 SHA-256；不输出正文、密码哈希或会话值。
- [ ] stop 使用 compose stop，仅本栈；check 通过浏览器入口 /api/health/ready 及 /login 核验，输出环回 URL。重跑测试通过；用新栈验证初始化迁移至当前 head，无开发库变动。

### Task 4: 停机成对备份

**Files:** backup.py、archive.py、container_ops.py、test_backup.py、test_archive.py。

**Interfaces:** `backup_stack(ctx: StackContext, backup_id: str) -> Path`；`validate_backup(path: Path) -> BackupManifest`；备份根固定 infra/deploy/backups/<project>/<backup_id>，拒绝既有目录。

- [ ] 写失败测试：写入入口未停止、dump/tar/复制失败、剩余空间错误都不写 complete 清单；原应用停止状态恢复精确，恢复服务失败返回专用错误而非成功。
- [ ] 写失败测试：二进制哨兵字节往返不变、备份 hash 篡改拒绝；归档 ../、绝对路径、盘符、反斜杠路径、符号/硬链接、重复条目与非普通文件拒绝；只允许存储键格式 .bin 文件，禁止 .part，空上传卷合法。
- [ ] 运行测试确认失败，再实现备份锁定与状态记录；只停止原本运行的 web/api，检查其退出，postgres 必须可用。inventory 与 pg_dump 期间禁止本工具的其他写操作。
- [ ] pg_dump 以 --format=custom --no-owner --no-acl 在 postgres 容器生成临时文件，再 docker cp 至新备份目录；通过 pg_restore --list 核对转储可读，临时文件仅清理明确生成的固定前缀路径。
- [ ] uploads 通过只读卷挂载的维护容器生成归档和文件哈希；数据流为容器临时文件 → docker cp → 本机文件，不经过文本标准输出。维护任务不记录目录内原文。
- [ ] 计算 SHA-256、大小与 inventory，校验版本/上传文件清单后，最后同目录原子写入 manifest.json complete=true；此前仅 partial 进度文件，恢复命令不接受 partial。
- [ ] finally 恢复原本运行的应用并检查状态；若失败，保留已完成备份，返回 backup_service_resume_failed，提示单独执行 start/check。重跑测试通过，真实备份含一份演练上传文件和历史记录。

### Task 5: 全新环境恢复与核对

**Files:** restore.py、archive.py、container_ops.py、config.py、test_restore.py。

**Interfaces:** `restore_backup(ctx: StackContext, backup_path: Path, restore_id: str, *, port: int = 3101) -> dict`。恢复配置固定 `.env.restore-<id>`，项目 devdocs-restore-<id>；源与目标锁按名称排序获取。

- [ ] 写失败测试：备份格式/哈希/归档/PG 主版本不兼容、已有项目/卷/配置、端口冲突时，在创建目标资源前拒绝；不得调用源栈迁移/还原/删除命令。
- [ ] 写失败测试：恢复库旧 auth_sessions 删除，源库会话不变；其他业务表数量和每个文件 hash 必须匹配；session 计数预期为 0 单独验证；版本不匹配不隐式 upgrade。
- [ ] 运行测试确认失败，再实现完整备份预检与恢复目标预检；本地备份归档必须先验证完再创建任何目标。拒绝不认识的备份文件名、相对目录与格式版本。
- [ ] 创建全新恢复配置，数据库随机新密码、模型密钥空、Cookie 名独立；启动新数据库与 uploads 卷，校验容器和卷所属标签。镜像复用备份记录的本地镜像 ID，缺失时阻止恢复并提示，不拉取不明旧版本代替。
- [ ] docker cp 导入二进制 dump，pg_restore --no-owner --no-acl 到目标空库；预期扩展已存在时采用明确可验证的恢复顺序，不通过忽略非零退出码掩盖错误。上传文件按已验证相对键逐个恢复，设置正确 UID/GID，禁止 extractall 不受控解压。
- [ ] 通过维护入口只清理恢复库会话，核对 Alembic revision 与当前应用 head、其他表计数、上传逐文件 hash，全部通过才启动应用。失败保持应用关闭，保留目标供排障，不自动删除重做。
- [ ] 启动恢复 api/web 并检查 URL、就绪与恢复报告；重跑单测，通过真实 Docker 完成一次恢复。确认源演练栈数据、端口及开发栈不变，业务验证无真实模型调用。

### Task 6: 生产入口验收、指南与交付

**Files:** production-rehearsal.spec.ts、infra/deploy/tests、infra/deploy/README.md、docs/stages/06-local-production-guide.md、README.md、docs/stages/06-release.md、.gitignore。

**CLI Contract:** 从项目根运行 `./infra/deploy/rehearsal.ps1 <command>`，或 `python -m infra.deploy.cli <command>`；命令为 init、doctor、build、start、check、stop、upgrade、backup、restore；backup 必需 --backup-id，restore 必需 --backup 与 --restore-id；upgrade 必需 --backup-id。restore 默认 3101，init 默认 3100，允许显式空闲端口；禁止任意项目名/任意 DSN/--force。

- [ ] 写 CLI 测试：help 无副作用、错误退出码 1、参数错误 2、成功 0；除 init 外配置缺失不自动生成；敏感输出哨兵不出现。运行观察失败，再连接前述模块，PowerShell 原样传递参数且不拼接 shell 命令。
- [ ] 编写生产入口浏览器验收：注册/登录、知识库 CRUD、MD 上传解析、用量与历史、空库 SSE、退出与另一账号隔离。测试唯一前缀，显式 E2E_BASE_URL，不默认访问开发地址或执行索引。
- [ ] 复用已有假模型测试，独立测试栈通过专用 override 在 api 服务注入固定测试 app，web 仍使用生产镜像；假服务与文档留在测试构建目标，不进入生产镜像。验证有依据 SSE 的 meta/token/citations/done、持久化和代理超时；不提供运行时开启生产假模型的开关。
- [ ] 用真实生产镜像 + 新演练库验证页面布局与非空内容（桌面/手机）、上传文件重启后持久化、原 Cookie 不被开发登录覆盖；再备份恢复，登录恢复环境检查文档与历史，旧会话已失效。
- [ ] 指南写明生成配置、Docker 首次拉取/构建需要联网及磁盘空间、非加密敏感备份、本机 HTTP 的安全边界、真实模型由用户自行配置与显式调用、失败排障及不删卷的停止方式。
- [ ] 更新状态：评测工具按用户确认已验收，生产演练待用户验收；公网部署、域名/HTTPS、远程加密备份与开发者试用仍待办。记录本轮实际 Docker/镜像/迁移结果及未验证项到 work/local-production-ledger.md。
- [ ] 执行 `apps/api/.venv/Scripts/python.exe -m pytest infra/deploy/tests evals/tests -q -p no:cacheprovider --basetemp work/deploy-final-tests`，预期全部通过；后端从 apps/api 单独跑 pytest 与 Ruff；部署脚本 Ruff 采用后端配置，前端 tsc 和生产构建通过。
- [ ] 使用 Playwright 指向隔离生产及恢复端口跑受影响用例并检查截图；全部有限测试进程结束。无法运行 Docker 时保留配置并明确阻塞，不用静态测试代替真实恢复验证。
- [ ] 完成一次独立安全/正确性审查，发现实质问题先写失败测试再修复，再跑受影响套件；不自动合并、提交或清理数据卷。
- [ ] 向用户交付演练指南、启动 URL、验证结果与下一步验收清单。默认停止助手新建的测试辅助服务，保留演练数据；用户服务及开发环境不停止。

## 自检与实施方式

覆盖设计中的镜像、隔离、配置、迁移、备份、恢复和验收；恢复与备份使用同一版本化清单类型，源/目标操作全部通过 StackContext，不允许绕过项目约束。
备份恢复并非独立扩展功能，而是本模块可恢复性验收链路，必须在宣称完成前真实验证。
推荐继续由当前会话直接实施，任务间接口紧密，最后统一独立审查；也可选择逐任务独立实现与审查，代价是更多交接与上下文开销。
计划经用户审阅并确认执行方式后再开始；本次只生成计划，不运行容器、迁移或备份，不读取现有密钥。
