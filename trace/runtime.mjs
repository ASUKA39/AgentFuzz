import { appendFileSync, writeFileSync } from 'node:fs'
import { AsyncLocalStorage } from 'node:async_hooks'

const context = new AsyncLocalStorage()
let configured = false
let files = { hook: '/tmp/hook.log', if: '/tmp/if.log', callstack: '/tmp/callstack.log', oracle: '/tmp/oracle.log' }
function emit(event) {
  const enriched = { ...event, chain: context.getStore() ?? [] }
  const file = event.type === 'if' ? files.if : (event.type === 'oracle' || event.type === 'sink' ? files.oracle : files.hook)
  appendFileSync(file, JSON.stringify(enriched) + '\n')
  appendFileSync(files.callstack, (context.getStore() ?? []).join(' -> ') + '\n')
  if (event.type === 'function_enter' && event.function) {
    appendFileSync(files.hook, `match: ${event.file ?? ''}: ${event.function}\n`)
  }
  if (event.type === 'if') {
    appendFileSync(files.hook, `match: ${event.file ?? ''}:L${event.line}, ${event.function ?? ''}\n`)
    appendFileSync(files.hook, `${event.value ?? ''}\n{}\n`)
  }
  if (event.type === 'oracle' || event.type === 'sink') {
    appendFileSync(files.oracle, '<=======================>\n')
    appendFileSync(files.oracle, `${event.value ?? ''}\n`)
    appendFileSync(files.oracle, `${event.sink}@${event.file}:${event.line}\n`)
  }
}
export function startTrace(options = {}) {
  files = { ...files, ...options }
  for (const file of Object.values(files)) writeFileSync(file, '')
  configured = true
}
export function enter(functionName, file, line, column) {
  if (!configured) startTrace()
  const chain = [...(context.getStore() ?? []), functionName]
  context.enterWith(chain)
  emit({ type: 'function_enter', function: functionName, file, line, column })
}
export function exit(functionName, file, line, column) {
  if (!configured) return
  emit({ type: 'function_exit', function: functionName, file, line, column })
  const chain = [...(context.getStore() ?? [])]
  if (chain.at(-1) === functionName) chain.pop()
  context.enterWith(chain)
}
export function branch(expression, file, line, column) { if (configured) emit({ type: 'if', value: expression, file, line, column }) }
export function oracle(sink, file, line, column, value) { if (configured) emit({ type: 'oracle', sink, file, line, column, value }) }
export function runWithContext(chain, callback) { return context.run(chain, callback) }
if (process.env.AGENTFUZZ_TRACE === '1') startTrace()
globalThis.__agentfuzz = { startTrace, enter, exit, branch, oracle, runWithContext }
