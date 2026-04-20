# s11: Autonomous Agents (Autonomous Agent)

`s01 > s02 > s03 > s04 > s05 > s06 | s07 > s08 > s09 > s10 > [ s11 ] s12`

> *"队友自己看看板, 有活就认领"* -- 不需要领导逐个分配, 自组织。
>
> **Harness 层**: 自治 -- 模型自己找活干, 无需指派。

## 问题

s09-s10 中, 队友只在被明确指派时才动。领导得给每个队友写 prompt, 任务看板上 10 个未认领的任务得手动分配。这扩展不了。

真正的自治: 队友自己扫描任务看板, 认领没人做的任务, 做完再找下一个。

一个细节: Context Compact (s06) 后 Agent 可能忘了自己是谁。身份重注入解决这个问题。

## 解决方案

```
Teammate lifecycle with idle cycle:

+-------+
| spawn |
+---+---+
    |
    v
+-------+   tool_use     +-------+
| WORK  | <------------- |  LLM  |
+---+---+                +-------+
    |
    | stop_reason != tool_use (or idle tool called)
    v
+--------+
|  IDLE  |  poll every 5s for up to 60s
+---+----+
    |
    +---> check inbox --> message? ----------> WORK
    |
    +---> scan .tasks/ --> unclaimed? -------> claim -> WORK
    |
    +---> 60s timeout ----------------------> SHUTDOWN

Identity re-injection after compression:
  if len(messages) <= 3:
    messages.insert(0, identity_block)
```

## 工作原理

1. 队友循环分两个阶段: WORK 和 IDLE。LLM 停止调用工具 (或调用了 `idle`) 时, 进入 IDLE。

```python
def _loop(self, name, role, prompt):
    while True:
        # -- WORK PHASE --
        messages = [{"role": "user", "content": prompt}]
        for _ in range(50):
            response = client.messages.create(...)
            if response.stop_reason != "tool_use":
                break
            # execute tools...
            if idle_requested:
                break

        # -- IDLE PHASE --
        self._set_status(name, "idle")
        resume = self._idle_poll(name, messages)
        if not resume:
            self._set_status(name, "shutdown")
            return
        self._set_status(name, "working")
```

2. 空闲阶段循环轮询收件箱和任务看板。

```python
def _idle_poll(self, name, messages):
    for _ in range(IDLE_TIMEOUT // POLL_INTERVAL):  # 60s / 5s = 12
        time.sleep(POLL_INTERVAL)
        inbox = BUS.read_inbox(name)
        if inbox:
            messages.append({"role": "user",
                "content": f"<inbox>{inbox}</inbox>"})
            return True
        unclaimed = scan_unclaimed_tasks()
        if unclaimed:
            claim_task(unclaimed[0]["id"], name)
            messages.append({"role": "user",
                "content": f"<auto-claimed>Task #{unclaimed[0]['id']}: "
                           f"{unclaimed[0]['subject']}</auto-claimed>"})
            return True
    return False  # timeout -> shutdown
```

3. 任务看板扫描: 找 pending 状态、无 owner、未被阻塞的任务。

```python
def scan_unclaimed_tasks() -> list:
    unclaimed = []
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        task = json.loads(f.read_text())
        if (task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")):
            unclaimed.append(task)
    return unclaimed
```

4. 身份重注入: 上下文过短 (说明发生了压缩) 时, 在开头插入身份块。

```python
if len(messages) <= 3:
    messages.insert(0, {"role": "user",
        "content": f"<identity>You are '{name}', role: {role}, "
                   f"team: {team_name}. Continue your work.</identity>"})
    messages.insert(1, {"role": "assistant",
        "content": f"I am {name}. Continuing."})
```

## 相对 s10 的变更

| 组件           | 之前 (s10)       | 之后 (s11)                       |
|----------------|------------------|----------------------------------|
| Tools          | 12               | 14 (+idle, +claim_task)          |
| 自治性         | 领导指派         | 自组织                           |
| 空闲阶段       | 无               | 轮询收件箱 + 任务看板            |
| 任务认领       | 仅手动           | 自动认领未分配任务               |
| 身份           | 系统提示         | + 压缩后重注入                   |
| 超时           | 无               | 60 秒空闲 -> 自动关机            |

## 调用案例

**用户输入**

```text
启动 3 个队友，让他们自己从任务板领活
```

**典型调用顺序**

1. 主 Agent 只负责启动队友
2. 队友进入空闲轮询, 扫描 inbox 和 `.tasks/`
3. 某个队友发现未认领任务, 自己 claim
4. 做完后回到空闲态, 再继续找下一个

**终端关键输出**

```text
[alice] claimed task 3
[bob] claimed task 4
[carol] idle -> working
```

**这个案例说明了什么**

s11 让团队从“领导分派”进化到 **队友自组织认领任务**。

## 试一试

```sh
cd learn-claude-code
python agents/s11_autonomous_agents.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Create 3 tasks on the board, then spawn alice and bob. Watch them auto-claim.`
2. `Spawn a coder teammate and let it find work from the task board itself`
3. `Create tasks with dependencies. Watch teammates respect the blocked order.`
4. 输入 `/tasks` 查看带 owner 的任务看板
5. 输入 `/team` 监控谁在工作、谁在空闲

## 一句话总结

下面我按你给的 **s11 四个输入**，结合 `agents/s11_autonomous_agents.py` 和文档，详细解释它的 **LLM 数据流 / 状态流 / 任务看板流**。

这一章的核心升级是：

> **队友不等 lead 分配任务，而是自己进 idle，轮询任务板，自动 claim。**

也就是说，s11 从：

- s09 的“能通信”
- s10 的“能协议握手”

继续升级到：

- **s11 的“能自主找活”**

---

# 先给一句最核心总结

在 s11 里，一个 teammate 的生命周期变成：

```text
spawn -> WORK -> IDLE -> 发现消息/任务 -> WORK -> IDLE -> ... -> 超时 shutdown
```

与前几章最大不同的是：

- 以前：lead 明确告诉 agent 去做什么
- 现在：agent 在空闲时 **自己扫描 `.tasks/`，找到可做任务并 claim**

---

# 先看 s11 新增的关键机制

---

## 1. Task board：`.tasks/`
任务文件放在：

```text
.tasks/task_1.json
.tasks/task_2.json
...
```

每个任务大概长这样：

```json
{
  "id": 1,
  "subject": "Setup project",
  "description": "Initial project setup",
  "status": "pending",
  "blockedBy": [],
  "owner": ""
}
```

关键字段：

- `status`
- `blockedBy`
- `owner`

---

## 2. 自动扫描未认领任务

```python
def scan_unclaimed_tasks() -> list:
    TASKS_DIR.mkdir(exist_ok=True)
    unclaimed = []
    for f in sorted(TASKS_DIR.glob("task_*.json")):
        task = json.loads(f.read_text())
        if (task.get("status") == "pending"
                and not task.get("owner")
                and not task.get("blockedBy")):
            unclaimed.append(task)
    return unclaimed
```

只有满足这三个条件才会被自动发现：

1. `status == "pending"`
2. `owner` 为空
3. `blockedBy` 为空

所以它天然会**跳过被依赖阻塞的任务**。

---

## 3. claim_task 是原子认领

```python
def claim_task(task_id: int, owner: str) -> str:
    with _claim_lock:
        ...
        if task.get("owner"):
            return "Error..."
        if task.get("status") != "pending":
            return "Error..."
        if task.get("blockedBy"):
            return "Error..."
        task["owner"] = owner
        task["status"] = "in_progress"
        path.write_text(json.dumps(task, indent=2))
```

这里 `_claim_lock` 很关键：

- 多个 teammate 同时扫描到同一个任务时
- 只有一个能真正 claim 成功

所以 claim 是**线程安全**的。

---

## 4. teammate 新增两个工具

相比 s10，s11 的 teammate tool 多了：

- `idle`
- `claim_task`

### `idle`
表示：
> “我现在没活了，进入 idle phase 轮询。”

### `claim_task`
允许 agent 主动认领任务板里的某个任务。

---

## 5. identity re-injection
这是 s11 一个容易忽略但很重要的点：

```python
def make_identity_block(name: str, role: str, team_name: str) -> dict:
    return {
        "role": "user",
        "content": f"<identity>You are '{name}', role: {role}, team: {team_name}. Continue your work.</identity>",
    }
```

如果上下文很短：

```python
if len(messages) <= 3:
    messages.insert(0, make_identity_block(name, role, team_name))
    messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
```

说明可能发生过 context compression，这时系统会重新提醒它：

- 你是谁
- 你是什么角色
- 你属于哪个团队

---

# 场景 1
# `Create 3 tasks on the board, then spawn alice and bob. Watch them auto-claim.`

这是 s11 最经典的演示：**多个 agent 自动从任务板抢活**。

---

## Step 1：lead 先创建 3 个任务

用户输入：

```text
Create 3 tasks on the board, then spawn alice and bob. Watch them auto-claim.
```

lead LLM 先会用文件工具往 `.tasks/` 写入任务文件。

例如：

```text
.tasks/task_1.json
.tasks/task_2.json
.tasks/task_3.json
```

每个文件内容可能像：

```json
{
  "id": 1,
  "subject": "Task 1",
  "description": "First task",
  "status": "pending",
  "blockedBy": [],
  "owner": ""
}
```

此时任务板状态是：

| id | status   | owner | blockedBy |
|----|----------|-------|-----------|
| 1  | pending  | 空    | []        |
| 2  | pending  | 空    | []        |
| 3  | pending  | 空    | []        |

---

## Step 2：lead spawn alice 和 bob

lead 调用：

```python
TEAM.spawn("alice", "coder", prompt)
TEAM.spawn("bob", "tester", prompt)
```

每次 spawn 都会：

- 在 `.team/config.json` 里新增成员
- 状态设为 `working`
- 启动线程 `_loop(name, role, prompt)`

例如：

```json
{
  "team_name": "default",
  "members": [
    {"name": "alice", "role": "coder", "status": "working"},
    {"name": "bob", "role": "tester", "status": "working"}
  ]
}
```

---

## Step 3：alice / bob 进入 WORK phase

在 `_loop()` 里一开始：

```python
messages = [{"role": "user", "content": prompt}]
tools = self._teammate_tools()
```

teammate 的 system prompt 是：

```python
"You are '{name}', role: {role}, team: {team_name}, at {WORKDIR}. Use idle tool when you have no more work. You will auto-claim new tasks."
```

所以 agent 被明确告知：

- 没活就 `idle`
- 你会自动认领任务

如果 spawn prompt 本身没有给特别具体的工作，LLM 很可能很快就调用：

```json
{
  "name": "idle",
  "input": {}
}
```

此时 harness 返回：

```text
Entering idle phase. Will poll for new tasks.
```

然后跳出 WORK phase。

---

## Step 4：进入 IDLE phase

代码：

```python
self._set_status(name, "idle")
resume = False
polls = IDLE_TIMEOUT // max(POLL_INTERVAL, 1)
for _ in range(polls):
    time.sleep(POLL_INTERVAL)
    inbox = BUS.read_inbox(name)
    ...
    unclaimed = scan_unclaimed_tasks()
    if unclaimed:
        task = unclaimed[0]
        result = claim_task(task["id"], name)
```

这里的轮询顺序是：

1. 先看 inbox 有没有消息
2. 再看 `.tasks/` 有没有可认领任务

---

## Step 5：alice / bob 自动扫描任务板

假设 alice 先执行到：

```python
unclaimed = scan_unclaimed_tasks()
```

返回：

```python
[
  {"id": 1, "subject": "...", "status": "pending", "owner": "", "blockedBy": []},
  {"id": 2, ...},
  {"id": 3, ...}
]
```

然后她拿第一个：

```python
task = unclaimed[0]   # task 1
result = claim_task(1, "alice")
```

在 `claim_task()` 中：

- 加锁 `_claim_lock`
- 检查 owner/status/blockedBy
- 成功后写回：

```json
{
  "id": 1,
  "subject": "...",
  "description": "...",
  "status": "in_progress",
  "blockedBy": [],
  "owner": "alice"
}
```

---

## Step 6：alice 被重新唤醒进入 WORK

claim 成功后，系统构造新的上下文注入：

```python
task_prompt = (
    f"<auto-claimed>Task #{task['id']}: {task['subject']}\n"
    f"{task.get('description', '')}</auto-claimed>"
)
```

如果上下文很短，还会插入 identity block：

```python
messages.insert(0, make_identity_block(name, role, team_name))
messages.insert(1, {"role": "assistant", "content": f"I am {name}. Continuing."})
```

然后追加：

```python
messages.append({"role": "user", "content": task_prompt})
messages.append({"role": "assistant", "content": f"Claimed task #{task['id']}. Working on it."})
resume = True
```

这一步非常关键：

**任务不是 lead 分配给 alice 的，而是 harness 在 idle 轮询中把 auto-claimed task 注入给她。**

随后：

```python
self._set_status(name, "working")
```

alice 回到 WORK phase。

---

## Step 7：bob 会 claim 另一个任务

bob 也在轮询。  
如果 bob 在 alice 之后扫描，会看到：

- task 1 已被 alice 认领
- task 2 / task 3 仍可认领

于是 bob claim task 2：

```json
{
  "id": 2,
  "status": "in_progress",
  "owner": "bob"
}
```

这就形成了“自动分工”。

---

## 场景 1 的关键教学点

这句输入展示的是：

- lead 只负责 **建任务 + spawn 人**
- 真正的任务分配发生在 **teammate idle polling**
- claim 用 `_claim_lock` 保证抢任务不冲突

也就是说：

> **任务板成了 work queue，teammate 成了 autonomous workers。**

---

# 场景 2
# `Spawn a coder teammate and let it find work from the task board itself`

这个例子是场景 1 的单人版，更纯粹地展示“自治”。

---

## Step 1：lead 只 spawn，不下发具体任务

lead 做的事只有：

```python
TEAM.spawn("alice", "coder", prompt)
```

关键点是：**prompt 不必具体指定某个 task**。

---

## Step 2：teammate 自己进入 idle

因为一开始没有明确工作，agent 很可能调用：

```json
{"name": "idle", "input": {}}
```

进入 IDLE phase。

---

## Step 3：IDLE phase 自动扫 `.tasks/`

```python
unclaimed = scan_unclaimed_tasks()
```

如果任务板上已经有：

```json
{"id": 3, "status": "pending", "owner": "", "blockedBy": []}
```

那它会：

```python
claim_task(3, "alice")
```

写回任务：

```json
{
  "id": 3,
  "status": "in_progress",
  "owner": "alice"
}
```

然后注入：

```text
<auto-claimed>Task #3: ...</auto-claimed>
```

再回到 WORK。

---

## 场景 2 的关键点

这个输入突出：

- lead 不需要逐项指挥
- teammate 不需要收到 `send_message("do task #3")`
- **任务板本身就是 coordination mechanism**

---

# 场景 3
# `Create tasks with dependencies. Watch teammates respect the blocked order.`

这是 s11 非常重要的一点：**自动认领只认领“当前可做”的任务**。

---

## Step 1：创建带依赖的任务

例如 lead 写入：

### `task_1.json`
```json
{
  "id": 1,
  "subject": "Setup project",
  "description": "Initial setup",
  "status": "pending",
  "blockedBy": [],
  "owner": ""
}
```

### `task_2.json`
```json
{
  "id": 2,
  "subject": "Write code",
  "description": "Implement feature",
  "status": "pending",
  "blockedBy": [1],
  "owner": ""
}
```

### `task_3.json`
```json
{
  "id": 3,
  "subject": "Write tests",
  "description": "Add tests",
  "status": "pending",
  "blockedBy": [2],
  "owner": ""
}
```

---

## Step 2：scan_unclaimed_tasks() 如何过滤 blocked task

代码里筛选条件是：

```python
if (task.get("status") == "pending"
        and not task.get("owner")
        and not task.get("blockedBy")):
    unclaimed.append(task)
```

关键是：

```python
and not task.get("blockedBy")
```

这意味着：

- `blockedBy=[]` -> 可认领
- `blockedBy=[1]` -> 不可认领
- `blockedBy=[2]` -> 不可认领

所以在这个例子里，初始只有 task 1 会被扫出来。

---

## Step 3：teammate 只能先 claim task 1

无论有几个 teammate，在当前实现中：

- 他们都只能看到 task 1 是可认领的
- task 2 / task 3 不在 `unclaimed` 列表里

所以自动 claim 顺序天然会遵循依赖顺序。

---

## Step 4：为什么说“respect blocked order”

因为 claim 层面就已经把 blocked task 过滤掉了。  
甚至 `claim_task()` 内部也再次检查：

```python
if task.get("blockedBy"):
    return f"Error: Task {task_id} is blocked by other task(s) and cannot be claimed yet"
```

所以是双保险：

1. `scan_unclaimed_tasks()` 不会返回 blocked task
2. `claim_task()` 就算被硬调用也会拒绝

---

## 一个重要现实点

当前这份 demo 里，“blockedBy” 的解除不是自动推导完成依赖链。  
也就是说：

- 它会阻止 claim blocked task
- 但谁来把 `blockedBy` 清空，或者在上游任务完成后更新状态，需要额外逻辑

所以文档说“Watch teammates respect the blocked order”，主要强调的是：

> **他们不会越过 blocked 任务抢活。**

而不是说依赖图会被自动完整调度。

---

# 场景 4
# 输入 `/tasks` 查看带 owner 的任务看板

这个是 CLI 级调试/观察命令。

和 `/team` 类似，通常应该是主循环里特殊处理，不经过 LLM。

---

## `/tasks` 想看的是什么

文档里说：

```text
输入 `/tasks` 查看带 owner 的任务看板
```

所以它应该把 `.tasks/task_*.json` 全部列出来，至少展示：

- id
- subject
- status
- owner
- blockedBy

例如可能显示：

```text
#1 Setup project    in_progress   owner=alice   blockedBy=[]
#2 Write code       pending       owner=        blockedBy=[1]
#3 Write tests      pending       owner=        blockedBy=[2]
```

或者在场景 1 中会看到：

```text
#1 Task 1           in_progress   owner=alice   blockedBy=[]
#2 Task 2           in_progress   owner=bob     blockedBy=[]
#3 Task 3           pending       owner=        blockedBy=[]
```

---

## `/tasks` 的意义

这是观察 autonomous behavior 的最直接入口，因为它展示了：

- 哪些任务还未被认领
- 哪些任务已被谁 claim
- 哪些任务被 blocked

可以说 `/tasks` 是 s11 的“自治控制面仪表盘”。

---

# s11 的完整 teammate 状态机

这一章最重要的是看 `_loop()` 的双阶段结构。

---

## WORK phase

```python
for _ in range(50):
    inbox = BUS.read_inbox(name)
    ...
    response = adapter.create_response(messages, tools, sys_prompt)
    ...
    if adapter.get_stop_reason(response) != "tool_use":
        break
    ...
    if idle_requested:
        break
```

WORK phase 是“正常 agent 工作阶段”：

- 读消息
- 调 LLM
- 执行工具
- 直到：
  - 模型不再调工具，或
  - 模型显式调用 `idle`

---

## IDLE phase

```python
self._set_status(name, "idle")
for _ in range(polls):
    time.sleep(POLL_INTERVAL)
    inbox = BUS.read_inbox(name)
    if inbox:
        ...
        resume = True
        break
    unclaimed = scan_unclaimed_tasks()
    if unclaimed:
        ...
        resume = True
        break
```

IDLE phase 是“自治轮询阶段”：

先看有没有消息，再看有没有任务。

如果什么都没有：

```python
if not resume:
    self._set_status(name, "shutdown")
    return
```

也就是 **60 秒 idle timeout 后自动 shutdown**。

---

# 这一章最重要的 4 条数据流

---

## 1. 任务发现流
```text
.tasks/*.json -> scan_unclaimed_tasks() -> unclaimed list
```

---

## 2. 原子认领流
```text
claim_task(task_id, owner) -> lock -> 校验 -> 写回 task.json
```

---

## 3. 任务注入流
```text
claim success -> append <auto-claimed>Task #n...</auto-claimed> -> teammate resumes WORK
```

---

## 4. 身份恢复流
```text
messages 太短 -> insert <identity>...</identity> -> 防止 agent 忘记自己是谁
```

---

# 把你这 4 个输入映射成知识点

---

## 1. `Create 3 tasks on the board, then spawn alice and bob. Watch them auto-claim.`
看点：
- 多人并发扫任务板
- `_claim_lock` 防抢同一任务
- owner 自动填到 task 文件里

---

## 2. `Spawn a coder teammate and let it find work from the task board itself`
看点：
- 单 agent 自治找活
- lead 不再逐项派工

---

## 3. `Create tasks with dependencies. Watch teammates respect the blocked order.`
看点：
- `scan_unclaimed_tasks()` 只返回未 blocked 任务
- `claim_task()` 再次拒绝 blocked claim
- 自动认领遵循依赖顺序

---

## 4. `/tasks` 查看带 owner 的任务看板
看点：
- 直接观察任务板状态
- 是自治行为的外显结果

---

# 跟 s10 的本质差别

一句话说：

### s10
“队友要做什么，还是主要靠 lead 发起。”

### s11
“lead 只需要把人和任务板准备好，队友会自己找下一份工作。”

因此 s11 的核心从“协议协调”进一步变成“**基于共享任务板的自组织调度**”。

---

如果你愿意，我下一步可以继续帮你做两种增强版之一：

1. **把 s11 这 4 个输入画成 Mermaid 时序图 / 状态图**
2. **继续按源码逐函数拆解 `_loop -> idle -> scan_unclaimed_tasks -> claim_task -> resume WORK`**

