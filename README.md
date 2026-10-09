# AgentFuzz

AgentFuzz is the implementation accompanying *Make Agent Defeat Agent: Automatic Detection of Taint-Style Vulnerabilities in LLM-based Agents*.

This branch is the TypeScript/JavaScript port of AgentFuzz. It builds a CodeQL
JavaScript database, converts call-chain, condition, and string-constraint
results into the original JSON rule contracts, instruments the target runtime,
and runs the existing fuzzer against a configured input adapter. The high-level
fuzzing flow and rule contracts remain those of AgentFuzz; language-specific
parts are replaced with CodeQL JavaScript models, a TypeScript Compiler API
instrumenter, Node.js async tracing, and a TypeScript/Z3 expression bridge.

## Reproduce a target

The complete configuration-driven procedure is documented in [REPRODUCTION_GUIDE.md](REPRODUCTION_GUIDE.md). The short form is:

```bash
python3 -m venv .workspace/agentfuzz-venv
.workspace/agentfuzz-venv/bin/pip install -r requirements.txt
.workspace/agentfuzz-venv/bin/python -c 'import z3; print(z3.get_version_string())'
npm ci --ignore-scripts
python3 scripts/reproduce.py --config config.json --duration 900 --iterations 100
```

`config.json` supplies the pinned Target repository and commit, independent AgentFuzz/Target model settings, CodeQL executable and packs, Target dependency/build/run commands, optional patch and mock services, an optional Target preparation script, instrumentation script, rule output directory, call chain, and POC adapter. `scripts/reproduce.py` performs static analysis, builds the Target image, resets the Target workspace, runs the baseline command, starts the long-lived Target container and configured mocks, waits for health checks, runs preparation, checks the POC adapter, runs AgentFuzz for the requested wall-clock duration, collects logs, and removes the temporary container.

Generated source copies, CodeQL databases, SARIF files, rule JSON, logs, and manifests remain under `.workspace`. The Target Docker image contains the Target runtime and its dependencies; the AgentFuzz model client and Z3 solver run on the host-side AgentFuzz virtual environment, while the independently configured Target model is injected only at runtime/preparation.

## Manual stages

The automatic runner invokes the same stages separately when troubleshooting:

```bash
python3 scripts/analyze_target.py --config config.json
python3 scripts/build_target_image.py --config config.json
python3 scripts/run_target.py --config config.json
```

The static-analysis command obtains the configured commit, creates the CodeQL database, runs the three repository queries, and writes `if.json`, `oracle.json`, `enter_hook.json`, and `dsc.json`. The build command copies the pinned source, configured dependencies, instrumentation script, tracer, and generated rules into a Docker build context. The run command executes the configured one-shot baseline command.

For a long-running Target, start the image with the configured workspace mounted at `/workspace`, run the configured POC adapter, and then invoke:

```bash
AGENTFUZZ_TARGET_CONTAINER=<container> \
  .workspace/agentfuzz-venv/bin/python main.py \
  --iteration <count> \
  --application_name <application>
```

`main.py` retains the original hook, condition, call-stack, and Oracle log paths (`/tmp/hook.log`, `/tmp/if.log`, `/tmp/callstack.log`, `/tmp/oracle.log`). `CALLCHAIN` may override the configured chain, but the value must be a key produced in `oracle.json`.

## Citation

```text
Fengyu Liu, Yuan Zhang, Jiaqi Luo, Jiarun Dai, Tian Chen, Letian Yuan,
Zhengmin Yu, Youkun Shi, Ke Li, Chengyuan Zhou, et al.
"Make Agent Defeat Agent: Automatic Detection of Taint-Style Vulnerabilities
in LLM-based Agents." 34th USENIX Security Symposium, 2025.
```
