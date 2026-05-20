from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Type

from .schemas import ScoutItem, SourceConfig, utc_now_iso


class SourceAdapter(ABC):
    source_type = "base"

    def __init__(self, config: SourceConfig, *, timeout: int = 20):
        self.config = config
        self.timeout = timeout

    @abstractmethod
    def fetch(self) -> List[ScoutItem]:
        raise NotImplementedError

    def _request_text(self, url: str) -> str:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "quant_ex-knowledge-scout/0.1 (+research metadata only)",
                "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def _make_item(self, *, title: str, url: str, summary: str = "", published_at: str = "", authors: Iterable[str] = (), tags: Iterable[str] = (), raw: Dict | None = None) -> ScoutItem:
        return ScoutItem(
            title=html.unescape(" ".join((title or "").split())),
            url=url,
            source_name=self.config.name,
            source_type=self.config.source_type,
            retrieved_at=utc_now_iso(),
            published_at=published_at,
            summary=html.unescape(" ".join((summary or "").split())),
            authors=list(authors),
            tags=list(tags),
            raw=raw or {},
        )


class ArxivSource(SourceAdapter):
    source_type = "arxiv"

    def fetch(self) -> List[ScoutItem]:
        params = urllib.parse.urlencode(
            {
                "search_query": self.config.query,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
                "max_results": str(self.config.max_items),
            }
        )
        text = self._request_text(f"https://export.arxiv.org/api/query?{params}")
        root = ET.fromstring(text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        items: List[ScoutItem] = []
        for entry in root.findall("a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            url = (entry.findtext("a:id", default="", namespaces=ns) or "").strip().replace("http://", "https://")
            summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
            published_at = (entry.findtext("a:published", default="", namespaces=ns) or "")[:10]
            authors = [a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)]
            tags = [c.get("term", "") for c in entry.findall("a:category", ns)]
            if title and url:
                items.append(
                    self._make_item(
                        title=title,
                        url=url,
                        summary=summary,
                        published_at=published_at,
                        authors=[a for a in authors if a],
                        tags=[t for t in tags if t],
                    )
                )
        return items


class RSSSource(SourceAdapter):
    source_type = "rss"

    def fetch(self) -> List[ScoutItem]:
        text = self._request_text(self.config.url)
        root = ET.fromstring(text)
        items: List[ScoutItem] = []
        channel_items = root.findall("./channel/item")
        if not channel_items:
            channel_items = root.findall("{http://www.w3.org/2005/Atom}entry")
        for node in channel_items[: self.config.max_items]:
            if node.tag.endswith("entry"):
                item = self._parse_atom_entry(node)
            else:
                item = self._parse_rss_item(node)
            if item:
                items.append(item)
        return items

    def _parse_rss_item(self, node: ET.Element) -> ScoutItem | None:
        title = node.findtext("title", default="")
        url = node.findtext("link", default="")
        summary = node.findtext("description", default="")
        published = node.findtext("pubDate", default="")
        published_at = _normalize_date(published)
        tags = [c.text or "" for c in node.findall("category")]
        if not title or not url:
            return None
        return self._make_item(title=title, url=url.strip(), summary=_strip_tags(summary), published_at=published_at, tags=tags)

    def _parse_atom_entry(self, node: ET.Element) -> ScoutItem | None:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        title = node.findtext("a:title", default="", namespaces=ns)
        link = node.find("a:link", ns)
        url = link.get("href") if link is not None else ""
        summary = node.findtext("a:summary", default="", namespaces=ns) or node.findtext("a:content", default="", namespaces=ns)
        published_at = (node.findtext("a:published", default="", namespaces=ns) or node.findtext("a:updated", default="", namespaces=ns) or "")[:10]
        if not title or not url:
            return None
        return self._make_item(title=title, url=url, summary=_strip_tags(summary), published_at=published_at)


class HtmlIndexSource(SourceAdapter):
    source_type = "html_index"

    def fetch(self) -> List[ScoutItem]:
        text = self._request_text(self.config.url)
        title = _html_title(text) or self.config.name
        description = _meta_description(text)
        return [
            self._make_item(
                title=title,
                url=self.config.url,
                summary=description or "HTML index source collected as metadata only. Use linked pages for manual review.",
                raw={"metadata_only": True},
            )
        ]


class PlaceholderSource(SourceAdapter):
    """Disabled-by-default extension point for optional non-Tier1 sources."""

    source_type = "placeholder"

    def fetch(self) -> List[ScoutItem]:
        return []


ADAPTERS: Dict[str, Type[SourceAdapter]] = {
    ArxivSource.source_type: ArxivSource,
    RSSSource.source_type: RSSSource,
    HtmlIndexSource.source_type: HtmlIndexSource,
    "semantic_scholar": PlaceholderSource,
    "x_search": PlaceholderSource,
    "youtube": PlaceholderSource,
    "github": PlaceholderSource,
}


def build_adapter(config: SourceConfig, *, timeout: int = 20) -> SourceAdapter:
    adapter_cls = ADAPTERS.get(config.source_type)
    if adapter_cls is None:
        raise ValueError(f"Unsupported source_type: {config.source_type}")
    return adapter_cls(config, timeout=timeout)


def _normalize_date(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except Exception:
        return value[:10]


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    return " ".join(text.split())


def _html_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text or "", flags=re.I | re.S)
    return _strip_tags(match.group(1)) if match else ""


def _meta_description(text: str) -> str:
    match = re.search(
        r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"'](.*?)[\"']",
        text or "",
        flags=re.I | re.S,
    )
    return _strip_tags(match.group(1)) if match else ""
