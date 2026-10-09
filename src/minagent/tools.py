"""Typed tools.

A `Tool` is a name, a JSON schema for its arguments, a validator, and a callable.
`@tool` builds one from a plain function by reading its type hints: the hints
become a pydantic model that yields both the advertised schema and the validation
applied to model-supplied arguments before the function runs. Tools from other
sources (an MCP server, a sub-agent) construct a `Tool` directly with an explicit
schema. Validation and execution errors are surfaced to the loop, which turns
them into error tool results rather than crashing.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints

from pydantic import create_model


class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        schema: dict,
        caller: Callable[..., Any],
        validator: Callable[[dict], dict] | None = None,
        side_effecting: bool = False,
    ) -> None:
        self.name = name
        self.description = description
        self._schema = schema
        self._caller = caller
        # Default validator is a passthrough (e.g. MCP tools validate server-side).
        self._validator = validator or (lambda raw: dict(raw or {}))
        self.side_effecting = side_effecting

    @property
    def schema(self) -> dict:
        return self._schema

    def spec_dict(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self._schema}

    def validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate raw model-supplied arguments. May raise `pydantic.ValidationError`."""
        return self._validator(raw or {})

    def call(self, **kwargs: Any) -> Any:
        return self._caller(**kwargs)


def tool(
    _func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    side_effecting: bool = False,
) -> Any:
    """Decorator. Usage: `@tool` or `@tool(side_effecting=True)`.

    Side-effecting tools are, by convention, approval-gated by the policy layer;
    the flag is recorded here so that layer can find it.
    """

    def wrap(func: Callable[..., Any]) -> Tool:
        hints = get_type_hints(func)
        sig = inspect.signature(func)
        fields: dict[str, tuple[Any, Any]] = {}
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            annotation = hints.get(pname, Any)
            default = ... if param.default is inspect.Parameter.empty else param.default
            fields[pname] = (annotation, default)
        args_model = create_model(f"{func.__name__}_Args", **fields)  # type: ignore[call-overload]

        def validator(raw: dict, _model=args_model) -> dict:
            model = _model.model_validate(raw or {})
            return {n: getattr(model, n) for n in _model.model_fields}

        t = Tool(
            name=name or func.__name__,
            description=description or (inspect.getdoc(func) or ""),
            schema=args_model.model_json_schema(),
            caller=func,
            validator=validator,
            side_effecting=side_effecting,
        )
        t.args_model = args_model  # type: ignore[attr-defined]  # kept for introspection
        return t

    return wrap(_func) if _func is not None else wrap
