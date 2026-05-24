"""Minimal Ollama adapter interface for local model execution."""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Dict, List


class OllamaAdapter:
    """HTTP adapter for Ollama chat endpoint.

    The adapter is optional in Milestone-1 and not required by default runtime
    tests. It can be used by future executor implementations.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        timeout_seconds: int = 180,
        max_retries: int = 1,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))

    def chat(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        return self._chat(system_prompt, messages, json_mode=False)

    def chat_json(self, system_prompt: str, messages: List[Dict[str, str]]) -> str:
        return self._chat(system_prompt, messages, json_mode=True)

    def _chat(self, system_prompt: str, messages: List[Dict[str, str]], json_mode: bool) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "stream": False,
        }
        if json_mode:
            payload["format"] = "json"
        req = urllib.request.Request(
            url=f"{self.base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    return body.get("message", {}).get("content", "")
            except (TimeoutError, socket.timeout) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "Ollama request timed out. "
                        f"Model={self.model}, timeout={self.timeout_seconds}s, attempts={self.max_retries}."
                    ) from exc
                time.sleep(min(attempt, 3))
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        "Ollama request failed. Ensure Ollama is running and reachable "
                        f"at {self.base_url}."
                    ) from exc
                time.sleep(min(attempt, 3))

        if last_error is not None:
            raise RuntimeError(str(last_error)) from last_error
        raise RuntimeError("Ollama request failed without a captured error.")
