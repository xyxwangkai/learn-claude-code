# s08-s12 总览：从后台执行到自治协作再到目录隔离

`s01 > s02 > s03 > s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> 这一段不是 5 个孤立功能, 而是一条连续的 harness 演进路线：
> **先解决等待, 再解决协作, 再解决协议, 再解决自治, 最后解决执行隔离。**

---

## 一张图先看全局

```text
s08 Background Tasks
  单 Agent + 后台命令
  关键词: non-blocking

        |
        v

s09 Agent Teams
  多 Agent + 持久身份 + 邮箱通信
  关键词: teammates

        |
        v

s10 Team Protocols
  request_id + pending/approved/rejected
  关键词: structured coordination

        |
        v

s11 Autonomous Agents
  idle polling + task board + auto-claim
  关键词: self-organizing

        |
        v

s12 Worktree + Task Isolation
  task 绑定独立 git worktree
  关键词: isolated execution lanes
```

如果把它们看成同一个系统的逐层升级, 那么每一章都在回答一个新问题：

- s08：**慢操作会卡住 Agent，怎么办？**
- s09：**一个 Agent 不够，怎么让多个 Agent 协作？**
- s10：**协作不能靠随口聊天，怎么做成协议？**
- s11：**leader 不可能永远手工派工，怎么让队友自己找活？**
- s12：**即使会并行协作，大家还在一个目录里干活，怎么避免互相污染？**

---

## s08：Background Tasks —— 先把“等待”从 LLM 身上拿走

### 这一章解决什么

s08 解决的是最基础的问题：

> 有些命令很慢，如果 Agent 一边等 `pytest`、`npm install`、`docker build`，一边什么都做不了，那整个系统就会被阻塞。

所以 s08 的答案是：

- 慢命令放后台线程执行
- 主 Agent 不阻塞
- 结果在下一次 LLM 调用前注入上下文

### 核心数据流

```text
user input
  -> LLM decides background_run(...)
  -> BackgroundManager starts thread
  -> returns task_id immediately
  -> Agent keeps working
  -> thread finishes
  -> notification_queue
  -> next LLM call injects <background-results>
```

### 关键价值

它并没有让多个 LLM 并发思考，而是让：

- **命令执行** 并行化
- **LLM 决策流** 保持连续

一句话：

> s08 把“等待”交给 harness，把“推进任务”留给模型。

---

## s09：Agent Teams —— 再把“一次性 subagent”升级成持久队友

### 这一章解决什么

s08 之后，命令可以后台跑了，但系统仍然只有一个主要 Agent。\
如果任务复杂，需要不同角色长期协作，就需要：

- 有名字的队友
- 持久存在的生命周期
- 能互相发消息的通道

所以 s09 引入：

- `config.json`：团队名册和状态
- `.team/inbox/*.jsonl`：每个成员一个邮箱
- 每个 teammate 一个独立线程 + 独立 agent loop

### 核心数据流

```text
lead spawns alice/bob
  -> config.json persists identity/status
  -> teammate threads start
  -> BUS.send(...) appends JSON line to inbox
  -> teammate read_inbox() at next loop boundary
  -> message injected into that teammate's context
  -> teammate acts/responds
```

### 关键价值

s09 的重点不是“多开线程”本身，而是：

> **让多个有身份的持久 Agent，通过邮箱这种简单持久化介质彼此协调。**

这一步后，系统第一次从“单 Agent 工具调用器”变成“多 Agent 团队”。

---

## s10：Team Protocols —— 再把“能说话”升级成“按协议协商”

### 这一章解决什么

到 s09，队友可以聊天了，但聊天不等于可靠协作。\
如果是高风险动作，例如：

- 优雅关机
- 大型重构前先提计划

就不能只靠一条普通 message，而要有：

- 请求 ID
- 可跟踪状态
- 明确的 approve / reject 结果

所以 s10 引入两个 tracker：

- `shutdown_requests`
- `plan_requests`

它们共享同一套状态机：

```text
pending -> approved | rejected
```

### 核心数据流

#### shutdown

```text
lead creates request_id
  -> send shutdown_request
  -> teammate reads inbox
  -> teammate sends shutdown_response(request_id, approve=...)
  -> tracker updates
  -> if approved, teammate exits and status becomes shutdown
```

#### plan approval

```text
teammate creates request_id
  -> submits plan
  -> lead reviews
  -> lead sends plan_approval_response(request_id, approve=...)
  -> tracker updates
  -> teammate continues or revises
```

### 关键价值

s10 的本质是：

> 把“消息”升级成“可关联、可追踪、可审批的协议事件”。

从这一步开始，团队协作不再只是“互相发话”，而是有正式握手语义。

---

## s11：Autonomous Agents —— 再把“等待派工”升级成“自己找活”

### 这一章解决什么

即使有了协议，队友还是太依赖 lead：

- 任务板上有 10 个任务
- lead 还得一个个指派给 alice、bob、charlie

这显然不扩展。

所以 s11 的目标是：

> 队友空闲时自己去看任务板，发现未认领任务就自己 claim。

### 新增机制

- `.tasks/` 任务板成为共享协调介质
- teammate 增加 `idle` 和 `claim_task` 工具
- agent loop 分成两阶段：
  - WORK phase
  - IDLE phase

### 核心数据流

```text
WORK ends / idle tool called
  -> teammate enters IDLE
  -> poll inbox
  -> if no inbox message, scan .tasks/
  -> find pending + no owner + not blocked task
  -> claim_task(task_id, name)
  -> task file updated: owner=name, status=in_progress
  -> <auto-claimed> task injected into context
  -> teammate resumes WORK
```

### blocked 任务为什么会被尊重

因为扫描函数只返回：

- `status == pending`
- `owner` 为空
- `blockedBy` 为空

所以依赖任务不会被提前 claim。

### 身份重注入为什么重要

当 context 很短时，说明可能刚做过 compact。\
这时 s11 会把：

```text
<identity>You are 'alice', role: coder, team: default...</identity>
```

重新塞回上下文，防止 agent 忘记自己是谁。

### 关键价值

s11 的本质是：

> 把任务分配从“leader 显式调度”变成“队友围绕任务板自组织调度”。

---

## s12：Worktree + Task Isolation —— 最后把“逻辑分工”落实到“目录隔离”

### 这一章解决什么

到 s11，任务可以自动分工了，但它们仍然在**同一个工作目录**里执行。\
这会带来经典问题：

- 两个 Agent 同时改同一个文件
- 未提交改动互相污染
- 回滚和收尾都很难干净

所以 s12 的核心是：

> 每个任务绑定一个独立 git worktree，形成真正的隔离执行通道。

### 三份持久化状态

1. `.tasks/task_N.json`\
   记录任务目标、状态、绑定 worktree

2. `.worktrees/index.json`\
   记录 worktree 名、路径、branch、绑定 task_id

3. `.worktrees/events.jsonl`\
   记录 create / keep / remove / task.completed 等事件

### 核心数据流

```text
TASKS.create(...)
  -> task file created

WORKTREES.create(name, task_id)
  -> emit worktree.create.before
  -> git worktree add -b wt/<name> .worktrees/<name> HEAD
  -> write index.json
  -> bind task.worktree = name
  -> if pending -> task.status = in_progress
  -> emit worktree.create.after
```

### 在隔离目录执行命令

```text
WORKTREES.run("auth-refactor", "git status --short")
  -> cwd = .worktrees/auth-refactor
```

这说明同样的命令，不同 worktree name，就落在不同目录中运行。

### 收尾两种方式

- `keep(name)`：保留目录和上下文，便于后续继续开发或人工检查
- `remove(name, complete_task=True)`：删除目录、完成绑定任务、写事件流

### 关键价值

s12 把系统从“逻辑上能并行”推进到：

> **文件系统层面也真正互不干扰。**

---

## s08-s12 一起看：它们到底是怎么一层层长出来的

可以把这五章理解为 **五层能力叠加**：

### 第 1 层：不阻塞
- s08 让慢命令不再卡住 Agent

### 第 2 层：多主体
- s09 让系统从单 Agent 变成多 Agent 团队

### 第 3 层：有协议
- s10 让关键协作变成 request-response + request_id 的结构化流程

### 第 4 层：会自治
- s11 让队友可以自己从任务板找活做

### 第 5 层：真隔离
- s12 让每个任务拥有自己的目录和 branch，互不污染

这五层叠起来，系统就从一个“会调用工具的 agent demo”，逐步变成一个更接近真实工程环境的协作框架。

---

## 一张总表：每章新增的关键能力

| 章节 | 解决的问题 | 新增核心机制 | 关键词 |
|------|------------|--------------|--------|
| s08 | 慢命令阻塞 | 后台线程 + 通知队列 | non-blocking |
| s09 | 单 Agent 不够协作 | 持久 teammate + JSONL inbox | team communication |
| s10 | 聊天式协作不可靠 | request_id + tracker + FSM | structured protocol |
| s11 | lead 手工派工不扩展 | idle polling + task board auto-claim | autonomy |
| s12 | 并行改动互相污染 | task-worktree binding + event log | isolation |

---

## 如果你要用一句话向别人解释 s08-s12

可以这样说：

> s08-s12 展示的是 harness 如何一步步把 Agent 从“会调用工具”升级成“能后台执行、能团队协作、能协议审批、能自主认领任务、还能在独立目录并行开发”的系统。

或者再工程化一点：

> 这五章对应的是 Agent 系统的五个基础能力层：**并发、协作、协议、自治、隔离**。

---

## 建议的阅读顺序

如果你要带别人讲这几章, 推荐这样讲：

1. **先讲 s08**：让大家理解 harness 可以替模型“等”\
2. **再讲 s09**：让大家理解多 Agent 不能只靠临时 subagent\
3. **再讲 s10**：让大家理解生产化协作必须协议化\
4. **再讲 s11**：让大家理解任务板如何驱动自组织\
5. **最后讲 s12**：让大家理解为什么最终必须做目录隔离\

这样顺序最符合系统自然演化逻辑。
