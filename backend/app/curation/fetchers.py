"""Fetcher abstractions for structural crawling (Req 10.7, 16.1, 16.2).

This module defines the fetcher protocol and provides a local/fixture
implementation. Before owner-approved live network access, the only concrete
fetcher reads from local fixture files or returns synthetic responses.

## Why a protocol

The structural crawler must work identically whether it reads from a local
directory or from a live HTTP endpoint. The protocol boundary lets tests
prove that zero network calls happen during the local path, and lets the
future AWS/live fetcher swap in without touching the crawler logic.

## Fixture fetcher

`LocalFixtureFetcher` reads from a directory of HTML files keyed by URL hash
or returns a configurable synthetic response. It never opens a socket.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Result of fetching a single URL.

    `status_code` mirrors HTTP semantics (200, 404, 403, etc.).
    `gap_reason` records why a page could not be fetched (robots, login, JS-only, etc.).
    """

    url: str
    status_code: int
    content: str = ""
    content_type: str = "text/html"
    gap_reason: str | None = None

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_html(self) -> bool:
        return "html" in self.content_type.lower()


class FetcherPort(Protocol):
    """Protocol for page fetching — injectable for local/mock/live."""

    def fetch(self, url: str) -> FetchResult:
        """Fetch a single URL. Must not raise; errors become FetchResult."""
        ...

    @property
    def network_call_count(self) -> int:
        """Number of actual network calls made. Must be 0 for local fetchers."""
        ...


@dataclass(slots=True)
class LocalFixtureFetcher:
    """Reads from local fixture files or returns synthetic responses.

    Never touches the network. `fixture_dir` contains files named by URL hash.
    If a URL is not in the fixture directory, returns a configurable default.
    """

    fixture_dir: Path | None = None
    default_content: str = "<html><body>synthetic fixture</body></html>"
    default_status: int = 200
    _call_count: int = field(default=0, init=False)
    _network_calls: int = field(default=0, init=False)

    # Pre-configured responses for specific URLs
    _responses: dict[str, FetchResult] = field(default_factory=dict, init=False)

    def configure_response(self, url: str, result: FetchResult) -> None:
        """Pre-configure a response for a specific URL."""
        self._responses[url] = result

    def fetch(self, url: str) -> FetchResult:
        """Fetch from fixtures. Zero network calls."""
        self._call_count += 1

        # Check pre-configured responses first
        if url in self._responses:
            return self._responses[url]

        # Try fixture directory
        if self.fixture_dir is not None:
            file_path = self.fixture_dir / _url_to_filename(url)
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                return FetchResult(url=url, status_code=200, content=content)

        # Return synthetic default
        return FetchResult(
            url=url,
            status_code=self.default_status,
            content=self.default_content,
        )

    @property
    def network_call_count(self) -> int:
        """Always zero — this fetcher never contacts the network."""
        return self._network_calls

    @property
    def call_count(self) -> int:
        """Total fetch calls made (all local)."""
        return self._call_count


@dataclass(slots=True)
class GapRecordingFetcher:
    """Wraps a fetcher and records gap reasons for inaccessible pages.

    This is used by the structural crawler to track robots.txt blocks,
    login-required pages, JS-only pages, and broken links.
    """

    inner: FetcherPort
    robots_blocked_urls: set[str] = field(default_factory=set, init=False)
    login_required_urls: set[str] = field(default_factory=set, init=False)
    js_only_urls: set[str] = field(default_factory=set, init=False)
    broken_urls: set[str] = field(default_factory=set, init=False)

    def fetch(self, url: str) -> FetchResult:
        """Delegate to inner and record gaps."""
        result = self.inner.fetch(url)
        if result.gap_reason == "robots_policy":
            self.robots_blocked_urls.add(url)
        elif result.gap_reason == "login_required":
            self.login_required_urls.add(url)
        elif result.gap_reason == "javascript_only":
            self.js_only_urls.add(url)
        elif result.gap_reason == "broken_link" or (
            result.gap_reason is None and result.status_code >= 400
        ):
            self.broken_urls.add(url)
        return result

    @property
    def network_call_count(self) -> int:
        return self.inner.network_call_count

    @property
    def all_gaps(self) -> dict[str, set[str]]:
        """All recorded gaps by category."""
        gaps: dict[str, set[str]] = {}
        if self.robots_blocked_urls:
            gaps["robots_policy"] = set(self.robots_blocked_urls)
        if self.login_required_urls:
            gaps["login_required"] = set(self.login_required_urls)
        if self.js_only_urls:
            gaps["javascript_only"] = set(self.js_only_urls)
        if self.broken_urls:
            gaps["broken_link"] = set(self.broken_urls)
        return gaps


def _url_to_filename(url: str) -> str:
    """Deterministic filename for a URL, safe for all filesystems."""
    return hashlib.sha256(url.encode()).hexdigest()[:16] + ".html"
