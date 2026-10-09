"""Bridge AgentFuzz's legacy DSC call to the TypeScript AST implementation."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def solve_dsc(rules: list, payload: str) -> str:
    """Apply supported TypeScript string constraints to ``payload``.

    The public function and call sites remain unchanged. Parsing and semantic
    handling live in ``ts/solve-dsc.mjs`` so Python syntax is never assumed.
    Unsupported constraints are deliberately left untouched.
    """
    if not isinstance(payload, str) or not isinstance(rules, list) or not rules:
        return payload
    request = json.dumps({"rules": rules, "payload": payload})
    try:
        result = subprocess.run(
            ["node", str(ROOT / "ts" / "solve-dsc.mjs"), request],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return payload
        value = json.loads(result.stdout)
        return value if isinstance(value, str) else payload
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return payload
