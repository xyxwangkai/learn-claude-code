# s03: TodoWrite (待办写入)

`s01 > s02 > [ s03 ] s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> *"没有计划的 agent 走哪算哪"* -- 先列步骤再动手, 完成率翻倍。
>
> **Harness 层**: 规划 -- 让模型不偏航, 但不替它画航线。

## 问题

多步任务中, 模型会丢失进度 -- 重复做过的事、跳步、跑偏。对话越长越严重: 工具结果不断填满上下文, 系统提示的影响力逐渐被稀释。一个 10 步重构可能做完 1-3 步就开始即兴发挥, 因为 4-10 步已经被挤出注意力了。

## 解决方案

```
+--------+      +-------+      +---------+
|  User  | ---> |  LLM  | ---> | Tools   |
| prompt |      |       |      | + todo  |
+--------+      +---+---+      +----+----+
                    ^                |
                    |   tool_result  |
                    +----------------+
                          |
              +-----------+-----------+
              | TodoManager state     |
              | [ ] task A            |
              | [>] task B  <- doing  |
              | [x] task C            |
              +-----------------------+
                          |
              if rounds_since_todo >= 3:
                inject <reminder> into tool_result
```

## 工作原理

1. TodoManager 存储带状态的项目。同一时间只允许一个 `in_progress`。

```python
class TodoManager:
    def update(self, items: list) -> str:
        validated, in_progress_count = [], 0
        for item in items:
            status = item.get("status", "pending")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"id": item["id"], "text": item["text"],
                              "status": status})
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress")
        self.items = validated
        return self.render()
```

2. `todo` 工具和其他工具一样加入 dispatch map。

```python
TOOL_HANDLERS = {
    # ...base tools...
    "todo": lambda **kw: TODO.update(kw["items"]),
}
```

3. nag reminder: 模型连续 3 轮以上不调用 `todo` 时注入提醒。

```python
if rounds_since_todo >= 3 and messages:
    last = messages[-1]
    if last["role"] == "user" and isinstance(last.get("content"), list):
        last["content"].insert(0, {
            "type": "text",
            "text": "<reminder>Update your todos.</reminder>",
        })
```

"同时只能有一个 in_progress" 强制顺序聚焦。nag reminder 制造问责压力 -- 你不更新计划, 系统就追着你问。

## 相对 s02 的变更

| 组件           | 之前 (s02)       | 之后 (s03)                     |
|----------------|------------------|--------------------------------|
| Tools          | 4                | 5 (+todo)                      |
| 规划           | 无               | 带状态的 TodoManager           |
| Nag 注入       | 无               | 3 轮后注入 `<reminder>`        |
| Agent loop     | 简单分发         | + rounds_since_todo 计数器     |

## 调用案例

下面是一条典型的 s03 调用链, 重点不是自然语言回答, 而是 **模型先写 todo, 再按 todo 执行**。

**用户输入**

```text
为 agents/s03_todo_write.py 补一个调用案例，并更新中文文档
```

**模型预期的第一步：先调用 `todo`**

```json
{
  "name": "todo",
  "input": {
    "items": [
      {"id": "1", "text": "阅读 s03 与现有文档", "status": "completed"},
      {"id": "2", "text": "整理调用案例内容", "status": "in_progress"},
      {"id": "3", "text": "写入 docs/zh/s03-todo-write.md", "status": "pending"}
    ]
  }
}
```

**接着读取文件**

```json
{
  "name": "read_file",
  "input": {
    "path": "docs/zh/s03-todo-write.md",
    "limit": 120
  }
}
```

**然后写入或编辑文档**

```json
{
  "name": "edit_file",
  "input": {
    "path": "docs/zh/s03-todo-write.md",
    "old_text": "## 调用案例

这个案例展示 s03 的关键行为：**模型先更新 todo，再按 todo 执行文件操作，最后再次更新 todo 收尾。**

### 用户输入

```text
为 agents/s03_todo_write.py 补一个调用案例，并更新中文文档
```

## 预期工具调用流程

### 第一步：先调用 `todo`
模型先把任务拆成可执行步骤，并标记当前正在做的事项。

```json
{
  "name": "todo",
  "input": {
    "items": [
      {
        "id": "1",
        "text": "阅读 s03 与现有文档",
        "status": "completed"
      },
      {
        "id": "2",
        "text": "整理调用案例内容",
        "status": "in_progress"
      },
      {
        "id": "3",
        "text": "写入 docs/zh/s03-todo-write.md",
        "status": "pending"
      }
    ]
  }
}
```

这里体现了 s03 的核心原则：
- todo 不是装饰
- agent 要显式维护执行状态
- 同一时间只保留一个 `in_progress`

### 第二步：读取目标文档
确认文档当前位置，找到适合插入案例的段落。

```json
{
  "name": "read_file",
  "input": {
    "path": "docs/zh/s03-todo-write.md",
    "limit": 120
  }
}
```

### 第三步：编辑文档
把“调用案例”写进中文文档中。

```json
{
  "name": "edit_file",
  "input": {
    "path": "docs/zh/s03-todo-write.md",
    "old_text": "## 试一试",
    "new_text": "## 调用案例\n...\n\n## 试一试"
  }
}
```

### 第四步：完成后更新 `todo`
任务完成后，把所有事项标记为 `completed`。

```json
{
  "name": "todo",
  "input": {
    "items": [
      {
        "id": "1",
        "text": "阅读 s03 与现有文档",
        "status": "completed"
      },
      {
        "id": "2",
        "text": "整理调用案例内容",
        "status": "completed"
      },
      {
        "id": "3",
        "text": "写入 docs/zh/s03-todo-write.md",
        "status": "completed"
      }
    ]
  }
}
```

## 终端中的典型输出

```text
> todo:
[x] #1: 阅读 s03 与现有文档
[>] #2: 整理调用案例内容
[ ] #3: 写入 docs/zh/s03-todo-write.md

(1/3 completed)

> read_file:
# s03: TodoWrite (待办写入)
...

> edit_file:
Edited docs/zh/s03-todo-write.md

> todo:
[x] #1: 阅读 s03 与现有文档
[x] #2: 整理调用案例内容
[x] #3: 写入 docs/zh/s03-todo-write.md

(3/3 completed)
```

## 这个案例说明了什么

这个调用链体现了 s03 的几个重点：

- **先计划，再执行**
- **todo 是工具链的一部分，不是回答里的附属说明**
- **模型通过 todo 显式维护自己的执行状态**
- **用户可以直接看到当前进度，而不是猜它做到哪一步了**

一句话总结：

> s03 的 todo 机制，让 agent 在多步任务里具备“可见的执行状态”。

## 试一试",
    "new_text": "## 调用案例\n...\n\n## 试一试"
  }
}
```

**完成后更新 todo**

```json
{
  "name": "todo",
  "input": {
    "items": [
      {"id": "1", "text": "阅读 s03 与现有文档", "status": "completed"},
      {"id": "2", "text": "整理调用案例内容", "status": "completed"},
      {"id": "3", "text": "写入 docs/zh/s03-todo-write.md", "status": "completed"}
    ]
  }
}
```

**你在终端里会看到类似输出**

```text
> todo:
[x] #1: 阅读 s03 与现有文档
[>] #2: 整理调用案例内容
[ ] #3: 写入 docs/zh/s03-todo-write.md

(1/3 completed)

> read_file:
# s03: TodoWrite (待办写入)
...

> edit_file:
Edited docs/zh/s03-todo-write.md

> todo:
[x] #1: 阅读 s03 与现有文档
[x] #2: 整理调用案例内容
[x] #3: 写入 docs/zh/s03-todo-write.md

(3/3 completed)
```

这个例子说明 s03 的关键价值：**todo 不是给人看的装饰，而是模型在工具调用链里显式维护自己的执行状态。**

## 试一试

```sh
cd learn-claude-code
python agents/s03_todo_write.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Refactor the file hello.py: add type hints, docstrings, and a main guard`
2. `Create a Python package with __init__.py, utils.py, and tests/test_utils.py`
3. `Review all Python files and fix any style issues`
