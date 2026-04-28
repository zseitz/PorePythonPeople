"""Minimal Ollama adapter interface for local model execution."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List


class OllamaAdapter:
    """HTTP adapter for Ollama chat endpoint.

    The adapter is optional in Milestone-1 and not required by default runtime
    tests. It can be used by future executor implementations.
    """

    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False,
        }
        req = urllib.request.Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
                return body.get("message", {}).get("content", "")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Ollama request failed. Ensure Ollama is running and reachable "
                f"at {self.base_url}."
            ) from exc
