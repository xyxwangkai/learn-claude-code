# s12: Worktree + Task Isolation (Worktree 任务隔离)

`s01 > s02 > s03 > s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > [ s12 ]`

> *"各干各的目录, 互不干扰"* -- 任务管目标, worktree 管目录, 按 ID 绑定。
>
> **Harness 层**: 目录隔离 -- 永不碰撞的并行执行通道。

## 问题

到 s11, Agent 已经能自主认领和完成任务。但所有任务共享一个目录。两个 Agent 同时重构不同模块 -- A 改 `config.py`, B 也改 `config.py`, 未提交的改动互相污染, 谁也没法干净回滚。

任务板管 "做什么" 但不管 "在哪做"。解法: 给每个任务一个独立的 git worktree 目录, 用任务 ID 把两边关联起来。

## 解决方案

```
Control plane (.tasks/)             Execution plane (.worktrees/)
+------------------+                +------------------------+
| task_1.json      |                | auth-refactor/         |
|   status: in_progress  <------>   branch: wt/auth-refactor
|   worktree: "auth-refactor"   |   task_id: 1             |
+------------------+                +------------------------+
| task_2.json      |                | ui-login/              |
|   status: pending    <------>     branch: wt/ui-login
|   worktree: "ui-login"       |   task_id: 2             |
+------------------+                +------------------------+
                                    |
                          index.json (worktree registry)
                          events.jsonl (lifecycle log)

State machines:
  Task:     pending -> in_progress -> completed
  Worktree: absent  -> active      -> removed | kept
```

## 工作原理

1. **创建任务。** 先把目标持久化。

```python
TASKS.create("Implement auth refactor")
# -> .tasks/task_1.json  status=pending  worktree=""
```

2. **创建 worktree 并绑定任务。** 传入 `task_id` 自动将任务推进到 `in_progress`。

```python
WORKTREES.create("auth-refactor", task_id=1)
# -> git worktree add -b wt/auth-refactor .worktrees/auth-refactor HEAD
# -> index.json gets new entry, task_1.json gets worktree="auth-refactor"
```

绑定同时写入两侧状态:

```python
def bind_worktree(self, task_id, worktree):
    task = self._load(task_id)
    task["worktree"] = worktree
    if task["status"] == "pending":
        task["status"] = "in_progress"
    self._save(task)
```

3. **在 worktree 中执行命令。** `cwd` 指向隔离目录。

```python
subprocess.run(command, shell=True, cwd=worktree_path,
               capture_output=True, text=True, timeout=300)
```

4. **收尾。** 两种选择:
   - `worktree_keep(name)` -- 保留目录供后续使用。
   - `worktree_remove(name, complete_task=True)` -- 删除目录, 完成绑定任务, 发出事件。一个调用搞定拆除 + 完成。

```python
def remove(self, name, force=False, complete_task=False):
    self._run_git(["worktree", "remove", wt["path"]])
    if complete_task and wt.get("task_id") is not None:
        self.tasks.update(wt["task_id"], status="completed")
        self.tasks.unbind_worktree(wt["task_id"])
        self.events.emit("task.completed", ...)
```

5. **事件流。** 每个生命周期步骤写入 `.worktrees/events.jsonl`:

```json
{
  "event": "worktree.remove.after",
  "task": {"id": 1, "status": "completed"},
  "worktree": {"name": "auth-refactor", "status": "removed"},
  "ts": 1730000000
}
```

事件类型: `worktree.create.before/after/failed`, `worktree.remove.before/after/failed`, `worktree.keep`, `task.completed`。

崩溃后从 `.tasks/` + `.worktrees/index.json` 重建现场。会话记忆是易失的; 磁盘状态是持久的。

## 相对 s11 的变更

| 组件               | 之前 (s11)                 | 之后 (s12)                                   |
|--------------------|----------------------------|----------------------------------------------|
| 协调               | 任务板 (owner/status)      | 任务板 + worktree 显式绑定                   |
| 执行范围           | 共享目录                   | 每个任务独立目录                             |
| 可恢复性           | 仅任务状态                 | 任务状态 + worktree 索引                     |
| 收尾               | 任务完成                   | 任务完成 + 显式 keep/remove                  |
| 生命周期可见性     | 隐式日志                   | `.worktrees/events.jsonl` 显式事件流         |

## 调用案例

**用户输入**

```text
让两个任务并行开发：一个改认证，一个改登录页，而且互不影响
```

**典型调用顺序**

1. 为两个目标分别创建任务
2. `worktree_create(name="auth-refactor", task_id=1)`
3. `worktree_create(name="ui-login", task_id=2)`
4. 两个 Agent 各自在自己的 worktree 目录执行命令
5. 完成后按需 `worktree_keep(...)` 或 `worktree_remove(..., complete_task=True)`

**终端关键输出**

```text
> worktree_create:
Created .worktrees/auth-refactor for task 1

> worktree_create:
Created .worktrees/ui-login for task 2
```

**这个案例说明了什么**

s12 把“任务隔离”真正落到文件系统层: **每个任务一套目录, 并行改动互不污染。**

## 试一试

```sh
cd learn-claude-code
python agents/s12_worktree_task_isolation.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Create tasks for backend auth and frontend login page, then list tasks.`
2. `Create worktree "auth-refactor" for task 1, then bind task 2 to a new worktree "ui-login".`
3. `Run "git status --short" in worktree "auth-refactor".`
4. `Keep worktree "ui-login", then list worktrees and inspect events.`
5. `Remove worktree "auth-refactor" with complete_task=true, then list tasks/worktrees/events.`

## 一句话总结

下面我按你给的 **s12 五个输入**，结合 `agents/s12_worktree_task_isolation.py` 和文档，详细解析它的 **数据流 / 状态流 / worktree 绑定流 / 事件流**。

这一章的本质升级是：

> **s11 只有任务隔离的“逻辑层”，s12 把隔离真正落到“目录层”。**

一句话理解：

- `.tasks/` 是 **控制平面**：记录任务做什么
- `.worktrees/` 是 **执行平面**：每个任务在哪个目录里做

---

# 先给总览：s12 的三套持久化状态

---

## 1. 任务板：`.tasks/task_N.json`

例如：

```json
{
  "id": 1,
  "subject": "Implement auth refactor",
  "status": "in_progress",
  "owner": "",
  "worktree": "auth-refactor",
  "blockedBy": []
}
```

负责记录：

- task id
- subject / description
- status
- owner
- 绑定的 worktree 名

---

## 2. worktree 索引：`.worktrees/index.json`

例如：

```json
{
  "worktrees": [
    {
      "name": "auth-refactor",
      "path": ".../.worktrees/auth-refactor",
      "branch": "wt/auth-refactor",
      "task_id": 1,
      "status": "active"
    }
  ]
}
```

负责记录：

- worktree 名字
- 路径
- 分支名
- 绑定 task_id
- 当前状态

---

## 3. 生命周期事件流：`.worktrees/events.jsonl`

每行一条 JSON 事件，例如：

```json
{
  "event": "worktree.create.after",
  "ts": 1730000000,
  "task": {"id": 1},
  "worktree": {"name": "auth-refactor", "status": "active"}
}
```

负责记录：

- 创建前/后/失败
- 删除前/后/失败
- keep
- task completed

这相当于 **审计日志 / 可观测性日志**。

---

# 先讲 s12 的最核心抽象

文档那句非常准确：

> **Tasks are the control plane and worktrees are the execution plane.**

也就是说：

### task
回答：
- 这个工作是什么？
- 现在做到哪一步？
- 对应哪个 worktree？

### worktree
回答：
- 这个工作在哪个目录里独立执行？
- 对应哪个 branch？
- 当前还 active / kept / removed 吗？

---

# 场景 1
# `Create tasks for backend auth and frontend login page, then list tasks.`

这是 task control plane 的起点：**先有任务，再谈 worktree**。

---

## Step 1：lead 创建两个任务

用户输入：

```text
Create tasks for backend auth and frontend login page, then list tasks.
```

LLM 会调用 `TASKS.create(...)` 两次，等价于：

```python
TASKS.create("backend auth", "...")
TASKS.create("frontend login page", "...")
```

`TaskManager.create()`：

```python
task = {
    "id": self._next_id,
    "subject": subject,
    "description": description,
    "status": "pending",
    "owner": "",
    "worktree": "",
    "blockedBy": [],
    "created_at": time.time(),
    "updated_at": time.time(),
}
self._save(task)
```

---

## Step 2：磁盘状态变化

### `.tasks/task_1.json`
可能变成：

```json
{
  "id": 1,
  "subject": "backend auth",
  "description": "",
  "status": "pending",
  "owner": "",
  "worktree": "",
  "blockedBy": [],
  "created_at": 1760000000.0,
  "updated_at": 1760000000.0
}
```

### `.tasks/task_2.json`
```json
{
  "id": 2,
  "subject": "frontend login page",
  "description": "",
  "status": "pending",
  "owner": "",
  "worktree": "",
  "blockedBy": [],
  "created_at": 1760000001.0,
  "updated_at": 1760000001.0
}
```

---

## Step 3：list tasks

调用：

```python
TASKS.list_all()
```

代码里会把每个任务转换成一行：

```python
marker = {
    "pending": "[ ]",
    "in_progress": "[>]",
    "completed": "[x]",
}
owner = f" owner={t['owner']}" if t.get("owner") else ""
wt = f" wt={t['worktree']}" if t.get("worktree") else ""
lines.append(f"{marker} #{t['id']}: {t['subject']}{owner}{wt}")
```

因此输出大概是：

```text
[ ] #1: backend auth
[ ] #2: frontend login page
```

这里没有 `owner`、没有 `wt=`，因为还没绑定。

---

## 场景 1 的关键点

这个输入说明：

- task 可以先存在
- 此时只是控制面记录
- 任务还没进入具体执行目录
- `status=pending, worktree=""`

---

# 场景 2
# `Create worktree "auth-refactor" for task 1, then bind task 2 to a new worktree "ui-login".`

这是 s12 的核心：**把 task 和独立目录绑定起来**。

---

## Part A：给 task 1 创建 worktree `auth-refactor`

调用等价于：

```python
WORKTREES.create("auth-refactor", task_id=1)
```

进入 `WorktreeManager.create()`。

---

## Step 2.1：输入校验

```python
self._validate_name(name)
if self._find(name):
    raise ValueError(...)
if task_id is not None and not self.tasks.exists(task_id):
    raise ValueError(...)
```

也就是：

- worktree 名必须合法
- 不能重名
- task 1 必须存在

---

## Step 2.2：先发事件 `worktree.create.before`

```python
self.events.emit(
    "worktree.create.before",
    task={"id": task_id},
    worktree={"name": name, "base_ref": base_ref},
)
```

于是 `.worktrees/events.jsonl` 追加一条：

```json
{
  "event": "worktree.create.before",
  "ts": ...,
  "task": {"id": 1},
  "worktree": {"name": "auth-refactor", "base_ref": "HEAD"}
}
```

---

## Step 2.3：真正创建 git worktree

```python
self._run_git(["worktree", "add", "-b", branch, str(path), base_ref])
```

其中：

- `path = .worktrees/auth-refactor`
- `branch = wt/auth-refactor`

真实 shell 等价于：

```bash
git worktree add -b wt/auth-refactor .worktrees/auth-refactor HEAD
```

这一步会：

- 新建一个独立目录
- 以新 branch `wt/auth-refactor` 指向它
- 目录内容与 repo 当前基线对应

---

## Step 2.4：写入 index.json

```python
entry = {
    "name": name,
    "path": str(path),
    "branch": branch,
    "task_id": task_id,
    "status": "active",
    "created_at": time.time(),
}
idx["worktrees"].append(entry)
self._save_index(idx)
```

于是 `.worktrees/index.json` 变成：

```json
{
  "worktrees": [
    {
      "name": "auth-refactor",
      "path": ".../.worktrees/auth-refactor",
      "branch": "wt/auth-refactor",
      "task_id": 1,
      "status": "active",
      "created_at": 1760000010.0
    }
  ]
}
```

---

## Step 2.5：绑定 task 1 到这个 worktree

```python
if task_id is not None:
    self.tasks.bind_worktree(task_id, name)
```

进入：

```python
def bind_worktree(self, task_id: int, worktree: str, owner: str = "") -> str:
    task = self._load(task_id)
    task["worktree"] = worktree
    if owner:
        task["owner"] = owner
    if task["status"] == "pending":
        task["status"] = "in_progress"
    task["updated_at"] = time.time()
    self._save(task)
```

所以 `.tasks/task_1.json` 从：

```json
"status": "pending",
"worktree": ""
```

变成：

```json
"status": "in_progress",
"worktree": "auth-refactor"
```

这一步非常关键：

> **绑定 worktree 会把任务从 pending 推进到 in_progress。**

---

## Step 2.6：发事件 `worktree.create.after`

```python
self.events.emit(
    "worktree.create.after",
    task={"id": task_id},
    worktree={
        "name": name,
        "path": str(path),
        "branch": branch,
        "status": "active",
    },
)
```

于是 events.jsonl 再追加：

```json
{
  "event": "worktree.create.after",
  "ts": ...,
  "task": {"id": 1},
  "worktree": {
    "name": "auth-refactor",
    "path": ".../.worktrees/auth-refactor",
    "branch": "wt/auth-refactor",
    "status": "active"
  }
}
```

---

## Part B：给 task 2 创建 `ui-login`

完全一样，再来一遍：

```python
WORKTREES.create("ui-login", task_id=2)
```

最后：

### `.tasks`
- task 1 -> `worktree="auth-refactor"`, `status="in_progress"`
- task 2 -> `worktree="ui-login"`, `status="in_progress"`

### `.worktrees/index.json`
会有两个条目：

```json
{
  "worktrees": [
    {
      "name": "auth-refactor",
      "path": ".../.worktrees/auth-refactor",
      "branch": "wt/auth-refactor",
      "task_id": 1,
      "status": "active"
    },
    {
      "name": "ui-login",
      "path": ".../.worktrees/ui-login",
      "branch": "wt/ui-login",
      "task_id": 2,
      "status": "active"
    }
  ]
}
```

---

## 场景 2 的关键点

这个输入真正展示的是：

- 一个 task 对应一个 worktree lane
- 任务与目录通过 `task_id <-> worktree name` 绑定
- worktree 是执行隔离层
- task 是协调层

---

# 场景 3
# `Run "git status --short" in worktree "auth-refactor".`

这里展示的是：**命令不是在主 repo cwd 跑，而是在 worktree 的 cwd 跑。**

---

## Step 3.1：调用 `WORKTREES.run(name, command)`

```python
WORKTREES.run("auth-refactor", "git status --short")
```

代码：

```python
wt = self._find(name)
path = Path(wt["path"])
r = subprocess.run(
    command,
    shell=True,
    cwd=path,
    capture_output=True,
    text=True,
    timeout=300,
)
```

关键点是：

```python
cwd=path
```

其中 `path` 是：

```text
.../.worktrees/auth-refactor
```

---

## Step 3.2：这意味着什么

你执行的是：

```bash
git status --short
```

但作用目录是：

```text
.worktrees/auth-refactor
```

所以结果只反映这个隔离工作目录里的改动，不受 `ui-login` 影响。

---

## Step 3.3：典型输出

如果 worktree 干净，可能是：

```text
(no output)
```

因为 `git status --short` 在 clean 时通常不输出内容。

如果想更显式，可以用 `status(name)`：

```python
git status --short --branch
```

那 clean 时会显示分支信息。

---

## 场景 3 的关键点

这条输入说明：

> **同样一条 shell 命令，因为 cwd 不同，会落在不同的隔离执行平面。**

这是 s12 “真正隔离”的根本。

---

# 场景 4
# `Keep worktree "ui-login", then list worktrees and inspect events.`

这个场景展示的是：**任务完成后不一定删目录，可以 keep 保留现场。**

虽然你截的源码没完全显示 `keep()`，但文档已明确它存在：

- `worktree_keep(name)`
- 发事件 `worktree.keep`

---

## Step 4.1：keep 的语义

keep 不是删除 worktree，而是：

- 保留目录
- 保留 branch / path
- 可能把索引状态改成 `kept`
- 写入事件流

这样后续可以继续进入那个目录查东西、继续开发、手动处理。

---

## Step 4.2：list worktrees

调用：

```python
WORKTREES.list_all()
```

输出来自 `index.json`：

```python
for wt in wts:
    suffix = f" task={wt['task_id']}" if wt.get("task_id") else ""
    lines.append(
        f"[{wt.get('status', 'unknown')}] {wt['name']} -> "
        f"{wt['path']} ({wt.get('branch', '-')}){suffix}"
    )
```

如果 `ui-login` 被 keep，而 `auth-refactor` 仍 active，则可能输出：

```text
[active] auth-refactor -> .../.worktrees/auth-refactor (wt/auth-refactor) task=1
[kept] ui-login -> .../.worktrees/ui-login (wt/ui-login) task=2
```

---

## Step 4.3：inspect events

调用：

```python
EVENTS.list_recent(limit=20)
```

它会读取 `.worktrees/events.jsonl` 最后若干行，并 JSON pretty print。

你会看到类似：

```json
[
  {
    "event": "worktree.create.before",
    "task": {"id": 1},
    "worktree": {"name": "auth-refactor", "base_ref": "HEAD"}
  },
  {
    "event": "worktree.create.after",
    "task": {"id": 1},
    "worktree": {"name": "auth-refactor", "status": "active"}
  },
  {
    "event": "worktree.create.before",
    "task": {"id": 2},
    "worktree": {"name": "ui-login", "base_ref": "HEAD"}
  },
  {
    "event": "worktree.create.after",
    "task": {"id": 2},
    "worktree": {"name": "ui-login", "status": "active"}
  },
  {
    "event": "worktree.keep",
    "task": {"id": 2},
    "worktree": {"name": "ui-login", "status": "kept"}
  }
]
```

---

## 场景 4 的关键点

这个输入展示的是：

- worktree 生命周期不只有 create/remove
- 还可以进入 `kept`
- events.jsonl 是完整的生命周期可观测层

---

# 场景 5
# `Remove worktree "auth-refactor" with complete_task=true, then list tasks/worktrees/events.`

这是 s12 最完整的一条 closeout 流程。

---

## Step 5.1：调用 remove

```python
WORKTREES.remove("auth-refactor", complete_task=True)
```

代码里先做：

```python
self.events.emit(
    "worktree.remove.before",
    task={"id": wt.get("task_id")},
    worktree={"name": name, "path": wt.get("path")},
)
```

events 追加：

```json
{
  "event": "worktree.remove.before",
  "task": {"id": 1},
  "worktree": {"name": "auth-refactor", "path": ".../.worktrees/auth-refactor"}
}
```

---

## Step 5.2：真正删除 git worktree

```python
args = ["worktree", "remove"]
args.append(wt["path"])
self._run_git(args)
```

等价于：

```bash
git worktree remove .worktrees/auth-refactor
```

这会删除该 worktree 目录并从 git worktree registry 移除。

---

## Step 5.3：如果 `complete_task=True`，同时完成绑定任务

这是 s12 最漂亮的设计点：

```python
if complete_task and wt.get("task_id") is not None:
    task_id = wt["task_id"]
    before = json.loads(self.tasks.get(task_id))
    self.tasks.update(task_id, status="completed")
    self.tasks.unbind_worktree(task_id)
    self.events.emit(
        "task.completed",
        task={
            "id": task_id,
            "subject": before.get("subject", ""),
            "status": "completed",
        },
        ...
    )
```

这会导致 task 1 发生两个变化：

### 1) 状态变 completed
```json
"status": "completed"
```

### 2) worktree 字段清空
```json
"worktree": ""
```

所以 task_1.json 最终类似：

```json
{
  "id": 1,
  "subject": "backend auth",
  "status": "completed",
  "owner": "",
  "worktree": "",
  "blockedBy": [],
  ...
}
```

---

## Step 5.4：worktree 索引也要反映 removed

你截的代码在这里后半段没全部显示，但按文档和结构可以确定它会：

- 从 index 删除该条目，或
- 标记其状态为 removed

这样 `list worktrees` 时就不会再把它当 active。

---

## Step 5.5：发后续事件

至少应有：

- `task.completed`
- `worktree.remove.after`

于是 events 会继续追加：

```json
{
  "event": "task.completed",
  "task": {"id": 1, "subject": "backend auth", "status": "completed"},
  "worktree": {"name": "auth-refactor"}
}
```

```json
{
  "event": "worktree.remove.after",
  "task": {"id": 1, "status": "completed"},
  "worktree": {"name": "auth-refactor", "status": "removed"}
}
```

---

## Step 5.6：list tasks / worktrees / events

### tasks
此时大概会看到：

```text
[x] #1: backend auth
[>] #2: frontend login page wt=ui-login
```

如果 `ui-login` 是 kept，也可能任务 2 仍显示绑定 worktree。

---

### worktrees
可能看到：

```text
[kept] ui-login -> .../.worktrees/ui-login (wt/ui-login) task=2
```

`auth-refactor` 已不存在或已 removed，不再 active。

---

### events
会包含完整链路：

1. task create
2. worktree create before/after
3. keep
4. remove before
5. task completed
6. remove after

---

# s12 最重要的三条状态机

---

## 1. Task 状态机

```text
pending -> in_progress -> completed
```

### 触发点
- `create()` -> pending
- `bind_worktree()` -> in_progress
- `remove(..., complete_task=True)` -> completed

---

## 2. Worktree 状态机

```text
absent -> active -> kept | removed
```

### 触发点
- `create()` -> active
- `keep()` -> kept
- `remove()` -> removed / 从索引移除

---

## 3. Event 流

```text
create.before -> create.after
keep
remove.before -> task.completed -> remove.after
```

这个不直接驱动执行，但负责**可观测性与恢复**。

---

# 把你这 5 个输入串成完整业务流

---

## 输入 1：Create tasks
建立控制平面：

- `.tasks/task_1.json`
- `.tasks/task_2.json`

状态都还是 `pending`

---

## 输入 2：Create/bind worktrees
建立执行平面并绑定：

- `.worktrees/auth-refactor`
- `.worktrees/ui-login`
- `.worktrees/index.json`
- task 1 / task 2 变成 `in_progress`

---

## 输入 3：Run command in worktree
在独立 cwd 内运行命令：

- `auth-refactor` 中的 git status
- 不污染 `ui-login`

---

## 输入 4：Keep ui-login
表示任务/目录生命周期先不结束：

- worktree 保留
- 事件记录 keep

---

## 输入 5：Remove auth-refactor with complete_task=true
一键完成：

- 删除目录
- 完成 task 1
- 清空 task 1 的 worktree 绑定
- 写入事件

---

# 这一章相对 s11 的根本升级

如果你要一句话讲清楚：

### s11
“多个 agent 可以基于任务板逻辑分工，但还是共用一个目录。”

### s12
“每个 task 进入自己的 git worktree，逻辑隔离升级成物理目录隔离。”

所以 s12 真正解决的是：

- 改动互相污染
- 难以回滚
- 并行开发冲突
- 现场恢复困难

---

# 你可以这样记 s12 的“数据流四件套”

---

## 1. task create
```text
user intent -> TASKS.create -> .tasks/task_N.json
```

## 2. worktree bind
```text
task_id -> WORKTREES.create -> git worktree add -> index.json + task.worktree
```

## 3. isolated execution
```text
run(command, worktree_name) -> cwd=.worktrees/<name>
```

## 4. closeout
```text
keep/remove -> index/task/events 同步更新
```

---

如果你愿意，我下一步可以继续做两种增强版之一：

1. **把 s12 这 5 个输入画成 Mermaid 时序图 + 状态图**
2. **继续按源码逐函数拆 `TaskManager / WorktreeManager / EventBus` 的完整调用链**