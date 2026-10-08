ARG PYTHON_VERSION=3.10
FROM python:${PYTHON_VERSION}-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    ca-certificates \
    git \
    libffi-dev \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/target
COPY . /opt/target/
COPY .target-build-config.json /opt/target-build-config.json

# AgentFuzz's Z3 solver runs in the host-side AgentFuzz virtual environment.
# This image installs only the Target runtime and its dependencies.

# The build context supplies a small JSON file generated from the target
# configuration.  A target-specific build script takes precedence when the
# normal install/build commands cannot express the setup.
RUN python - <<'PY'
import json
import subprocess
from pathlib import Path

config = json.loads(Path('/opt/target-build-config.json').read_text())
root = Path('/opt/target')
script = config.get('build_script')
if script:
    script_path = root / script
    if not script_path.is_file():
        raise SystemExit(f'configured target build script does not exist: {script_path}')
    subprocess.run(['bash', str(script_path)], cwd=root, check=True)
else:
    for key in ('install_command', 'build_command'):
        command = config.get(key)
        if command:
            subprocess.run(command, cwd=root, shell=True, executable='/bin/bash', check=True)
PY

# Instrumentation is staged only when the target configuration requests it.
# The script applies a target-specific patch after dependencies are installed,
# while the tracer and generated rules remain outside the target source tree.
COPY .agentfuzz /opt/agentfuzz
COPY .target-build-config.json /opt/target-build-config.json
RUN if [ -f /opt/agentfuzz/instrument.sh ]; then \
      chmod +x /opt/agentfuzz/instrument.sh && \
      AGENTFUZZ_TARGET_ROOT=/opt/target \
      AGENTFUZZ_TRACE_ROOT=/opt/agentfuzz \
      bash /opt/agentfuzz/instrument.sh; \
    fi

# The target-specific runtime command is intentionally not baked into this
# image until it has been verified for the selected target.
CMD ["bash"]
