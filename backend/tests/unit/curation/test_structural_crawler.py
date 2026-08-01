"""Unit tests for structural crawler (Task 12.1, 12.5).

Covers:
- Only registered sources are accepted
- Fixture/local fetcher performs zero network calls
- Discovered pages are always candidate status
- Gaps (robots, login, JS-only, broken) are recorded honestly
- Crawler stays within canonical host
- Depth limit is respected
- Page limit is respected
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.curation.fetchers import FetchResult, LocalFixtureFetcher
from app.curation.structural_crawler import (
    ALLOWED_DISCOVERY_STATUSES,
    DiscoveredPage,
    RegisteredSource,
    StructuralCrawler,
)

T0 = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

SYNTH_SOURCE = RegisteredSource(
    source_id="synth-src-01",
    name="Synthetic Labour Insurance",
    entry_url="https://synth.example.gov.tw/benefits",
    canonical_host="synth.example.gov.tw",
    enabled=True,
)

DISABLED_SOURCE = RegisteredSource(
    source_id="synth-src-02",
    name="Disabled Source",
    entry_url="https://disabled.example.gov.tw/",
    canonical_host="disabled.example.gov.tw",
    enabled=False,
)


def _page_html(title: str, links: list[str] | None = None) -> str:
    link_tags = ""
    if links:
        link_tags = "\n".join(f'<a href="{url}">Link</a>' for url in links)
    return f"<html><head><title>{title}</title></head><body>{link_tags}</body></html>"


# ---------------------------------------------------------------------------
# Registered source validation
# ---------------------------------------------------------------------------


def test_disabled_source_raises() -> None:
    """Cannot crawl a disabled source."""
    fetcher = LocalFixtureFetcher()
    crawler = StructuralCrawler(fetcher, now=T0)

    with pytest.raises(ValueError, match="not enabled"):
        crawler.crawl(DISABLED_SOURCE)


def test_enabled_source_succeeds() -> None:
    """An enabled registered source can be crawled."""
    fetcher = LocalFixtureFetcher(default_content=_page_html("Home"))
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    assert result.source_id == SYNTH_SOURCE.source_id
    assert len(result.pages) >= 1


# ---------------------------------------------------------------------------
# Zero network calls
# ---------------------------------------------------------------------------


def test_local_fetcher_zero_network_calls() -> None:
    """The local fetcher never contacts the network."""
    fetcher = LocalFixtureFetcher(default_content=_page_html("Test"))
    crawler = StructuralCrawler(fetcher, now=T0)

    crawler.crawl(SYNTH_SOURCE)
    assert crawler.network_call_count == 0
    assert fetcher.network_call_count == 0


# ---------------------------------------------------------------------------
# Discovered pages are always candidate
# ---------------------------------------------------------------------------


def test_discovered_pages_are_candidate() -> None:
    """All discovered pages have candidate review_status."""
    fetcher = LocalFixtureFetcher(default_content=_page_html("Benefits Page"))
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    for page in result.pages:
        assert page.review_status in ALLOWED_DISCOVERY_STATUSES
        assert page.review_status == "candidate"


def test_discovered_page_rejects_verified_status() -> None:
    """Cannot construct a DiscoveredPage with verified status."""
    with pytest.raises(ValueError, match="candidate"):
        DiscoveredPage(
            url="https://example.com/page",
            source_id="src-1",
            title="Test",
            review_status="verified",
        )


# ---------------------------------------------------------------------------
# Gap recording
# ---------------------------------------------------------------------------


def test_robots_gap_is_recorded() -> None:
    """Robots.txt blocked pages are recorded as gaps."""
    fetcher = LocalFixtureFetcher()
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=403,
            gap_reason="robots_policy",
        ),
    )
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    assert "robots_policy" in result.gaps
    assert SYNTH_SOURCE.entry_url in result.gaps["robots_policy"]


def test_login_required_gap_is_recorded() -> None:
    """Login-required pages are recorded as gaps."""
    fetcher = LocalFixtureFetcher()
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=401,
            gap_reason="login_required",
        ),
    )
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    assert "login_required" in result.gaps


def test_javascript_only_gap_is_recorded() -> None:
    """JS-only pages are recorded as gaps."""
    fetcher = LocalFixtureFetcher()
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=200,
            content="<html><body><noscript>JS required</noscript></body></html>",
            gap_reason="javascript_only",
        ),
    )
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    assert "javascript_only" in result.gaps


def test_broken_link_gap_is_recorded() -> None:
    """404 pages are recorded as broken link gaps."""
    fetcher = LocalFixtureFetcher()
    entry_html = _page_html("Home", ["https://synth.example.gov.tw/broken"])
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(url=SYNTH_SOURCE.entry_url, status_code=200, content=entry_html),
    )
    fetcher.configure_response(
        "https://synth.example.gov.tw/broken",
        FetchResult(
            url="https://synth.example.gov.tw/broken",
            status_code=404,
        ),
    )
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    assert "broken_link" in result.gaps


def test_crawl_result_gap_categories() -> None:
    """gap_categories returns sorted distinct categories."""
    fetcher = LocalFixtureFetcher()
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=403,
            gap_reason="robots_policy",
        ),
    )
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    assert result.has_gaps
    assert "robots_policy" in result.gap_categories


# ---------------------------------------------------------------------------
# Canonical host boundary
# ---------------------------------------------------------------------------


def test_stays_within_canonical_host() -> None:
    """Crawler does not follow links to other domains."""
    fetcher = LocalFixtureFetcher()
    entry_html = _page_html(
        "Home",
        [
            "https://synth.example.gov.tw/page1",
            "https://other-domain.com/external",
        ],
    )
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(url=SYNTH_SOURCE.entry_url, status_code=200, content=entry_html),
    )
    fetcher.configure_response(
        "https://synth.example.gov.tw/page1",
        FetchResult(
            url="https://synth.example.gov.tw/page1",
            status_code=200,
            content=_page_html("Page 1"),
        ),
    )
    crawler = StructuralCrawler(fetcher, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    discovered_urls = {page.url for page in result.pages}
    assert "https://synth.example.gov.tw/page1" in discovered_urls
    assert "https://other-domain.com/external" not in discovered_urls


# ---------------------------------------------------------------------------
# Depth and page limits
# ---------------------------------------------------------------------------


def test_respects_max_depth() -> None:
    """Crawler stops at configured max depth."""
    fetcher = LocalFixtureFetcher()
    # Chain: entry -> page1 -> page2 -> page3
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=200,
            content=_page_html("Home", ["https://synth.example.gov.tw/d1"]),
        ),
    )
    fetcher.configure_response(
        "https://synth.example.gov.tw/d1",
        FetchResult(
            url="https://synth.example.gov.tw/d1",
            status_code=200,
            content=_page_html("D1", ["https://synth.example.gov.tw/d2"]),
        ),
    )
    fetcher.configure_response(
        "https://synth.example.gov.tw/d2",
        FetchResult(
            url="https://synth.example.gov.tw/d2",
            status_code=200,
            content=_page_html("D2", ["https://synth.example.gov.tw/d3"]),
        ),
    )
    fetcher.configure_response(
        "https://synth.example.gov.tw/d3",
        FetchResult(
            url="https://synth.example.gov.tw/d3",
            status_code=200,
            content=_page_html("D3"),
        ),
    )
    # Max depth 2 means entry(0) -> d1(1) -> d2(2), d3 should not be reached
    crawler = StructuralCrawler(fetcher, max_depth=2, now=T0)

    result = crawler.crawl(SYNTH_SOURCE)
    discovered_urls = {page.url for page in result.pages}
    assert "https://synth.example.gov.tw/d2" in discovered_urls
    assert "https://synth.example.gov.tw/d3" not in discovered_urls
    assert result.max_depth_reached == 2


def test_respects_max_pages() -> None:
    """Crawler stops after configured max pages."""
    fetcher = LocalFixtureFetcher()
    # Entry links to many pages
    links = [f"https://synth.example.gov.tw/p{i}" for i in range(20)]
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=200,
            content=_page_html("Home", links),
        ),
    )
    for link in links:
        fetcher.configure_response(
            link,
            FetchResult(url=link, status_code=200, content=_page_html("Page")),
        )

    crawler = StructuralCrawler(fetcher, max_pages=5, now=T0)
    result = crawler.crawl(SYNTH_SOURCE)

    assert result.pages_visited <= 5
