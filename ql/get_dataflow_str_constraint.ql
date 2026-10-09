/**
 * @id agentfuzz-typescript/string-constraints
 * @kind problem
 * @name AgentFuzz TypeScript string constraints
 * @description Extract the three string-operation families from the TypeScript data-flow model.
 * @severity warning
 */
import javascript
import DataFlow

predicate isStringOperation(InvokeExpr call, string name) {
  name = call.getCalleeName() and name in ["split", "indexOf", "lastIndexOf"]
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

predicate flowsToSink(InvokeExpr source, InvokeExpr sink) {
  exists(int argument |
    argument >= 0 and argument < sink.getNumArgument() and
    DataFlow::localFlowStep*(
      DataFlow::valueNode(source),
      DataFlow::valueNode(sink.getArgument(argument))
    )
  )
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

string anchor(Location loc) {
  result = loc.getFile().getAbsolutePath() + "$$" +
    loc.getStartLine().toString() + ":" + loc.getStartColumn().toString() + "$$" +
    loc.getEndLine().toString() + ":" + loc.getEndColumn().toString()
}

from InvokeExpr call, Function caller, InvokeExpr sinkCall, Function sinkCaller,
  Function entry, string operation, string sink, int before, int after, int depth,
  string chain
where
  caller = call.getEnclosingFunction() and
  isStringOperation(call, operation) and
  sinkCaller = sinkCall.getEnclosingFunction() and
  isSink(sinkCall, sink) and
  flowsToSink(call, sinkCall) and
  before >= 0 and after >= 0 and depth = before + after + 1 and
  depth <= 10 and reaches(entry, caller, before) and
  reaches(caller, sinkCaller, after) and
  callPath(entry, sinkCaller, depth) = chain
select call,
  chain + " -> " + sink + "@@" + operation + "#" + anchor(call.getLocation())
