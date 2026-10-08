#!/usr/bin/env python3
"""Run the configured target command in its pinned Docker image.

The target source and image are prepared by ``build_target_image.py``. This
runner only starts the target-specific command and mounts the target runtime
workspace, so the same deployment path can be reused for other targets.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def safe_tag(target_name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", target_name).lower().strip("-")
    return value or "target"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--image", help="Docker image; defaults to the build script tag")
    parser.add_argument("--name", help="Optional Docker container name")
    parser.add_argument("--serve", action="store_true", help="Start the configured long-running service")
    args = parser.parse_args()

    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    target = config.get("target")
    if not isinstance(target, dict):
        raise ValueError("config.target must be an object")
    command_key = "serve_command" if args.serve else "run_command"
    if not target.get(command_key):
        raise ValueError(f"config.target.{command_key} is required")

    image = args.image or f"agentfuzz-target:{safe_tag(config['target_name'])}"
    workspace = (ROOT / target.get("workspace", ".workspace")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/amd64",
    ]
    if args.name:
        command.extend(["--name", args.name])
    if args.serve:
        port = target.get("serve_port")
        if not isinstance(port, int) or not 1 <= port <= 65535:
            raise ValueError("config.target.serve_port must be a valid TCP port")
        command.extend(["-p", f"{port}:{port}"])
    command.extend(
        [
            "-v",
            f"{workspace}:/workspace",
            image,
            "bash",
            "-lc",
            target[command_key],
        ],
    )
    print("+", " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
