#!/usr/bin/env python3
"""Run the configured AgentFuzz reproduction from preparation to cleanup.

The only target-specific code is the Dockerfile, instrumentation script, and
POC adapter named by ``config.json``.  The runner retains all generated
artifacts under ``.workspace`` and always removes the temporary target
container.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from build_target_image import ROOT, safe_tag


def run(command: list[str], *, env: dict[str, str] | None = None, check: bool = True) -> int:
    print("+", " ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if check and completed.returncode:
        raise subprocess.CalledProcessError(completed.returncode, command)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--duration", type=int, default=900, help="fuzzing wall-clock limit in seconds")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--skip-analysis", action="store_true")
    parser.add_argument("--skip-baseline", action="store_true")
    args = parser.parse_args()

    config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
    target = config.get("target")
    agent = config.get("agentfuzz")
    if not isinstance(target, dict) or not isinstance(agent, dict):
        raise ValueError("config.target and config.agentfuzz must be objects")
    app = agent.get("application_name")
    container = target.get("container_name") or agent.get("container_name")
    if not app or not container:
        raise ValueError("target.container_name and agentfuzz.application_name are required")

    workspace = (ROOT / target.get("workspace", ".workspace/target-workspace")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    image = f"agentfuzz-target:{safe_tag(config['target_name'])}"
    python_bin = ROOT / ".workspace" / "agentfuzz-venv" / "bin" / "python"
    if not python_bin.is_file():
        python_bin = Path(sys.executable)
    artifact = ROOT / ".workspace" / "fuzz-results" / safe_tag(config["target_name"])
    artifact.mkdir(parents=True, exist_ok=True)
    log_paths = {
        "hook": Path("/tmp/hook.log"),
        "if": Path("/tmp/if.log"),
        "callstack": Path("/tmp/callstack.log"),
        "oracle": Path("/tmp/oracle.log"),
    }
    for path in log_paths.values():
        path.write_text("", encoding="utf-8")

    container_started = False
    result = {"target_name": config["target_name"], "application": app, "image": image,
              "duration": args.duration, "iterations": args.iterations, "started_at": time.time()}
    try:
        # Make reruns safe after an interrupted invocation.  The name comes
        # from the target configuration and is never expanded as a shell
        # expression.
        run(["docker", "container", "rm", "--force", str(container)], check=False)
        if not args.skip_analysis:
            run([str(python_bin), "scripts/analyze_target.py", "--config", str(args.config.resolve())])
        run([str(python_bin), "scripts/build_target_image.py", "--config", str(args.config.resolve())])

        if not args.skip_baseline:
            baseline_log = artifact / "baseline.log"
            with baseline_log.open("w", encoding="utf-8") as handle:
                print("+ baseline target run")
                completed = subprocess.run(
                    [str(python_bin), "scripts/run_target.py", "--config", str(args.config.resolve())],
                    cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, check=False,
                )
            if completed.returncode:
                raise subprocess.CalledProcessError(completed.returncode, ["run_target.py"])

        run([
            "docker", "run", "-d", "--name", container, "--platform", "linux/amd64",
            "-v", f"{workspace}:/workspace", image, "tail", "-f", "/dev/null",
        ])
        container_started = True
        payload = agent.get("poc_test_payload")
        poc_spec = agent.get("poc", "")
        module_name, separator, function_name = poc_spec.partition(":")
        if not isinstance(payload, str) or not separator:
            raise ValueError("agentfuzz.poc_test_payload and agentfuzz.poc are required")
        poc_log = artifact / "poc-test.log"
        poc_code = (
            "import importlib; "
            f"getattr(importlib.import_module({module_name!r}), {function_name!r})({payload!r})"
        )
        poc_env = os.environ.copy()
        poc_env["AGENTFUZZ_TARGET_CONTAINER"] = str(container)
        with poc_log.open("w", encoding="utf-8") as handle:
            completed = subprocess.run(
                [str(python_bin), "-c", poc_code], cwd=ROOT, env=poc_env,
                stdout=handle, stderr=subprocess.STDOUT, check=False,
            )
        if completed.returncode:
            raise subprocess.CalledProcessError(completed.returncode, ["poc-test"])
        fuzz_env = os.environ.copy()
        fuzz_env["AGENTFUZZ_FUZZ_TIMEOUT"] = str(args.duration)
        fuzz_env["AGENTFUZZ_TARGET_CONTAINER"] = str(container)
        fuzz_log = artifact / "agentfuzz.log"
        with fuzz_log.open("w", encoding="utf-8") as handle:
            print("+ AgentFuzz fuzzing", flush=True)
            completed = subprocess.run(
                [str(python_bin), "main.py", "-i", str(args.iterations), "-app", str(app)],
                cwd=ROOT, env=fuzz_env, stdout=handle, stderr=subprocess.STDOUT,
                check=False,
            )
        result["fuzz_exit_code"] = completed.returncode
    except Exception as exc:
        result["error"] = repr(exc)
        raise
    finally:
        runtime = artifact / "runtime-logs"
        runtime.mkdir(parents=True, exist_ok=True)
        for name, source in log_paths.items():
            if source.exists():
                shutil.copy2(source, runtime / f"{name}.log")
        if container_started:
            run(["docker", "container", "rm", "--force", str(container)], check=False)
        result["finished_at"] = time.time()
        (artifact / "manifest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    return int(result.get("fuzz_exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
