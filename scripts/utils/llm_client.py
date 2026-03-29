"""Multi-provider LLM client using httpx.

Supports: anthropic, openai, gemini, custom (e.g. Runway proxy).
Provider selection via constructor arg or LLM_PROVIDER env var.
API keys from env: ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY,
or CUSTOM_LLM_BASE_URL + CUSTOM_LLM_API_KEY.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


class LLMClient:
    """Thin wrapper around LLM provider HTTP APIs."""

    def __init__(self, provider: str | None = None, api_key: str | None = None):
        self.provider = provider or os.environ.get("LLM_PROVIDER", "anthropic")
        self._api_key = api_key
        self._http = httpx.Client(timeout=180)

    # -- public API ----------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        system: str | None = None,
        temperature: float = 0,
        max_tokens: int = 8192,
    ) -> str:
        """Send messages, return assistant text."""
        dispatch = {
            "anthropic": self._chat_anthropic,
            "openai": self._chat_openai,
            "gemini": self._chat_gemini,
            "runway": self._chat_runway,
            "custom": self._chat_custom,
        }
        fn = dispatch.get(self.provider)
        if fn is None:
            raise ValueError(f"Unknown provider: {self.provider}")
        return fn(
            messages,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0,
        max_tokens: int = 8192,
    ) -> dict:
        """Convenience: send system+user prompt, parse JSON from response."""
        messages = [{"role": "user", "content": user_prompt}]
        raw = self.chat(
            messages,
            model=model,
            system=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _extract_json(raw)

    # -- Anthropic -----------------------------------------------------------

    def _key_anthropic(self) -> str:
        return self._api_key or os.environ["ANTHROPIC_API_KEY"]

    def _chat_anthropic(self, messages, *, model, system, temperature, max_tokens) -> str:
        model = model or "claude-haiku-4-5-20251001"
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": messages,
        }
        if system:
            payload["system"] = system
        resp = self._http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._key_anthropic(),
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return _extract_anthropic_text(data)

    # -- OpenAI --------------------------------------------------------------

    def _key_openai(self) -> str:
        return self._api_key or os.environ["OPENAI_API_KEY"]

    def _chat_openai(self, messages, *, model, system, temperature, max_tokens) -> str:
        model = model or "gpt-4o-mini"
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        resp = self._http.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._key_openai()}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": msgs,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    # -- Gemini --------------------------------------------------------------

    def _key_gemini(self) -> str:
        return self._api_key or os.environ["GEMINI_API_KEY"]

    def _chat_gemini(self, messages, *, model, system, temperature, max_tokens) -> str:
        model = model or "gemini-2.5-flash"
        contents = []
        for m in messages:
            contents.append({
                "role": "user" if m["role"] == "user" else "model",
                "parts": [{"text": m["content"]}],
            })
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        resp = self._http.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self._key_gemini(),
            },
            json=payload,
        )
        resp.raise_for_status()
        return _extract_gemini_text(resp.json())

    # -- Runway (Bedrock proxy for Claude) ------------------------------------

    _RUNWAY_CLAUDE_URL = "https://runway.devops.rednote.life/openai/bedrock_runtime/model/invoke"

    def _key_runway(self) -> str:
        return self._api_key or os.environ.get("RUNWAY_CLAUDE_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", "")

    def _chat_runway(self, messages, *, model, system, temperature, max_tokens) -> str:
        # Runway Bedrock proxy uses Anthropic messages format but:
        # - auth header is "token" (not x-api-key)
        # - needs anthropic_version: "bedrock-2023-05-31"
        # - NO "model" field in body — the gateway routes to the model
        #   (currently Claude Opus 4.6) based on the auth token, not the request.
        # The `model` param is accepted but intentionally ignored.
        formatted_messages = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, str):
                content = [{"type": "text", "text": content}]
            formatted_messages.append({"role": m["role"], "content": content})

        payload: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": formatted_messages,
        }
        if system:
            payload["system"] = system
        resp = self._http.post(
            self._RUNWAY_CLAUDE_URL,
            headers={
                "token": self._key_runway(),
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return _extract_anthropic_text(resp.json())

    # -- Custom (e.g. Runway proxy) -----------------------------------------

    def _chat_custom(self, messages, *, model, system, temperature, max_tokens) -> str:
        base_url = os.environ.get("CUSTOM_LLM_BASE_URL", "")
        api_key = self._api_key or os.environ.get("CUSTOM_LLM_API_KEY", "")
        header_name = os.environ.get("CUSTOM_LLM_AUTH_HEADER", "Authorization")
        header_value = os.environ.get("CUSTOM_LLM_AUTH_VALUE", f"Bearer {api_key}")
        if not base_url:
            raise ValueError("CUSTOM_LLM_BASE_URL not set")

        # Default: OpenAI-compatible format
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        payload: dict[str, Any] = {
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if model:
            payload["model"] = model
        resp = self._http.post(
            base_url,
            headers={
                header_name: header_value,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        # Try OpenAI format first, then Anthropic format
        if "choices" in data:
            return data["choices"][0]["message"]["content"]
        return _extract_anthropic_text(data)


# -- helpers -----------------------------------------------------------------

def _extract_anthropic_text(data: dict) -> str:
    parts = []
    for block in data.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block["text"])
    return "".join(parts).strip()


def _extract_gemini_text(data: dict) -> str:
    candidates = data.get("candidates", [])
    if not candidates:
        return ""
    parts = candidates[0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def _extract_json(text: str) -> dict:
    """Extract JSON object from LLM response text.

    Handles: raw JSON, ```json fenced blocks, JSON embedded in prose.
    """
    # Try direct parse
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try fenced code block
    match = re.search(r"```(?:json)?\s*\n(\{.*?\})\s*\n```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find the largest { ... } block
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = None

    raise ValueError(f"Could not extract JSON from LLM response:\n{text[:500]}")
