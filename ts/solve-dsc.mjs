#!/usr/bin/env node
/**
 * Apply the three string-constraint repairs retained from AgentFuzz's Python
 * solver.  TypeScript's parser is used to identify the operation and its
 * literal arguments; no Python-expression regular expressions are involved.
 */
import ts from 'typescript'

function parseExpression(expression) {
  const source = ts.createSourceFile('constraint.ts', `const __constraint = (${expression});`, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  return source.statements[0]?.declarationList?.declarations[0]?.initializer ?? null
}

function literal(node) {
  if (!node) return null
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isNumericLiteral(node)) return Number(node.text)
  return null
}

function operationNode(node) {
  if (!node) return null
  if (ts.isParenthesizedExpression(node)) return operationNode(node.expression)
  if (ts.isElementAccessExpression(node)) {
    const call = operationNode(node.expression)
    if (call) return { ...call, listIndex: literal(node.argumentExpression) }
    return null
  }
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
    const method = node.expression.name.text
    if (!['split', 'indexOf', 'lastIndexOf'].includes(method)) return null
    return {
      method,
      delimiter: literal(node.arguments[0]),
      splitIndex: literal(node.arguments[1]),
      listIndex: null,
    }
  }
  return null
}

function applyRule(rule, payload) {
  const expression = typeof rule === 'string' ? rule : rule?.expr
  if (typeof expression !== 'string' || !expression.trim()) return payload
  const operation = operationNode(parseExpression(expression))
  if (!operation || typeof operation.delimiter !== 'string') return payload
  const delimiter = operation.delimiter
  if (operation.method === 'indexOf') return delimiter + payload
  if (operation.method === 'lastIndexOf') return payload + delimiter
  if (operation.method !== 'split') return payload
  const listIndex = operation.listIndex
  const splitIndex = operation.splitIndex
  if (listIndex === null || listIndex === undefined || listIndex === 0) return payload + delimiter
  if (listIndex > 0 || listIndex === -1) return delimiter.repeat(Math.abs(listIndex)) + payload
  return payload + delimiter.repeat(Math.abs(listIndex) - 1)
}

export function solveDsc(rules, payload) {
  if (!Array.isArray(rules) || typeof payload !== 'string') return payload
  return rules.reduce((current, rule) => applyRule(rule, current), payload)
}

if (process.argv[1]?.endsWith('solve-dsc.mjs')) {
  const input = JSON.parse(process.argv[2] || '{}')
  process.stdout.write(JSON.stringify(solveDsc(input.rules, input.payload)))
}
