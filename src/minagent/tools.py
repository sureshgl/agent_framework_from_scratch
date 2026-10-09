"""Typed tools.

`@tool` turns a plain Python function into a `Tool` by reading its type hints:
the hints become a pydantic model, and that model yields both the JSON schema
advertised to the model and the validation applied to the model's arguments
before the function runs. Validation and execution errors are surfaced to the
loop, which turns them into error tool results rather than crashing (that policy
lives in `loop.py`, not here).
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints

from pydantic import BaseModel, create_model


class Tool:
    def __init__(
        self,
        func: Callable[..., Any],
        name: str,
        description: str,
        args_model: type[BaseModel],
        side_effecting: bool = False,
    ) -> None:
        self.func = func
        self.name = name
        self.description = description
        self.args_model = args_model
        self.side_effecting = side_effecting

    @property
    def schema(self) -> dict:
        """JSON Schema for the arguments, as advertised to the model."""
        return self.args_model.model_json_schema()

    def spec_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }

    def validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate raw model-supplied arguments. Raises `pydantic.ValidationError`."""
        model = self.args_model.model_validate(raw or {})
        return {name: getattr(model, name) for name in self.args_model.model_fields}

    def call(self, **kwargs: Any) -> Any:
        return self.func(**kwargs)


def tool(
    _func: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    side_effecting: bool = False,
) -> Any:
    """Decorator. Usage: `@tool` or `@tool(side_effecting=True)`.

    Side-effecting tools are, by convention, approval-gated by the policy layer
    (increment 3); the flag is recorded here so that layer can find it.
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
        return Tool(
            func=func,
            name=name or func.__name__,
            description=description or (inspect.getdoc(func) or ""),
            args_model=args_model,
            side_effecting=side_effecting,
        )

    return wrap(_func) if _func is not None else wrap
