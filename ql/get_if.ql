/**
 * @id agentfuzz-typescript/if
 * @kind problem
 * @name AgentFuzz TypeScript conditions
 * @description Extract if conditions in the enclosing function.
 * @severity warning
 */
import javascript
import DataFlow

string anchor(Location loc) {
  result = loc.getFile().getAbsolutePath() + "$$" +
    loc.getStartLine().toString() + ":" + loc.getStartColumn().toString() + "$$" +
    loc.getEndLine().toString() + ":" + loc.getEndColumn().toString()
}

predicate isSink(InvokeExpr call, string sink) {
  sink = call.getCalleeName() and
  sink in [
    "eval", "Function", "runInNewContext", "runInThisContext",
    "exec", "execFile", "execFileSync", "spawn", "spawnSync", "fork",
    "fetch", "request", "get", "post", "query", "execute", "raw",
    "runPythonAsync", "compile", "render", "renderString"
  ]
}

predicate calls(Function caller, Function callee) {
  exists(InvokeExpr invoke, DataFlow::InvokeNode node |
    node.getInvokeExpr() = invoke and
    node.getEnclosingFunction() = caller and
    node.getACallee() = callee
  )
}

predicate reaches(Function sourceFn, Function targetFn, int depth) {
  depth = 0 and sourceFn = targetFn
  or
  depth > 0 and depth <= 10 and
  exists(Function next | calls(sourceFn, next) and reaches(next, targetFn, depth - 1))
}

string callPath(Function start, Function target, int depth) {
  depth = 1 and start = target and result = target.getName()
  or
  depth > 1 and depth <= 10 and
  exists(Function next, string suffix |
    calls(start, next) and
    callPath(next, target, depth - 1) = suffix and
    result = start.getName() + " -> " + suffix
  )
}

from IfStmt stmt, Function ifCaller, InvokeExpr sinkCall, Function sinkCaller,
  Function entry, string sink, int depth, int before, int after, string chain
where
  ifCaller = stmt.getContainer() and
  sinkCaller = sinkCall.getEnclosingFunction() and
  isSink(sinkCall, sink) and
  before >= 0 and after >= 0 and depth = before + after + 1 and
  depth <= 10 and reaches(entry, ifCaller, before) and
  reaches(ifCaller, sinkCaller, after) and
  callPath(entry, sinkCaller, depth) = chain
select stmt,
  chain + " -> " + sink + "@@" +
  ifCaller.getName() + "#" + anchor(stmt.getCondition().getLocation()) + "@@" +
  stmt.getCondition().toString()
