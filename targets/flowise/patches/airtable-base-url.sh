#!/usr/bin/env bash
set -euo pipefail
: "${AGENTFUZZ_TARGET_ROOT:?AGENTFUZZ_TARGET_ROOT is required}"
node - "$AGENTFUZZ_TARGET_ROOT/packages/components/nodes/agents/AirtableAgent/AirtableAgent.ts" <<'NODE'
const fs = require('node:fs')
const file = process.argv[2]
let source = fs.readFileSync(file, 'utf8')
const old = [
  'data = await fetchAirtableData(`https://api.airtable.com/v0/${baseId}/${tableId}`, params, accessToken)',
  'const data = await fetchAirtableData(`https://api.airtable.com/v0/${baseId}/${tableId}`, params, accessToken)'
]
const replacement = 'const airtableBaseUrl = process.env.AGENTFUZZ_AIRTABLE_BASE_URL ?? \'https://api.airtable.com\'\n    '
if (!source.includes(old[0]) || !source.includes(old[1])) throw new Error('Airtable source does not match the expected pinned version')
const rewrittenAll = replacement + 'data = await fetchAirtableData(`${airtableBaseUrl}/v0/${baseId}/${tableId}`, params, accessToken)'
const rewrittenLimit = replacement + 'const data = await fetchAirtableData(`${airtableBaseUrl}/v0/${baseId}/${tableId}`, params, accessToken)'
source = source.replace(old[0], rewrittenAll)
source = source.replace(old[1], rewrittenLimit)
fs.writeFileSync(file, source)
NODE
