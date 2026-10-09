#!/usr/bin/env bash
set -euo pipefail

: "${AGENTFUZZ_TARGET_ROOT:?AGENTFUZZ_TARGET_ROOT is required}"
: "${AGENTFUZZ_TRACE_ROOT:?AGENTFUZZ_TRACE_ROOT is required}"

# TypeScript probes are inserted before the target build.  The transform is
# generic and uses only the target root plus the existing AgentFuzz runtime.
test -f "${AGENTFUZZ_TRACE_ROOT}/runtime.mjs"
test -f "${AGENTFUZZ_TRACE_ROOT}/instrument.mjs"
test -d "${AGENTFUZZ_TRACE_ROOT}/rules"
node "${AGENTFUZZ_TRACE_ROOT}/instrument.mjs" "${AGENTFUZZ_TARGET_ROOT}"
