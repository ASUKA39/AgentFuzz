"""AgentScope v0.0.4 input adapter for AgentFuzz.

The v0.0.4 target does not expose the later Studio Workstation/Dashboard
browser UI. Its workflow entry point is the ``as_workflow`` command, so a
payload is submitted by writing a workflow JSON file and executing that
command in the already-running target container.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / ".workspace" / "agentscope-workflow" / "rce.json"
DEFAULT_WORKFLOW = ROOT / ".workspace" / "agentscope-workflow" / "agentfuzz-current.json"


def _set_dot_path(document: dict[str, Any], path: str, value: str) -> None:
    """Set a string value at a dotted JSON path."""
    parts = path.split(".")
    current: Any = document
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    last = parts[-1]
    if isinstance(current, list):
        current[int(last)] = value
    else:
        current[last] = value


def _workflow_for_payload(payload: str) -> tuple[Path, str]:
    template = Path(os.environ.get("AGENTFUZZ_WORKFLOW_TEMPLATE", str(DEFAULT_TEMPLATE)))
    output = Path(os.environ.get("AGENTFUZZ_WORKFLOW_FILE", str(DEFAULT_WORKFLOW)))
    payload_path = os.environ.get("AGENTFUZZ_PAYLOAD_PATH", "1.data.args.name")
    if not template.is_file():
        raise FileNotFoundError(f"AgentScope workflow template not found: {template}")

    document = json.loads(template.read_text(encoding="utf-8"))
    _set_dot_path(document, payload_path, payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return output, payload_path


def connect_with_auth(payload: str) -> None:
    """Submit one AgentFuzz payload to an AgentScope v0.0.4 container.

    The target container must already be running. AgentFuzz's tracer and
    generated rule files are installed in that same container in the later
    instrumentation step; this adapter only submits the target input and
    waits for the configured workflow command to finish.
    """
    container = os.environ.get("AGENTFUZZ_TARGET_CONTAINER", "agentfuzz-agentscope")
    container_workflow = os.environ.get(
        "AGENTFUZZ_CONTAINER_WORKFLOW_FILE", "/workspace/agentfuzz-current.json",
    )
    workflow, payload_path = _workflow_for_payload(payload)
    command = os.environ.get("AGENTFUZZ_TARGET_COMMAND", "as_workflow")
    timeout = int(os.environ.get("AGENTFUZZ_TARGET_TIMEOUT", "300"))

    # The standard runner mounts the host workspace at /workspace. Requiring
    # that mount keeps the adapter independent of a host-specific docker cp
    # path and makes generated inputs inspectable after a run.
    check = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode != 0 or check.stdout.strip().lower() != "true":
        raise RuntimeError(
            f"AgentScope target container {container!r} is not running; "
            "start it before running AgentFuzz",
        )

    command_line = f"{command} {shlex.quote(container_workflow)}"
    print(f"[*] AgentScope payload path: {payload_path}")
    print(f"[*] AgentScope workflow: {container_workflow}")
    subprocess.run(
        ["docker", "exec", container, "bash", "-lc", command_line],
        check=True,
        timeout=timeout,
    )

