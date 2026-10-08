#!/usr/bin/env bash
set -euo pipefail

target_root="${AGENTFUZZ_TARGET_ROOT:?AGENTFUZZ_TARGET_ROOT is required}"
trace_root="${AGENTFUZZ_TRACE_ROOT:?AGENTFUZZ_TRACE_ROOT is required}"
workflow="$target_root/src/agentscope/web/workstation/workflow.py"
config_file="$trace_root/instrumentation.json"

python3 - "$workflow" "$trace_root" "$config_file" <<'PY'
import json
import os
import pathlib
import sys

workflow = pathlib.Path(sys.argv[1])
trace_root = pathlib.Path(sys.argv[2])
config_file = pathlib.Path(sys.argv[3])
if not workflow.is_file():
    raise SystemExit(f"workflow entry point not found: {workflow}")

text = workflow.read_text(encoding="utf-8")
marker = "# AgentFuzz runtime instrumentation"
if marker in text:
    raise SystemExit("workflow entry point is already instrumented")

config = json.loads(config_file.read_text(encoding="utf-8"))
delay = config.get("startup_delay", 40)
rules = trace_root / "rules"
if_rule = rules / "if.json"
if not if_rule.is_file():
    raise SystemExit(f"required CodeQL condition rule not found: {if_rule}")
snippet = f'''{marker}
import os as _agentfuzz_os
import sys as _agentfuzz_sys
_agentfuzz_sys.path.insert(0, {str(trace_root)!r})
_agentfuzz_os.environ.setdefault("AGENTFUZZ_TRACE_STARTUP_DELAY", {str(delay)!r})
import cetracer as _agentfuzz_cetracer
_agentfuzz_cetracer.start_ce_trace(
    conf={str(if_rule)!r},
    enter_input_conf={str(rules / "enter_hook.json")!r},
    oracle_rule_conf={str(rules / "oracle.json")!r},
    log="/tmp/if.log",
    match_log="/tmp/hook.log",
    call_stack_log="/tmp/callstack.log",
    oracle_name="/tmp/oracle.log",
)
'''

anchor = "from agentscope.web.workstation.workflow_dag import build_dag\n"
if anchor not in text:
    raise SystemExit(f"expected import anchor not found in {workflow}")
workflow.write_text(text.replace(anchor, anchor + "\n" + snippet, 1), encoding="utf-8")
PY
