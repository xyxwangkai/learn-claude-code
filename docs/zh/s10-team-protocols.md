# s10: Team Protocols (团队协议)

`s01 > s02 > s03 > s04 > s05 > s06 | s07 > s08 > s09 > [ s10 ] s11 > s12`

> *"队友之间要有统一的沟通规矩"* -- 一个 request-response 模式驱动所有协商。
>
> **Harness 层**: 协议 -- 模型之间的结构化握手。

## 问题

s09 中队友能干活能通信, 但缺少结构化协调:

**关机**: 直接杀线程会留下写了一半的文件和过期的 config.json。需要握手 -- 领导请求, 队友批准 (收尾退出) 或拒绝 (继续干)。

**计划审批**: 领导说 "重构认证模块", 队友立刻开干。高风险变更应该先过审。

两者结构一样: 一方发带唯一 ID 的请求, 另一方引用同一 ID 响应。

## 解决方案

```
Shutdown Protocol            Plan Approval Protocol
==================           ======================

Lead             Teammate    Teammate           Lead
  |                 |           |                 |
  |--shutdown_req-->|           |--plan_req------>|
  | {req_id:"abc"}  |           | {req_id:"xyz"}  |
  |                 |           |                 |
  |<--shutdown_resp-|           |<--plan_resp-----|
  | {req_id:"abc",  |           | {req_id:"xyz",  |
  |  approve:true}  |           |  approve:true}  |

Shared FSM:
  [pending] --approve--> [approved]
  [pending] --reject---> [rejected]

Trackers:
  shutdown_requests = {req_id: {target, status}}
  plan_requests     = {req_id: {from, plan, status}}
```

## 工作原理

1. 领导生成 request_id, 通过收件箱发起关机请求。

```python
shutdown_requests = {}

def handle_shutdown_request(teammate: str) -> str:
    req_id = str(uuid.uuid4())[:8]
    shutdown_requests[req_id] = {"target": teammate, "status": "pending"}
    BUS.send("lead", teammate, "Please shut down gracefully.",
             "shutdown_request", {"request_id": req_id})
    return f"Shutdown request {req_id} sent (status: pending)"
```

2. 队友收到请求后, 用 approve/reject 响应。

```python
if tool_name == "shutdown_response":
    req_id = args["request_id"]
    approve = args["approve"]
    shutdown_requests[req_id]["status"] = "approved" if approve else "rejected"
    BUS.send(sender, "lead", args.get("reason", ""),
             "shutdown_response",
             {"request_id": req_id, "approve": approve})
```

3. 计划审批遵循完全相同的模式。队友提交计划 (生成 request_id), 领导审查 (引用同一个 request_id)。

```python
plan_requests = {}

def handle_plan_review(request_id, approve, feedback=""):
    req = plan_requests[request_id]
    req["status"] = "approved" if approve else "rejected"
    BUS.send("lead", req["from"], feedback,
             "plan_approval_response",
             {"request_id": request_id, "approve": approve})
```

一个 FSM, 两种用途。同样的 `pending -> approved | rejected` 状态机可以套用到任何请求-响应协议上。

## 相对 s09 的变更

| 组件           | 之前 (s09)       | 之后 (s10)                           |
|----------------|------------------|--------------------------------------|
| Tools          | 9                | 12 (+shutdown_req/resp +plan)        |
| 关机           | 仅自然退出       | 请求-响应握手                        |
| 计划门控       | 无               | 提交/审查与审批                      |
| 关联           | 无               | 每个请求一个 request_id              |
| FSM            | 无               | pending -> approved/rejected         |

## 调用案例

**用户输入**

```text
让 reviewer 先提交重构计划，等我审批后再开工
```

**典型调用顺序**

1. 队友发送 `plan_approval_request`，附带唯一 `request_id`
2. 主 Agent 审查计划内容
3. 主 Agent 返回 `plan_approval_response(request_id=..., approve=true)`
4. 队友收到批准后才继续执行

**终端关键输出**

```text
> plan_approval_request:
request_id=abc12345 status=pending

> plan_approval_response:
request_id=abc12345 approve=true
```

**这个案例说明了什么**

s10 的价值是 **把“协作”从随意聊天升级成带 request_id 的协议握手**。

## 试一试

```sh
cd learn-claude-code
python agents/s10_team_protocols.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Spawn alice as a coder. Then request her shutdown.`
2. `List teammates to see alice's status after shutdown approval`
3. `Spawn bob with a risky refactoring task. Review and reject his plan.`
4. `Spawn charlie, have him submit a plan, then approve it.`
5. 输入 `/team` 监控状态

## 一句话总结

- **核心能力**: 用统一的 request-response 模式管理队友协作。
- **数据流关键词**: `request_id -> tracker(pending) -> response -> approved/rejected`。
- **你应该记住**: s10 解决的是 **“协作要可追踪、可审批”** —— 不再只是随意发消息。

## 两类协议, 一个模式

s10 有两套协议, 但底层模式完全相同:

1. **shutdown protocol**
   - lead 发 `shutdown_request(request_id=...)`
   - teammate 回 `shutdown_response(request_id=..., approve=...)`
   - `shutdown_requests[request_id]` 从 `pending` 变成 `approved/rejected`

2. **plan approval protocol**
   - teammate 提交计划并生成 `request_id`
   - lead 审查后返回 `plan_approval_response(request_id=..., approve=...)`
   - `plan_requests[request_id]` 从 `pending` 变成 `approved/rejected`

这就是本章最核心的抽象: **同一个有限状态机, 复用到不同协作域**。

## 从输入到结果的数据流

以这句输入为例:

```text
Spawn alice as a coder. Then request her shutdown.
```

典型链路如下:

1. lead 先 `spawn("alice", "coder", prompt)`。
2. lead 生成 `request_id` 并记录到 `shutdown_requests`。
3. lead 发送 `shutdown_request` 到 `alice.jsonl`。
4. alice 下一轮读到该消息后, 调用 `shutdown_response(request_id, approve=True/False)`。
5. harness 更新 tracker 状态。
6. 如果 approve=True, alice 在线程退出前把自己的状态写成 `shutdown`。

所以 s10 的重点不只是“发消息”, 而是 **每次关键交互都能通过 request_id 关联起来并进入可观察状态机**。

## 本章和前后章节的衔接

- s09 解决 **能通信**。
- s10 解决 **通信要有规矩和状态机**。
- s11 再进一步, 解决 **队友如何自己找任务而不是等 lead 派工**。

