from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class LLMError(RuntimeError):
    pass


def load_hermes_llm_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load the same OpenAI-compatible endpoint settings used by Hermes Agent."""
    path = config_path or Path.home() / ".hermes" / "config.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    model_cfg = data.get("model", {}) if isinstance(data, dict) else {}
    provider = model_cfg.get("provider") or data.get("provider") if isinstance(data, dict) else None
    base_url = model_cfg.get("base_url") or data.get("base_url") if isinstance(data, dict) else None
    api_key = model_cfg.get("api_key") or data.get("api_key") if isinstance(data, dict) else None
    model = model_cfg.get("default") or model_cfg.get("model") or data.get("model") if isinstance(data, dict) else None
    return {
        "provider": provider,
        "base_url": base_url,
        "api_key": _resolve_secret(api_key),
        "model": model,
        "timeout": int(model_cfg.get("timeout", 300)) if isinstance(model_cfg, dict) else 300,
    }


def call_openai_compatible_chat(prompt: str, *, config: Optional[Dict[str, Any]] = None) -> str:
    cfg = config or load_hermes_llm_config()
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = cfg.get("api_key") or ""
    model = cfg.get("model") or ""
    if not base_url or not api_key or not model:
        raise LLMError("Missing base_url, api_key, or model in Hermes LLM config")
    url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You write rigorous Chinese research memos for quant strategy iteration."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "stream": True,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(cfg.get("timeout", 300))) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"LLM HTTP {exc.code}: {detail[:500]}") from exc
    except Exception as exc:  # pragma: no cover - network/runtime failure path
        raise LLMError(f"LLM call failed: {exc}") from exc
    if raw.lstrip().startswith("data:"):
        return _parse_sse_chat_content(raw)
    try:
        payload = json.loads(raw)
        return payload["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise LLMError(f"Unexpected LLM response shape: {raw[:500]!r}") from exc


def _parse_sse_chat_content(raw: str) -> str:
    chunks: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        choice = (payload.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        content = delta.get("content") or choice.get("message", {}).get("content") or ""
        if content:
            chunks.append(content)
    text = "".join(chunks).strip()
    if not text:
        raise LLMError("Empty streaming LLM response")
    return text


def _resolve_secret(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    if value.startswith("env:"):
        return os.getenv(value.split(":", 1)[1], "")
    if value.startswith("$"):
        return os.getenv(value[1:], "")
    return value
