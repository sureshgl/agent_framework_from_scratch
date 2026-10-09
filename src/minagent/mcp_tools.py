"""Mount an MCP server's tools as `minagent` tools.

An MCP server is just another tool *source*: the drive loop, policy, and event
log never learn that a tool came from MCP. The MCP Python client is async and the
framework is synchronous, so the session runs on a dedicated event loop in a
background thread; each sync `call()` hands a coroutine to that loop and waits.

Only stdio transport is in scope (spec non-goal: remote/SSE). A failing MCP call
raises, so the loop records it as an error tool result like any other.
"""

from __future__ import annotations

import asyncio
import json
import threading
from contextlib import AsyncExitStack
from typing import Any, Iterable

from .tools import Tool


def _result_text(result: Any) -> str:
    parts: list[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
    if parts:
        return "\n".join(parts)
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return json.dumps(structured)
    return ""


class MCPToolset:
    """Connect to a stdio MCP server and expose its tools.

    Use as a context manager so the server subprocess is always torn down::

        with MCPToolset([sys.executable, "-m", "pkg.server"], namespace="erp",
                        side_effecting={"post_invoice"}) as erp:
            agent = Agent(..., tools=erp.tools())
    """

    def __init__(
        self,
        command: list[str],
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        namespace: str | None = None,
        side_effecting: Iterable[str] = (),
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.env = env
        self.namespace = namespace
        self.side_effecting = set(side_effecting)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stack: AsyncExitStack | None = None
        self._session: Any = None
        self._specs: list[Any] = []

    # -- lifecycle -----------------------------------------------------------

    def __enter__(self) -> "MCPToolset":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._run(self._connect())

    def close(self) -> None:
        if self._loop is None:
            return
        if self._stack is not None:
            try:
                self._run(self._stack.aclose())
            except Exception:
                pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop.close()
        self._loop = None

    def _run(self, coro: Any) -> Any:
        assert self._loop is not None
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    async def _connect(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._stack = AsyncExitStack()
        params = StdioServerParameters(
            command=self.command[0], args=self.command[1:], cwd=self.cwd, env=self.env
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        self._specs = (await self._session.list_tools()).tools

    async def _call(self, name: str, args: dict) -> str:
        result = await self._session.call_tool(name, args)
        text = _result_text(result)
        if getattr(result, "is_error", False):
            raise RuntimeError(text or f"MCP tool {name!r} reported an error")
        return text

    # -- tools ---------------------------------------------------------------

    def tools(self) -> list[Tool]:
        return [self._wrap(spec) for spec in self._specs]

    def _wrap(self, spec: Any) -> Tool:
        remote_name = spec.name
        # Namespace with "__" (not "."): tool names exposed to the model must
        # match ^[a-zA-Z0-9_-]{1,128}$, which excludes dots.
        display = f"{self.namespace}__{remote_name}" if self.namespace else remote_name
        schema = spec.input_schema or {"type": "object", "properties": {}}

        def caller(**kwargs: Any) -> str:
            return self._run(self._call(remote_name, kwargs))

        return Tool(
            name=display,
            description=spec.description or "",
            schema=schema,
            caller=caller,
            side_effecting=remote_name in self.side_effecting,
        )
