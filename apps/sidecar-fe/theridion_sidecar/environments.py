"""Environment storage + {{var}} substitution.

Environments live alongside collections under ``$THERIDION_HOME``::

    $THERIDION_HOME/
    └── environments/
        ├── <env-uuid>.json
        └── <env-uuid>.json

Each environment is a flat list of name/value pairs. Substitution looks
for the ``{{name}}`` token (alphanumeric + underscore + dash, optional
whitespace inside the braces) and replaces with the value, or leaves the
token in place if the variable isn't defined.

Built-in template functions start with ``$``: ``{{$timestamp}}``,
``{{$uuid}}``, ``{{$isoDate}}``, ``{{$randomInt}}``.
"""

from __future__ import annotations

import json
import os
import random
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .storage import home_dir


# Allow {{ name }} or {{name}}; identifiers match what users typically pick.
# Also matches $-prefixed built-in functions like {{$uuid}}.
_VAR_PATTERN = re.compile(r"\{\{\s*(\$?[A-Za-z_][A-Za-z0-9_-]*)\s*\}\}")


def _builtin(name: str) -> str | None:
    """Evaluate a built-in $-function. Returns None if unknown."""
    if name == "$timestamp":
        return str(int(datetime.now(tz=timezone.utc).timestamp() * 1000))
    if name == "$isoDate":
        return datetime.now(tz=timezone.utc).isoformat()
    if name == "$uuid":
        return str(uuid.uuid4())
    if name == "$randomInt":
        return str(random.randint(0, 1_000_000))
    return None


class EnvVariable(BaseModel):
    name: str
    value: str
    enabled: bool = True


class Environment(BaseModel):
    id: str
    name: str
    variables: list[EnvVariable] = Field(default_factory=list)


class EnvironmentSummary(BaseModel):
    id: str
    name: str
    variable_count: int


def envs_dir() -> Path:
    d = home_dir() / "environments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(env_id: str) -> Path:
    safe = uuid.UUID(env_id)
    return envs_dir() / f"{safe}.json"


def list_summaries() -> list[EnvironmentSummary]:
    out: list[EnvironmentSummary] = []
    for p in sorted(envs_dir().glob("*.json")):
        try:
            data = json.loads(p.read_text())
            env = Environment(**data)
        except Exception:
            continue
        out.append(
            EnvironmentSummary(
                id=env.id,
                name=env.name,
                variable_count=len(env.variables),
            )
        )
    return out


def get(env_id: str) -> Environment | None:
    p = _path_for(env_id)
    if not p.exists():
        return None
    return Environment(**json.loads(p.read_text()))


def create(name: str) -> Environment:
    env = Environment(id=str(uuid.uuid4()), name=name, variables=[])
    _atomic_write(env)
    return env


def replace_variables(env_id: str, variables: list[EnvVariable]) -> Environment:
    env = get(env_id)
    if env is None:
        raise FileNotFoundError(f"environment {env_id} not found")
    env.variables = list(variables)
    _atomic_write(env)
    return env


def rename(env_id: str, name: str) -> Environment:
    env = get(env_id)
    if env is None:
        raise FileNotFoundError(f"environment {env_id} not found")
    env.name = name
    _atomic_write(env)
    return env


def delete(env_id: str) -> bool:
    p = _path_for(env_id)
    if not p.exists():
        return False
    p.unlink()
    return True


def substitute(
    text: str,
    env: Environment | None,
    extra: dict[str, str] | None = None,
    collection_vars: dict[str, str] | None = None,
) -> str:
    """Replace every ``{{var}}`` in ``text`` with the matching enabled
    variable's value or built-in function result.

    Resolution order (later wins):
    globals -> collection_vars -> env -> extra (runtime) -> built-in.

    Unknown vars are left as-is.
    """
    from . import globals as global_store

    lookup: dict[str, str] = global_store.as_dict()
    if collection_vars:
        lookup.update(collection_vars)
    if env:
        lookup.update({v.name: v.value for v in env.variables if v.enabled})
    if extra:
        lookup.update(extra)

    def _sub(m: re.Match[str]) -> str:
        name = m.group(1)
        if name.startswith("$"):
            result = _builtin(name)
            if result is not None:
                return result
        return lookup.get(name, m.group(0))

    return _VAR_PATTERN.sub(_sub, text)


def substitute_dict(
    d: dict[str, str],
    env: Environment | None,
    collection_vars: dict[str, str] | None = None,
) -> dict[str, str]:
    return {k: substitute(v, env, collection_vars=collection_vars) for k, v in d.items()}


def _atomic_write(env: Environment) -> None:
    p = _path_for(env.id)
    payload: dict[str, Any] = env.model_dump(mode="json")
    fd, tmp_str = tempfile.mkstemp(
        prefix=f"{env.id}.", suffix=".json.tmp", dir=str(p.parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise
