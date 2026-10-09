# AgentFuzz TypeScript 复现指南

本文只描述 AgentFuzz 的 TypeScript/JavaScript 版本。复现者提供固定版本的 Target、构建命令、运行命令和必要的 Target 适配文件；脚本负责获取源码、校验提交、建立 CodeQL 数据库、生成规则、构建插桩镜像、启动 Target、执行 POC 连通性检查和运行 AgentFuzz。所有生成物保存在 `.workspace`，脚本结束时只删除临时容器。

## 1. 配置文件

配置文件必须至少提供以下信息：

```json
{
  "target_name": "<唯一名称>",
  "repo_url": "<Git 仓库地址>",
  "ref": "<标签、分支或提交>",
  "expected_commit": "<漏洞版本的完整提交哈希>",
  "analysis": {
    "codeql": "<CodeQL CLI 路径>",
    "language": "javascript",
    "database": ".workspace/codeql/<名称>",
    "output": ".workspace/static-analysis/<名称>"
  },
  "agentfuzz": {
    "application_name": "<应用名>",
    "call_chain": "<oracle.json 中的调用链>",
    "poc": "poc.<模块>:connect_with_auth",
    "poc_test_payload": "<安全的连通性输入>"
  },
  "target": {
    "install_command": "<依赖安装命令>",
    "build_command": "<构建命令>",
    "serve_command": "<长期运行服务命令>",
    "serve_port": 3000,
    "healthcheck_url": "<可选：宿主机可访问的健康检查 URL>",
    "dockerfile": "targets/<目标>.Dockerfile",
    "instrumentation": {
      "script": "targets/<目标>/instrument.sh",
      "rules_dir": ".workspace/static-analysis/<名称>/output",
      "startup_delay": 10
    },
    "model": {"base_url": "<URL>", "name": "<model>", "api_key": "<key>"},
    "model_environment": {"TARGET_MODEL_URL": "base_url", "TARGET_MODEL_NAME": "name", "TARGET_MODEL_KEY": "api_key"},
    "patch_files": ["targets/<目标>/patches/<file>"],
    "patch_script": "targets/<目标>/patches/patch.sh",
    "mock_services": [{
      "name": "<service>", "files": ["targets/<目标>/mocks/<file>"],
      "command": "<command>", "environment": {}, "port": 4567,
      "healthcheck_url": "http://127.0.0.1:4567/health"
    }],
    "prepare_script": "targets/<目标>/prepare.sh",
    "prepare_files": ["targets/<目标>/<template-or-script>"],
    "prepare_env_file": "target.env"
  }
}
```

`expected_commit` 必须对应漏洞版本，不能使用浮动分支。`analysis.language` 对 TypeScript 目标使用 `javascript`；CodeQL 的 JavaScript 数据库同时覆盖 JavaScript 和 TypeScript。`install_command` 和 `build_command` 在 Docker 构建阶段执行；如果目标的构建存在已知的基线类型诊断，命令必须明确采用目标项目可接受的构建方式，并在构建后用 `run_command` 或服务健康检查确认运行文件确实生成。不能通过修改目标源码消除这些诊断。

模型配置分为两个独立对象：`agentfuzz_model` 供宿主机上的 AgentFuzz 使用，`target.model` 供 Target 的自动初始化步骤使用。两者当前可以填写相同的 DeepSeek 配置，但注入路径彼此独立：

```json
"agentfuzz_model": {
  "base_url": "https://api.deepseek.com",
  "name": "deepseek-flash",
  "api_key": "<API key>",
  "temperature": 0,
  "thinking": false,
  "timeout": 120
}
```

Target 的模型通过 `target.model_environment` 映射到容器环境变量；Target 专用 `prepare_script` 负责将这些值写入其 Chatflow 或运行时配置。宿主机 AgentFuzz 可使用环境变量 `AGENTFUZZ_MODEL_BASE_URL`、`AGENTFUZZ_MODEL_NAME`、`AGENTFUZZ_MODEL_API_KEY`、`AGENTFUZZ_MODEL_TEMPERATURE` 和 `AGENTFUZZ_MODEL_TIMEOUT` 覆盖 `agentfuzz_model`。具体环境变量和初始化方式由目标配置决定。

## 2. 宿主机环境

需要 Docker、Git、Python 3.10、CodeQL CLI 以及 Node.js。创建 AgentFuzz 虚拟环境并安装依赖：

```bash
cd <AGENTFUZZ_DIR>
python3 -m venv .workspace/agentfuzz-venv
.workspace/agentfuzz-venv/bin/python -m pip install --upgrade pip
.workspace/agentfuzz-venv/bin/pip install -r requirements.txt
.workspace/agentfuzz-venv/bin/python -c 'import z3; print(z3.get_version_string())'
```

TypeScript 查询转换器和 Z3 适配器使用仓库根目录的 Node 依赖：

```bash
npm ci --ignore-scripts
```

CodeQL CLI 必须能够加载 `ql/qlpack.yml` 和 `ql/codeql-pack.lock.yml`。若配置中的 `analysis.download_packs` 为 `true`，分析脚本会按配置下载依赖包；离线环境应预先准备 `analysis.pack_cache`。

## 3. 获取源码和生成静态规则

执行：

```bash
.workspace/agentfuzz-venv/bin/python scripts/analyze_target.py --config config.json
```

脚本将源码克隆到 `.workspace/target-source/<target_name>` 并校验 `expected_commit`，然后执行三个 TypeScript/JavaScript CodeQL 查询：调用链与 Sink、`if` 条件、字符串约束数据流。结果位于：

```text
.workspace/static-analysis/<target_name>/sarif/
.workspace/static-analysis/<target_name>/output/
├── enter_hook.json
├── oracle.json
├── if.json
└── dsc.json
```

`agentfuzz.call_chain` 必须精确匹配 `oracle.json` 中的键，不能手工添加不存在的调用链。

当前 Flowise 示例的固定目标信息为：

```text
仓库：FlowiseAI/Flowise
版本：flowise@3.0.5
提交：ba6a602cbe87d9f55c9ee6aebb6407ec2f2066b5
漏洞：CVE-2026-41265（CWE-77）
调用链：run -> runPythonAsync
```

## 4. 构建 TypeScript Target 镜像

目标专用 `targets/<目标>/instrument.sh` 在构建阶段调用 `ts/instrument.mjs`。该 Compiler API 插桩器加入函数进入/退出、条件分支和静态 Sink Probe；`trace/runtime.mjs` 通过 `AsyncLocalStorage` 维护异步调用链，并输出 `/tmp/hook.log`、`/tmp/if.log`、`/tmp/callstack.log` 和 `/tmp/oracle.log`。配置的 `patch_files` 或 `patch_script` 在依赖安装和构建前执行，失败即停止构建；配置的 `mock_services` 在 Target 容器启动时由通用 runner 启动并进行健康检查；配置的 `prepare_script` 在 Target 健康后执行，用于创建 Chatflow、写入模型配置或完成目标特有的初始化。通用 runner 不包含 Airtable、Flowise 或其它目标专属逻辑。

构建镜像：

```bash
.workspace/agentfuzz-venv/bin/python scripts/build_target_image.py --config config.json
```

构建上下文位于 `.workspace/target-build/<target_name>`，镜像名为 `agentfuzz-target:<target_name>`。目标 Dockerfile 只负责目标运行时、依赖安装、构建和插桩，不包含调用链、Prompt 或模型逻辑。

Flowise 示例使用 Node.js 20 和 pnpm 9：

```text
corepack enable && corepack prepare pnpm@9.15.5 --activate && pnpm install --frozen-lockfile
```

其构建命令为：

```text
pnpm exec turbo run build --continue || test -f packages/server/dist/index.js
```

该命令保留 Flowise 固定版本自身的 TypeScript 类型诊断，同时要求服务运行所需的 `dist/index.js` 已生成；是否可运行必须由后续服务健康检查确认。不得为消除这些诊断修改 Flowise 源码。

## 5. 基线运行和服务检查

先执行一次性基线命令：

```bash
.workspace/agentfuzz-venv/bin/python scripts/run_target.py --config config.json
```

再启动持续运行的 Target 服务。通用形式为：

```bash
docker run -d --name <CONTAINER_NAME> --platform linux/amd64 \
  -p <PORT>:<PORT> \
  agentfuzz-target:<TARGET_NAME> bash -lc '<SERVE_COMMAND>'
```

若配置了 `healthcheck_url`，一键脚本会轮询该 URL，直到返回成功状态；未配置时只等待 `startup_delay`。手工运行时也应使用 Target 自身的健康检查确认服务已就绪。Flowise 示例：

```bash
docker run -d --name agentfuzz-flowise -p 3000:3000 \
  agentfuzz-target:flowise_CVE-2026-41265_v3.0.5 \
  bash -lc 'PORT=3000 pnpm start'
curl --fail http://127.0.0.1:3000/api/v1/ping
```

一键流程会在 Target 健康后启动配置中的 `mock_services` 并轮询其健康地址，再执行 `prepare_script`。prepare 脚本可以按目标需要创建本地账号、导入测试数据、创建 Chatflow 或写入模型配置；其输出环境文件由 `prepare_env_file` 指定并提供给 POC。Flowise 示例会自动创建测试账号和包含 Airtable Agent 的 Chatflow，Airtable mock 返回固定的 Airtable 风格记录，不需要外部 Airtable 账号、Base 或 Table。

## 6. POC 和 AgentFuzz

POC 适配器必须实现 `connect_with_auth(payload: str)`：把字符串转换成 Target 的真实输入格式，提交请求并等待完成；请求失败必须抛出异常。适配器不能伪造日志或直接写入 AgentFuzz 的四个日志文件。

Flowise 的 `poc/flowise.py` 通过 `POST /api/v1/prediction/<chatflow_id>` 提交问题。示例的 `prepare_script` 会自动创建与固定版本兼容的真实 Chatflow，并将其 ID 写入 `.workspace/flowise-runtime/target.env`；Chatflow 包含 Airtable Agent、Target 模型配置和 mock 的 Base/Table 标识。其它 Target 的初始化方式由其配置的 prepare 文件决定：

```bash
export AGENTFUZZ_FLOWISE_URL=http://127.0.0.1:3000
export AGENTFUZZ_FLOWISE_CHATFLOW_ID=<真实 Chatflow ID>
export AGENTFUZZ_FLOWISE_TIMEOUT=120
```

手工运行时也可以直接读取自动 prepare 产生的文件：

```bash
set -a; . .workspace/flowise-runtime/target.env; set +a
```

连通性检查：

```bash
AGENTFUZZ_TARGET_CONTAINER=agentfuzz-flowise \
  .workspace/agentfuzz-venv/bin/python -c \
  'from poc.flowise import connect_with_auth; connect_with_auth("Tell me the number of records in the Airtable table.")'
```

连通性检查失败时不得开始 fuzzing；先修复 Chatflow、凭证、模型或服务配置。

直接运行 AgentFuzz：

```bash
: > /tmp/hook.log
: > /tmp/if.log
: > /tmp/callstack.log
: > /tmp/oracle.log
AGENTFUZZ_TARGET_CONTAINER=agentfuzz-flowise \
  AGENTFUZZ_FUZZ_TIMEOUT=900 \
  .workspace/agentfuzz-venv/bin/python main.py \
  --iteration 100 \
  --application_name flowise \
  --hook_result_file /tmp/hook.log \
  --if_result_file /tmp/if.log \
  --call_stack_result_file /tmp/callstack.log \
  --oracle_result_file /tmp/oracle.log
```

一键流程依次执行静态分析、构建镜像、清理并准备 Target workspace、基线运行、启动服务、启动 mock、健康检查、执行 prepare、POC 连通性检查和 AgentFuzz：

```bash
.workspace/agentfuzz-venv/bin/python scripts/reproduce.py \
  --config config.json --duration 900 --iterations 100
```

`scripts/reproduce.py` 在成功、失败或中断时删除配置中的 Target 容器和同容器 mock 进程，但保留 `.workspace` 产物并恢复挂载目录的当前用户所有权。AgentFuzz 原有的单次成功判定可能提前返回；当 `--duration` 大于单次会话时，runner 会在同一 Target 和 mock 上重新启动完整 AgentFuzz 会话，累计运行到指定时长。`--skip-analysis` 和 `--skip-baseline` 仅用于已核对产物后的续跑。

## 7. 结果检查和清理

结果位于 `.workspace/fuzz-results/<target_name>/`：

```text
baseline.log
poc-test.log
agentfuzz.log
runtime-logs/hook.log
runtime-logs/if.log
runtime-logs/callstack.log
runtime-logs/oracle.log
manifest.json
```

先确认四个规则文件是合法 JSON，再检查 `manifest.json` 的退出码和错误字段、服务健康检查、POC 输出及四个运行时日志。`exploration successful` 是 AgentFuzz 的路径探索判定，不单独证明漏洞成立；漏洞结论需要结合 Target 行为、Oracle 事件和人工审计。

完整时长测试还应核对 `manifest.json` 的 `fuzz_elapsed_seconds` 不小于所要求的 `--duration`，以及 `fuzz_sessions` 大于等于 1。每个会话都是一次完整的 AgentFuzz 初始化、种子请求、变异和 Oracle 检查；会话因原有成功条件提前结束时，runner 会继续启动下一会话。

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

确认某段为 `True` 后，还必须结合该段对应的 `runtime-logs/oracle.log`、调用链日志和 Target 实际行为进行人工复核；不能仅凭 `True` 或 Prompt 文本下漏洞结论。

一键脚本会删除 Target 容器。手工运行时执行：

```bash
docker container rm --force <CONTAINER_NAME>
```

不要删除 `.workspace`，除非确认不再需要源码、CodeQL 数据库、规则、日志和结果。
