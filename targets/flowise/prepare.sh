#!/usr/bin/env bash
set -euo pipefail

: "${AGENTFUZZ_TARGET_MODEL_API_KEY:?target model API key is required}"
: "${AGENTFUZZ_TARGET_MODEL_BASE_URL:?target model base URL is required}"
: "${AGENTFUZZ_TARGET_MODEL_NAME:?target model name is required}"

node /opt/target/.agentfuzz/prepare-flowise.mjs
