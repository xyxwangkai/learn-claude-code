# s03: TodoWrite

`s01 > s02 > [ s03 ] s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> *"An agent without a plan drifts"* -- list the steps first, then execute.
>
> **Harness layer**: Planning -- keeping the model on course without scripting the route.

## Problem

On multi-step tasks, the model loses track. It repeats work, skips steps, or wanders off. Long conversations make this worse -- the system prompt fades as tool results fill the context. A 10-step refactoring might complete steps 1-3, then the model starts improvising because it forgot steps 4-10.

## Solution

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

## How It Works

1. TodoManager stores items with statuses. Only one item can be `in_progress` at a time.

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

2. The `todo` tool goes into the dispatch map like any other tool.

```python
TOOL_HANDLERS = {
    # ...base tools...
    "todo": lambda **kw: TODO.update(kw["items"]),
}
```

3. A nag reminder injects a nudge if the model goes 3+ rounds without calling `todo`.

```python
if rounds_since_todo >= 3 and messages:
    last = messages[-1]
    if last["role"] == "user" and isinstance(last.get("content"), list):
        last["content"].insert(0, {
            "type": "text",
            "text": "<reminder>Update your todos.</reminder>",
        })
```

The "one in_progress at a time" constraint forces sequential focus. The nag reminder creates accountability.

## What Changed From s02

| Component      | Before (s02)     | After (s03)                |
|----------------|------------------|----------------------------|
| Tools          | 4                | 5 (+todo)                  |
| Planning       | None             | TodoManager with statuses  |
| Nag injection  | None             | `<reminder>` after 3 rounds|
| Agent loop     | Simple dispatch  | + rounds_since_todo counter|

## Example Walkthrough

Here is a typical s03 call sequence. The point is not the final prose answer, but that the **model writes todos first, then executes against that plan**.

**User prompt**

```text
Add an example walkthrough for agents/s03_todo_write.py and update the Chinese docs
```

**Expected first step: call `todo`**

```json
{
  "name": "todo",
  "input": {
    "items": [
      {"id": "1", "text": "Read s03 and the current docs", "status": "completed"},
      {"id": "2", "text": "Draft the example walkthrough", "status": "in_progress"},
      {"id": "3", "text": "Write docs/zh/s03-todo-write.md", "status": "pending"}
    ]
  }
}
```

**Then read the target file**

```json
{
  "name": "read_file",
  "input": {
    "path": "docs/zh/s03-todo-write.md",
    "limit": 120
  }
}
```

**Then edit or write the document**

```json
{
  "name": "edit_file",
  "input": {
    "path": "docs/zh/s03-todo-write.md",
    "old_text": "## Try It",
    "new_text": "## Example Walkthrough\n...\n\n## Try It"
  }
}
```

**Finally, mark the plan complete**

```json
{
  "name": "todo",
  "input": {
    "items": [
      {"id": "1", "text": "Read s03 and the current docs", "status": "completed"},
      {"id": "2", "text": "Draft the example walkthrough", "status": "completed"},
      {"id": "3", "text": "Write docs/zh/s03-todo-write.md", "status": "completed"}
    ]
  }
}
```

**What you would see in the terminal**

```text
> todo:
[x] #1: Read s03 and the current docs
[>] #2: Draft the example walkthrough
[ ] #3: Write docs/zh/s03-todo-write.md

(1/3 completed)

> read_file:
# s03: TodoWrite
...

> edit_file:
Edited docs/zh/s03-todo-write.md

> todo:
[x] #1: Read s03 and the current docs
[x] #2: Draft the example walkthrough
[x] #3: Write docs/zh/s03-todo-write.md

(3/3 completed)
```

This captures the core value of s03: **the todo list is not decorative UI for the human; it is explicit execution state that the model maintains through the tool loop.**

## Try It

```sh
cd learn-claude-code
python agents/s03_todo_write.py
```

1. `Refactor the file hello.py: add type hints, docstrings, and a main guard`
2. `Create a Python package with __init__.py, utils.py, and tests/test_utils.py`
3. `Review all Python files and fix any style issues`
