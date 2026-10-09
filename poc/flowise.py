"""Minimal Flowise HTTP adapter used by the TypeScript reproduction guide."""

from __future__ import annotations

import json
import os
import urllib.request


def connect_with_auth(payload: str) -> None:
    base = os.environ.get("AGENTFUZZ_FLOWISE_URL", "http://127.0.0.1:3000").rstrip("/")
    chatflow = os.environ.get("AGENTFUZZ_FLOWISE_CHATFLOW_ID")
    if not chatflow:
        raise RuntimeError("AGENTFUZZ_FLOWISE_CHATFLOW_ID must identify the configured Airtable chatflow")
    request = urllib.request.Request(
        f"{base}/api/v1/prediction/{chatflow}",
        data=json.dumps({"question": payload}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=float(os.environ.get("AGENTFUZZ_FLOWISE_TIMEOUT", "120"))) as response:
        if response.status >= 400:
            raise RuntimeError(f"Flowise returned HTTP {response.status}")
        body = response.read().decode("utf-8", errors="replace")
        print(body, flush=True)
