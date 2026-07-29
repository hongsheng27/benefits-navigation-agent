"""驗證 on-demand refresh 的流程：先回答，再更新。

提案第 9 節的三個重點在這裡各有一組測試：先回傳目前 coverage snapshot、以非阻塞
方式排入 refresh、refresh 失敗不阻塞也不撤銷目前的回應。
"""

from datetime import UTC, datetime

from app.orchestration.data_contracts import CoverageMetadata
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    LocalSourceRecord,
    LocalSourceRefreshService,
    RefreshReceipt,
    RefreshRequest,
)
from app.orchestration.source_refresh import refresh_after_response

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
_FUNERAL_SCOPE = CoverageScope(source_ids=(), domain_tags=("funeral",))


def _snapshot(
    sources: tuple[CoverageMetadata, ...],
    *,
    scope: CoverageScope = _FUNERAL_SCOPE,
) -> CoverageSnapshot:
    return CoverageSnapshot(
        scope=scope,
        observed_at=_NOW,
        registered_source_count=len(sources),
        crawled_source_count=sum(
            source.crawl_status == "crawled" for source in sources
        ),
        pending_crawl_source_count=sum(
            source.crawl_status == "pending_crawl" for source in sources
        ),
        error_source_count=sum(source.crawl_status == "error" for source in sources),
        indexed_document_count=sum(source.indexed_document_count for source in sources),
        sources=sources,
        gap_categories=(),
    )


class _FailingRefreshService:
    """coverage 查得到，但排入工作會失敗。"""

    def __init__(self) -> None:
        self.coverage_calls = 0

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        self.coverage_calls += 1
        return _snapshot(
            (
                CoverageMetadata(
                    source_id="src_1",
                    crawl_status="pending_crawl",
                    last_crawled_at=None,
                    indexed_document_count=0,
                    domain_tags=("funeral",),
                    observed_at=_NOW,
                ),
            ),
            scope=scope,
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        del request
        msg = "本機佇列不可用"
        raise RuntimeError(msg)


class _RecordingRefreshService:
    """記錄有沒有被要求排入工作。"""

    def __init__(self, snapshot: CoverageSnapshot) -> None:
        self._snapshot = snapshot
        self.requests: list[RefreshRequest] = []

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        assert scope == self._snapshot.scope
        return self._snapshot

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        self.requests.append(request)
        return RefreshReceipt(job_id="job_1", accepted=True, deduplicated=False)


def _service() -> LocalSourceRefreshService:
    return LocalSourceRefreshService(
        sources=(
            LocalSourceRecord(
                source_id="src_pending",
                crawl_status="pending_crawl",
                domain_tags=("funeral",),
                check_frequency_days=7,
            ),
        ),
        clock=lambda: _NOW,
    )


def test_coverage_comes_back_with_the_current_local_data() -> None:
    """回應用的是目前本機資料，不是刷新之後的資料。

    來源仍然是 `pending_crawl`，證明這一次呼叫沒有等待任何抓取完成。
    """
    snapshot, receipt = refresh_after_response(
        _service(), "spouse_death", _FUNERAL_SCOPE, now=_NOW
    )

    assert [entry.source_id for entry in snapshot.sources] == ["src_pending"]
    assert snapshot.sources[0].crawl_status == "pending_crawl"
    assert receipt is not None
    assert receipt.accepted is True


def test_due_sources_are_queued_without_being_crawled() -> None:
    """排入工作就結束了，不在這裡執行抓取。"""
    service = _service()

    refresh_after_response(service, "spouse_death", _FUNERAL_SCOPE, now=_NOW)

    assert [job.source_id for job in service.pending_jobs()] == ["src_pending"]


def test_a_second_request_on_the_same_day_is_deduplicated() -> None:
    """同一來源同一天不因為多個使用者請求重複觸發。"""
    service = _service()

    refresh_after_response(service, "spouse_death", _FUNERAL_SCOPE, now=_NOW)
    _, second = refresh_after_response(
        service, "spouse_death", _FUNERAL_SCOPE, now=_NOW
    )

    assert second is not None
    assert second.deduplicated is True
    assert len(service.pending_jobs()) == 1


def test_a_refresh_failure_does_not_revoke_the_coverage_answer() -> None:
    """refresh 失敗不阻塞也不撤銷目前的回應。"""
    service = _FailingRefreshService()

    snapshot, receipt = refresh_after_response(
        service, "spouse_death", _FUNERAL_SCOPE, now=_NOW
    )

    assert [entry.source_id for entry in snapshot.sources] == ["src_1"]
    assert receipt is None
    assert service.coverage_calls == 1


def test_no_related_sources_means_no_request_is_sent() -> None:
    """「不知道相關的是哪些」不等於「全部都相關」，所以不送請求。"""
    empty_scope = CoverageScope(source_ids=(), domain_tags=())
    service = _RecordingRefreshService(_snapshot((), scope=empty_scope))

    snapshot, receipt = refresh_after_response(
        service, "unmapped_event", empty_scope, now=_NOW
    )

    assert snapshot.sources == ()
    assert receipt is None
    assert service.requests == []


def test_the_request_carries_every_related_source() -> None:
    """到期判斷屬於 service，所以流程層把 scope 內來源全部交給它。"""
    sources = (
        CoverageMetadata(
            source_id="src_a",
            crawl_status="pending_crawl",
            last_crawled_at=None,
            indexed_document_count=0,
            domain_tags=("funeral",),
            observed_at=_NOW,
        ),
        CoverageMetadata(
            source_id="src_b",
            crawl_status="crawled",
            last_crawled_at=_NOW,
            indexed_document_count=2,
            domain_tags=("funeral",),
            observed_at=_NOW,
        ),
    )
    service = _RecordingRefreshService(_snapshot(sources))

    refresh_after_response(service, "spouse_death", _FUNERAL_SCOPE, now=_NOW)

    assert service.requests[0].source_ids == ("src_a", "src_b")
    assert service.requests[0].requested_at == _NOW
