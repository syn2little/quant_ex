from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import yaml

from .schemas import SourceConfig


def load_config(path: Path) -> Dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_sources(config: Dict[str, Any], *, tier: int | None = None) -> List[SourceConfig]:
    sources = [SourceConfig.from_dict(item) for item in config.get("sources", [])]
    enabled = [source for source in sources if source.enabled]
    if tier is not None:
        enabled = [source for source in enabled if source.tier <= tier]
    return enabled


def load_optional_source_stubs(config: Dict[str, Any]) -> List[SourceConfig]:
    return [SourceConfig.from_dict(item) for item in config.get("optional_sources", [])]
