# s08: Background Tasks (后台任务)

`s01 > s02 > s03 > s04 > s05 > s06 | s07 > [ s08 ] s09 > s10 > s11 > s12`

> *"慢操作丢后台, agent 继续想下一步"* -- 后台线程跑命令, 完成后注入通知。
>
> **Harness 层**: 后台执行 -- 模型继续思考, harness 负责等待。

## 问题

有些命令要跑好几分钟: `npm install`、`pytest`、`docker build`。阻塞式循环下模型只能干等。用户说 "装依赖, 顺便建个配置文件", Agent 却只能一个一个来。

## 解决方案

```
Main thread                Background thread
+-----------------+        +-----------------+
| agent loop      |        | subprocess runs |
| ...             |        | ...             |
| [LLM call] <---+------- | enqueue(result) |
|  ^drain queue   |        +-----------------+
+-----------------+

Timeline:
Agent --[spawn A]--[spawn B]--[other work]----
             |          |
             v          v
          [A runs]   [B runs]      (parallel)
             |          |
             +-- results injected before next LLM call --+
```

## 工作原理

1. BackgroundManager 用线程安全的通知队列追踪任务。

```python
class BackgroundManager:
    def __init__(self):
        self.tasks = {}
        self._notification_queue = []
        self._lock = threading.Lock()
```

2. `run()` 启动守护线程, 立即返回。

```python
def run(self, command: str) -> str:
    task_id = str(uuid.uuid4())[:8]
    self.tasks[task_id] = {"status": "running", "command": command}
    thread = threading.Thread(
        target=self._execute, args=(task_id, command), daemon=True)
    thread.start()
    return f"Background task {task_id} started"
```

3. 子进程完成后, 结果进入通知队列。

```python
def _execute(self, task_id, command):
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
            capture_output=True, text=True, timeout=300)
        output = (r.stdout + r.stderr).strip()[:50000]
    except subprocess.TimeoutExpired:
        output = "Error: Timeout (300s)"
    with self._lock:
        self._notification_queue.append({
            "task_id": task_id, "result": output[:500]})
```

4. 每次 LLM 调用前排空通知队列。

```python
def agent_loop(messages: list):
    while True:
        notifs = BG.drain_notifications()
        if notifs:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}] {n['result']}" for n in notifs)
            messages.append({"role": "user",
                "content": f"<background-results>\n{notif_text}\n"
                           f"</background-results>"})
        response = client.messages.create(...)
```

循环保持单线程。只有子进程 I/O 被并行化。

## 相对 s07 的变更

| 组件           | 之前 (s07)       | 之后 (s08)                         |
|----------------|------------------|------------------------------------|
| Tools          | 8                | 6 (基础 + background_run + check)  |
| 执行方式       | 仅阻塞           | 阻塞 + 后台线程                    |
| 通知机制       | 无               | 每轮排空的队列                     |
| 并发           | 无               | 守护线程                           |

## 调用案例

**用户输入**

```text
后台跑 pytest，同时继续帮我检查 README 结构
```

**典型调用顺序**

1. 模型调用 `background_run(command="pytest")`
2. harness 立刻返回任务 ID, 不阻塞主循环
3. 模型继续调用读文件工具检查 README
4. 下次调用模型前, 后台任务完成通知被注入上下文

**终端关键输出**

```text
> background_run:
Background task a1b2c3d4 started

[bg:a1b2c3d4] 12 passed in 2.31s
```

**这个案例说明了什么**

s08 让慢操作和思考过程并行: **等待交给 harness, 模型继续往前走。**

## 试一试

```sh
cd learn-claude-code
python agents/s08_background_tasks.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Run "sleep 5 && echo done" in the background, then create a file while it runs`
2. `Start 3 background tasks: "sleep 2", "sleep 4", "sleep 6". Check their status.`
3. `Run pytest in the background and keep working on other things`

## 一句话总结

- **核心能力**: 把慢命令放到后台线程执行, 让主 Agent 不阻塞。
- **数据流关键词**: `background_run -> thread -> notification_queue -> 下次 LLM 调用前注入`。
- **你应该记住**: s08 解决的是 **等待问题** —— 等待交给 harness, 模型继续思考和调用其他工具。

## 从输入到结果的数据流

以这句输入为例:

```text
Run "sleep 5 && echo done" in the background, then create a file while it runs
```

典型链路如下:

1. 用户输入进入 `messages`。
2. LLM 根据 system prompt 选择 `background_run(command=...)`。
3. `BackgroundManager.run()` 立刻:
   - 生成 `task_id`
   - 写入 `tasks[task_id] = running`
   - 启动后台线程
   - 立即返回 `started` 文本
4. 主循环继续, LLM 还能再调用 `write_file(...)` 等工具。
5. 后台线程执行完后, `_execute()` 将结果写入 `_notification_queue`。
6. **下一次** 调用 LLM 前, `drain_notifications()` 把结果包装成 `<background-results>` 注入上下文。

也就是说, s08 的关键不是“LLM 并行思考”, 而是 **harness 并行执行命令, LLM 非阻塞继续推进任务**。

## 本章和后续章节的衔接

- s08 解决 **单 Agent 如何不被慢命令卡住**。
- s09 开始解决 **多个 Agent 如何持久存在并彼此通信**。

