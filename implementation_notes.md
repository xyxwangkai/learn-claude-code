# Implementation Notes

## Workspace overview
- Repository: `learn-claude-code`
- Purpose: a learning project about agent harness engineering, progressing from a minimal agent loop to task systems, background work, teams, autonomous claiming, and worktree isolation.
- Primary languages and stacks:
  - Python reference implementations under `agents/`
  - Markdown documentation under `docs/`
  - Next.js web app under `web/`

## Top-level structure
- `agents/`: session-based Python examples (`s01` through `s12`) plus related implementations.
- `docs/`: English, Chinese, and Japanese documentation.
- `skills/`: skill files used for on-demand loading examples.
- `tests/`: test files for the repository.
- `web/`: interactive web platform with frontend assets and source.
- `mcp_server/`: MCP-related server code.
- `.tasks/`: local task board state stored as JSON files.
- `.team/`: team coordination data such as inboxes.

## Current notable files
- `README.md`: main project overview, learning path, architecture, and setup instructions.
- `requirements.txt`: Python dependencies.
- `.env.example`: environment variable template.
- `background_test.txt`: small workspace file present at repo root.

## Repository themes from README
- Core idea: agency comes from the model; the harness provides tools, context, permissions, and interfaces.
- Teaching progression:
  - simple agent loop
  - tool dispatch
  - planning
  - subagents
  - skill loading
  - context compression
  - task graph persistence
  - background execution
  - team mailboxes/protocols
  - autonomous task claiming
  - worktree isolation

## Directory snapshot
- Root contains code, docs, tests, and a web app.
- `docs/` has `en/`, `zh/`, and `ja/` subdirectories.
- `web/` contains `public/`, `scripts/`, `src/`, plus build/dependency directories.
- `agents/` contains multiple session scripts and supporting files.

## Notes for collaborators
- Task board data appears file-based in `.tasks/`.
- Team communication artifacts appear under `.team/`.
- This notes file is a lightweight orientation summary for the current workspace.
