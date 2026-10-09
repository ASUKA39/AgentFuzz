# AgentFuzz 复现指南

本指南定义一条可重复、配置驱动的 AgentFuzz 运行流程。当前 `main` 分支使用 Python CodeQL 查询分析 Python Target，并使用 `generate_z3.py` 将 `if.json` 中的条件表达式直接转换为 Z3 约束；它不再通过 `py-conbyte` 或单独的 py373/pipenv 环境求解。流程适用于能够被 CodeQL Python extractor 建库、并能够通过一个输入适配器提交字符串输入的 Target。换用其他 Target 时只需要提供配置、必要时提供 Dockerfile 覆盖、插桩脚本和 POC 适配器；AgentFuzz 的核心流程、规则 JSON 契约和编排脚本不需要复制或重写。TypeScript、Java 等其他语言仍不属于当前 Python 查询版本的适用范围，除非先完成对应的语言迁移查询和转换器。

流程顺序固定为：准备配置和定制文件 → 获取并固定 Target 源码 → 生成 CodeQL 数据库和四个规则 JSON → 构建带插桩的 Target 镜像 → 运行一次基线命令 → 启动长期运行的 Target 容器 → 用 POC 提交输入 → 启动 AgentFuzz → 回收日志和结果 → 删除临时容器。`scripts/reproduce.py` 将这些步骤串成一条命令；需要人工判断的内容仅限于准备 Target 的输入格式、插桩位置、POC 提交方式和结果含义。

## 一、复现者必须提供的内容

在仓库根目录创建一个 JSON 配置文件（默认名为 `config.json`）。配置中的路径相对于 AgentFuzz 根目录；绝对路径也可以使用。配置至少包含以下字段：

```json
{
  "target_name": "<唯一目标名>",
  "repo_url": "<Target Git 仓库地址>",
  "ref": "<漏洞版本的分支、标签或提交>",
  "expected_commit": "<固定提交哈希>",
  "model": {
    "base_url": "<OpenAI-compatible Chat Completions 地址>",
    "name": "<模型名>",
    "api_key": "<API key>",
    "temperature": 0,
    "thinking": false,
    "timeout": 120
  },
  "analysis": {
    "codeql": "<CodeQL 2.19.2 可执行文件，或 PATH 中的 codeql>",
    "pack_cache": "~/.codeql/packages",
    "download_packs": true,
    "packs": ["<qlpack 及版本>"],
    "language": "python",
    "database": ".workspace/codeql/<目标名>",
    "output": ".workspace/static-analysis/<目标名>",
  },
  "agentfuzz": {
    "application_name": "<命令行中的应用名>",
    "call_chain": "<oracle.json 中要执行的调用链>",
    "container_name": "<长期运行的 Target 容器名>",
    "oracle_json": ".workspace/static-analysis/<目标名>/output/oracle.json",
    "if_json": ".workspace/static-analysis/<目标名>/output/if.json",
    "hook_json": ".workspace/static-analysis/<目标名>/output/enter_hook.json",
    "dsc_json": ".workspace/static-analysis/<目标名>/output/dsc.json",
    "poc": "poc.<目标适配器模块>:connect_with_auth",
    "poc_test_payload": "<不会破坏环境的固定测试输入>"
  },
  "target": {
    "python_version": "3.10",
    "install_command": "<在镜像中安装 Target 及其依赖的命令>",
    "build_command": "<可选的构建命令>",
    "build_script": "<可选的仓库内构建脚本路径>",
    "run_command": "<一次性基线运行命令>",
    "workspace": ".workspace/<目标运行时工作区>",
    "container_name": "<长期运行的 Target 容器名>",
    "instrumentation": {
      "script": "targets/<目标>/instrument.sh",
      "rules_dir": ".workspace/static-analysis/<目标名>/output",
      "startup_delay": 40
    }
  }
}
```

`expected_commit` 必须是漏洞版本的实际提交哈希，不能只填写浮动分支。`install_command` 在默认 Dockerfile 内执行，负责安装运行时依赖；`build_command` 用于需要额外编译步骤的 Target；`build_script` 用于多步或需要条件逻辑的构建，路径必须位于 AgentFuzz 仓库内，且在 Docker 构建上下文中执行。默认使用 `targets/default.Dockerfile`；只有基础镜像、系统依赖或构建流程确实不同，才在 `target.dockerfile` 指定覆盖文件。设置 `build_script` 后，Dockerfile 优先执行它，不再执行两个命令字段。三者都可以为空，但只有确认 Target 不需要对应步骤时才留空。`run_command` 是一次性基线验证命令，不是 AgentFuzz 的 POC；它必须能够从挂载的 `/workspace` 读取输入并将可检查结果写回 `/workspace` 或标准输出。

模型参数由 `config/__init__.py` 读取，也可以由环境变量覆盖：`AGENTFUZZ_MODEL_BASE_URL`、`AGENTFUZZ_MODEL_NAME`、`AGENTFUZZ_MODEL_API_KEY`、`AGENTFUZZ_MODEL_TEMPERATURE` 和 `AGENTFUZZ_MODEL_TIMEOUT`。`thinking` 通过 OpenAI-compatible 请求的 `extra_body` 传递；不支持该参数的服务应将其设为 `false`。API key 不会传入 Target 容器。模型请求由 AgentFuzz 宿主机进程发送，Target Docker 容器不需要模型 SDK 或模型 key。

## 二、必须编写的 Target 定制文件

### 1. Dockerfile（可选覆盖）

默认模板 `targets/default.Dockerfile` 已提供 Python 运行时、基础系统工具、源码复制、依赖/构建命令执行和插桩入口。大多数 Python Target 只需配置 `python_version`、`install_command` 和可选的 `build_command`/`build_script`，不需要单独 Dockerfile。Z3 求解器属于 AgentFuzz 宿主机侧依赖，由根目录 `requirements.txt` 安装；不要把 py-conbyte 或第二套求解环境写入 Target Dockerfile。只有以下内容与默认模板不同，才编写 `targets/<目标>/Dockerfile` 并在配置中填写 `target.dockerfile`：基础镜像或语言运行时、额外系统包、特殊构建工具链、必须在镜像阶段准备的目录或环境。Dockerfile 不包含漏洞调用链、CodeQL 查询、模型配置或 POC 逻辑。构建上下文由 `scripts/build_target_image.py` 自动生成，源码来自 `repo_url` 和 `expected_commit`。

### 2. 插桩脚本

`targets/<目标>/instrument.sh` 在镜像构建阶段执行，只能修改构建上下文中的 Target 副本。脚本接收以下环境变量：`AGENTFUZZ_TARGET_ROOT` 是 Target 根目录，`AGENTFUZZ_TRACE_ROOT` 包含 `cetracer.py`、四个规则 JSON 和 `instrumentation.json`。脚本必须：

1. 找到真正承载 Target 处理逻辑的进程入口；
2. 在该入口注入一次 `cetracer.start_ce_trace(...)`；
3. 使用 `AGENTFUZZ_TRACE_ROOT/rules/` 中的 `enter_hook.json`、`oracle.json`、`if.json` 和 `dsc.json`；
4. 使用配置的 `startup_delay`；
5. 当入口文件、注入锚点或规则文件不存在时立即退出并使 Docker 构建失败。

插桩必须保留 AgentFuzz 的四个日志路径：`/tmp/hook.log`、`/tmp/if.log`、`/tmp/callstack.log` 和 `/tmp/oracle.log`。长期运行进程和每次 POC 调用都必须使用同一套路径。默认启动宽限期为 40 秒；短生命周期命令可以在确认进程启动后立即处理输入的情况下将 `startup_delay` 设为 `0`。

### 3. POC 适配器

`poc.<目标适配器模块>:connect_with_auth` 接收一个字符串参数，并完成四件事：将字符串写入 Target 能接受的输入格式；向正在运行的 Target 提交该输入；等待该次处理完成；Target 或提交过程失败时抛出异常。适配器必须从环境变量读取容器名、输入模板、输入文件、payload 字段、Target 命令和超时，不得依赖当前机器地址或未配置的外部服务。

POC 运行时可使用以下约定环境变量：`AGENTFUZZ_TARGET_CONTAINER`、`AGENTFUZZ_WORKFLOW_TEMPLATE`、`AGENTFUZZ_WORKFLOW_FILE`、`AGENTFUZZ_CONTAINER_WORKFLOW_FILE`、`AGENTFUZZ_PAYLOAD_PATH`、`AGENTFUZZ_TARGET_COMMAND` 和 `AGENTFUZZ_TARGET_TIMEOUT`。如果 Target 不是 JSON 工作流，适配器可以使用 HTTP、CLI、消息队列或其他真实接口，但必须保持同一个 `connect_with_auth(payload)` 接口。

## 三、安装依赖和准备环境

在宿主机安装 Docker、Python 3.10、CodeQL CLI 2.19.2 和 Git。CodeQL CLI 版本必须与 `ql/codeql-pack.lock.yml` 兼容。创建 AgentFuzz 虚拟环境并安装固定依赖：

```bash
cd <AGENTFUZZ_DIR>
python3 -m venv .workspace/agentfuzz-venv
.workspace/agentfuzz-venv/bin/python -m pip install --upgrade pip
.workspace/agentfuzz-venv/bin/pip install -r requirements.txt
# 必须由同一个 AgentFuzz Python 环境加载 z3-solver
.workspace/agentfuzz-venv/bin/python -c 'import z3; print(z3.get_version_string())'
```

`generate_z3.py` 会把当前条件表达式生成临时 Python 求解脚本，并使用运行 AgentFuzz 的同一个 Python 解释器执行它。因此不能用系统 `python3` 代替 AgentFuzz 虚拟环境，也不再需要创建 Python 3.7、pipenv 或单独的 `py-conbyte` 环境。上面的检查必须输出 `z3-solver` 的版本；若 `import z3` 失败，应先重新安装 `requirements.txt`。

如果使用 `scripts/reproduce.py`，CodeQL pack 会按 `analysis.packs` 自动下载到 CodeQL 用户缓存。若所在环境不能联网，应预先下载这些 pack，并将 `analysis.download_packs` 设为 `false`；`analysis.pack_cache` 必须指向已经存在的缓存目录。

AgentFuzz 的静态分析只需要 CodeQL 数据库，不要求把 Target 的 Python 依赖安装到宿主机。Target 运行依赖由 Dockerfile 内的 `install_command` 和 `build_command` 安装；AgentFuzz 自身依赖（包括 `z3-solver`）安装在宿主机的 AgentFuzz 虚拟环境中。

## 四、生成静态分析规则

使用配置驱动脚本完成源码获取、提交校验、CodeQL 建库、三个内置查询执行和 SARIF 转 JSON：

```bash
cd <AGENTFUZZ_DIR>
python3 scripts/analyze_target.py --config config.json
```

脚本会将源码放在 `.workspace/target-source/<target_name>`，数据库放在 `analysis.database`，SARIF 和转换后的 JSON 放在 `analysis.output`。三个 QL 文件固定为仓库内的 `ql/get_if.ql`、`ql/get_callchain_and_location.ql` 和 `ql/get_dataflow_str_constraint.ql`，不需要写入配置；SARIF 由脚本自动生成。四个结果文件固定为 `if.json`、`oracle.json`、`enter_hook.json` 和 `dsc.json`。`if.json` 的条件规则只需要提供原有的 `expr` 等字段，当前 `generate_z3.py` 直接接收表达式，不再读取 `input_vars` 或 `function_code`。`oracle.json` 可以为空；这表示查询没有找到调用链，不表示转换器失败。使用 `main.py` 时，`agentfuzz.call_chain` 必须精确对应 `oracle.json` 的键；运行全部调用链时可以通过调用方设置 `CALLCHAIN`，但每个调用链仍必须来自该文件，不能手工伪造。

## 五、构建并验证 Target 镜像

先构建带依赖和插桩的镜像：

```bash
python3 scripts/build_target_image.py --config config.json
```

脚本会校验目标提交，建立 `.workspace/target-build/<target_name>` 构建上下文，并生成镜像 `agentfuzz-target:<target_name>`。构建失败表示源码、安装命令、插桩锚点或规则文件不满足配置，必须修复配置或定制文件后重新构建。

然后运行一次性基线命令：

```bash
python3 scripts/run_target.py --config config.json
```

该命令将 `target.workspace` 挂载为容器内 `/workspace`，执行 `target.run_command`，输出命令日志并在结束后删除一次性容器。复现者必须在配置中准备好 `run_command` 所需的输入文件，并检查该命令的退出码、输出和工作区结果；不能把一次性基线命令当成 fuzzing。

## 六、启动 Target 并运行 AgentFuzz

AgentFuzz 的 POC 需要 Target 容器持续运行。使用和配置相同的镜像、容器名和工作区启动空闲容器：

```bash
docker run -d --name <CONTAINER_NAME> --platform linux/amd64 \
  -v "$PWD/<WORKSPACE>:/workspace" \
  agentfuzz-target:<TARGET_NAME> tail -f /dev/null
```

配置中的 `agentfuzz.poc_test_payload` 是一次固定的、不会破坏环境的连通性输入。一键脚本在启动长期容器后先调用 POC 适配器提交该输入；该调用失败时停止 fuzzing，并将输出写入 `poc-test.log`。手工运行时也必须先完成等价的 POC 连通性检查，再启动 fuzzing：

```bash
AGENTFUZZ_TARGET_CONTAINER=<CONTAINER_NAME> \
  <AGENTFUZZ_DIR>/.workspace/agentfuzz-venv/bin/python -c \
  'from <POC_MODULE> import connect_with_auth; connect_with_auth(<POC_TEST_PAYLOAD>)'
```

其中 `<POC_TEST_PAYLOAD>` 必须替换为配置中同一个字符串的 Python 字面量；不能把占位符原样执行。

之后启动完整 fuzzing。变量变异命中 `if` 规则后，当前 Fuzzer 将该规则的 `expr` 交给 `generate_z3.get_z3_result(expr)`；求解结果回填到 Prompt，之后仍按原有 DSC、评分和调度流程继续。若表达式无法由当前适配器可靠转换、无解或求解器进程失败，本轮变量求解返回空结果，Fuzzer 继续原有后续流程，不会伪造输入。生成的临时求解脚本默认位于宿主机 `/tmp/z3_script_tmp.py`，不属于 Target 容器或规则 JSON。

之后启动完整 fuzzing：

```bash
AGENTFUZZ_TARGET_CONTAINER=<CONTAINER_NAME> \
  <AGENTFUZZ_DIR>/.workspace/agentfuzz-venv/bin/python main.py \
  --iteration <ITERATION_COUNT> \
  --application_name <APPLICATION_NAME> \
  --hook_result_file /tmp/hook.log \
  --if_result_file /tmp/if.log \
  --call_stack_result_file /tmp/callstack.log \
  --oracle_result_file /tmp/oracle.log
```

`main.py` 的 Click 命令使用短选项或长选项，等价写法是 `-i`、`-app`、`-hr`、`-ir`、`-cr` 和 `-or`。默认 AgentFuzz 超时为 300 秒；复现者可以设置 `AGENTFUZZ_FUZZ_TIMEOUT`，但该变量只改变等待上限，不改变变异、评分、Oracle 或成功判定逻辑。每次调用都会清空四个日志、提交模型生成的输入、复制并解析日志，然后进入下一次变异。

一键流程使用：

```bash
python3 scripts/reproduce.py --config config.json --duration 900 --iterations 100
```

该脚本依次执行静态分析、镜像构建、基线运行、启动长期容器和 fuzzing，并在成功、失败或中断时删除配置的 Target 容器。`--skip-analysis` 和 `--skip-baseline` 只适用于已经明确保留并核对对应产物的续跑，不应作为首次复现步骤。脚本不会删除 `.workspace` 中的源码、数据库、规则、输入、日志或结果。

## 七、结果和完整性检查

所有产物位于 `.workspace`：

- `target-source/<target_name>/`：已校验提交的 Target 源码；
- `codeql/<target_name>/`：CodeQL 数据库；
- `static-analysis/<target_name>/sarif/`：三个内置查询自动生成的 SARIF；
- `static-analysis/<target_name>/output/`：四个 AgentFuzz 规则 JSON；
- `fuzz-results/<target_name>/baseline.log`：基线命令日志；
- `fuzz-results/<target_name>/poc-test.log`：固定 POC 连通性检查日志；
- `fuzz-results/<target_name>/agentfuzz.log`：AgentFuzz 标准输出和错误输出；
- `fuzz-results/<target_name>/runtime-logs/`：四个运行时日志；
- `fuzz-results/<target_name>/manifest.json`：运行参数、开始/结束时间、退出码和错误信息。

检查顺序必须是：确认 `manifest.json` 中没有错误并记录了退出码；确认四个规则 JSON 都是合法 JSON；确认 Target 容器日志和基线结果符合 Target 自身的成功条件；确认 `oracle.log`、`hook.log`、`if.log`、`callstack.log` 是本次运行产生的文件；最后再读取 AgentFuzz 输出中的 `exploration successful`。该字段是 AgentFuzz 自身的成功判定，不等价于 Target 漏洞是否存在；是否命中漏洞必须依据对应 Oracle 规则、运行时日志和 Target 结果共同判断。

### 查看成功 Prompt

AgentFuzz 将每次运行最终保留下来的输入打印在 `FINAL PROMPT` 标记之间，并在后面的 `exploration successful` 标记处打印 `True` 或 `False`。`True` 表示该 Prompt 经过 AgentFuzz 的 Oracle 匹配并重新执行验证，可以作为待人工复核的漏洞 PoC 候选；它不表示漏洞已经被人工确认。`False` 或空的 Prompt 表示本次运行没有得到成功的 PoC 候选。

使用一键脚本时，在以下文件中查看这些内容：

```text
.workspace/fuzz-results/<target_name>/agentfuzz.log
```

每个 AgentFuzz 会话最多输出一个最终 Prompt。若一键脚本因单次会话提前结束而启动多个会话，`agentfuzz.log` 会按会话顺序包含多个 `FINAL PROMPT`/`exploration successful` 段落；逐段读取，不要只看文件末尾。手工运行 `main.py` 时，同样的内容直接显示在终端。中间尝试过但未成为最终结果的候选 Prompt 不会作为独立 PoC 文件保存。

可以用以下命令定位结果：

```bash
rg -n -A2 -B1 'FINAL PROMPT|exploration successful' \
  .workspace/fuzz-results/<target_name>/agentfuzz.log
```

确认某段为 `True` 后，还必须结合该段对应的 `oracle.log`、调用链日志和 Target 实际行为进行人工复核；不能仅凭 `True` 或 Prompt 文本下漏洞结论。

## 八、清理

一键脚本会自动删除长期运行的 Target 容器。手工运行时必须执行：

```bash
docker container rm --force <CONTAINER_NAME>
```

删除容器不会删除 `.workspace` 中的复现结果。只有在确认不再需要数据库、构建上下文或日志后，才由复现者自行清理这些大型产物。

## 九、当前配置示例

仓库当前提供的 `config.json` 使用 AgentScope `v0.0.4` 的固定提交作为示例。它展示了一个 JSON 工作流 POC：Target 工作区中的 `rce.json` 是版本对应的输入模板，`poc/agentscope/poc.py` 将 AgentFuzz 字符串写入 `1.data.args.name`，然后在长期运行的容器中执行 `as_workflow`。该配置直接使用默认 Dockerfile；仓库中的 `targets/agentscope/Dockerfile` 仅作为需要覆盖默认环境时的参考。其他普通 Python Target 也应优先使用默认模板。替换其他 Target 时，应替换配置中的仓库、提交、输出目录、插桩脚本、输入模板、POC 模块和 `poc_test_payload`；不应复制当前示例的调用链、文件名或 payload 字段。
