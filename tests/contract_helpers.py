"""What the contract's tests share: store.yaml itself, and checking a value against one of its schemas.

`check(schema, value)` checks a JSON value both ways a consumer might: against the schema itself with jsonschema
(which the tests skip without; this repository's CI has it), and with the schema's Pydantic model in
countdown_api.models, as it would arrive from Redis (its JSON).
"""

import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import TypeAdapter

from countdown_api import models

ROOT = Path(__file__).resolve().parents[1]


@cache
def contract() -> dict[str, Any]:
    """Return store.yaml, parsed."""
    return yaml.safe_load((ROOT / "store.yaml").read_text(encoding="utf-8"))


def check_schema(name: str, value: Any) -> None:  # noqa: ANN401 -- any JSON
    """Fail unless `value` is what the schema `name` allows, by jsonschema; skip without jsonschema."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = {"$defs": contract()["$defs"], "$ref": f"#/$defs/{name}"}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(value)


def check_schema_property(name: str, field: str, value: Any) -> None:  # noqa: ANN401 -- any JSON
    """Fail unless `value` is what the schema `name` allows for its property `field`; skip without jsonschema.

    For a hash's text fields beside one that isn't JSON (FrameRecord's frame).
    """
    jsonschema = pytest.importorskip("jsonschema")
    schema = {"$defs": contract()["$defs"], **contract()["$defs"][name]["properties"][field]}
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(value)


def check_model(name: str, value: Any) -> Any:  # noqa: ANN401 -- any JSON, and whatever its model makes of it
    """Return `value` read with the schema `name`'s model, from its JSON, as a consumer reads it from Redis."""
    return TypeAdapter(getattr(models, name)).validate_json(json.dumps(value))


def check(name: str, value: Any) -> Any:  # noqa: ANN401 -- any JSON
    """Fail unless `value` is what the schema `name` allows, both ways; return what its model makes of it."""
    check_schema(name, value)
    return check_model(name, value)
