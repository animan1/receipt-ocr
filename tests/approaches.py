"""Load named stage callables and their keyword arguments from a comparison config."""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path


@dataclass(frozen=True)
class Approach:
    name: str
    method: str
    run: Callable[..., object]
    params: dict[str, object]


def load_approaches(config: Path) -> list[Approach]:
    definitions = json.loads(config.read_text(encoding="utf-8"))
    if not isinstance(definitions, list) or len(definitions) < 2:
        raise ValueError("Approach config must list at least two methods.")
    approaches = []
    names = set()
    for definition in definitions:
        name: str = definition["name"]
        method: str = definition["method"]
        params: dict[str, object] = definition.get("params", {})
        if not re.fullmatch(r"[a-z0-9_-]+", name) or name in names:
            raise ValueError(f"Invalid or duplicate approach name: {name!r}")
        module_name, _, function = method.partition(":")
        if not module_name or not function:
            raise ValueError(f"Expected a module:callable for {name!r}.")
        run = getattr(import_module(module_name), function)
        if not callable(run) or not isinstance(params, dict):
            raise TypeError(f"Expected a callable and keyword parameters for {name!r}.")
        approaches.append(Approach(name, method, run, params))
        names.add(name)
    return approaches
