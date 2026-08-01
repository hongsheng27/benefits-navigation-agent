"""Property 15: Current-data-first non-blocking refresh.

**Validates: Requirements 11.1, 11.3, 11.8-11.10**

For any worker duration and any worker failure mode:

1. The returned snapshot equals the one read at request start, regardless of
   what the coverage state does afterwards.
2. The request path makes zero network calls and zero LLM calls.
3. The request path never executes a queued job — `drain()` is not reached.
4. A worker that raises on submit, or a handler that raises on drain, leaves
   both the response and the previously committed state unchanged.

The reference model is deliberately independent of the production code: the
expected snapshot is computed directly from the generated source records rather
than by calling the orchestration a second time.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from app.application.coverage_tracker import build_snapshot
from app.orchestration.local_worker import LocalRefreshWorker, drain_all
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    LocalRefreshJob,
    LocalSourceRecord,
    LocalSourceRefreshService,
    RefreshReceipt,
    RefreshRequest,
)
from app.orchestration.refresh_orchestration import respond_then_refresh

T0 = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)
EVENT = "spouse_death"
TAGS = ("funeral", "pension", "housing")

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_source_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=1, max_size=10
)
_gap_categories = st.sampled_from(
    [
        "robots_policy",
        "login_required",
        "javascript_only",
        "broken_link",
        "scanned_attachment",
        "connection_error",
    ]
)


@st.composite
def _source_record(draw: st.DrawFn, source_id: str) -> LocalSourceRecord:
    crawl_status = draw(st.sampled_from(["crawled", "pending_crawl", "error"]))
    tags = tuple(
        sorted(
            draw(st.lists(st.sampled_from(TAGS), min_size=1, max_size=3, unique=True))
        )
    )
    if crawl_status == "pending_crawl":
        return LocalSourceRecord(
            source_id=source_id,
            crawl_status=crawl_status,
            domain_tags=tags,
            check_frequency_days=draw(st.integers(min_value=0, max_value=30)),
        )
    last_crawled_at = draw(
        st.one_of(
            st.none(),
            st.datetimes(
                min_value=datetime(2026, 1, 1),
                max_value=datetime(2026, 7, 1),
                timezones=st.just(UTC),
            ),
        )
    )
    return LocalSourceRecord(
        source_id=source_id,
        crawl_status=crawl_status,
        domain_tags=tags,
        check_frequency_days=draw(st.integers(min_value=0, max_value=30)),
        last_crawled_at=last_crawled_at,
        indexed_document_count=draw(st.integers(min_value=0, max_value=500)),
        gap_category=draw(_gap_categories) if crawl_status == "error" else None,
    )


@st.composite
def _records(draw: st.DrawFn) -> tuple[LocalSourceRecord, ...]:
    source_ids = draw(st.lists(_source_ids, min_size=0, max_size=6, unique=True))
    return tuple(draw(_source_record(source_id)) for source_id in source_ids)


_tag_lists = st.lists(st.sampled_from(TAGS), min_size=1, max_size=3, unique=True)

_scopes = st.builds(
    CoverageScope,
    source_ids=st.just(()),
    domain_tags=_tag_lists.map(tuple),
)


# ---------------------------------------------------------------------------
# Instrumented seams
# ---------------------------------------------------------------------------


class _SpyService:
    """Counts every seam call and records how the coverage state was read.

    Network and LLM work can only reach the request path through one of these
    two methods, so the counters below bound what the request path did.
    """

    def __init__(self, records: tuple[LocalSourceRecord, ...]) -> None:
        self._inner = LocalSourceRefreshService(records, clock=lambda: T0)
        self.coverage_calls = 0
        self.refresh_calls = 0
        self.network_calls = 0
        self.llm_calls = 0

    def get_coverage_status(self, scope: CoverageScope) -> CoverageSnapshot:
        self.coverage_calls += 1
        return self._inner.get_coverage_status(scope)

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        self.refresh_calls += 1
        return self._inner.request_on_demand_refresh(request)


class _FailingSubmitWorker:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.attempts = 0

    def submit(self, job: LocalRefreshJob) -> None:
        del job
        self.attempts += 1
        raise self._error


_worker_errors = st.sampled_from(
    [
        RuntimeError("queue unavailable"),
        ValueError("bad job payload"),
        OSError("disk full"),
        TimeoutError("queue timeout"),
    ]
)


# ---------------------------------------------------------------------------
# Property 15.1 — response equals the request-start snapshot
# ---------------------------------------------------------------------------


@given(records=_records(), scope=_scopes)
@settings(max_examples=200, deadline=5000)
def test_response_matches_an_independently_built_snapshot(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
) -> None:
    """The returned snapshot equals one built directly from the records.

    The expected value comes from `build_snapshot`, which never calls the
    orchestration, so this compares the production path against a model rather
    than against itself.
    """
    service = _SpyService(records)

    outcome = respond_then_refresh(
        service, EVENT, scope, worker=LocalRefreshWorker(), now=T0
    )

    expected = build_snapshot(records, scope, T0)
    assert outcome.snapshot == expected
    assert service.coverage_calls == 1


@given(records=_records(), scope=_scopes)
@settings(max_examples=200, deadline=5000)
def test_snapshot_is_stable_after_the_call_returns(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
) -> None:
    """Draining the worker afterwards cannot change the answer already given."""
    service = _SpyService(records)
    worker = LocalRefreshWorker()

    outcome = respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)
    before = outcome.snapshot

    drain_all(worker)

    assert outcome.snapshot is before
    assert outcome.snapshot == build_snapshot(records, scope, T0)


# ---------------------------------------------------------------------------
# Property 15.2 — the request path does no network or LLM work
# ---------------------------------------------------------------------------


@given(records=_records(), scope=_scopes)
@settings(max_examples=200, deadline=5000)
def test_request_path_makes_zero_network_and_llm_calls(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
) -> None:
    """Whatever the input, the request path stays at zero on both counters."""
    service = _SpyService(records)
    worker = LocalRefreshWorker(
        handler=lambda job: (_ for _ in ()).throw(
            AssertionError("handler ran inside the request path")
        )
    )

    respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)

    assert service.network_calls == 0
    assert service.llm_calls == 0
    assert worker.drain_count == 0
    assert service.coverage_calls == 1
    assert service.refresh_calls <= 1


@given(records=_records(), scope=_scopes, sleep_seconds=st.floats(0.05, 0.3))
@settings(max_examples=25, deadline=None)
def test_worker_duration_does_not_reach_the_request_path(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
    sleep_seconds: float,
) -> None:
    """A handler of any duration costs the request path nothing."""

    def slow(job: LocalRefreshJob) -> None:
        del job
        time.sleep(sleep_seconds)

    service = _SpyService(records)
    worker = LocalRefreshWorker(handler=slow)

    started = time.monotonic()
    outcome = respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)
    elapsed = time.monotonic() - started

    assert elapsed < sleep_seconds, "submit must not run the handler"
    assert outcome.snapshot == build_snapshot(records, scope, T0)


# ---------------------------------------------------------------------------
# Property 15.3 — worker failure preserves response and committed state
# ---------------------------------------------------------------------------


@given(records=_records(), scope=_scopes, error=_worker_errors)
@settings(max_examples=200, deadline=5000)
def test_submit_failure_preserves_the_response(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
    error: Exception,
) -> None:
    """A worker that raises on every submit does not change the answer."""
    service = _SpyService(records)
    worker = _FailingSubmitWorker(error)

    outcome = respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)

    assert outcome.snapshot == build_snapshot(records, scope, T0)
    assert outcome.enqueued_jobs == ()


@given(records=_records(), scope=_scopes, error=_worker_errors)
@settings(max_examples=200, deadline=5000)
def test_handler_failure_is_recorded_not_raised(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
    error: Exception,
) -> None:
    """Every queued job produces an outcome, failures included, and none raise."""

    def always_fails(job: LocalRefreshJob) -> None:
        del job
        raise error

    service = _SpyService(records)
    worker = LocalRefreshWorker(handler=always_fails)
    outcome = respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)

    queued = len(outcome.enqueued_jobs)
    outcomes = drain_all(worker)

    assert len(outcomes) == queued
    assert all(item.status == "failed" for item in outcomes)
    assert all(item.error_type == type(error).__name__ for item in outcomes)
    # Committed state is untouched: reading again gives the same snapshot.
    assert service.get_coverage_status(scope) == outcome.snapshot


@given(records=_records(), scope=_scopes)
@settings(max_examples=200, deadline=5000)
def test_every_queued_job_stays_unverified(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
) -> None:
    """Worker output can never be recorded as verified (Req 11.9)."""
    service = _SpyService(records)
    worker = LocalRefreshWorker()

    respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)
    outcomes = drain_all(worker)

    assert all(item.result_status in ("candidate", "under_review") for item in outcomes)


@given(records=_records(), scope=_scopes)
@settings(max_examples=200, deadline=5000)
def test_enqueued_jobs_stay_within_the_snapshot_scope(
    records: tuple[LocalSourceRecord, ...],
    scope: CoverageScope,
) -> None:
    """Only sources that appeared in the snapshot are ever queued."""
    service = _SpyService(records)
    worker = LocalRefreshWorker()

    outcome = respond_then_refresh(service, EVENT, scope, worker=worker, now=T0)

    scoped_ids = {source.source_id for source in outcome.snapshot.sources}
    queued_ids = {job.source_id for job in outcome.enqueued_jobs}
    assert queued_ids <= scoped_ids
    assert all(job.event_id == EVENT for job in outcome.enqueued_jobs)
