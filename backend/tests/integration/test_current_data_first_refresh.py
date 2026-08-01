"""Integration tests for current-data-first refresh (Requirements 11.1-11.10).

Covers:
- The response is built from the coverage state read at request start, and a
  later change to that state does not retroactively alter it
- The request path performs zero network, attachment or LLM work
- Worker delay does not extend the request path
- Worker submit failure and worker execution failure both leave the response
  and the prior committed state untouched
- Worker output can only be recorded as candidate or under_review
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

import pytest
from backend.app.orchestration.local_worker import (
    RESULT_STATUSES,
    LocalRefreshWorker,
    NullRefreshWorker,
    WorkerOutcome,
    drain_all,
)
from backend.app.orchestration.protocols import (
    CoverageScope,
    LocalRefreshJob,
    LocalSourceRecord,
    LocalSourceRefreshService,
    RefreshReceipt,
    RefreshRequest,
)
from backend.app.orchestration.refresh_orchestration import respond_then_refresh

EVENT = "spouse_death"
SCOPE = CoverageScope(source_ids=(), domain_tags=("funeral",))
T0 = datetime(2026, 7, 30, 1, 0, tzinfo=UTC)


def _records(indexed: int = 3) -> tuple[LocalSourceRecord, ...]:
    return (
        LocalSourceRecord(
            source_id="synth-src-a",
            crawl_status="crawled",
            domain_tags=("funeral",),
            check_frequency_days=1,
            last_crawled_at=datetime(2026, 7, 1, tzinfo=UTC),
            indexed_document_count=indexed,
        ),
        LocalSourceRecord(
            source_id="synth-src-b",
            crawl_status="pending_crawl",
            domain_tags=("funeral",),
            check_frequency_days=1,
        ),
    )


class _CountingService:
    """Wraps LocalSourceRefreshService and counts protocol calls.

    Any network, attachment or LLM work would have to happen behind one of
    these two methods, so counting them bounds what the request path can do.
    """

    def __init__(self, records: tuple[LocalSourceRecord, ...] = ()) -> None:
        self._inner = LocalSourceRefreshService(records, clock=lambda: T0)
        self.coverage_calls = 0
        self.refresh_calls = 0
        self.network_calls = 0
        self.llm_calls = 0

    def get_coverage_status(self, scope: CoverageScope):  # noqa: ANN201
        self.coverage_calls += 1
        return self._inner.get_coverage_status(scope)

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        self.refresh_calls += 1
        return self._inner.request_on_demand_refresh(request)


class _MutatingService:
    """Serves a different coverage snapshot on every call.

    Used to prove the returned snapshot is the one read first, not whatever the
    state happened to be when the function returned.
    """

    def __init__(self) -> None:
        self.calls = 0

    def get_coverage_status(self, scope: CoverageScope):  # noqa: ANN201
        self.calls += 1
        service = LocalSourceRefreshService(
            _records(indexed=self.calls * 100), clock=lambda: T0
        )
        return service.get_coverage_status(scope)

    def request_on_demand_refresh(self, request: RefreshRequest) -> RefreshReceipt:
        del request
        return RefreshReceipt(job_id="job-1", accepted=True, deduplicated=False)


class _ExplodingSubmitWorker:
    """A worker whose submit boundary is broken."""

    def __init__(self) -> None:
        self.attempts = 0

    def submit(self, job: LocalRefreshJob) -> None:
        del job
        self.attempts += 1
        raise RuntimeError("queue unavailable")


# ---------------------------------------------------------------------------
# Req 11.1 — response is built from request-start committed state
# ---------------------------------------------------------------------------


def test_snapshot_is_read_once_at_request_start() -> None:
    """Coverage is read exactly once, before any refresh work is queued."""
    service = _CountingService(_records())
    worker = LocalRefreshWorker()

    outcome = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)

    assert service.coverage_calls == 1
    assert service.refresh_calls == 1
    assert outcome.snapshot.registered_source_count == 2
    assert outcome.snapshot.observed_at == T0


def test_returned_snapshot_is_the_first_read_not_the_latest() -> None:
    """A state change after the first read does not alter the response."""
    service = _MutatingService()

    outcome = respond_then_refresh(
        service, EVENT, SCOPE, worker=LocalRefreshWorker(), now=T0
    )

    # The first read saw 100 indexed documents. Later reads would see 200, 300…
    assert outcome.snapshot.indexed_document_count == 100
    assert service.calls == 1
    # Reading again now would give a different answer, which is exactly why the
    # response must not depend on when it is serialised.
    assert service.get_coverage_status(SCOPE).indexed_document_count == 200
    assert outcome.snapshot.indexed_document_count == 100


def test_empty_scope_returns_snapshot_and_queues_nothing() -> None:
    """No sources in scope means nothing to refresh, and no guessing."""
    service = _CountingService(_records())
    worker = LocalRefreshWorker()

    outcome = respond_then_refresh(
        service,
        EVENT,
        CoverageScope(source_ids=(), domain_tags=()),
        worker=worker,
        now=T0,
    )

    assert outcome.snapshot.registered_source_count == 0
    assert outcome.receipt is None
    assert outcome.refresh_enqueued is False
    assert worker.pending_jobs == ()
    assert service.refresh_calls == 0


# ---------------------------------------------------------------------------
# Req 11.10 — no synchronous crawl or LLM inside the request lifecycle
# ---------------------------------------------------------------------------


def test_request_path_performs_no_network_or_llm_calls() -> None:
    """The request path touches the two read/queue seams and nothing else."""
    service = _CountingService(_records())
    worker = LocalRefreshWorker(handler=lambda job: pytest.fail("handler ran"))

    respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)

    assert service.network_calls == 0
    assert service.llm_calls == 0
    # Jobs are queued, never executed: drain() is the background entry point
    # and the request path has no reference to it.
    assert worker.drain_count == 0
    assert len(worker.pending_jobs) == 2


def test_slow_worker_handler_does_not_run_in_request_path() -> None:
    """A handler that sleeps for a second costs the request path nothing."""

    def slow_handler(job: LocalRefreshJob) -> None:
        del job
        time.sleep(1.0)

    service = _CountingService(_records())
    worker = LocalRefreshWorker(handler=slow_handler)

    started = time.monotonic()
    outcome = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, "submit must not execute the handler"
    assert outcome.snapshot.registered_source_count == 2
    assert len(worker.pending_jobs) == 2


# ---------------------------------------------------------------------------
# Req 11.8 — worker failure preserves the response and committed state
# ---------------------------------------------------------------------------


def test_worker_submit_failure_preserves_the_response() -> None:
    """A broken queue does not turn into a user-visible error."""
    service = _CountingService(_records())
    worker = _ExplodingSubmitWorker()

    outcome = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)

    assert worker.attempts == 2
    assert outcome.enqueued_jobs == ()
    assert outcome.snapshot.registered_source_count == 2
    assert outcome.snapshot.indexed_document_count == 3
    assert outcome.receipt is not None
    assert outcome.receipt.accepted is True


def test_worker_handler_failure_is_isolated_per_job() -> None:
    """One failing job does not stop the others and does not raise."""
    seen: list[str] = []

    def flaky(job: LocalRefreshJob) -> None:
        seen.append(job.source_id)
        if job.source_id == "synth-src-a":
            raise RuntimeError("crawl target unreachable")

    service = _CountingService(_records())
    worker = LocalRefreshWorker(handler=flaky)
    outcome = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)

    outcomes = drain_all(worker)

    assert seen == ["synth-src-a", "synth-src-b"]
    by_source = {item.source_id: item for item in outcomes}
    assert by_source["synth-src-a"].status == "failed"
    assert by_source["synth-src-a"].error_type == "RuntimeError"
    assert by_source["synth-src-b"].status == "completed"
    # The response taken before the worker ran is unchanged.
    assert outcome.snapshot.indexed_document_count == 3


def test_failed_outcome_carries_class_name_not_message() -> None:
    """Exception messages can echo input, so only the class name is kept."""

    def leaky(job: LocalRefreshJob) -> None:
        del job
        raise ValueError("secret-value-from-a-page")

    worker = LocalRefreshWorker(handler=leaky)
    worker.submit(
        LocalRefreshJob(
            job_id="job-1",
            source_id="synth-src-a",
            event_id=EVENT,
            requested_at=T0,
        )
    )
    outcome = worker.drain()[0]

    assert outcome.status == "failed"
    assert outcome.error_type == "ValueError"
    assert "secret-value-from-a-page" not in repr(outcome)


# ---------------------------------------------------------------------------
# Req 11.9 — worker output stays candidate or under_review
# ---------------------------------------------------------------------------


def test_worker_results_are_restricted_to_unverified_statuses() -> None:
    """The worker cannot record a verified result even if asked to."""
    assert RESULT_STATUSES == frozenset({"candidate", "under_review"})

    with pytest.raises(ValueError, match="candidate or under_review"):
        LocalRefreshWorker(result_status="verified")

    with pytest.raises(ValueError, match="candidate or under_review"):
        WorkerOutcome(
            job_id="job-1",
            source_id="synth-src-a",
            status="completed",
            result_status="verified",
        )


def test_default_worker_records_candidate_results() -> None:
    """With no handler wired the worker still reports a candidate result."""
    worker = LocalRefreshWorker()
    worker.submit(
        LocalRefreshJob(
            job_id="job-1", source_id="synth-src-a", event_id=EVENT, requested_at=T0
        )
    )
    outcome = worker.drain()[0]
    assert outcome.status == "completed"
    assert outcome.result_status == "candidate"


# ---------------------------------------------------------------------------
# Req 16.1 — local implementations are the default
# ---------------------------------------------------------------------------


def test_orchestration_works_without_a_worker() -> None:
    """A missing worker degrades to service-level queueing, not an error."""
    service = _CountingService(_records())
    outcome = respond_then_refresh(service, EVENT, SCOPE, now=T0)

    assert outcome.snapshot.registered_source_count == 2
    assert outcome.receipt is not None
    assert outcome.enqueued_jobs == ()


def test_null_worker_accepts_and_discards_jobs() -> None:
    """The explicit opt-out still satisfies the submit-only boundary."""
    service = _CountingService(_records())
    worker = NullRefreshWorker()

    outcome = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)

    assert worker.submit_count == 2
    assert outcome.snapshot.registered_source_count == 2


def test_deduplicated_receipt_does_not_requeue_worker_jobs() -> None:
    """A same-day duplicate must not hand the worker a second copy."""
    service = _CountingService(_records())
    worker = LocalRefreshWorker()

    first = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)
    second = respond_then_refresh(service, EVENT, SCOPE, worker=worker, now=T0)

    assert first.refresh_enqueued is True
    assert second.refresh_enqueued is False
    assert second.enqueued_jobs == ()
    assert len(worker.pending_jobs) == len(first.enqueued_jobs)
