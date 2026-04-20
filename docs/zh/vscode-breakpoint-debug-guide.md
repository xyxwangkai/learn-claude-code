# VSCode 断点调试指南（12 个递进式课程）

本指南配合仓库中的 `agents/s01` 到 `agents/s12` 以及 `agents/s_full.py` 使用。

## 你已经有的配置

当前仓库已经生成：

- `.vscode/launch.json`：每节课单独调试入口
- `.vscode/settings.json`：固定使用 `.venv/bin/python`
- `.vscode/tasks.json`：每节课一键运行入口

## 通用调试方法

### 方式 1：断点调试

1. 打开左侧 **运行和调试**
2. 选择对应课程，例如 `Agent: s01 agent loop`
3. 在代码左侧行号处打断点
4. 按 `F5`
5. 在底部终端输入任务

### 方式 2：只运行不调试

1. `Terminal -> Run Task`
2. 选择 `Agent: run s01` 等任务

### 通用建议

- 第一次学习，优先在 **agent_loop**、**tool handler**、**状态对象更新** 处下断点
- 观察变量时重点看：
  - `messages`
  - `response.stop_reason`
  - `response.content`
  - 各类 manager 的内部状态
- 如果程序在等你输入，不是卡死，而是在 REPL 等待命令

---

## s01 - Agent Loop

文件：`agents/s01_agent_loop.py`

### 建议断点

1. `response = client.messages.create(...)`
2. `if response.stop_reason != "tool_use":`
3. `output = run_bash(block.input["command"])`
4. `messages.append({"role": "user", "content": results})`

### 建议输入

```text
列出当前目录
```

或：

```text
pwd
```

### 重点观察

- `messages` 如何不断追加 assistant / user / tool_result
- `stop_reason` 是否是 `tool_use`
- `block.input["command"]` 是模型要求执行的命令
- `run_bash()` 输出如何再次喂回模型

### 这一节要理解的核心

最小 agent 本质就是：

- 模型决定是否调工具
- 代码执行工具
- 结果回填给模型
- 循环直到模型停止

---

## s02 - Tool Use

文件：`agents/s02_tool_use.py`

### 建议断点

1. `safe_path()`
2. `TOOL_HANDLERS = { ... }`
3. `handler = TOOL_HANDLERS.get(block.name)` 附近
4. `result = handler(**block.input)` 附近

### 建议输入

```text
读取 README.md 的前 20 行
```

或：

```text
创建一个 test.txt 文件，写入 hello
```

### 重点观察

- `block.name` 如何从 `bash` 变成 `read_file` / `write_file`
- 同一个 agent loop 没变，只是工具集合和分发表扩展了
- `safe_path()` 如何限制越界路径

### 这一节要理解的核心

新增能力不是改 loop，而是：

- 加工具定义
- 加 handler
- 加 dispatch map

---

## s03 - TodoWrite

文件：`agents/s03_todo_write.py`

### 建议断点

1. `TodoManager.update()`
2. `TodoManager.render()`
3. 注入 reminder 的逻辑附近
4. agent loop 中处理 todo tool 的位置

### 建议输入

```text
先阅读 README.md，再总结这个仓库的核心观点
```

### 重点观察

- `TODO.items` 如何变化
- `in_progress` 是否最多只有一个
- 多轮对话后 reminder 如何提醒模型更新 todo

### 这一节要理解的核心

任务规划不是外部脚本硬编码，而是让模型自己维护进度结构。

---

## s04 - Subagent

文件：`agents/s04_subagent.py`

### 建议断点

1. `run_subagent(prompt)` 入口
2. `sub_messages = [{"role": "user", "content": prompt}]`
3. 子 agent 的 `client.messages.create(...)`
4. 父 agent 接收 summary 的位置

### 建议输入

```text
阅读 README.md，帮我总结这个仓库在讲什么
```

### 重点观察

- 父 agent 的 `messages` 与子 agent 的 `sub_messages` 是隔离的
- 子 agent 完成后只把总结返回给父 agent
- 为什么这种机制能减少主上下文污染

### 这一节要理解的核心

进程/会话隔离 = 上下文隔离。

---

## s05 - Skill Loading

文件：`agents/s05_skill_loading.py`

### 建议断点

1. `SkillLoader._load_all()`
2. `_parse_frontmatter()`
3. `get_descriptions()`
4. `get_content(name)`

### 建议输入

```text
先看看有哪些 skills 可用，再解决任务
```

如果当前仓库没有实际 `skills/` 内容，也可以直接先观察初始化流程。

### 重点观察

- 系统提示词只放 skill 简介，不放全文
- 模型真正需要时，再通过 `load_skill` 工具拿全文
- `self.skills` 中保存了 name / meta / body

### 这一节要理解的核心

按需加载知识，避免 system prompt 膨胀。

---

## s06 - Context Compact

文件：`agents/s06_context_compact.py`

### 建议断点

1. `estimate_tokens(messages)`
2. `micro_compact(messages)`
3. `auto_compact(...)` 或 compact tool 对应逻辑
4. 写入 `.transcripts/` 的位置

### 建议输入

```text
连续执行多个读写或命令任务，让上下文变长
```

### 重点观察

- `messages` 在压缩前后有什么变化
- 哪些 tool result 被替换成占位文本
- 什么时候会触发自动压缩
- 摘要如何替代原始长上下文

### 这一节要理解的核心

长会话能持续，不靠无限上下文，而靠分层压缩。

---

## s07 - Task System

文件：`agents/s07_task_system.py`

### 建议断点

1. TaskManager 初始化位置
2. `create_task`
3. `update_task`
4. `list_tasks` / `get_task`
5. 写入 `.tasks/` 的位置

### 建议输入

```text
创建两个任务：一个阅读 README，一个阅读 docs/zh/s01-the-agent-loop.md
```

### 重点观察

- 磁盘上的 `.tasks/` 如何成为持久化任务板
- 任务状态如何变化
- 为什么任务系统是后续多 agent 协作的基础

### 这一节要理解的核心

目标不能只存在上下文里，还要落盘成为外部状态。

---

## s08 - Background Tasks

文件：`agents/s08_background_tasks.py`

### 建议断点

1. `BackgroundManager.run()`
2. `threading.Thread(...)`
3. `_execute(...)`
4. `drain_notifications()`

### 建议输入

```text
后台执行一个稍慢一点的命令，然后继续做别的事
```

例如可尝试：

```text
后台执行 sleep 3 && echo done，然后告诉我任务状态
```

### 重点观察

- 主 agent 不会阻塞等待后台任务
- `self.tasks` 中状态如何变化：`running -> completed`
- 完成通知如何进入 queue，再被主循环注入

### 这一节要理解的核心

慢操作应该异步化，让 agent 不被单个命令卡住。

---

## s09 - Agent Teams

文件：`agents/s09_agent_teams.py`

### 建议断点

1. `MessageBus.send()`
2. `MessageBus.read_inbox()`
3. `spawn_teammate(...)`
4. teammate thread 启动位置

### 建议输入

```text
创建一个队友 alice，让她帮我阅读 README.md 并回报结论
```

### 重点观察

- `.team/inbox/*.jsonl` 如何作为邮箱
- 队友是长期存在的，而不是一次性 subagent
- lead 和 teammate 如何通过消息文件通信

### 这一节要理解的核心

多 agent 协作的第一步，是有持久身份和邮箱机制。

---

## s10 - Team Protocols

文件：`agents/s10_team_protocols.py`

### 建议断点

1. `shutdown_requests` / `plan_requests` 更新位置
2. 生成 `request_id` 的位置
3. 发送 shutdown request 的位置
4. 处理 response 的位置

### 建议输入

```text
创建一个队友，然后发起 shutdown 请求
```

或者：

```text
让一个队友提交计划，再审批它
```

### 重点观察

- 同一套 `request_id` 相关联模式如何复用于不同协议
- `pending -> approved/rejected` 的状态转换
- 为什么结构化协议比自然语言协商更稳定

### 这一节要理解的核心

agent 之间需要正式协议，而不是只靠自由文本。

---

## s11 - Autonomous Agents

文件：`agents/s11_autonomous_agents.py`

### 建议断点

1. idle loop 入口
2. `read_inbox()`
3. task claim 逻辑
4. `IDLE_TIMEOUT` 超时退出位置

### 建议输入

```text
创建一个队友，并创建几个待认领任务
```

### 重点观察

- 队友在空闲时如何轮询 inbox 和 task board
- 任务如何被自动 claim
- 为什么压缩后还要重新注入 identity

### 这一节要理解的核心

真正自治不是“能调用工具”，而是“能主动找活干”。

---

## s12 - Worktree + Task Isolation

文件：`agents/s12_worktree_task_isolation.py`

### 建议断点

1. `detect_repo_root()`
2. worktree 创建逻辑
3. task 与 worktree 绑定位置
4. `EventBus.emit()`
5. `list_recent()`

### 建议输入

```text
创建一个任务，并为它分配独立 worktree
```

### 重点观察

- `.tasks/` 是控制面，`.worktrees/` 是执行面
- 不同任务如何绑定不同目录
- 生命周期事件如何被记录下来

### 这一节要理解的核心

并行开发要避免互相污染，最终要落到目录隔离。

---

## s_full - 全量参考实现

文件：`agents/s_full.py`

### 建议断点

1. `safe_path()` / `run_bash()`
2. `TodoManager.update()`
3. `run_subagent()`
4. `SkillLoader.__init__()` / `load()`
5. compact 相关逻辑
6. background notification 注入位置
7. inbox 检查位置
8. team / task 工具分发位置

### 建议输入

```text
先列一个 todo，然后阅读 README.md，再总结仓库结构
```

后续再逐步尝试：

```text
创建任务
创建队友
让队友做子任务
检查 inbox
```

### 重点观察

- 所有机制是怎样叠加在一起的
- 每次 LLM 调用前，系统会先做哪些 housekeeping
- dispatch map 如何持续扩展而不破坏主 loop

### 这一节要理解的核心

完整 agent 不是一个神秘大框架，而是前面各节机制的组合。

---

## 推荐学习顺序

推荐严格按下面顺序打断点：

1. `s01` 看 loop
2. `s02` 看工具分发
3. `s03` 看 todo 状态
4. `s04` 看上下文隔离
5. `s05` 看按需知识加载
6. `s06` 看上下文压缩
7. `s07` 看落盘任务系统
8. `s08` 看后台异步
9. `s09` 看 agent 邮箱
10. `s10` 看协议
11. `s11` 看自治认领
12. `s12` 看 worktree 隔离
13. 最后回到 `s_full`

---

## 常见问题

### 1. 断点没有进来

优先检查：

- 你选对了 launch 配置没有
- 你打断点的文件和实际运行文件是不是同一个
- 当前 Python 解释器是不是 `.venv/bin/python`

### 2. 程序启动就报环境变量错误

检查 `.env`：

- `MODEL_ID`
- `ANTHROPIC_API_KEY`

### 3. 程序像卡住了一样

多数情况是在等待你在终端输入 prompt。

### 4. 某些课的效果不明显

这是正常的。有些课程重点在：

- 观察内部状态
- 看磁盘文件变化
- 看线程 / inbox / tasks / worktrees 的变化

建议边调试边看这些目录：

- `.tasks/`
- `.team/`
- `.transcripts/`
- `.worktrees/`

