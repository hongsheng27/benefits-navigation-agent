"""驗證 on-demand refresh 的流程：先回答，再更新。

提案第 9 節的三個重點在這裡各有一組測試：先回傳目前 coverage 狀態、以非阻塞方式排入
refresh、refresh 失敗不阻塞也不撤銷目前的回應。
"""

from datetime import UTC, datetime

from app.orchestration.data_contracts import CoverageMetadata
from app.orchestration.protocols import (
    LocalSourceRecord,
    LocalSourceRefreshService,
    RefreshReceipt,
    RefreshRequest,
)
from app.orchestration.source_refresh import refresh_after_response

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


class _FailingRefreshService:
    """coverage 查得到，但排入工作會失敗。"""

    def __init__(self) -> None:
        self.coverage_calls = 0

    def get_coverage_status(self, event_id: str) -> tuple[CoverageMetadata, ...]:
        del event_id
        self.coverage_calls += 1
        return (
            CoverageMetadata(
                source_id="src_1",
                crawl_status="pending_crawl",
                last_crawled_at=None,
                indexed_document_count=0,
                domain_tags=("funeral",),
            ),
        )

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        del request
        msg = "本機佇列不可用"
        raise RuntimeError(msg)


class _RecordingRefreshService:
    """記錄有沒有被要求排入工作。"""

    def __init__(self, coverage: tuple[CoverageMetadata, ...]) -> None:
        self._coverage = coverage
        self.requests: list[RefreshRequest] = []

    def get_coverage_status(self, event_id: str) -> tuple[CoverageMetadata, ...]:
        del event_id
        return self._coverage

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
        event_domain_tags={"spouse_death": ("funeral",)},
    )


def test_coverage_comes_back_with_the_current_local_data() -> None:
    """回應用的是目前本機資料，不是刷新之後的資料。

    來源仍然是 `pending_crawl`，證明這一次呼叫沒有等待任何抓取完成。
    """
    coverage, receipt = refresh_after_response(_service(), "spouse_death", now=_NOW)

    assert [entry.source_id for entry in coverage] == ["src_pending"]
    assert coverage[0].crawl_status == "pending_crawl"
    assert receipt is not None
    assert receipt.accepted is True


def test_due_sources_are_queued_without_being_crawled() -> None:
    """排入工作就結束了，不在這裡執行抓取。"""
    service = _service()

    refresh_after_response(service, "spouse_death", now=_NOW)

    assert [job.source_id for job in service.pending_jobs()] == ["src_pending"]


def test_a_second_request_on_the_same_day_is_deduplicated() -> None:
    """同一來源同一天不因為多個使用者請求重複觸發。"""
    service = _service()

    refresh_after_response(service, "spouse_death", now=_NOW)
    _, second = refresh_after_response(service, "spouse_death", now=_NOW)

    assert second is not None
    assert second.deduplicated is True
    assert len(service.pending_jobs()) == 1


def test_a_refresh_failure_does_not_revoke_the_coverage_answer() -> None:
    """refresh 失敗不阻塞也不撤銷目前的回應。"""
    service = _FailingRefreshService()

    coverage, receipt = refresh_after_response(service, "spouse_death", now=_NOW)

    assert [entry.source_id for entry in coverage] == ["src_1"]
    assert receipt is None
    assert service.coverage_calls == 1


def test_no_related_sources_means_no_request_is_sent() -> None:
    """「不知道相關的是哪些」不等於「全部都相關」，所以不送請求。"""
    service = _RecordingRefreshService(coverage=())

    coverage, receipt = refresh_after_response(service, "unmapped_event", now=_NOW)

    assert coverage == ()
    assert receipt is None
    assert service.requests == []


def test_the_request_carries_every_related_source() -> None:
    """到期判斷屬於 service，所以流程層把相關來源全部交給它。"""
    coverage = (
        CoverageMetadata(
            source_id="src_a",
            crawl_status="pending_crawl",
            last_crawled_at=None,
            indexed_document_count=0,
            domain_tags=("funeral",),
        ),
        CoverageMetadata(
            source_id="src_b",
            crawl_status="crawled",
            last_crawled_at=_NOW,
            indexed_document_count=2,
            domain_tags=("funeral",),
        ),
    )
    service = _RecordingRefreshService(coverage=coverage)

    refresh_after_response(service, "spouse_death", now=_NOW)

    assert service.requests[0].source_ids == ("src_a", "src_b")
    assert service.requests[0].requested_at == _NOW
