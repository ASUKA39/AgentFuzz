ARG NODE_VERSION=20
FROM node:${NODE_VERSION}-bookworm

ENV CI=true \
    NODE_ENV=development \
    AGENTFUZZ_TRACE=1

RUN corepack enable
WORKDIR /opt/target
COPY . /opt/target/
COPY .target-build-config.json /opt/target-build-config.json

RUN node - <<'NODE'
const fs = require('node:fs')
const cp = require('node:child_process')
const cfg = JSON.parse(fs.readFileSync('/opt/target-build-config.json', 'utf8'))
if (cfg.install_command) cp.execFileSync('/bin/bash', ['-lc', cfg.install_command], { cwd: '/opt/target', stdio: 'inherit' })
NODE

COPY .agentfuzz /opt/agentfuzz
ENV NODE_OPTIONS=--import=/opt/agentfuzz/runtime.mjs
RUN if [ -f /opt/agentfuzz/instrument.sh ]; then \
      chmod +x /opt/agentfuzz/instrument.sh && \
      AGENTFUZZ_TARGET_ROOT=/opt/target \
      AGENTFUZZ_TRACE_ROOT=/opt/agentfuzz \
      bash /opt/agentfuzz/instrument.sh; \
    fi

RUN node - <<'NODE'
const fs = require('node:fs')
const cp = require('node:child_process')
const cfg = JSON.parse(fs.readFileSync('/opt/target-build-config.json', 'utf8'))
if (cfg.build_command) cp.execFileSync('/bin/bash', ['-lc', cfg.build_command], { cwd: '/opt/target', stdio: 'inherit' })
NODE

CMD ["bash"]
