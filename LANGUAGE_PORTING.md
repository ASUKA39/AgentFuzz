# AgentFuzz 语言移植分析

本文档评估 AgentFuzz 从 Python Target 扩展到 TypeScript/JavaScript 和 Rust Target 的可行性，重点分析现有组件的语言耦合程度，以及 TypeScript/JavaScript 和 Rust 中可用的同功能工具。

## 结论摘要

AgentFuzz 是部分解耦的：

- LLM Prompt 生成、语义变异、种子调度、评分和迭代控制具有较好的复用性。
- 静态分析、运行时 Trace、Concolic Execution 深度耦合 Python。
- 这些层之间的交互协议也带有明显的 Python 假设：SARIF 被转换为自定义 JSON，运行时事件写入文本日志，`fuzzer.py` 依赖精确的 Python 函数名、文件名和行号。

TypeScript 是更适合首先移植的语言。CodeQL 有可用的 JavaScript/TypeScript Extractor，Node.js 生态存在运行时插桩和符号执行工具，并且可以使用 Z3。但是仍然需要重写查询和运行时/约束适配层，不能只修改几个 import。

Rust 的移植成本明显更高。CodeQL 目前已经支持 Rust，但没有能够直接替代 `sys.settrace` 或 `py-conbyte`、同时适用于任意异步 Rust 服务的成熟方案。Rust 版本应先限定范围，从静态调用/敏感 Sink 分析和显式源码插桩开始；完整的全程序 Concolic Execution 应作为独立的研究任务评估。

## 当前架构和耦合点

### 相对可复用的部分

以下组件本质上不依赖 Target 的实现语言：

- LLM 生成初始 Prompt 和语义变异。
- [`fuzzer.py`](fuzzer.py) 中的 `Chromosome`、种子调度、语义评分和迭代控制。
- [`poc/poc_factory.py`](poc/poc_factory.py) 中的 POC 边界。POC 可以通过 HTTP、WebSocket 或浏览器交互，因此 Target 使用何种实现语言并不重要。
- 高层反馈循环：生成 Prompt、调用 Target、收集观测、评分/变异和重试。

Fuzzing Controller 可以继续使用 Python。这里的语言移植主要针对 Target 侧的分析和插桩，并不意味着必须重写 Controller。

### 静态分析

当前 CodeQL Pack 是 Python 专用的：

- [`ql/qlpack.yml`](ql/qlpack.yml) 依赖 `codeql/python-all`。
- [`ql/call/call.qll`](ql/call/call.qll) 使用 `PyFunctionObject` 和 Python AST 谓词构造源码到 Sink 的调用链。
- [`ql/get_if.ql`](ql/get_if.ql) 查找 Python `If` 节点。
- [`ql/get_dataflow_str_constraint.ql`](ql/get_dataflow_str_constraint.ql) 导入 Python Data Flow 和 Taint Tracking 库。
- [`auto_analyze.py`](auto_analyze.py) 的文档化工作流硬编码了 `--language=python`，同时默认使用 Python 风格的查询名称和路径。

SARIF 到中间产物的转换脚本（`generate_hook.py`、`generate_if.py`、`generate_dsc.py`）也假设 Target 是 Python：它们去掉 `.py` 作为模块名，解析 Python 风格的调用链，并从本地 Python 文件提取源码。

### 运行时观测

[`trace/cetracer.py`](trace/cetracer.py) 是 Python Runtime Tracer，而不是语言无关的 Probe：

- `sys.settrace` 和 `threading.settrace` 观察 Call、Line、Return 事件。
- `sys.addaudithook` 观察选定的 Python Audit Event。
- Monkey-patch `subprocess.run` 和 `eval`；代码中也定义了 `os.system` Wrapper。
- Locals 通过 `str(frame.f_locals)` 序列化。
- 规则通过 Python 函数名、`.py` 模块名和行号匹配。

输出是纯文本日志（`hook.log`、`if.log`、`callstack.log` 和 `oracle.log`）。[`fuzzer.py`](fuzzer.py) 再使用固定文本格式解析这些日志，并精确比较文件路径、函数名、Sink 名和行号。这是跨层耦合的主要来源之一。

### 约束求解和 Concolic Execution

当前实现并不只是更换一个 Solver Binding：

- [`generate_conbyte.py`](generate_conbyte.py) 解析 Python `ast` 表达式，生成临时 Python 函数，然后启动 `py-conbyte`。
- `py-conbyte` 直接探索 Python Bytecode，并实现整数、字符串、列表、Map 和对象的符号操作。
- Solver Backend 通过 SMT-LIB 与 Z3/CVC4 通信，但表达式生成和具体执行语义仍是 Python 专用的。
- [`solve_dsc.py`](solve_dsc.py) 还针对 `split`、`index` 和 `rindex` 实现了 Python 字符串操作的额外修正。

因此，单独替换 SMT Solver 不能完成移植。新语言至少需要自己的 Parser/IR、具体语义、符号语义、路径探索和 Payload 重建逻辑；或者明确限制只支持一小部分约束。

## TypeScript / JavaScript 移植

### 静态分析

CodeQL 官方通过 JavaScript Extractor 分析 TypeScript，相关 Pack 为：

- `codeql/javascript-all`
- `codeql/javascript-queries`

现有 Python 查询需要基于 JavaScript/TypeScript 类和谓词完整重写，并明确以下语义范围：

- 同步调用、Promise 链、`async`/`await`、Callback 和 Event Emitter；
- 动态属性访问和框架依赖注入；
- 生成代码、转译代码和 Source Map；
- `eval`、`Function`、`child_process`、文件系统、网络、数据库、模板和反序列化 Sink；
- 输入究竟来自普通用户、模型输出、Tool Argument，还是普通配置。

TypeScript 通常以 JavaScript 形式被提取。因此需要保留源码位置，并决定查询针对原始 TypeScript 还是转译后的 JavaScript。仓库当前本地 CodeQL 属于较旧的 2.19.x 时代版本，实际实现前必须检查 Extractor 和 Pack 是否可用，必要时升级；上游文档声称支持某语言，不代表本地 CLI 已包含对应组件。

### 插桩和 Trace

Node.js 没有与 Python `sys.settrace` 语义完全对应的内置机制。可行方案如下：

1. **构建期/源码级插桩（推荐）。** 使用 Babel、SWC 或 TypeScript AST Transform 为指定函数入口、分支和 Sink 加入事件，并通过小型 Runtime Library 输出结构化事件。这最接近当前设计，也可以结合 Source Map 保留源码位置。
2. **Jalangi2。** 提供 JavaScript 动态分析 Callback 和插桩，适合原型验证；但需针对目标 Node.js 版本和现代 TypeScript 输出检查其 Runtime 与 ECMAScript 支持。
3. **ExpoSE。** 基于 Jalangi2 和 Z3 的 JavaScript 动态符号执行引擎。它适合评估局部符号探索，不是完整的 AgentFuzz Runtime Tracer。
4. **V8 Inspector/CDP。** 可做调试级检查，但侵入性较高，不适合高吞吐的分支和 Local Value Trace。
5. **eBPF 或 Frida。** 适合观察进程、文件、网络和 OS 级事件，但不能完整提供 JavaScript 层的来源关系、分支和 Locals。

源码插桩应实现与 Python 侧相同的概念事件，而不是试图模拟 Python API。

### 约束求解

没有能够执行真实 Node.js Agent 应用完整语义、并直接等价于 `py-conbyte` 的 TypeScript 工具。可行选项包括：

- 对支持的 JavaScript 程序和字符串/正则操作使用 ExpoSE；
- 使用 Babel 或 TypeScript ESTree Parser，把明确限定的分支表达式子集转换为 SMT-LIB 或 Z3 Term；
- 使用 Node.js 的 `z3-solver` Package 或独立 Z3 Service 作为 Backend；
- 将生成的 Model 放回 JavaScript Runtime，通过隔离的 Predicate Harness 验证。

对 AgentFuzz 而言，第二种路线更容易控制可靠性。可以先支持常见比较、Boolean 表达式、字符串拼接、前缀/后缀/包含、长度、索引和有限的正则表达式。遇到不支持的表达式应返回 `unknown`，让普通语义变异继续工作。

### TypeScript 风险

- TypeScript 往往先被编译，静态位置和动态位置可能因 Source Map 不一致。
- Promise 和事件驱动代码使单一同步 Call Stack 变得不准确。
- JavaScript 的动态对象和反射会降低静态分析精度。
- 对第三方依赖插桩可能产生很高的性能开销。
- `eval`、Worker Thread、子进程和 Native Addon 可能越过插桩边界。

## Rust 移植

### 静态分析

当前上游 CodeQL 支持 Rust 2021 和 2024 Edition，相关 Pack 为：

- `codeql/rust-all`
- `codeql/rust-queries`

现有 Python QL 逻辑仍然需要完整的语义重写，重点包括：

- Ownership、Borrowing 和 Lifetime 相关的数据流；
- Trait、Generic、Monomorphization 和 Macro Expansion；
- `async` 状态机和 Executor 边界；
- Process、文件系统、HTTP、SQL、模板以及 serde/反序列化 Sink；
- 生成代码和 Build Script。

本仓库当前使用的 CodeQL CLI 属于较旧的 2.19.x 时代版本；在把 Rust 当作可用 Target 之前，应验证本地 Rust Extractor 和 Pack，或先升级 CodeQL。

### 插桩和 Trace

Rust 没有与 `sys.settrace` 对应的通用源码级 Tracer。可控性最好的方式是显式、可通过 Feature 开关启用的插桩：

- 使用 [`tracing`](https://crates.io/crates/tracing) Crate 输出结构化事件；
- 使用 Procedural Attribute Macro 标记函数入口/退出；
- 使用 Macro 或 Wrapper 包装选定分支和安全敏感 Sink；
- 以 JSON Event Stream 收集有长度限制的值和 Call Chain 标识。

其他机制的适用范围更窄：

- `cargo llvm-cov` 提供覆盖率，不能提供分支 Locals 或来源关系；
- LLDB、GDB 和 rr 适合调试，不适合可扩展的在线 Probe；
- eBPF、Frida 和 `LD_PRELOAD` 可以观察进程/OS 边界，但会丢失 Rust 应用层语义。

初始 Rust 版本应在 Target Crate 和选定依赖上进行源码/构建期插桩，不应承诺对所有 Rust 操作透明追踪。

### 约束求解

目前没有能对任意 Rust Agent 应用直接替代 Python Bytecode 级 `py-conbyte` 的成熟工具。候选方案用途不同：

- **Kani**：通过显式 Harness 和非确定性输入进行 Rust Model Checking，适合安全属性验证，不是交互式 Payload 生成器。
- **Crux**：提供符号测试/Model Checking，并有 Rust/MIR 方向的工作流；适合受控函数，不是运行中异步服务的透明替代品。
- **SymCC/SymRustC**：在 LLVM 层进行混合 Fuzzing 和符号执行，可尝试选定的 Rust Binary 或 Fuzzing Workflow，但对构建链和运行时有较多限制。
- **KLEE/SeaHorn 等 LLVM 工具**：属于需要定制编译和 Harness 流程的研究组件。

实际 Rust 版本应先把少量 CodeQL 提取的 Predicate 或人工标注的分支表达式转换为 Z3 约束，再通过定向 Rust Harness 验证 Model。全程序符号执行应暂时作为可选能力单独评估。

### Rust 风险

- Async Runtime、Channel 和 Spawned Task 使动态来源关系难以恢复。
- Macro 和生成代码会增加源码位置和稳定标识的处理复杂度。
- Generic Code 和 Monomorphization 可能使插桩点数量膨胀。
- Native Library 和 Unsafe Code 可能位于 Probe 边界之外。
- 编译时间和插桩开销可能成为 Fuzzing 吞吐的主要瓶颈。

## 参考资料

- [CodeQL 支持的语言和框架](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/)
- [Jalangi2](https://github.com/Samsung/jalangi2)
- [ExpoSE](https://github.com/ExpoSEJS/ExpoSE)
- [Z3 JavaScript Bindings](https://www.npmjs.com/package/z3-solver)
- [Rust `tracing`](https://crates.io/crates/tracing)
- [Kani Rust Verifier](https://github.com/model-checking/kani)
- [Crux](https://github.com/GaloisInc/crux)
- [SymRustC](https://github.com/sfu-rsl/symrustc)
