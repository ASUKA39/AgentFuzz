#!/usr/bin/env node
/**
 * Convert AgentFuzz TypeScript CodeQL SARIF into the original JSON rule
 * contracts. The converter is deliberately independent of the Target and
 * keeps the same four consumer files as the Python implementation.
 */
import fs from 'node:fs'
import path from 'node:path'

function args() {
  const out = {}
  for (let i = 2; i < process.argv.length; i += 1) {
    const key = process.argv[i]
    if (key.startsWith('--')) out[key.slice(2)] = process.argv[++i]
  }
  if (!out.input || !out.kind) throw new Error('--input and --kind are required')
  if (out.kind === 'callchain' && (!out.enter || !out.oracle)) {
    throw new Error('--enter and --oracle are required for callchain conversion')
  }
  if (out.kind !== 'callchain' && !out.output) {
    throw new Error('--output is required for this conversion kind')
  }
  return out
}

function results(file) {
  const sarif = JSON.parse(fs.readFileSync(file, 'utf8'))
  return sarif.runs?.flatMap(run => run.results ?? []) ?? []
}

function location(value, sourceRoot = '') {
  const m = value.match(/^(.*)\$\$(\d+):(\d+)\$\$(\d+):(\d+)$/)
  if (!m) return null
  let filePath = m[1]
  if (sourceRoot && filePath.startsWith(sourceRoot + path.sep)) filePath = path.relative(sourceRoot, filePath)
  return { file_path: filePath.split(path.sep).join('/'), start_line: Number(m[2]), start_col: Number(m[3]), end_line: Number(m[4]), end_col: Number(m[5]) }
}

function sourceSnippet(loc, sourceRoot = '') {
  const file = sourceRoot ? path.join(sourceRoot, loc.file_path) : loc.file_path
  if (!fs.existsSync(file)) return ''
  const lines = fs.readFileSync(file, 'utf8').split(/\r?\n/)
  // CodeQL reports the invocation location. Preserve the exact expression so
  // the TypeScript AST solver does not have to infer it from a source line.
  if (loc.start_line === loc.end_line) {
    return lines[loc.start_line - 1]?.slice(loc.start_col - 1, loc.end_col).trim() ?? ''
  }
  return lines.slice(loc.start_line - 1, loc.end_line)
    .map((line, index, selected) => index === 0 ? line.slice(loc.start_col - 1) : index === selected.length - 1 ? line.slice(0, loc.end_col) : line)
    .join('\n').trim()
}

function write(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true })
  fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n')
}

function callchain(items, enterFile, oracleFile, sourceRoot) {
  const enter = []
  const oracle = Object.create(null)
  const seen = new Set()
  for (const result of items) {
    for (const line of String(result.message?.text ?? '').split('\n')) {
      const [chainPart, nodesPart] = line.split('@@')
      if (!chainPart || !nodesPart) continue
      const chain = chainPart.trim()
      const nodes = []
      for (const node of nodesPart.split('->')) {
        const hash = node.indexOf('#')
        if (hash < 0) continue
        const name = node.slice(0, hash).trim()
        const loc = location(node.slice(hash + 1).trim(), sourceRoot)
        if (!loc) continue
        nodes.push({ name, loc })
        if (!seen.has(`${name}@${loc.file_path}`)) {
          seen.add(`${name}@${loc.file_path}`)
          enter.push({ package_name: '*', module_name: path.basename(loc.file_path).replace(/\.[^.]+$/, ''), func_name: name })
        }
      }
      const sink = nodes.at(-1)
      if (!sink) continue
      const caller = nodes.at(-2) ?? sink
      const sourcePath = sourceRoot ? path.join(sourceRoot, sink.loc.file_path) : sink.loc.file_path
      const source = fs.existsSync(sourcePath)
        ? fs.readFileSync(sourcePath, 'utf8').split(/\r?\n/)[sink.loc.start_line - 1]?.trim() ?? ''
        : ''
      ;(oracle[chain] ??= []).push({
        file_path: sink.loc.file_path,
        sink: sink.name,
        line: sink.loc.start_line,
        expr: source,
        caller: caller.name
      })
    }
  }
  write(enterFile, enter)
  write(oracleFile, oracle)
}

function ifRules(items, output, sourceRoot) {
  const rules = Object.create(null)
  for (const result of items) {
    for (const line of String(result.message?.text ?? '').split('\n')) {
      const [chain, node = '', expression = ''] = line.split('@@')
      const hash = node.indexOf('#')
      if (!chain || hash < 0) continue
      const loc = location(node.slice(hash + 1), sourceRoot)
      if (!loc) continue
      const functionName = node.slice(0, hash).trim()
      ;(rules[chain] ??= []).push({
        file_path: loc.file_path,
        module_name: path.basename(loc.file_path).replace(/\.[^.]+$/, ''),
        func_name: functionName,
        expr: expression.trim(),
        start_line: loc.start_line
      })
    }
  }
  write(output, rules)
}

function dscRules(items, output, sourceRoot) {
  const rules = Object.create(null)
  for (const result of items) {
    for (const line of String(result.message?.text ?? '').split('\n')) {
      const [chain, node = ''] = line.split('@@')
      const hash = node.indexOf('#')
      if (!chain || hash < 0) continue
      const loc = location(node.slice(hash + 1), sourceRoot)
      if (!loc) continue
      ;(rules[chain] ??= []).push({
        file_path: loc.file_path,
        operation: node.slice(0, hash).trim(),
        line: loc.start_line,
        expr: sourceSnippet(loc, sourceRoot),
      })
    }
  }
  write(output, rules)
}

const options = args()
const items = results(options.input)
if (options.kind === 'callchain') callchain(items, options.enter, options.oracle, options.sourceRoot)
else if (options.kind === 'if') ifRules(items, options.output, options.sourceRoot)
else if (options.kind === 'dsc') dscRules(items, options.output, options.sourceRoot)
else throw new Error(`unknown converter kind: ${options.kind}`)
