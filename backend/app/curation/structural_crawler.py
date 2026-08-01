"""Registered-source structural discovery (Req 10.7, 11.9, 12.6-12.8, 16.1).

This module discovers pages from registered sources using a structural approach:
starting from the source's entry URL, it follows links within the same canonical
host up to a configurable depth. It does NOT claim comprehensive crawling — gaps
from robots.txt, login requirements, JS-only pages, and broken links are explicitly
recorded.

## Key constraints

- Only accepts registered sources (validated by source_id + entry_url)
- Uses fixture/local fetcher before live network is approved
- Discovered pages can only be `candidate` — never `verified`
- Records all gaps honestly (Req 12.6-12.8)
- Does not claim full crawl coverage
- Does not execute LLM, attachments, or network calls (those are separate concerns)

## What "structural" means

The crawler follows the document structure: links in `<a href>` tags within the
same canonical host. It does NOT render JavaScript, fill forms, or authenticate.
Pages that require those capabilities are recorded as gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final
from urllib.parse import urljoin, urlparse

from app.curation.fetchers import FetcherPort, GapRecordingFetcher

# Maximum pages to discover per source in a single crawl run.
MAX_PAGES_PER_SOURCE: Final[int] = 50

# Maximum link-follow depth from the entry URL.
MAX_DEPTH: Final[int] = 3

# Only these review statuses are allowed for discovered pages.
ALLOWED_DISCOVERY_STATUSES: Final[frozenset[str]] = frozenset(
    {"candidate", "under_review"}
)


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    """A source that has been registered and is allowed to be crawled.

    Only registered sources can be structurally discovered. This prevents
    the crawler from wandering into arbitrary domains.
    """

    source_id: str
    name: str
    entry_url: str
    canonical_host: str
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class DiscoveredPage:
    """A page found during structural discovery.

    `review_status` is always `candidate` — the crawler cannot verify content.
    """

    url: str
    source_id: str
    title: str
    discovery_method: str = "structural_crawl"
    review_status: str = "candidate"
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.review_status not in ALLOWED_DISCOVERY_STATUSES:
            raise ValueError(
                f"Discovered pages must be {ALLOWED_DISCOVERY_STATUSES}, "
                f"got '{self.review_status}'"
            )


@dataclass(frozen=True, slots=True)
class CrawlResult:
    """Result of crawling a single registered source.

    Honestly reports what was found AND what could not be reached.
    """

    source_id: str
    pages: tuple[DiscoveredPage, ...]
    gaps: dict[str, tuple[str, ...]]
    pages_visited: int
    max_depth_reached: int
    started_at: datetime
    completed_at: datetime

    @property
    def has_gaps(self) -> bool:
        return any(urls for urls in self.gaps.values())

    @property
    def gap_categories(self) -> tuple[str, ...]:
        """Sorted distinct gap categories encountered."""
        return tuple(sorted(cat for cat, urls in self.gaps.items() if urls))


class StructuralCrawler:
    """Discovers pages from registered sources by following links.

    Uses a `FetcherPort` for all page retrieval — the fetcher determines whether
    this is a local/fixture crawl or a live one. The crawler itself is unaware.
    """

    def __init__(
        self,
        fetcher: FetcherPort,
        *,
        max_pages: int = MAX_PAGES_PER_SOURCE,
        max_depth: int = MAX_DEPTH,
        now: datetime | None = None,
    ) -> None:
        self._fetcher = GapRecordingFetcher(inner=fetcher)
        self._max_pages = max_pages
        self._max_depth = max_depth
        self._now = now or datetime.now(UTC)

    def crawl(self, source: RegisteredSource) -> CrawlResult:
        """Structurally discover pages from a registered source.

        Returns discovered pages and honestly recorded gaps.
        Raises ValueError if the source is not enabled.
        """
        if not source.enabled:
            raise ValueError(f"Source '{source.source_id}' is not enabled for crawling")

        started_at = self._now
        visited: set[str] = set()
        pages: list[DiscoveredPage] = []
        max_depth_reached = 0

        # BFS from entry URL
        queue: list[tuple[str, int]] = [(source.entry_url, 0)]

        while queue and len(visited) < self._max_pages:
            url, depth = queue.pop(0)

            if url in visited:
                continue
            if depth > self._max_depth:
                continue

            # Only follow links within the canonical host
            if not _is_same_host(url, source.canonical_host):
                continue

            visited.add(url)
            max_depth_reached = max(max_depth_reached, depth)

            result = self._fetcher.fetch(url)

            if not result.is_success:
                continue

            if not result.is_html:
                continue

            # Extract page info
            title = _extract_title(result.content)
            page = DiscoveredPage(
                url=url,
                source_id=source.source_id,
                title=title,
                discovery_method="structural_crawl",
                review_status="candidate",
                discovered_at=self._now,
            )
            pages.append(page)

            # Extract and queue links for next depth level
            if depth < self._max_depth:
                links = _extract_links(result.content, url)
                for link in links:
                    if link not in visited and _is_same_host(
                        link, source.canonical_host
                    ):
                        queue.append((link, depth + 1))

        # Collect gaps from the recording fetcher
        gaps: dict[str, tuple[str, ...]] = {
            category: tuple(sorted(urls))
            for category, urls in self._fetcher.all_gaps.items()
        }

        return CrawlResult(
            source_id=source.source_id,
            pages=tuple(pages),
            gaps=gaps,
            pages_visited=len(visited),
            max_depth_reached=max_depth_reached,
            started_at=started_at,
            completed_at=self._now,
        )

    @property
    def network_call_count(self) -> int:
        """Number of actual network calls made by the underlying fetcher."""
        return self._fetcher.network_call_count


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\']+)["\']', re.IGNORECASE)


def _extract_title(html: str) -> str:
    """Extract the <title> content from HTML. Returns '' if not found."""
    match = _TITLE_RE.search(html)
    if match:
        return match.group(1).strip()
    return ""


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract all <a href> links, resolving relative URLs."""
    links: list[str] = []
    for match in _LINK_RE.finditer(html):
        href = match.group(1).strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        # Strip fragment
        parsed = urlparse(absolute)
        clean = parsed._replace(fragment="").geturl()
        links.append(clean)
    return links


def _is_same_host(url: str, canonical_host: str) -> bool:
    """Check if a URL belongs to the same canonical host."""
    parsed = urlparse(url)
    return parsed.hostname == canonical_host
