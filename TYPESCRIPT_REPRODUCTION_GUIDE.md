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
    }
  }
}
```

`expected_commit` 必须对应漏洞版本，不能使用浮动分支。`analysis.language` 对 TypeScript 目标使用 `javascript`；CodeQL 的 JavaScript 数据库同时覆盖 JavaScript 和 TypeScript。`install_command` 和 `build_command` 在 Docker 构建阶段执行；如果目标的构建存在已知的基线类型诊断，命令必须明确采用目标项目可接受的构建方式，并在构建后用 `run_command` 或服务健康检查确认运行文件确实生成。不能通过修改目标源码消除这些诊断。

模型配置位于配置文件的 `model` 对象中，宿主机上的 AgentFuzz 读取它发送 OpenAI-compatible 请求：

```json
"model": {
  "base_url": "https://api.deepseek.com",
  "name": "deepseek-flash",
  "api_key": "<API key>",
  "temperature": 0,
  "thinking": false,
  "timeout": 120
}
```

也可以使用环境变量 `AGENTFUZZ_MODEL_BASE_URL`、`AGENTFUZZ_MODEL_NAME`、`AGENTFUZZ_MODEL_API_KEY`、`AGENTFUZZ_MODEL_TEMPERATURE` 和 `AGENTFUZZ_MODEL_TIMEOUT` 覆盖配置。模型 key 只在宿主机使用，不传入 Target 容器。

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

目标专用 `targets/<目标>/instrument.sh` 在构建阶段调用 `ts/instrument.mjs`。该 Compiler API 插桩器加入函数进入/退出、条件分支和静态 Sink Probe；`trace/runtime.mjs` 通过 `AsyncLocalStorage` 维护异步调用链，并输出 `/tmp/hook.log`、`/tmp/if.log`、`/tmp/callstack.log` 和 `/tmp/oracle.log`。

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

## 6. POC 和 AgentFuzz

POC 适配器必须实现 `connect_with_auth(payload: str)`：把字符串转换成 Target 的真实输入格式，提交请求并等待完成；请求失败必须抛出异常。适配器不能伪造日志或直接写入 AgentFuzz 的四个日志文件。

Flowise 的 `poc/flowise.py` 通过 `POST /api/v1/prediction/<chatflow_id>` 提交问题。运行前必须准备一个与固定版本兼容的真实 Chatflow，该 Chatflow 至少包含 Airtable Agent、可用的 Airtable 凭证/Base/Table 配置和运行所需的模型配置。将其 ID 通过环境变量提供：

```bash
export AGENTFUZZ_FLOWISE_URL=http://127.0.0.1:3000
export AGENTFUZZ_FLOWISE_CHATFLOW_ID=<真实 Chatflow ID>
export AGENTFUZZ_FLOWISE_TIMEOUT=120
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

一键流程依次执行静态分析、构建镜像、基线运行、启动服务、POC 连通性检查和 AgentFuzz：

```bash
.workspace/agentfuzz-venv/bin/python scripts/reproduce.py \
  --config config.json --duration 900 --iterations 100
```

`scripts/reproduce.py` 在成功、失败或中断时删除配置中的 Target 容器，但保留 `.workspace` 产物。`--skip-analysis` 和 `--skip-baseline` 仅用于已核对产物后的续跑。

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

一键脚本会删除 Target 容器。手工运行时执行：

```bash
docker container rm --force <CONTAINER_NAME>
```

不要删除 `.workspace`，除非确认不再需要源码、CodeQL 数据库、规则、日志和结果。
