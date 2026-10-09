/**
 * @id agentfuzz-typescript/callchain
 * @kind problem
 * @name AgentFuzz TypeScript call chain
 * @description Extract TypeScript/JavaScript calls to sensitive operations.
 * @severity warning
 */
import javascript
import DataFlow

predicate isSink(InvokeExpr call, string sink) {
  sink = call.getCalleeName() and
  sink in [
    "eval", "Function", "runInNewContext", "runInThisContext",
    "exec", "execFile", "execFileSync", "spawn", "spawnSync", "fork",
    "fetch", "request", "get", "post", "query", "execute", "raw",
    "runPythonAsync", "compile", "render", "renderString"
  ]
}

string anchor(Location loc) {
  result = loc.getFile().getAbsolutePath() + "$$" +
    loc.getStartLine().toString() + ":" + loc.getStartColumn().toString() + "$$" +
    loc.getEndLine().toString() + ":" + loc.getEndColumn().toString()
}

predicate projectFunction(Function f) {
  f.getFile().getRelativePath() != ""
}

// Migration placeholders retained from AgentFuzz's Python call model. The
// official JavaScript/TypeScript call graph supplies these ordinary edges;
// add_calls remains intentionally empty until a real TS framework analogue is
// identified.
predicate method_calls(Function caller, Function callee) { none() }
predicate direct_calls(Function caller, Function callee) { none() }
predicate module_calls(Function caller, Function callee) { none() }
predicate add_calls(Function caller, Function callee) { none() }

predicate calls(Function caller, Function callee) {
  exists(InvokeExpr invoke, DataFlow::InvokeNode node |
    node.getInvokeExpr() = invoke and
    node.getEnclosingFunction() = caller and
    node.getACallee() = callee
  )
}

/** A bounded CodeQL call graph path, preserving AgentFuzz's depth limit. */
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

from InvokeExpr sinkCall, Function sinkCaller, Function entry, string sink, int depth, string chain
where
  sinkCaller = sinkCall.getEnclosingFunction() and
  isSink(sinkCall, sink) and
  projectFunction(entry) and
  callPath(entry, sinkCaller, depth) = chain
select sinkCall,
  chain + " -> " + sink + "@@" +
  entry.getName() + "#" + anchor(entry.getLocation()) + "->" +
  sink + "#" + anchor(sinkCall.getLocation())
