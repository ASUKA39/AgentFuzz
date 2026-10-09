#!/usr/bin/env node
/*
 * Build-time TypeScript/JavaScript probes.  This is deliberately a small
 * Compiler API transform: it only adds the observations consumed by the
 * existing AgentFuzz logs and leaves the target's control/data flow intact.
 */
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'

const root = path.resolve(process.argv[2] || process.env.AGENTFUZZ_TARGET_ROOT || '.')
let ts
try { ts = createRequire(path.join(root, 'package.json'))('typescript') }
catch { ts = createRequire(import.meta.url)('typescript') }
const exts = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'])
const sinkNames = new Set([
  'eval', 'Function', 'runInNewContext', 'runInThisContext', 'exec', 'execFile',
  'execFileSync', 'spawn', 'spawnSync', 'fork', 'fetch', 'request', 'get', 'post',
  'query', 'execute', 'raw', 'runPythonAsync', 'compile', 'render', 'renderString'
])
let currentFile = ''

function files(dir) {
  const out = []
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name === 'node_modules' || ent.name === '.git' || ent.name === '.agentfuzz' || ent.name === 'dist' || ent.name === 'build') continue
    const p = path.join(dir, ent.name)
    if (ent.isDirectory()) out.push(...files(p))
    else if (exts.has(path.extname(ent.name))) out.push(p)
  }
  return out
}

function helper(method, args) {
  const f = ts.factory
  let receiver = f.createIdentifier('globalThis')
  if (['.ts', '.tsx'].includes(path.extname(currentFile))) {
    receiver = f.createAsExpression(receiver, f.createKeywordTypeNode(ts.SyntaxKind.AnyKeyword))
  }
  const global = f.createPropertyAccessExpression(receiver, '__agentfuzz')
  return f.createCallExpression(f.createElementAccessExpression(global, f.createStringLiteral(method)), undefined, args)
}

function string(value) { return ts.factory.createStringLiteral(value) }
function probe(method, args) { return ts.factory.createExpressionStatement(helper(method, args)) }

function transformFile(file) {
  currentFile = file
  const text = fs.readFileSync(file, 'utf8')
  const source = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX)
  const printer = ts.createPrinter({ newLine: ts.NewLineKind.LineFeed })
  const rel = path.relative(root, file).split(path.sep).join('/')
  const lineAt = node => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1
  const colAt = node => source.getLineAndCharacterOfPosition(node.getStart(source)).character + 1
  const f = ts.factory

  const functionName = node => {
    if (node.name && ts.isIdentifier(node.name)) return node.name.text
    if (node.name && ts.isPropertyAccessExpression(node.name)) return node.name.name.text
    return '<anonymous>'
  }

  function wrapFunction(node, body, name) {
    if (!body || (ts.isConstructorDeclaration(node))) return node
    const line = lineAt(node)
    const col = colAt(node)
    const enter = probe('enter', [string(name), string(rel), f.createNumericLiteral(line), f.createNumericLiteral(col)])
    const exit = probe('exit', [string(name), string(rel), f.createNumericLiteral(line), f.createNumericLiteral(col)])
    const guarded = f.createTryStatement(body, undefined, f.createBlock([exit], true))
    const nextBody = f.createBlock([enter, guarded], true)
    if (ts.isFunctionDeclaration(node)) return f.updateFunctionDeclaration(node, node.modifiers, node.asteriskToken, node.name, node.typeParameters, node.parameters, node.type, nextBody)
    if (ts.isFunctionExpression(node)) return f.updateFunctionExpression(node, node.modifiers, node.asteriskToken, node.name, node.typeParameters, node.parameters, node.type, nextBody)
    if (ts.isMethodDeclaration(node)) return f.updateMethodDeclaration(node, node.modifiers, node.asteriskToken, node.name, node.questionToken, node.typeParameters, node.parameters, node.type, nextBody)
    if (ts.isArrowFunction(node)) return f.updateArrowFunction(node, node.modifiers, node.typeParameters, node.parameters, node.type, node.equalsGreaterThanToken, nextBody)
    return node
  }

  const transformer = context => {
    const visit = node => {
      let current = ts.visitEachChild(node, visit, context)
      if (ts.isIfStatement(current)) {
        const line = lineAt(current.expression)
        const col = colAt(current.expression)
        const value = text.slice(current.expression.getStart(source), current.expression.getEnd()).trim()
        const call = probe('branch', [string(value), string(rel), f.createNumericLiteral(line), f.createNumericLiteral(col), string('<unknown>')])
        const thenStmt = ts.isBlock(current.thenStatement)
          ? f.updateBlock(current.thenStatement, [call, ...current.thenStatement.statements])
          : f.createBlock([call, current.thenStatement], true)
        current = f.updateIfStatement(current, current.expression, thenStmt, current.elseStatement)
      }
      if (ts.isCallExpression(current)) {
        const expr = current.expression
        const name = ts.isIdentifier(expr) ? expr.text : ts.isPropertyAccessExpression(expr) ? expr.name.text : ''
        if (sinkNames.has(name)) {
          const line = lineAt(current)
          const col = colAt(current)
          const mark = helper('oracle', [string(name), string(rel), f.createNumericLiteral(line), f.createNumericLiteral(col)])
          return f.createParenthesizedExpression(f.createComma(mark, current))
        }
      }
      if (ts.isFunctionDeclaration(current) || ts.isFunctionExpression(current) || ts.isMethodDeclaration(current)) {
        return wrapFunction(current, current.body, functionName(current))
      }
      if (ts.isArrowFunction(current)) {
        if (ts.isBlock(current.body)) return wrapFunction(current, current.body, functionName(current))
        const line = lineAt(current)
        const col = colAt(current)
        const enter = helper('enter', [string(functionName(current)), string(rel), f.createNumericLiteral(line), f.createNumericLiteral(col)])
        return f.updateArrowFunction(current, current.modifiers, current.typeParameters, current.parameters, current.type, current.equalsGreaterThanToken, f.createParenthesizedExpression(f.createComma(enter, current.body)))
      }
      return current
    }
    return node => ts.visitNode(node, visit)
  }

  const result = ts.transform(source, [transformer]).transformed[0]
  const output = printer.printFile(result)
  if (output !== text) fs.writeFileSync(file, output)
}

for (const file of files(root)) {
  try { transformFile(file) } catch (error) {
    console.error(`AgentFuzz instrumentation failed for ${file}:`, error)
    process.exitCode = 1
  }
}
