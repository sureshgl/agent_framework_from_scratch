"""Built-in tools: filesystem, shell, web search.

Each is a *factory* that captures its safety boundary (an allowed root, a command
allowlist, a fixtures table) and returns a `Tool`. Boundaries are enforced in the
tool, so a bad path or command becomes an error result rather than a real effect.
These are demo-grade guards, not production hardening (see spec C-shell).
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from .tools import Tool, tool


def _safe_path(root: Path, path: str) -> Path:
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"path escapes the allowed directory: {path!r}")
    return target


def read_file_tool(root: str | Path) -> Tool:
    root = Path(root).resolve()

    @tool
    def read_file(path: str) -> str:
        """Read a UTF-8 text file from within the allowed directory."""
        return _safe_path(root, path).read_text(encoding="utf-8")

    return read_file


def write_file_tool(root: str | Path) -> Tool:
    root = Path(root).resolve()

    @tool(side_effecting=True)
    def write_file(path: str, content: str) -> str:
        """Write a UTF-8 text file within the allowed directory (creates parents)."""
        target = _safe_path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} characters to {path}"

    return write_file


def shell_tool(allow: list[str], cwd: str | Path, timeout_s: float = 30.0) -> Tool:
    allowed = set(allow)
    cwd = Path(cwd).resolve()

    @tool(side_effecting=True)
    def shell(command: str) -> str:
        """Run an allow-listed, non-interactive command in the working directory."""
        argv = shlex.split(command)
        if not argv:
            raise ValueError("empty command")
        if argv[0] not in allowed:
            raise ValueError(f"command not allow-listed: {argv[0]!r}")
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout_s
        )
        out = proc.stdout
        if proc.stderr:
            out += f"\n[stderr]\n{proc.stderr}"
        if proc.returncode != 0:
            out += f"\n[exit {proc.returncode}]"
        return out.strip()

    return shell


def web_search_tool(fixtures: dict[str, str] | None = None) -> Tool:
    """A deterministic, fixture-backed web search.

    Keeps evals and unit tests offline (NFR-3). The live path would route to the
    provider's server-side web search; that is out of scope for the keyless suite.
    """
    table = fixtures or {}

    @tool
    def web_search(query: str) -> str:
        """Search the web for background on a vendor or entity."""
        q = query.lower()
        hits = [v for k, v in table.items() if k.lower() in q]
        return "\n".join(hits) if hits else "No results."

    return web_search
