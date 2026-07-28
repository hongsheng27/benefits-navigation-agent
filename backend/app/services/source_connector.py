"""Minimal targeted HTTP connector for reviewed benefit source entry pages."""

from __future__ import annotations

import hashlib
import re
import sqlite3
import ssl
import uuid
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from backend.app.services.benefit_catalog import utc_now
from backend.app.services.link_discovery import is_taiwan_government_host

MAX_PAGE_BYTES = 5 * 1024 * 1024
USER_AGENT = "benefits-navigation-agent/source-connector/0.1"
DYNAMIC_COUNTER_PATTERN = re.compile(
    r"^(?:瀏覽人次|點閱數|瀏覽次數)\s*[：:]?\s*[\d,]+\s*(?:人|次)?$"
)


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status_code: int
    content_type: str
    title: str
    body: bytes
    content_hash: str
    raw_content_hash: str


@dataclass(frozen=True)
class SourceSyncSummary:
    sync_run_id: str
    source_id: str
    document_id: str
    canonical_url: str
    title: str
    changed: bool
    storage_ref: str


@dataclass(frozen=True)
class _RegisteredSource:
    entry_url: str
    source_type: str
    jurisdiction_code: str
    organization_name: str
    official_status: str


class _ContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self._ignored_depth = 0
        self.title_parts: list[str] = []
        self.visible_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in ("script", "style", "noscript", "svg"):
            self._ignored_depth += 1
        if normalized_tag == "title":
            self._inside_title = True

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "title":
            self._inside_title = False
        if (
            normalized_tag in ("script", "style", "noscript", "svg")
            and self._ignored_depth > 0
        ):
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_parts.append(data)
        if self._ignored_depth == 0:
            normalized_data = " ".join(data.split())
            if normalized_data:
                self.visible_parts.append(normalized_data)

    @property
    def title(self) -> str:
        return " ".join(" ".join(self.title_parts).split())

    @property
    def normalized_visible_text(self) -> str:
        return "\n".join(
            part
            for part in self.visible_parts
            if not DYNAMIC_COUNTER_PATTERN.fullmatch(part)
        )


def _ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


def _decode_html(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        key, separator, value = part.strip().partition("=")
        if separator and key.lower() == "charset" and value.strip():
            charset = value.strip("\"' ")
            break
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def fetch_html(url: str, timeout_seconds: int = 30) -> FetchedPage:
    """Fetch one reviewed HTML entry page without following child links."""

    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
            "Accept-Language": "zh-TW,zh;q=0.9",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(
        request,
        timeout=timeout_seconds,
        context=_ssl_context(),
    ) as response:
        status_code = int(getattr(response, "status", 200))
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            raise ValueError(
                f"Expected HTML from {url}, received {content_type or 'unknown'}."
            )
        body = response.read(MAX_PAGE_BYTES + 1)
        if len(body) > MAX_PAGE_BYTES:
            raise ValueError(
                f"HTML response from {url} exceeds {MAX_PAGE_BYTES} bytes."
            )
        final_url = response.geturl()

    parser = _ContentParser()
    parser.feed(_decode_html(body, content_type))
    visible_text = parser.normalized_visible_text.encode("utf-8")
    return FetchedPage(
        requested_url=url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        title=parser.title,
        body=body,
        content_hash=hashlib.sha256(visible_text).hexdigest(),
        raw_content_hash=hashlib.sha256(body).hexdigest(),
    )


def _write_raw_page(
    raw_directory: Path,
    source_id: str,
    page: FetchedPage,
) -> str:
    source_directory = raw_directory / source_id
    source_directory.mkdir(parents=True, exist_ok=True)
    output_path = source_directory / f"{page.raw_content_hash}.html"
    if not output_path.exists():
        output_path.write_bytes(page.body)
    return str(output_path)


def _load_registered_source(
    connection: sqlite3.Connection,
    source_id: str,
) -> _RegisteredSource:
    source = connection.execute(
        """
        SELECT
            entry_url,
            source_type,
            jurisdiction_code,
            organization_name,
            official_status
        FROM source_registry
        WHERE source_id = ?
          AND enabled = 1
        """,
        (source_id,),
    ).fetchone()
    if source is None:
        raise ValueError(f"Unknown or disabled source_id: {source_id}")
    return _RegisteredSource(*source)


def _validate_reviewed_government_url(url: str) -> None:
    parts = urlsplit(url)
    if (
        parts.scheme.lower() != "https"
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or not is_taiwan_government_host(parts.hostname)
    ):
        raise ValueError(
            f"Reviewed child pages must use an HTTPS Taiwan government URL: {url}"
        )


def _sync_source_page(
    connection: sqlite3.Connection,
    *,
    source_id: str,
    page_url: str,
    raw_directory: Path,
    document_type: str,
    discovery_method: str,
    publisher_name: str,
    jurisdiction_code: str,
    update_source_health: bool,
    require_official_final_url: bool,
    timeout_seconds: int,
) -> SourceSyncSummary:
    sync_run_id = str(uuid.uuid4())
    started_at = utc_now()
    connection.execute(
        """
        INSERT INTO source_sync_runs (
            sync_run_id,
            source_id,
            started_at,
            status
        )
        VALUES (?, ?, ?, 'running')
        """,
        (sync_run_id, source_id, started_at),
    )
    connection.commit()

    try:
        page = fetch_html(page_url, timeout_seconds)
        if require_official_final_url:
            _validate_reviewed_government_url(page.final_url)
        document_id = str(uuid.uuid5(uuid.NAMESPACE_URL, page.final_url))
        existing = connection.execute(
            """
            SELECT document_id, current_content_hash, storage_ref
            FROM source_documents
            WHERE canonical_url = ?
            """,
            (page.final_url,),
        ).fetchone()
        observed_at = utc_now()
        changed = existing is None or existing[1] != page.content_hash
        storage_ref = (
            _write_raw_page(raw_directory, source_id, page) if changed else existing[2]
        )
        if not storage_ref:
            storage_ref = _write_raw_page(raw_directory, source_id, page)

        connection.execute("BEGIN")
        if existing is None:
            connection.execute(
                """
                INSERT INTO source_documents (
                    document_id,
                    canonical_url,
                    title,
                    document_type,
                    jurisdiction_code,
                    publisher_name,
                    current_content_hash,
                    storage_ref,
                    http_status,
                    first_seen_at,
                    last_seen_at,
                    last_changed_at,
                    retrieved_at,
                    review_status,
                    created_at,
                    updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?
                )
                """,
                (
                    document_id,
                    page.final_url,
                    page.title,
                    document_type,
                    jurisdiction_code,
                    publisher_name,
                    page.content_hash,
                    storage_ref,
                    page.status_code,
                    observed_at,
                    observed_at,
                    observed_at,
                    observed_at,
                    observed_at,
                    observed_at,
                ),
            )
        else:
            document_id = existing[0]
            connection.execute(
                """
                UPDATE source_documents
                SET
                    title = ?,
                    document_type = ?,
                    jurisdiction_code = ?,
                    publisher_name = ?,
                    current_content_hash = ?,
                    storage_ref = ?,
                    http_status = ?,
                    last_seen_at = ?,
                    last_changed_at = CASE
                        WHEN current_content_hash != ? THEN ?
                        ELSE last_changed_at
                    END,
                    retrieved_at = ?,
                    updated_at = ?
                WHERE document_id = ?
                """,
                (
                    page.title,
                    document_type,
                    jurisdiction_code,
                    publisher_name,
                    page.content_hash,
                    storage_ref,
                    page.status_code,
                    observed_at,
                    page.content_hash,
                    observed_at,
                    observed_at,
                    observed_at,
                    document_id,
                ),
            )

        connection.execute(
            """
            INSERT INTO document_discoveries (
                document_id,
                source_id,
                discovery_url,
                discovery_method,
                first_seen_at,
                last_seen_at,
                last_sync_run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (document_id, source_id)
            DO UPDATE SET
                discovery_url = excluded.discovery_url,
                last_seen_at = excluded.last_seen_at,
                last_sync_run_id = excluded.last_sync_run_id
            """,
            (
                document_id,
                source_id,
                page_url,
                discovery_method,
                observed_at,
                observed_at,
                sync_run_id,
            ),
        )
        connection.execute(
            """
            UPDATE source_sync_runs
            SET
                completed_at = ?,
                status = 'completed',
                discovered_document_count = 1,
                fetched_document_count = 1,
                unchanged_document_count = ?,
                changed_document_count = ?
            WHERE sync_run_id = ?
            """,
            (
                observed_at,
                int(not changed),
                int(changed),
                sync_run_id,
            ),
        )
        if update_source_health:
            connection.execute(
                """
                UPDATE source_registry
                SET connection_status = 'active', updated_at = ?
                WHERE source_id = ?
                """,
                (observed_at, source_id),
            )
        connection.commit()
    except Exception as exc:
        connection.rollback()
        completed_at = utc_now()
        connection.execute(
            """
            UPDATE source_sync_runs
            SET completed_at = ?, status = 'failed', error_message = ?
            WHERE sync_run_id = ?
            """,
            (completed_at, str(exc), sync_run_id),
        )
        if update_source_health:
            previous_status = connection.execute(
                """
                SELECT connection_status
                FROM source_registry
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()
            failed_status = (
                "degraded"
                if previous_status is not None
                and previous_status[0] in ("active", "degraded")
                else "failed"
            )
            connection.execute(
                """
                UPDATE source_registry
                SET connection_status = ?, updated_at = ?
                WHERE source_id = ?
                """,
                (failed_status, completed_at, source_id),
            )
        connection.commit()
        raise

    return SourceSyncSummary(
        sync_run_id=sync_run_id,
        source_id=source_id,
        document_id=document_id,
        canonical_url=page.final_url,
        title=page.title,
        changed=changed,
        storage_ref=storage_ref,
    )


def sync_registered_source(
    connection: sqlite3.Connection,
    source_id: str,
    raw_directory: Path,
    *,
    timeout_seconds: int = 30,
) -> SourceSyncSummary:
    """Fetch one registered entry page and record an auditable sync run."""

    connection.execute("PRAGMA foreign_keys = ON")
    source = _load_registered_source(connection, source_id)
    document_type = "index" if source.source_type == "benefit_index" else "benefit_page"
    return _sync_source_page(
        connection,
        source_id=source_id,
        page_url=source.entry_url,
        raw_directory=raw_directory,
        document_type=document_type,
        discovery_method="entry_page",
        publisher_name=source.organization_name,
        jurisdiction_code=source.jurisdiction_code,
        update_source_health=True,
        require_official_final_url=False,
        timeout_seconds=timeout_seconds,
    )


def sync_reviewed_source_page(
    connection: sqlite3.Connection,
    source_id: str,
    page_url: str,
    raw_directory: Path,
    *,
    timeout_seconds: int = 30,
) -> SourceSyncSummary:
    """Fetch one approved government child page without crawling its links."""

    connection.execute("PRAGMA foreign_keys = ON")
    source = _load_registered_source(connection, source_id)
    if source.official_status != "verified_official":
        raise ValueError(f"Source is not verified_official: {source_id}")
    _validate_reviewed_government_url(page_url)
    return _sync_source_page(
        connection,
        source_id=source_id,
        page_url=page_url,
        raw_directory=raw_directory,
        document_type="benefit_page",
        discovery_method="reviewed_candidate",
        publisher_name="",
        jurisdiction_code="",
        update_source_health=False,
        require_official_final_url=True,
        timeout_seconds=timeout_seconds,
    )
