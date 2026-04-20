#!/usr/bin/env python3
"""A simple MCP server for the learn-claude-code workspace."""

from __future__ import annotations

import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

WORKDIR = Path(__file__).resolve().parent.parent
mcp = FastMCP("learn-claude-code")


def safe_path(path: str) -> Path:
    target = (WORKDIR / path).resolve()
    if not target.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path}")
    return target


@mcp.tool()
def hello(name: str) -> str:
    """Say hello to someone.

    Args:
        name: The name to greet.
    """
    return f"Hello, {name}!"


@mcp.tool()
def read_file(path: str, limit: int = 200) -> str:
    """Read a text file from the workspace.

    Args:
        path: Relative path inside the workspace.
        limit: Maximum number of lines to return.
    """
    file_path = safe_path(path)
    lines = file_path.read_text().splitlines()
    if limit and limit < len(lines):
        lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
    return "\n".join(lines)


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write text content to a file in the workspace.

    Args:
        path: Relative path inside the workspace.
        content: File content to write.
    """
    file_path = safe_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content)
    return f"Wrote {len(content)} bytes to {path}"


@mcp.tool()
def run_bash(command: str, timeout: int = 30) -> str:
    """Run a shell command inside the workspace.

    Args:
        command: Shell command to execute.
        timeout: Timeout in seconds.
    """
    blocked = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(token in command for token in blocked):
        raise ValueError("Dangerous command blocked")

    completed = subprocess.run(
        command,
        shell=True,
        cwd=WORKDIR,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = (completed.stdout + completed.stderr).strip()
    return output or "(no output)"


@mcp.resource("workspace://readme")
def workspace_readme() -> str:
    """Return the project README."""
    return (WORKDIR / "README.md").read_text()


if __name__ == "__main__":
    mcp.run()
