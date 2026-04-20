# s09: Agent Teams (Agent 团队)

`s01 > s02 > s03 > s04 > s05 > s06 | s07 > s08 > [ s09 ] s10 > s11 > s12`

> *"任务太大一个人干不完, 要能分给队友"* -- 持久化队友 + JSONL 邮箱。
>
> **Harness 层**: 团队邮箱 -- 多个模型, 通过文件协调。

## 问题

Subagent (s04) 是一次性的: 生成、干活、返回摘要、消亡。没有身份, 没有跨调用的记忆。Background Tasks (s08) 能跑 shell 命令, 但做不了 LLM 引导的决策。

真正的团队协作需要三样东西: (1) 能跨多轮对话存活的持久 Agent, (2) 身份和生命周期管理, (3) Agent 之间的通信通道。

## 解决方案

```
Teammate lifecycle:
  spawn -> WORKING -> IDLE -> WORKING -> ... -> SHUTDOWN

Communication:
  .team/
    config.json           <- team roster + statuses
    inbox/
      alice.jsonl         <- append-only, drain-on-read
      bob.jsonl
      lead.jsonl

              +--------+    send("alice","bob","...")    +--------+
              | alice  | -----------------------------> |  bob   |
              | loop   |    bob.jsonl << {json_line}    |  loop  |
              +--------+                                +--------+
                   ^                                         |
                   |        BUS.read_inbox("alice")          |
                   +---- alice.jsonl -> read + drain ---------+
```

## 工作原理

1. TeammateManager 通过 config.json 维护团队名册。

```python
class TeammateManager:
    def __init__(self, team_dir: Path):
        self.dir = team_dir
        self.dir.mkdir(exist_ok=True)
        self.config_path = self.dir / "config.json"
        self.config = self._load_config()
        self.threads = {}
```

2. `spawn()` 创建队友并在线程中启动 agent loop。

```python
def spawn(self, name: str, role: str, prompt: str) -> str:
    member = {"name": name, "role": role, "status": "working"}
    self.config["members"].append(member)
    self._save_config()
    thread = threading.Thread(
        target=self._teammate_loop,
        args=(name, role, prompt), daemon=True)
    thread.start()
    return f"Spawned teammate '{name}' (role: {role})"
```

3. MessageBus: append-only 的 JSONL 收件箱。`send()` 追加一行; `read_inbox()` 读取全部并清空。

```python
class MessageBus:
    def send(self, sender, to, content, msg_type="message", extra=None):
        msg = {"type": msg_type, "from": sender,
               "content": content, "timestamp": time.time()}
        if extra:
            msg.update(extra)
        with open(self.dir / f"{to}.jsonl", "a") as f:
            f.write(json.dumps(msg) + "\n")

    def read_inbox(self, name):
        path = self.dir / f"{name}.jsonl"
        if not path.exists(): return "[]"
        msgs = [json.loads(l) for l in path.read_text().strip().splitlines() if l]
        path.write_text("")  # drain
        return json.dumps(msgs, indent=2)
```

4. 每个队友在每次 LLM 调用前检查收件箱, 将消息注入上下文。

```python
def _teammate_loop(self, name, role, prompt):
    messages = [{"role": "user", "content": prompt}]
    for _ in range(50):
        inbox = BUS.read_inbox(name)
        if inbox != "[]":
            messages.append({"role": "user",
                "content": f"<inbox>{inbox}</inbox>"})
        response = client.messages.create(...)
        if response.stop_reason != "tool_use":
            break
        # execute tools, append results...
    self._find_member(name)["status"] = "idle"
```

## 相对 s08 的变更

| 组件           | 之前 (s08)       | 之后 (s09)                         |
|----------------|------------------|------------------------------------|
| Tools          | 6                | 9 (+spawn/send/read_inbox)         |
| Agent 数量     | 单一             | 领导 + N 个队友                    |
| 持久化         | 无               | config.json + JSONL 收件箱         |
| 线程           | 后台命令         | 每线程完整 agent loop              |
| 生命周期       | 一次性           | idle -> working -> idle            |
| 通信           | 无               | message + broadcast                |

## 调用案例

**用户输入**

```text
找两个队友，一个检查测试，一个检查文档，我来统筹
```

**典型调用顺序**

1. `spawn(name="tester", role="test reviewer", prompt="Review the test suite")`
2. `spawn(name="writer", role="doc reviewer", prompt="Review the docs")`
3. 主 Agent 通过 `send_message` 给队友补充要求
4. 队友把结果写回各自 inbox, 主 Agent 汇总

**终端关键输出**

```text
> spawn:
Spawned teammate 'tester'

> spawn:
Spawned teammate 'writer'
```

**这个案例说明了什么**

s09 的关键不是“再开两个循环”, 而是 **让多个持久 Agent 通过邮箱通信协作**。

## 试一试

```sh
cd learn-claude-code
python agents/s09_agent_teams.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Spawn alice (coder) and bob (tester). Have alice send bob a message.`
2. `Broadcast "status update: phase 1 complete" to all teammates`
3. `Check the lead inbox for any messages`
4. 输入 `/team` 查看团队名册和状态
5. 输入 `/inbox` 手动检查领导的收件箱

## 一句话总结

- **核心能力**: 把一次性 subagent 升级为可持久存在的 teammate。
- **数据流关键词**: `spawn -> teammate thread -> JSONL inbox -> read+drain -> 注入上下文`。
- **你应该记住**: s09 解决的是 **协作问题** —— 队友有身份、有状态、能互相发消息。

## 从输入到结果的数据流

以这句输入为例:

```text
Spawn alice (coder) and bob (tester). Have alice send bob a message.
```

典型链路如下:

1. lead 调用 `spawn(name, role, prompt)` 创建 alice / bob。
2. `config.json` 持久化成员信息, 状态设为 `working`。
3. 每个 teammate 在独立线程中运行 `_teammate_loop()`。
4. lead 若想让 alice 联系 bob, 会先给 alice 发消息。
5. `BUS.send()` 不是直接内存调用, 而是向 `.team/inbox/alice.jsonl` 追加一行 JSON。
6. alice 下一轮调用 LLM 前执行 `read_inbox("alice")`, 读完并清空收件箱。
7. alice 根据消息内容再调用 `send_message(to="bob", ...)`。
8. bob 在自己的下一轮循环里读到来自 alice 的消息。

这里的关键是: **消息不是实时打断式推送, 而是每个 agent 在自己的循环边界主动 read + drain**。

## 本章和前后章节的衔接

- s08 解决 **等待**。
- s09 解决 **多 Agent 持久化与通信**。
- s10 则在此基础上进一步引入 **带 request_id 的协议握手**。

