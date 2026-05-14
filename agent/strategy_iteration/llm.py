from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


def _mojibake_score(value: str) -> int:
    markers = ("Ã", "Â", "â€", "â", "ã€", "ï¼", "ï½", "å", "æ", "ç", "è", "é")
    c1_controls = sum(1 for char in value if 0x80 <= ord(char) <= 0x9F)
    return c1_controls * 4 + sum(value.count(marker) for marker in markers)


def _cjk_count(value: str) -> int:
    return sum(1 for char in value if "\u4e00" <= char <= "\u9fff")


def _repair_mojibake(value: Any) -> Any:
    """Repair common UTF-8-as-Latin-1 mojibake from OpenAI-compatible proxies."""
    if isinstance(value, str):
        try:
            repaired = value.encode("latin1").decode("utf-8")
        except UnicodeError:
            return value
        if _mojibake_score(repaired) < _mojibake_score(value) or _cjk_count(repaired) > _cjk_count(value):
            return repaired
        return value
    if isinstance(value, list):
        return [_repair_mojibake(item) for item in value]
    if isinstance(value, dict):
        return {
            _repair_mojibake(key) if isinstance(key, str) else key: _repair_mojibake(item)
            for key, item in value.items()
        }
    return value


def _first_env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return None


@dataclass
class OpenAICompatibleChatClient:
    """Small OpenAI-compatible chat client used only when explicitly enabled."""

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout: int = 90
    temperature: float = 0.2
    max_tokens: int = 1800
    reasoning_effort: Optional[str] = None
    stream: bool = False
    chat_path: str = "/v1/chat/completions"

    @classmethod
    def from_env(
        cls,
        *,
        model_tier: str = "quick",
        llm_config: Optional[Dict[str, Any]] = None,
    ) -> "OpenAICompatibleChatClient":
        llm_config = llm_config or {}
        tiers = llm_config.get("tiers") or {}
        tier_config = tiers.get(model_tier) or {}
        fallback_config = llm_config.get("fallback") or {}

        model = None
        if model_tier == "deep":
            model = _first_env("QUANT_EX_AGENT_DEEP_MODEL", "OPENAI_DEEP_MODEL")
        elif model_tier == "quick":
            model = _first_env("QUANT_EX_AGENT_QUICK_MODEL", "OPENAI_QUICK_MODEL")
        model = (
            model
            or str(tier_config.get("model") or "")
            or _first_env("QUANT_EX_AGENT_MODEL", "MODEL")
            or str(fallback_config.get("model") or "")
            or "gpt-5.4-mini"
        )
        api_key = str(llm_config.get("api_key") or "")
        base_url = str(llm_config.get("base_url") or "")
        api_key_env = str(llm_config.get("api_key_env") or "")
        base_url_env = str(llm_config.get("base_url_env") or "")
        return cls(
            api_key=api_key or _first_env(api_key_env, "OPENAI_APIKEY", "OPENAI_API_KEY"),
            base_url=base_url or _first_env(base_url_env, "OPENAI_BASEURL", "OPENAI_BASE_URL", "OPENAI_API_BASE"),
            model=model,
            timeout=int(tier_config.get("timeout") or llm_config.get("timeout") or 90),
            temperature=float(tier_config.get("temperature", llm_config.get("temperature", 0.2))),
            max_tokens=int(tier_config.get("max_tokens") or llm_config.get("max_tokens") or 1800),
            reasoning_effort=tier_config.get("reasoning_effort") or llm_config.get("reasoning_effort"),
            stream=bool(tier_config.get("stream", llm_config.get("stream", False))),
            chat_path=str(tier_config.get("chat_path") or llm_config.get("chat_path") or "/v1/chat/completions"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def complete_json(self, *, system: str, user: str, max_tokens: Optional[int] = None) -> Dict[str, Any]:
        if not self.is_configured:
            raise EnvironmentError(
                "OpenAI-compatible client is not configured. Set OPENAI_APIKEY, OPENAI_BASEURL, and MODEL "
                "or use the offline planner."
            )

        url = self.base_url.rstrip("/") + self.chat_path
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.stream:
            payload["stream"] = True

        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        if self.stream:
            content = self._read_stream_content(response)
            return self._parse_json(content)
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return self._parse_json(content)

    @staticmethod
    def _read_stream_content(response: requests.Response) -> str:
        content = ""
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data:"):
                continue
            data = raw_line[5:].strip()
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            choice = (chunk.get("choices") or [{}])[0]
            delta = choice.get("delta") or {}
            message = choice.get("message") or {}
            content += delta.get("content") or message.get("content") or ""
        return content

    @staticmethod
    def _parse_json(text: str) -> Dict[str, Any]:
        try:
            data = json.loads(text)
            data = data if isinstance(data, dict) else {"value": data}
            return _repair_mojibake(data)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                raise
            data = json.loads(match.group())
            data = data if isinstance(data, dict) else {"value": data}
            return _repair_mojibake(data)
