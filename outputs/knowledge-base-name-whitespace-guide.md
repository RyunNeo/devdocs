# 知识库重名规则：忽略所有空白

规则更新：同一个账号下，名称比较忽略大小写和所有空白字符。
Python 学习、Python学习、Python  学习、PYTHON 学习都视为同名。
全角空格和制表符也忽略。展示名称仍保留用户填写的内部空格，不改写描述或记录 ID。

创建和改名接口已使用新规则。旧数据迁移前也会检查现有展示名称，防止继续新增冲突。
数据库仍通过 user_id + name_key 的联合唯一约束处理并发创建。

验证：52 项后端测试（包含隔离 PostgreSQL 迁移）和 14 项浏览器测试通过，
Ruff 检查通过，独立代码检查未发现可操作问题。

## 已有冲突记录

只读检查发现你的账号已有：

| ID | 名称 |
| --- | --- |
| 5ee518f9-ec56-4748-a00e-3f6067b42759 | Python 学习 |
| df4491b7-0c66-40a8-9ab4-b75cc12b891f | Python学习 |

没有自动删除、合并或改名。你需要决定保留哪个名称，给另一条换一个不同名称。
建议保留 Python 学习，将第二条改为 Python 练习；名称的内容必须不同，单纯增减空格无效。

先在 Swagger 的 PATCH /knowledge-bases/{knowledge_base_id} 中改名：
ID 使用第二条 df4491b7-0c66-40a8-9ab4-b75cc12b891f，请求体示例：

```json
{ "name": "Python 练习" }
```

只提交名称，不提交 description=null，原来的描述会保留。
你也可以选择其他名称，或者保留第二条而给第一条改名。删除不是必需的。
先确认返回 200，再进行下面的迁移。

## 检查与迁移

在 apps/api 目录：

```powershell
.\.venv\Scripts\python.exe scripts/check_knowledge_base_names.py
```

这个脚本只读取 ID、所属用户 ID 和名称，不修改数据。
conflict_groups=[] 表示没有冲突；退出码 1 表示发现冲突，2 表示无法检查数据库。
没有冲突后执行：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

预期版本为 0003_name_whitespace (head)。
迁移只重算 name_key，不修改展示名、描述、ID 或时间。
发现冲突时，在修改任何记录之前停止，保留原数据和旧版本，列出需处理的 ID。
不要删除数据库或数据卷来处理重名。

## 再验收

保留 Python 学习后，在创建弹窗尝试 Python学习，应显示已有同名知识库，输入仍保留。
不同账号仍能使用相同名称。本轮不增加编辑/删除页面，也不推进上传模块。
