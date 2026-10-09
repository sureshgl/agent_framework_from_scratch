"""Structured output.

When an agent declares an `output_schema`, the final answer must validate against
it. The schema is given to the model as guidance, but validation is enforced here
with pydantic once the model stops requesting tools. On failure the loop feeds the
validation error back to the model and lets it try again (bounded by
`max_output_retries`); the runtime never returns an unvalidated result.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ValidationError


def schema_instructions(schema: type[BaseModel]) -> str:
    pretty = json.dumps(schema.model_json_schema(), indent=2)
    return (
        "When you are ready to give your final answer, respond with ONLY a JSON "
        "value that matches this JSON Schema — no prose, no code fences:\n" + pretty
    )


def extract_json(text: str) -> str:
    """Best-effort extraction of a JSON value from model text (handles prose and
    ```json fences)."""
    s = text.strip()
    if "```" in s:
        for part in s.split("```"):
            p = part.strip()
            if p.startswith("json"):
                p = p[4:].strip()
            if p.startswith("{") or p.startswith("["):
                return p
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        return s[start : end + 1]
    start, end = s.find("["), s.rfind("]")
    if start != -1 and end > start:
        return s[start : end + 1]
    return s


def validate_output(schema: type[BaseModel], text: str) -> tuple[Any | None, str | None]:
    """Return (validated_object, None) on success, or (None, error_message)."""
    try:
        obj = schema.model_validate_json(extract_json(text))
    except ValidationError as e:
        return None, str(e)
    return obj, None
