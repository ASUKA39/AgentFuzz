import poc.agentzero.poc
import poc.bisheng.poc
import poc.devika.poc
import poc.ragflow.poc
import poc.openagents.poc
import poc.taskingai.poc
import poc.autogpt.poc
import poc.langflow.poc
import poc.TaskWeaver.poc
import poc.langchainchatchat.poc
import poc.chuanhu.poc
import poc.jarvis.poc
import poc.superagi.poc
import poc.dbgpt.poc
import poc.agentscope.poc
import poc.quivr.poc
import poc.vanna.poc
import importlib
import json
import os
from pathlib import Path


class MetaData:
    def __init__(self, call_chain: str, container_name: str, oracle_json: str, if_json: str, hook_json: str,
                 dsc_json: str,
                 connect_with_auth):
        self.call_chain = call_chain
        self.container_name = container_name
        self.oracle_json = oracle_json
        self.if_json = if_json
        self.dsc_json = dsc_json
        self.hook_json = hook_json
        self.connect_with_auth = connect_with_auth


def _configured_metadata(app: str):
    """Load a target adapter from the repository config when one is provided.

    Existing built-in adapters remain available below.  A new target only
    needs a JSON metadata entry and a ``module:function`` POC adapter; the
    AgentFuzz core and this factory do not need another source-code edit.
    """
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = config.get("agentfuzz", {})
    if not isinstance(entry, dict) or entry.get("application_name", app) != app:
        return None
    required = ("call_chain", "container_name", "oracle_json", "if_json", "hook_json", "dsc_json", "poc")
    missing = [key for key in required if not entry.get(key)]
    if missing:
        raise ValueError(f"config.json agentfuzz entry is missing: {', '.join(missing)}")
    module_name, separator, function_name = entry["poc"].partition(":")
    if not separator or not module_name or not function_name:
        raise ValueError("config.json agentfuzz.poc must use module:function syntax")
    module = importlib.import_module(module_name)
    connect_with_auth = getattr(module, function_name)
    return MetaData(
        entry["call_chain"],
        entry["container_name"],
        entry["oracle_json"],
        entry["if_json"],
        entry["hook_json"],
        entry["dsc_json"],
        connect_with_auth,
    )


def get_metadata(app: str):
    configured = _configured_metadata(app)
    if configured is not None:
        return configured
    factory = {
        "agentzero": MetaData(
            "WebpageContentTool.execute -> get",
            "agentzero-withoutdocker",
            "output/agentzero/oracle.json",
            "output/agentzero/agentzero-if.json",
            "output/agentzero/enter_hook.json",
            "output/agentzero/agentzero-dsc.json",
            poc.agentzero.poc.connect_with_auth
        ),
        "devika": MetaData(
            "Runner.run_code -> run",
            "devika",
            "output/devika/oracle.json",
            "output/devika/devika-if.json",
            "output/devika/enter_hook.json",
            "output/devika/devika-dsc.json",
            poc.devika.poc.connect_with_auth
        ),
        "ragflow": MetaData(
            "ExeSQL._run -> cursor.execute",
            "ragflow-server",
            "output/ragflow/win/oracle.json",
            "output/ragflow/win/ragflow-if.json",
            "output/ragflow/win/enter_hook.json",
            "output/ragflow/win/ragflow-dsc.json",
            poc.ragflow.poc.connect_with_auth
        ),
        "openagents": MetaData(
            "PythonEvaluator.run -> PythonEvaluator.run_program_local -> ip.run_cell",
            "openagents-backend-1",
            "output/openagents/oracle.json",
            "output/openagents/openagents-if.json",
            "output/openagents/enter_hook.json",
            "output/openagents/openagents-dsc.json",
            poc.openagents.poc.connect_with_auth
        ),
        "taskingai": MetaData(
            "ReadWebPage.execute -> session.get",
            "taskingai-backend-plugin-1",
            "output/TaskingAI/oracle.json",
            "output/TaskingAI/taskingai-if.json",
            "output/TaskingAI/enter_hook.json",
            "output/TaskingAI/taskingai-dsc.json",
            poc.taskingai.poc.connect_with_auth
        ),
        "autogpt": MetaData(
            "SendWebRequestBlock.run -> requests.request",
            "autogpt_platform-executor-1",
            "output/autogpt/oracle.json",
            "output/autogpt/autogpt-if.json",
            "output/autogpt/enter_hook.json",
            "output/autogpt/autogpt-dsc.json",
            poc.autogpt.poc.connect_with_auth
        ),
        "langflow": MetaData(
            "PythonREPLToolComponent.build_tool.run_python_code -> python_repl.run",
            "docker_example-langflow-1",
            "output/langflow/win/oracle.json",
            "output/langflow/win/langflow-if.json",
            "output/langflow/win/enter_hook.json",
            "output/langflow/win/langflow-dsc.json",
            poc.langflow.poc.connect_with_auth
        ),
        "Taskweaver": MetaData(
            "CodeExecutor.execute_code -> execute_code",
            "taskweaver",
            "output/TaskWeaver/oracle.json",
            "output/TaskWeaver/TaskWeaver-if.json",
            "output/TaskWeaver/enter_hook.json",
            "output/TaskWeaver/TaskWeaver-dsc.json",
            poc.TaskWeaver.poc.connect_with_auth
        ),
        "chatchat": MetaData(
            "shell -> run",
            "chatchat",
            "output/Langchain-Chatchat/oracle.json",
            "output/Langchain-Chatchat/Langchain-Chatchat-if.json",
            "output/Langchain-Chatchat/enter_hook.json",
            "output/Langchain-Chatchat/Langchain-Chatchat-dsc.json",
            poc.langchainchatchat.poc.connect_with_auth
        ),
        "chuanhu": MetaData(
            "ChuanhuAgent_Client.summary_url -> ChuanhuAgent_Client.fetch_url_content -> requests.get",
            "",
            "output/chuanhu/win/oracle.json",
            "output/chuanhu/win/chuanhu-if.json",
            "output/chuanhu/win/enter_hook.json",
            "output/chuanhu/win/chuanhu-dsc.json",
            poc.chuanhu.poc.connect_with_auth
        ),
        "jarvis": MetaData(
            "This application does not have any vulnerabilities.",
            "jarvis",
            "output/jarvis/oracle.json",
            "output/jarvis/jarvis-if.json",
            "output/jarvis/enter_hook.json",
            "output/jarvis/jarvis-dsc.json",
            poc.jarvis.poc.connect_with_auth
        ),
        "superagi": MetaData(
            "ReplaceTaskOutputHandler.handle -> eval",
            "superagi-celery-1",
            "output/superagi/oracle.json",
            "output/superagi/superagi-if.json",
            "output/superagi/enter_hook.json",
            "output/superagi/superagi-dsc.json",
            poc.superagi.poc.connect_with_auth
        ),
        "dbgpt": MetaData(
            "CodeAction.run -> CodeAction.execute_code_blocks -> execute_code -> submit",
            "dbgpt-allinone",
            "output/DB-GPT/oracle.json",
            "output/DB-GPT/DB-GPT-if.json",
            "output/DB-GPT/enter_hook.json",
            "output/DB-GPT/DB-GPT-dsc.json",
            poc.dbgpt.poc.connect_with_auth
        ),
        "agentscope": MetaData(
            "start_workflow -> build_dag -> sanitize_node_data -> is_callable_expression -> eval",
            "agentfuzz-agentscope",
            ".workspace/static-analysis/agentscope_CVE-2024-48050_v0.0.4-codeql-2.19.2/output/oracle.json",
            ".workspace/static-analysis/agentscope_CVE-2024-48050_v0.0.4-codeql-2.19.2/output/agentscope-if.json",
            ".workspace/static-analysis/agentscope_CVE-2024-48050_v0.0.4-codeql-2.19.2/output/enter_hook.json",
            ".workspace/static-analysis/agentscope_CVE-2024-48050_v0.0.4-codeql-2.19.2/output/agentscope-dsc.json",
            poc.agentscope.poc.connect_with_auth
        ),
        "quivr": MetaData(
            "",
            "",
            "output/quivr/win/oracle.json",
            "output/quivr/win/quivr-if.json",
            "output/quivr/win/enter_hook.json",
            "output/quivr/win/quivr-dsc.json",
            poc.quivr.poc.connect_with_auth
        ),
        "vanna": MetaData(
            "",
            "",
            "output/vanna/win/oracle.json",
            "output/vanna/win/vanna-if.json",
            "output/vanna/win/enter_hook.json",
            "output/vanna/win/vanna-dsc.json",
            poc.vanna.poc.connect_with_auth
        ),
        "bisheng_win": MetaData(
            "calculator -> eval",
            "bisheng-backend",
            "output/bisheng/win/oracle.json",
            "output/bisheng/win/bisheng-if.json",
            "output/bisheng/win/enter_hook.json",
            "output/bisheng/win/bisheng-dsc.json",
            poc.bisheng.poc.connect_with_auth
        )
    }
    if app not in factory.keys():
        print(f"[*] app: {app} not found, please fill in {__file__}")
        exit(0)
    return factory[app]
