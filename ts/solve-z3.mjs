import ts from 'typescript'
import { init } from 'z3-solver'

let contextPromise
function context() {
  contextPromise ??= init().then(api => api.Context('agentfuzz'))
  return contextPromise
}

function parse(expression) {
  const source = ts.createSourceFile('condition.ts', `const __condition = (${expression});`, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const declaration = source.statements[0]
  return declaration?.declarationList?.declarations[0]?.initializer ?? null
}

function text(node, source) { return node.getText(source) }

function translate(node, source, z3, variables) {
  if (!node) throw new Error('empty expression')
  if (ts.isParenthesizedExpression(node)) return translate(node.expression, source, z3, variables)
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return z3.String.val(node.text)
  if (ts.isNumericLiteral(node)) return z3.Int.val(node.text)
  if (node.kind === ts.SyntaxKind.TrueKeyword) return z3.Bool.val(true)
  if (node.kind === ts.SyntaxKind.FalseKeyword) return z3.Bool.val(false)
  if (ts.isIdentifier(node)) {
    variables.set(node.text, variables.get(node.text) ?? z3.String.const(node.text))
    return variables.get(node.text)
  }
  if (ts.isPropertyAccessExpression(node) && node.name.text === 'length') {
    return translate(node.expression, source, z3, variables).length()
  }
  if (ts.isPrefixUnaryExpression(node) && node.operator === ts.SyntaxKind.ExclamationToken) {
    return z3.Not(translate(node.operand, source, z3, variables))
  }
  if (ts.isBinaryExpression(node)) {
    const left = translate(node.left, source, z3, variables)
    const right = translate(node.right, source, z3, variables)
    switch (node.operatorToken.kind) {
      case ts.SyntaxKind.AmpersandAmpersandToken: return z3.And(left, right)
      case ts.SyntaxKind.BarBarToken: return z3.Or(left, right)
      case ts.SyntaxKind.EqualsEqualsToken:
      case ts.SyntaxKind.EqualsEqualsEqualsToken: return left.eq(right)
      case ts.SyntaxKind.ExclamationEqualsToken:
      case ts.SyntaxKind.ExclamationEqualsEqualsToken: return left.neq(right)
      case ts.SyntaxKind.GreaterThanToken: return left.gt(right)
      case ts.SyntaxKind.GreaterThanEqualsToken: return left.ge(right)
      case ts.SyntaxKind.LessThanToken: return left.lt(right)
      case ts.SyntaxKind.LessThanEqualsToken: return left.le(right)
      default: throw new Error(`unsupported operator ${text(node.operatorToken, source)}`)
    }
  }
  if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)) {
    const receiver = translate(node.expression.expression, source, z3, variables)
    const method = node.expression.name.text
    const argument = node.arguments[0] ? translate(node.arguments[0], source, z3, variables) : null
    if (method === 'includes' && argument) return receiver.contains(argument)
    if (method === 'indexOf' && argument) return receiver.indexOf(argument)
    // Z3's string theory exposes first-occurrence IndexOf, not a
    // last-occurrence primitive. Refuse this expression rather than silently
    // changing the original lastIndexOf semantics.
    if (method === 'lastIndexOf') throw new Error('lastIndexOf is not representable by the available Z3 string API')
  }
  throw new Error(`unsupported TypeScript expression: ${text(node, source)}`)
}

export async function getZ3Result(expression, timeoutMs = 5000) {
  try {
    const node = parse(expression)
    if (!node) return {}
    const z3 = await context()
    const variables = new Map()
    const constraint = translate(node, node.getSourceFile(), z3, variables)
    const solver = new z3.Solver()
    solver.set('timeout', timeoutMs)
    solver.add(constraint)
    if ((await solver.check()).toString() !== 'sat') return {}
    const model = solver.model()
    const output = {}
    for (const [name, value] of variables) {
      const rendered = model.eval(value, true).toString()
      // The Python z3 adapter returned the string value without the model's
      // surrounding quotes. Preserve that downstream replacement contract.
      if (rendered.length >= 2 && rendered.startsWith('"') && rendered.endsWith('"')) {
        try { output[name] = JSON.parse(rendered) } catch { output[name] = rendered.slice(1, -1) }
      } else {
        output[name] = rendered
      }
    }
    return output
  } catch { return {} }
}

if (process.argv[1] && process.argv[1].endsWith('solve-z3.mjs')) {
  const expression = process.argv.slice(2).join(' ')
  console.log(JSON.stringify(await getZ3Result(expression)))
}
