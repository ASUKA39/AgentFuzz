"""Language-neutral Python bridge to the TypeScript expression solver.

AgentFuzz's mutation and scheduling flow remains in ``fuzzer.py``. The
language-specific parser and solver live in ``ts/solve-z3.mjs`` and are
invoked through this deliberately small process boundary.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def infer_variable_types(expression: str) -> dict[str, str] | None:
    # This is only used to identify values to replace in the existing Prompt
    # mutation flow. Semantic parsing is performed by TypeScript's compiler
    # API in solve-z3.mjs.
    if not isinstance(expression, str) or not expression.strip():
        return None
    if re.search(r"\b(isinstance|lambda|yield)\b", expression):
        return None
    # Keep only free identifiers. String/template literals and property names
    # are syntax, not values that the existing Prompt replacement flow should
    # attempt to substitute.
    without_literals = re.sub(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", " ", expression)
    names = re.findall(r"(?<![.$])\b[A-Za-z_$][\w$]*\b", without_literals)
    keywords = {
        "true", "false", "null", "undefined", "this", "typeof", "instanceof",
        "includes", "indexOf", "lastIndexOf", "length",
    }
    return {name: "Bool" if name in {"true", "false"} else "String" for name in dict.fromkeys(names) if name not in keywords}


def get_z3_result(expression: str, timeout_ms: int = 5000) -> dict[str, str]:
    try:
        result = subprocess.run(
            ["node", str(ROOT / "ts" / "solve-z3.mjs"), expression],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
            check=False,
        )
        if result.returncode != 0:
            return {}
        parsed = json.loads(result.stdout.strip() or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}
