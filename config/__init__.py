"""
The Config module
"""
import json
import os
from pathlib import Path


def _model_config():
    """Load the optional model section from the repository config.

    Environment variables take precedence so the same checkout can be used
    with another endpoint without changing source code or the checked-in
    configuration.
    """
    configured = {}
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    try:
        configured = json.loads(config_path.read_text(encoding="utf-8")).get("model", {})
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "name": os.environ.get("AGENTFUZZ_MODEL_NAME", configured.get("name", "gpt-4o")),
        "base_url": os.environ.get(
            "AGENTFUZZ_MODEL_BASE_URL",
            configured.get("base_url", "https://api.openai.com/v1"),
        ),
        "api_key": os.environ.get(
            "AGENTFUZZ_MODEL_API_KEY", configured.get("api_key", ""),
        ),
        "temperature": float(
            os.environ.get(
                "AGENTFUZZ_MODEL_TEMPERATURE",
                configured.get("temperature", 0),
            ),
        ),
        "timeout": float(
            os.environ.get(
                "AGENTFUZZ_MODEL_TIMEOUT",
                configured.get("timeout", configured.get("request_timeout", 120)),
            ),
        ),
        "thinking": bool(configured.get("thinking", False)),
    }


_MODEL = _model_config()

# Tool Description
__description__ = 'Make Agent Defeat Agent'

# Tool Version
__version__ = '1.0.0'

# Tool Name
__prog__ = 'AgentFuzz'

__max_population__ = 10

__gpt_version__ = _MODEL["name"]
__gpt__temperature__ = _MODEL["temperature"]
__model_timeout__ = _MODEL["timeout"]
__model_thinking__ = _MODEL["thinking"]

OPENAI_API_BASE = _MODEL["base_url"]
OPENAI_API_KEY = _MODEL["api_key"]
