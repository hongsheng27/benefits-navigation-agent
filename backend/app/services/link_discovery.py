"""Discover child-link candidates from a previously fetched entry page."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

CONTENT_ELEMENT_ID = "CCMS_Content"
IGNORED_SCHEMES = ("javascript:", "mailto:", "tel:", "data:")
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
PRIORITY_ORDER = {"high": 0, "medium": 1, "review": 2}


@dataclass(frozen=True)
class RawLink:
    href: str
    text: str
    title: str


@dataclass(frozen=True)
class LinkCandidate:
    source_id: str
    source_page_url: str
    url: str
    text: str
    title: str
    host: str
    official_host: bool
    resource_type: str
    priority: str
    matched_terms: tuple[str, ...]

    def as_json(self) -> dict[str, object]:
        value = asdict(self)
        value["matched_terms"] = list(self.matched_terms)
        return value


class _MainContentLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._content_depth = 0
        self._active_link: dict[str, object] | None = None
        self.links: list[RawLink] = []

    @property
    def _inside_content(self) -> bool:
        return self._content_depth > 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        attributes = {key.lower(): value for key, value in attrs}

        if not self._inside_content:
            if attributes.get("id") != CONTENT_ELEMENT_ID:
                return
            self._content_depth = 1
        elif normalized_tag not in VOID_ELEMENTS:
            self._content_depth += 1

        if self._inside_content and normalized_tag == "a":
            self._active_link = {
                "href": attributes.get("href") or "",
                "title": attributes.get("title") or "",
                "text_parts": [],
            }

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.lower() == "a":
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if not self._inside_content:
            return

        if normalized_tag == "a" and self._active_link is not None:
            text_parts = self._active_link["text_parts"]
            assert isinstance(text_parts, list)
            self.links.append(
                RawLink(
                    href=str(self._active_link["href"]),
                    text=" ".join(" ".join(text_parts).split()),
                    title=" ".join(str(self._active_link["title"]).split()),
                )
            )
            self._active_link = None

        if normalized_tag not in VOID_ELEMENTS:
            self._content_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._active_link is None:
            return
        normalized_data = " ".join(data.split())
        if normalized_data:
            text_parts = self._active_link["text_parts"]
            assert isinstance(text_parts, list)
            text_parts.append(normalized_data)


def is_taiwan_government_host(host: str) -> bool:
    normalized_host = host.lower().split(":", 1)[0].rstrip(".")
    return (
        normalized_host == "gov.tw"
        or normalized_host.endswith(".gov.tw")
        or normalized_host == "gov.taipei"
        or normalized_host.endswith(".gov.taipei")
    )


def _canonicalize_url(source_page_url: str, href: str) -> str | None:
    normalized_href = href.strip()
    if (
        not normalized_href
        or normalized_href == "#"
        or normalized_href.startswith("#")
        or normalized_href.lower().startswith(IGNORED_SCHEMES)
    ):
        return None

    absolute_url = urljoin(source_page_url, normalized_href)
    parts = urlsplit(absolute_url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            parts.query,
            "",
        )
    )


def _resource_type(url: str, title: str) -> str:
    path = urlsplit(url).path.lower()
    normalized_title = title.lower()
    if path.endswith(".pdf") or "pdf" in normalized_title:
        return "pdf"
    if path.endswith((".doc", ".docx", ".odt")):
        return "document"
    if path.endswith((".xls", ".xlsx", ".ods", ".csv")):
        return "spreadsheet"
    return "html"


def _rank_link(
    text: str,
    title: str,
    terms: dict[str, list[str]],
) -> tuple[str, tuple[str, ...]]:
    searchable_text = f"{text} {title}"
    high_precision_groups = (
        "high_precision_subsidy_phrases",
        "government_service_phrases",
        "related_financial_phrases",
    )
    medium_precision_groups = (
        "death_event_low_precision",
        "funeral_service_terms",
        "economic_assistance_terms",
        "fee_schedule_terms",
        "fee_relief_terms",
    )

    high_matches = {
        term
        for group in high_precision_groups
        for term in terms.get(group, [])
        if term in searchable_text
    }
    medium_matches = {
        term
        for group in medium_precision_groups
        for term in terms.get(group, [])
        if term in searchable_text
    }
    matched_terms = tuple(sorted(high_matches | medium_matches))
    if high_matches:
        return "high", matched_terms
    if medium_matches:
        return "medium", matched_terms
    return "review", matched_terms


def discover_links(
    html: str,
    *,
    source_id: str,
    source_page_url: str,
    discovery_terms: dict[str, list[str]],
) -> list[LinkCandidate]:
    """Return unique HTTP(S) links found inside the page's main content."""

    parser = _MainContentLinkParser()
    parser.feed(html)
    canonical_source_url = _canonicalize_url(source_page_url, source_page_url)
    candidates_by_url: dict[str, LinkCandidate] = {}

    for raw_link in parser.links:
        url = _canonicalize_url(source_page_url, raw_link.href)
        if url is None or url == canonical_source_url:
            continue
        text = raw_link.text or raw_link.title
        title = raw_link.title
        if not text and not title:
            continue
        host = urlsplit(url).netloc.lower()
        priority, matched_terms = _rank_link(
            text,
            title,
            discovery_terms,
        )
        candidate = LinkCandidate(
            source_id=source_id,
            source_page_url=source_page_url,
            url=url,
            text=text,
            title=title,
            host=host,
            official_host=is_taiwan_government_host(host),
            resource_type=_resource_type(url, title),
            priority=priority,
            matched_terms=matched_terms,
        )
        existing = candidates_by_url.get(url)
        if existing is None or PRIORITY_ORDER[priority] < PRIORITY_ORDER[
            existing.priority
        ]:
            candidates_by_url[url] = candidate

    return sorted(
        candidates_by_url.values(),
        key=lambda candidate: (
            PRIORITY_ORDER[candidate.priority],
            not candidate.official_host,
            candidate.text,
            candidate.url,
        ),
    )


def load_discovery_terms(dictionary_path: Path) -> dict[str, list[str]]:
    with dictionary_path.open(encoding="utf-8") as file:
        data = json.load(file)
    terms = data.get("discovery_terms")
    if not isinstance(terms, dict):
        raise ValueError(
            f"Missing discovery_terms object in {dictionary_path}."
        )
    return {
        str(group): [str(term) for term in values]
        for group, values in terms.items()
        if isinstance(values, list)
    }
