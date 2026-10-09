import { appendFileSync, writeFileSync } from 'node:fs'
import { AsyncLocalStorage } from 'node:async_hooks'

export type TraceEvent = {
    type: 'function_enter' | 'function_exit' | 'if' | 'sink' | 'oracle'
    file?: string
    line?: number
    column?: number
    function?: string
    sink?: string
    value?: string
    chain?: string[]
}

const context = new AsyncLocalStorage<string[]>()
let configured = false
let files = { hook: '/tmp/hook.log', if: '/tmp/if.log', callstack: '/tmp/callstack.log', oracle: '/tmp/oracle.log' }

function emit(event: TraceEvent): void {
    const chain = context.getStore() ?? []
    const enriched = { ...event, chain }
    if (event.type === 'if') appendFileSync(files.if, JSON.stringify(enriched) + '\n')
    else if (event.type === 'oracle' || event.type === 'sink') appendFileSync(files.oracle, JSON.stringify(enriched) + '\n')
    else appendFileSync(files.hook, JSON.stringify(enriched) + '\n')
    appendFileSync(files.callstack, chain.join(' -> ') + '\n')
    if (event.type === 'function_enter' && event.function)
        appendFileSync(files.hook, `match: ${event.file ?? ''}: ${event.function}\n`)
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

export function startTrace(options: Partial<typeof files> = {}): void {
    files = { ...files, ...options }
    for (const file of Object.values(files)) writeFileSync(file, '')
    configured = true
}

export function enter(functionName: string, file?: string, line?: number, column?: number): void {
    if (!configured) startTrace()
    const chain = [...(context.getStore() ?? []), functionName]
    context.enterWith(chain)
    emit({ type: 'function_enter', function: functionName, file, line, column })
}

export function exit(functionName: string, file?: string, line?: number, column?: number): void {
    if (!configured) return
    emit({ type: 'function_exit', function: functionName, file, line, column })
    const chain = [...(context.getStore() ?? [])]
    if (chain.at(-1) === functionName) chain.pop()
    context.enterWith(chain)
}

export function branch(expression: string, file?: string, line?: number, column?: number): void {
    if (configured) emit({ type: 'if', value: expression, file, line, column })
}

export function oracle(sink: string, file?: string, line?: number, column?: number, value?: string): void {
    if (configured) emit({ type: 'oracle', sink, file, line, column, value })
}

export function runWithContext<T>(chain: string[], callback: () => T): T {
    return context.run(chain, callback)
}

;(globalThis as any).__agentfuzz = { startTrace, enter, exit, branch, oracle, runWithContext }
