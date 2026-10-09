# AgentFuzz TypeScript 迁移清单

## 测试用例

本次 TypeScript 迁移使用以下真实漏洞条目作为运行测试目标。测试用例用于确认迁移后的 AgentFuzz 能够在真实 TypeScript Agent 项目上完成静态分析、调用链提取、规则生成和运行流程；即使该漏洞最终超出工具的实际检测能力，也不影响迁移验收。

- 漏洞编号：`CVE-2026-41265`
- Target：`FlowiseAI/Flowise`
- 仓库链接：<https://github.com/FlowiseAI/Flowise>
- 漏洞版本范围：`< 3.1.0`
- 测试版本标签：`flowise@3.0.5`
- 测试版本提交：`ba6a602cbe87d9f55c9ee6aebb6407ec2f2066b5`
- CWE：`CWE-77`
- CVSS：`9.8`（Critical）
- LLM-in-the-Loop 类型：`LLM-generated artifacts`
- 漏洞描述：Flowise 的 `Airtable_Agents.run` 让 LLM 根据用户问题生成 Python 代码，并通过 Pyodide 执行。攻击者可通过 prompt injection 诱导 LLM 生成恶意 Python 脚本，从而执行攻击者控制的命令。
- 关键源码：`packages/components/nodes/agents/AirtableAgent/AirtableAgent.ts`、`packages/components/nodes/agents/AirtableAgent/core.ts`
- 关键函数：`Airtable_Agents.run`、`LoadPyodide`、`pyodide.runPythonAsync`
- 预期高层调用链：`Airtable_Agents.run -> LoadPyodide -> pyodide.runPythonAsync`
- 预期 Sink：Pyodide 的 Python 代码执行接口 `runPythonAsync`
- 构建前提：Node.js `>=18.15.0 <19.0.0 || ^20`，pnpm `>=9`；按仓库 workspace 配置安装依赖并执行构建。
- 运行前提：需要 Flowise 可用的数据库、LLM 配置，以及 Airtable Agent 所需的 Airtable 凭证和 Base/Table 配置；通过 chatflow 或 API 向 Airtable Agent 提交问题。

## 总体迁移约束

本次迁移的目标是实现与原版对等的 TypeScript 版本，而不是重写、重设计或扩展 AgentFuzz。具体约束如下：

- 尽可能保留原版源码、文件结构、模块职责、接口和文件契约格式。
- 优先采用代码替换和局部 Patch 的方式迁移：只替换 Python 特有的实现部件，保留原有调用关系、流程、调度、输出和消费者。
- 迁移前后不得新增、删除或改变原版的高层功能和处理流程。
- 不为 TypeScript 另造一套并行实现路径，也不通过参数在 Python/TypeScript 两套逻辑之间切换。
- 当前分支最终仅支持 TypeScript Target，直接成为 TypeScript 版本，而不是同时支持 Python 和 TypeScript 的通用版本。
- 只处理语言相关的实现差异；语言无关的逻辑、流程和组件应保持原样。

本清单只列出从 Python Target 迁移到 TypeScript Target 时，必须重新获得对等功能目的的源码组件。普通路径、文件名、参数和接口调整不单独列出。

尚未讨论的“迁移方案”留空；已经讨论并达成共识的方案在表格或对应章节中记录。

| 代码模块 | 当前职责 | TypeScript 迁移目标 | 迁移方案 |
|---|---|---|---|
| `ql/call/call.qll`、`ql/get_callchain_and_location.ql` | 识别函数调用关系，追踪入口到敏感调用的有限深度调用链，并输出函数、调用链和源码位置。 | 在 TypeScript/JavaScript 语义下获得同等的入口、调用链、敏感调用和源码位置结果。 | 普通函数调用、方法调用和静态模块调用使用 CodeQL 官方 JavaScript/TypeScript 调用模型，不照搬 Python 版按名称和 AST 形状猜测调用关系的实现。保留 AgentFuzz 自己的有限深度路径遍历、项目内入口筛选、调用链输出和源码位置输出。TypeScript 迁移代码中分别保留 `method_calls`、`direct_calls`、`module_calls`、`add_calls` 四个空实现或注释占位；它们不参与普通调用关系，只有后续确认存在真实的 TypeScript 对等框架语义时才单独启用。 |
| `ql/call/call.qll` 中的 `is_sink` | 识别代码执行、命令执行、网络请求、Agent 工具执行等安全敏感调用，作为调用链终点和 Oracle 候选。 | 按安全语义识别 TypeScript/Node.js 中的对等敏感操作，不依赖 Python API 名称。 | 按代码执行、命令执行、网络请求、数据库执行和模板代码编译/解释五类语义迁移；Agent 框架特定 Sink 留空占位。 |
| `ql/get_if.ql` | 提取调用链上到达敏感调用前经过的条件分支，并记录分支所属函数、表达式和位置。 | 提取 TypeScript/JavaScript 条件语句和等价控制流节点，并保持分支约束的下游用途。 | 只使用官方 `IfStmt`，保留 Sink 前过滤、完整复合表达式和调用链排序；不扩展到三元、循环或其它控制流结构。 |
| `ql/get_dataflow_str_constraint.ql` | 提取影响敏感调用参数的数据流和字符串约束，并将约束关联到调用链。 | 提取 TypeScript/JavaScript 数据流及表达式约束，保持其为定向输入生成提供约束的用途。 | 使用 CodeQL 官方 JavaScript/TypeScript DataFlow/TaintTracking 模型，保持原版的局部数据流范围、调用链关联和 `split`、`index`、`rindex` 三类字符串约束语义；继续输出 SARIF，不新增下游协议或字段。 |
| `generate_hook.py`、`generate_if.py`、`generate_dsc.py` | 将 CodeQL/SARIF 结果转换为入口、Oracle、分支和数据流约束规则，供运行时和 Fuzzer 使用。 | 将 TypeScript CodeQL 结果转换为具有相同语义的运行时规则，不改变规则在后续流程中的职责。 | 尽可能保持现有 JSON 结构、键名和消费者接口不变。根据 TypeScript/JavaScript 的 SARIF 路径、源码位置、函数名、文件扩展名和表达式形式对等调整解析正则与源码片段提取：`generate_hook.py` 保持入口/Oracle 分组，`generate_if.py` 保持 Sink 前过滤和调用链排序，`generate_dsc.py` 保持字符串约束归并；不新增规则协议，不扩大原版识别范围。 |
| `trace/cetracer.py` 的函数/行/返回追踪 | 运行时记录函数进入、执行位置、返回和调用栈，用于判断静态调用链是否实际到达。 | 在 TypeScript/Node.js 运行时获得等价的函数、控制流和调用链观测能力，包括异步执行路径。 | 使用 Compiler API 插入有限 Probe，Runtime 用 `AsyncLocalStorage` 关联异步上下文，输出语言无关事件后转换为现有反馈。 |
| `trace/cetracer.py` 的 Oracle Hook | 通过审计 Hook 和敏感 API 包装捕获 `eval`、`exec`、进程执行等操作，记录 Oracle 命中及相关值。 | 在 TypeScript/Node.js 中捕获对等安全敏感操作并产生可判定的 Oracle 事件。 | 静态 Sink 调用点优先插 Probe，无法插桩的 API 使用 Node Wrapper/Module Hook；只匹配静态规则指定的 Sink。 |
| `generate_conbyte.py` | 原主分支中解析静态约束、准备 `input_vars`/`function_code` 并调用 `py-conbyte` 的适配器。仓库 Issue #2 已确认 `generate_if.py` 和现有 `if.json` 不产生这两个字段，因此该路径实际无法有效工作。 | 不单独迁移该适配器；其原本的表达式求解职责由 `generate_z3.py` 的 TypeScript 对等实现承担。 | 不作为独立 TypeScript 迁移组件；以 `generate_z3.py` 条目为准。 |
| `generate_z3.py` | `z3` 分支新增的表达式求解适配器：解析 Python 条件表达式，转换为 Z3 约束，生成临时 Z3 脚本，调用 Z3 并解析模型。当前分支已合并该路径，Fuzzer 的变量变异改为直接调用 `get_z3_result(expr)`，不再依赖 `input_vars` 和 `function_code`。 | 在 TypeScript/JavaScript 上提供表达式解析、语义转换、Z3 求解和模型回填的对等适配能力。 | 不迁移 Python AST、Z3Py 文本脚本或 Python 字节码实现；使用 TypeScript Compiler API 将支持的 TypeScript 表达式转换为 Z3 约束，通过 JavaScript/TypeScript Z3 Binding 求解并返回变量值字典。无法可靠转换、不可满足、类型不明或超时的表达式直接放弃本次求解，继续原有普通变异流程；不改变 Fuzzer 的调度、Prompt 回填、评分和主循环。 |
| `py-conbyte/` | 原设计中的 Python 字节码具体/符号联合执行引擎，负责符号值传播、路径探索和输入生成；但主分支与它的调用接线已被 Issue #2 确认为不完整，作者后续 `z3` 分支绕过了该引擎，改用 `generate_z3.py`。 | 不迁移 Python 字节码级引擎，不在 TypeScript 版本中另行实现 JavaScript/TypeScript 字节码级 Concolic；保留目录作为原版代码和历史参考，不纳入当前迁移运行链。 | 不迁移；TypeScript 侧采用已确定的 `generate_z3.py` 对等方案。 |
| `solve_dsc.py` | 对 `split`、`index`、`rindex` 等字符串约束进行定向修正，使生成输入更可能满足目标路径。 | 保持字符串约束定向修正的功能目的，并覆盖 TypeScript/JavaScript 的对应字符串语义。 | 仅保留原版三类语义：`.split()`、`.index()` 对应 JavaScript `.split()`、`.indexOf()`，`.rindex()` 对应 `.lastIndexOf()`；不扩展其它字符串 API。无法可靠解析或语义不明确时保留当前 Payload，不伪造修正结果；调用时机、回填、评分、调度和主循环不变。 |

## Concolic 路径现状

仓库 Issue [#2](https://github.com/LFYSec/AgentFuzz/issues/2) 明确指出：`fuzzer.py` 的 `solve_and_get_new_prompt()` 读取 `input_vars` 和 `function_code`，但 `generate_if.py` 及仓库现有 `if.json` 并不生成这两个字段，因此原主分支中的 Variable mutator 不能有效驱动 `py-conbyte`。该 Issue 后续由作者关闭，作者要求检查 `z3` 分支，并在提交 `43b23409637d368014e607e8e0ad21e4fd4d5934`（`fix #2`）中采用了新的处理方式。

`z3` 分支的处理不是补齐 `input_vars` 和 `function_code`，而是新增 `generate_z3.py`，让 `fuzzer.py` 直接把 `if` 表达式传给 `get_z3_result(expr)`。该适配器负责解析表达式、转换为 Z3 约束、调用 Z3 并解析模型；因此它绕过了原 `py-conbyte` 接线，而不是修复 Python 字节码引擎本身。

当前分支已合并 `z3` 分支中与该问题直接相关的改动：新增 `generate_z3.py`，并将 `fuzzer.py` 的变量变异调用切换到 `generate_z3.get_z3_result(expr)`；没有合并 `z3` 分支中会删除当前复现流程、配置和文档的无关改动。

## 已确定方案：`generate_z3.py` 的 TypeScript 迁移

1. 不迁移原 `py-conbyte` 的 Python 字节码级 Concolic 执行，以作者 `z3` 分支中的 `generate_z3.py` 为实际基线，迁移其“条件表达式直接求解”功能。

2. 从静态 `if` 规则取得 TypeScript 条件表达式，例如 `text.includes("admin") || text.length > 10`。

3. 使用 TypeScript Compiler API 解析 AST，不使用正则或简单字符串替换推断语义。识别变量、字面量、布尔运算、比较、字符串长度和已支持的字符串方法。

4. 将支持的 TypeScript AST 转换为 Z3 约束：`a && b` 转为 `And(a, b)`，`a || b` 转为 `Or(a, b)`，`!a` 转为 `Not(a)`，`text.includes("x")` 转为 `Contains(text, "x")`，`text.length` 转为 `Length(text)`，`a === b` 转为相等约束；字符索引和 `indexOf` 仅在能够可靠映射时处理。只实现明确对齐的表达式语义，不扩展成完整 JavaScript 符号执行器。

5. 直接使用 JavaScript/TypeScript 的 Z3 Binding 或等价 Z3 接口，执行 `TypeScript AST -> Z3 约束 -> solver.check() -> model() -> 变量值字典`，不再生成临时 Python 文件，也不依赖 Python AST、Z3Py 文本输出或正则解析模型。

6. 保持现有 Fuzzer 的高层流程：根据运行时变量找到 Prompt 中对应文本，用 Z3 返回的变量值替换该文本，将新 Prompt 重新发送给 Target，必要时继续使用现有的 DSC 字符串修正逻辑。

7. 遇到不支持的 AST、无法可靠转换的语义、不可满足约束、类型不确定或 Solver 超时，直接放弃本次求解，不伪造结果，也不强行转换；Fuzzer 保持原有流程，继续进行后续普通变异或下一轮处理。

8. 不改变变量变异的调度、Prompt 回填、Fuzzer 评分、种子管理和整体循环；只替换原 `generate_z3.py` 中 Python 表达式解析和 Z3 调用的语言适配实现。

## 已确定方案：`solve_dsc.py`

1. 保留其独立职责：对已经提取出的字符串约束进行定向 Payload 修正；它不负责静态分析，也不负责 Z3 求解。

2. 只迁移原版明确处理的三类字符串操作，并按 TypeScript/JavaScript 的对等语义处理：Python `.split(...)` 对应 JavaScript `.split(...)`，Python `.index(...)` 对应通常的 `.indexOf(...)`，Python `.rindex(...)` 对应通常的 `.lastIndexOf(...)`。

3. 保持原版处理范围，不扩展到其它字符串 API。TypeScript 版本应解析对应的表达式语义，而不是照搬 Python 源码文本正则；只有能够可靠识别并修正的约束才处理。

4. 遇到无法可靠解析、语义不明确或不支持的表达式时，直接放弃本次 DSC 修正，保留当前 Payload，继续 AgentFuzz 原有流程，不伪造修正结果。

5. 保持调用时机和下游用途不变：它仍在变量变异求解后，以及 Oracle 命中后生成下一轮 Prompt 时，对 Payload 做字符串约束修正；不改变 Fuzzer 的调度、评分、回填和主循环。

## 此前暂缓、现已形成方案的项目

前面讨论中暂缓的项目只有以下两组。现在已完成消费者对齐，方案是保持原有高层职责、JSON 结构和下游接口，只对 TypeScript/JavaScript 的查询模型、SARIF 字段和源码语法进行等价适配：

1. `ql/get_dataflow_str_constraint.ql`

   原版用 CodeQL 的局部数据流/污点追踪，寻找会影响敏感调用参数的字符串约束；当前 `getStrFuncName()` 只列出 `split`、`index`、`rindex`。TypeScript 版本使用官方 JavaScript/TypeScript DataFlow/TaintTracking，保持同样的局部追踪和三类字符串语义，继续输出现有 SARIF 结果，由 `generate_dsc.py` 和 `solve_dsc.py` 按现有职责消费。

2. `generate_hook.py`、`generate_if.py`、`generate_dsc.py`

   这三个模块负责把 CodeQL/SARIF 结果转换成入口、Oracle、`if` 和字符串约束规则。保持原有 JSON 结构和下游消费者；仅按 TypeScript/JavaScript 的路径、位置、函数名、扩展名和表达式调整解析正则、源码提取和排序过滤，不凭空新增规则协议。

`generate_conbyte.py` 和 `py-conbyte/` 不属于上述暂缓项目：它们已经明确不作为独立的 TypeScript 迁移目标，表达式求解职责由 `generate_z3.py` 承担。

## 清单完整性核对

已对照当前仓库的静态分析、规则转换、运行时反馈和求解调用链核对，迁移清单覆盖了迁移中真正改变语言语义的组件：

- CodeQL 查询：调用链/Sink、`if` 条件、字符串约束数据流三类查询均已列出。
- SARIF 转换：入口/Oracle、`if`、DSC 三个现有转换器均已列出，并统一采用“保持 JSON 结构、按 TypeScript 语法适配”的方案。
- Runtime：函数/位置/返回 Trace 与 Oracle Hook 均已列出。
- 输入生成：`generate_z3.py` 与 `solve_dsc.py` 已列出；Python 字节码级 `py-conbyte` 已明确不迁移。

以下内容没有遗漏，而是按“只做普通适配、不单列迁移组件”的原则排除：`main.py`、`fuzzer.py` 的调度和评分逻辑，Prompt 与 POC，`trace/compare/compare.py` 的语言无关文本比较，Docker/目标生命周期脚本，以及 `qlpack.yml`、依赖包和路径等配置。它们在实现阶段只需完成 TypeScript 语言、CodeQL 包和运行命令的必要适配，不改变 AgentFuzz 的高层流程或功能范围。

## 已确定方案：CodeQL 调用链查询

AgentFuzz 的调用链目标不变：从项目内的入口函数出发，沿函数调用关系追踪到敏感调用，限制路径深度，并输出有序调用链和各节点源码位置。

1. 普通调用关系改用 CodeQL 官方 JavaScript/TypeScript 模型。使用官方的函数、调用表达式、方法调用和解析后调用目标来识别普通函数调用、类方法调用、`this.method()` 或对象方法调用，以及 ES Module/CommonJS 的静态导入调用。不把 Python 版 `direct_calls`、`method_calls`、`module_calls` 的名字匹配和 AST 猜测逻辑原样搬到 TypeScript。

2. 保留 AgentFuzz 自己的路径逻辑：从项目内函数作为起点，沿调用关系递归查找 Sink，限制调用深度，生成中间函数序列，输出入口、路径和 Sink 的源码位置，并为后续 Hook、Oracle、Fuzzer 距离计算提供同等信息。

3. 不新增通用动态调用分析。不因为 TypeScript 存在 Promise、回调、EventEmitter 或反射，就另外发明一套调用图推断逻辑。CodeQL 官方模型能够解析的边就使用；不能解析的边保留为该静态分析模型的边界。原版也没有完整解决 Python 的通用动态调用问题。

4. `add_calls` 单独按实际语义处理。`_sys_execute` 不是普通语言调用，而是针对某个 Python/AgentScope 包装模式的硬编码。如果 TypeScript Target 中存在语义相同的包装器，再建立对应规则；没有对应物就不迁移这个特例，也不凭空新增 TypeScript 版本。

5. 保持下游信息语义不变。文件后缀、函数命名形式和路径字符串中的语言细节可以变化，但下游仍需得到 `入口函数 -> 中间函数 -> Sink`，以及路径深度、函数位置和 Sink 位置。

针对原作者在 `calls` 中附加的四个关系，TypeScript 迁移版分别保留空实现或注释占位：`method_calls`、`direct_calls`、`module_calls`、`add_calls`。普通三类调用由 CodeQL 官方 JavaScript/TypeScript 调用模型承担；`add_calls` 只有在之后确认存在真实的 TypeScript 对等框架语义时才考虑启用。

## 已确定方案：Sink 定义

1. 保留 Sink 的原有职责：识别调用链终点和运行时 Oracle，不改变 AgentFuzz 的高层流程。

2. 代码执行迁移到 TypeScript/JavaScript 中具有同等执行语义的接口，例如 `eval`、`Function`、动态模块加载或等价的运行时代码解释接口。

3. 命令执行迁移到 Node.js 和目标项目中的对等危险接口，例如 `child_process.exec`、`execFile`、`spawn`、`fork` 以及项目自定义的命令执行封装。

4. 网络请求迁移到 TypeScript/JavaScript 中实际承担网络请求的接口，例如 `fetch`、`axios`、`got`、`http.request`、`https.request` 及目标项目使用的 HTTP 客户端封装。

5. 数据库执行迁移到各类 TypeScript/JavaScript 数据库客户端中执行查询或原始语句的接口，例如 `query`、`execute`、`raw` 等；按危险操作语义匹配，不按 ORM 函数名机械判断。

6. 上述四类迁移的是危险操作语义，不是简单替换函数名，也不是一次性穷举整个 Node.js 生态。Sink 列表保持可扩展。

7. Agent 特定操作留空占位。原版的 `GitLoader`、`SQLDatabaseChain`、`AsyncWebCrawler`、`ShellTool` 等属于针对特定 Agent 框架的补充规则，不在 TypeScript 迁移版中凭空制造对应规则。只有以后确认某个具体 TypeScript Agent 框架存在明确同语义操作时，才单独补充。

8. 模板操作保留为模板注入类 Sink。迁移的语义是“外部可控字符串被当作模板代码编译或解释”，而不是所有模板渲染都算 Sink。可覆盖的对等接口包括 `nunjucks.renderString`、`ejs.compile`、`ejs.render`、`pug.compile`、`Handlebars.compile`、`lodash.template` 以及其他允许模板表达式执行的模板引擎接口。只有把输入字符串当作模板程序编译或解释的接口才纳入；可信模板与数据分离的普通渲染调用不粗暴纳入。

最终保留的 Sink 类别为：代码执行、命令执行、网络请求、数据库执行、模板代码编译/解释。Agent 框架特定 Sink 保留空占位。所有类别均保持可扩展，首版不要求穷尽。

## 已确定方案：条件分支查询

1. 保留原版职责：提取从入口到 Sink 的静态调用路径上、且位于 Sink 之前的 `if` 条件，记录条件所属函数、表达式、源码位置和调用链顺序，供运行时路径反馈和后续定向输入生成使用。

2. TypeScript 版本使用 CodeQL 官方 JavaScript/TypeScript 控制流和 `IfStmt` 模型，识别普通 `if`、`else if`（对应嵌套的 `IfStmt`）以及 `if` 测试表达式中的完整复合条件。

3. 与 Python 版保持一致，复合条件作为一个完整表达式记录。例如 `if (a && b) { dangerous(); }` 记录整个 `a && b`，不拆成两个独立条件。

4. 严格只处理 `if` 语句，不扩展范围。三元条件表达式、`&&`、`||`、`??` 本身、`while`、`for`、`for...of`、`for await...of`、`switch`、`try/catch` 以及其它具有控制流效果但不是 `if` 的结构，不单独提取为条件规则。

5. 保留原版的路径筛选逻辑：只保留属于目标调用链、并且发生在 Sink 之前的 `if` 条件。

6. 保留 `generate_if.py` 的高层职责：将 CodeQL/SARIF 结果转换为 Fuzzer 现有的条件规则结构。只适配 TypeScript 的文件、函数、源码位置和 CodeQL 输出，不改变下游规则用途、调用链关联方式或排序逻辑。

## 已确定方案：运行时函数、位置和返回 Trace

1. 使用官方 TypeScript Compiler API，在 Target 的源码副本中按静态规则插入 Probe，不修改原始仓库。只插入函数进入和退出、`if` 条件执行、静态分析识别出的 Sink 调用三类 Probe，不对整个程序无差别插桩。

2. 提供一个小型 TypeScript/JavaScript Runtime Library，接收 Probe 事件并输出结构化事件：`function_enter`、`function_exit`、`if`、`sink`，以及文件、行列、函数和调用链标识。函数退出使用 `try/finally`，确保异常路径也能产生退出事件。

3. 使用 Node.js `AsyncLocalStorage` 保存逻辑调用上下文，关联 `async`/`await`、Promise、回调和事件任务。它只负责延续 AgentFuzz 的调用链上下文，不把所有 `async_hooks` 生命周期事件都当作 Trace。

4. 对静态规则指定的危险 API 使用调用包装或模块 Hook 产生 `sink` 事件。Sink 事件包含调用位置和必要的输入摘要，用于 Oracle 判定。

5. 保持原版的依赖包边界：默认只对 Target 自身源码和静态规则指定的代码插桩；默认不插桩整个 `node_modules`；某个依赖只有在其源码属于分析范围，或明确加入白名单时才进行 Trace；`child_process`、`eval`、模板引擎等 Sink 通过 API Hook 观测，不要求把整个依赖包全部插桩。

6. 插桩和编译过程生成 Source Map，运行时事件统一还原到 TypeScript 文件和源码位置。

7. 通过 Node preload/loader 或目标入口的一次性启动调用加载 Runtime Library，等价于 Python 版在入口注入 `cetracer.start_ce_trace(...)`，不要求手工修改每个函数。

8. 先让 Runtime 输出语言无关的结构化事件，再由适配层转换为 AgentFuzz 当前需要的调用栈、分支命中、距离和 Oracle 反馈。Trace 本身不改变 Fuzzer 的评分、调度和主循环。

9. 不使用 V8 Inspector 作为常规 Trace 后端，不以 Jalangi2 作为基础实现，不把 OpenTelemetry 或覆盖率工具当作函数级 Trace，也不要求模拟 Python `sys.settrace`，只保持其观测目的和反馈信息。

## 已确定方案：Oracle Hook

1. 保留静态 Oracle 规则，继续使用静态分析生成的 Sink 位置作为 Oracle 规则来源。每个规则至少包含 Sink 类型、TypeScript 源码文件、行列位置以及所属调用链或规则 ID。

2. 优先在 Sink 调用点插入 Probe。对静态分析已经定位的 Target Sink，在调用点插入 Oracle Probe。Probe 在敏感调用执行前记录 Oracle 规则 ID、文件和行列位置、Sink 类型以及必要的参数或值摘要。这样不依赖 Python `inspect.stack()` 的字符串匹配，也不会把同一 API 的所有调用都误判为 Oracle。

3. 对无法直接插桩的运行时 API 使用 Wrapper/Module Hook。对 `child_process`、动态代码执行、网络客户端、数据库客户端和模板引擎等无法稳定在源码调用点插入 Probe 的情况，使用 Node.js API Wrapper 或模块 Hook。Wrapper 只对静态规则指定的 Sink 产生 Oracle 事件，不把所有 API 调用都算作命中；必要时通过 `AsyncLocalStorage` 或当前调用上下文关联调用链和源码位置。

4. 保留执行时机。Oracle 事件应在敏感操作实际开始执行时产生，通常位于调用前；即使敏感操作随后抛出异常，也保留命中事件。这与原版在调用包装或审计事件中记录命中的行为一致。

5. 统一事件输出。Runtime Library 输出结构化 `oracle` 事件，包含规则 ID、Sink、位置、调用链上下文和必要值摘要。后续适配层再将其转换为 AgentFuzz 当前 Fuzzer 使用的 Oracle 反馈，不改变成功判定和调度逻辑。

6. 保持依赖边界。不默认插桩整个 `node_modules`。依赖内部的危险 API 通过 Wrapper/Module Hook 观测；只有依赖源码属于静态分析范围或明确加入白名单时，才关联其源码位置并生成源码级 Oracle Probe。

7. 不模拟 Python 具体机制。不迁移 `sys.addaudithook`、`inspect.stack()` 或 Python Monkey Patch 本身，只保留其目的：确认静态识别的敏感操作确实被执行，并向 Fuzzer 产生可靠的 Oracle 命中事件。

原版依赖边界保持如下：普通依赖函数默认不 Trace，明确白名单依赖可以 Trace；依赖中的敏感 API 可以通过全局 Hook 观测，但只有在匹配 Oracle 规则时才算命中。

## 不作为独立迁移项的内容

- LLM Prompt、语义变异、种子调度、评分和 Fuzzing 主循环。
- POC 的通信方式和 Target 生命周期管理。
- Dockerfile、模型配置、路径、文件名和普通接口适配。
- 运行日志格式、JSON 文件名以及不改变语义的字段调整。
