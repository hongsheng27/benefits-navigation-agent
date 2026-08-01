"""Integration tests for the curation pipeline and review transitions (Task 12.4, 12.5).

Covers:
- Full pipeline flow: crawl → classify → extract candidates
- Human-only protected transitions (non-human actors blocked)
- Incomplete artifacts block verified transition
- Complete artifacts with human reviewer succeed
- Pipeline stage isolation (failure in one stage doesn't corrupt prior state)
- Zero live HTTP/AWS/credential/LLM calls throughout
- Synthetic/fixture isolated test data
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.curation.fetchers import FetchResult, LocalFixtureFetcher
from app.curation.pipeline import (
    MACHINE_ALLOWED_STATUSES,
    CurationPipeline,
)
from app.curation.review_service import (
    FORBIDDEN_ACTORS,
    ReviewArtifacts,
    ReviewService,
    check_candidate_artifacts,
    validate_transition,
)
from app.curation.structural_crawler import RegisteredSource

T0 = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)

SYNTH_SOURCE = RegisteredSource(
    source_id="synth-pipeline-src",
    name="Synthetic Pipeline Source",
    entry_url="https://synth-pipeline.example.gov.tw/index",
    canonical_host="synth-pipeline.example.gov.tw",
    enabled=True,
)


def _page_html(title: str, links: list[str] | None = None) -> str:
    link_tags = ""
    if links:
        link_tags = "\n".join(f'<a href="{url}">Link</a>' for url in links)
    return (
        f"<html><head><title>{title}</title></head>"
        f"<body>喪葬給付補助申請{link_tags}</body></html>"
    )


class _InMemoryPersistence:
    """In-memory persistence for review service tests."""

    def __init__(self) -> None:
        self._statuses: dict[str, str] = {}
        self._records: list = []

    def seed(self, program_id: str, status: str) -> None:
        self._statuses[program_id] = status

    def persist_transition(self, record) -> None:
        self._statuses[record.program_id] = record.to_status
        self._records.append(record)

    def get_current_status(self, program_id: str) -> str | None:
        return self._statuses.get(program_id)


# ---------------------------------------------------------------------------
# Full pipeline flow
# ---------------------------------------------------------------------------


def test_pipeline_full_flow() -> None:
    """Pipeline runs crawl → classify → extract without errors."""
    fetcher = LocalFixtureFetcher()
    fetcher.configure_response(
        SYNTH_SOURCE.entry_url,
        FetchResult(
            url=SYNTH_SOURCE.entry_url,
            status_code=200,
            content=_page_html(
                "喪葬給付", ["https://synth-pipeline.example.gov.tw/apply"]
            ),
        ),
    )
    fetcher.configure_response(
        "https://synth-pipeline.example.gov.tw/apply",
        FetchResult(
            url="https://synth-pipeline.example.gov.tw/apply",
            status_code=200,
            content=_page_html("申請辦理"),
        ),
    )

    pipeline = CurationPipeline(fetcher=fetcher, now=T0)
    result = pipeline.run(SYNTH_SOURCE)

    assert result.success
    assert result.total_pages_discovered >= 1
    assert result.total_candidates >= 1
    assert all(c.review_status == "candidate" for c in result.candidates)


def test_pipeline_zero_network_and_llm() -> None:
    """Pipeline makes zero network and LLM calls."""
    fetcher = LocalFixtureFetcher(default_content=_page_html("Test"))
    pipeline = CurationPipeline(fetcher=fetcher, now=T0)

    pipeline.run(SYNTH_SOURCE)

    assert pipeline.network_call_count == 0
    assert pipeline.llm_call_count == 0


def test_pipeline_candidates_are_never_verified() -> None:
    """All pipeline outputs stay candidate/under_review."""
    fetcher = LocalFixtureFetcher(default_content=_page_html("給付補助"))
    pipeline = CurationPipeline(fetcher=fetcher, now=T0)

    result = pipeline.run(SYNTH_SOURCE)
    for candidate in result.candidates:
        assert candidate.review_status in MACHINE_ALLOWED_STATUSES
        assert candidate.review_status != "verified"


# ---------------------------------------------------------------------------
# Stage isolation
# ---------------------------------------------------------------------------


def test_crawl_failure_does_not_produce_candidates() -> None:
    """If crawl fails (disabled source), no candidates are produced."""
    disabled_source = RegisteredSource(
        source_id="disabled",
        name="Disabled",
        entry_url="https://disabled.example.gov.tw/",
        canonical_host="disabled.example.gov.tw",
        enabled=False,
    )
    fetcher = LocalFixtureFetcher()
    pipeline = CurationPipeline(fetcher=fetcher, now=T0)

    result = pipeline.run(disabled_source)
    assert not result.success
    assert result.candidates == ()


# ---------------------------------------------------------------------------
# Human-only protected transitions
# ---------------------------------------------------------------------------


def test_human_reviewer_with_complete_artifacts_succeeds() -> None:
    """Human reviewer with all artifacts can transition to verified."""
    persistence = _InMemoryPersistence()
    persistence.seed("prog-001", "under_review")
    service = ReviewService(persistence)

    artifacts = ReviewArtifacts(
        approved_rule_version="v1.0",
        citation_ids=("cite-001",),
        approved_excerpt="依據勞保條例第62條",
    )

    result = service.transition_status(
        program_id="prog-001",
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-a",
        approved_version="v1.0",
        artifacts=artifacts,
    )

    assert result.success
    assert result.audit_record is not None
    assert result.audit_record.to_status == "verified"


def test_non_human_actor_blocked_from_verified() -> None:
    """Non-human actors cannot transition to verified."""
    persistence = _InMemoryPersistence()
    persistence.seed("prog-001", "candidate")
    service = ReviewService(persistence)

    for actor_type in FORBIDDEN_ACTORS:
        result = service.transition_status(
            program_id="prog-001",
            to_status="verified",
            actor_type=actor_type,
            reviewer_ref=f"machine-{actor_type}",
            approved_version="v1.0",
            artifacts=ReviewArtifacts(
                approved_rule_version="v1.0",
                citation_ids=("cite-001",),
                approved_excerpt="text",
            ),
        )

        assert not result.success
        assert result.error_code == "forbidden_actor"


def test_incomplete_artifacts_block_verified() -> None:
    """Human reviewer without complete artifacts cannot verify."""
    persistence = _InMemoryPersistence()
    persistence.seed("prog-001", "under_review")
    service = ReviewService(persistence)

    # Missing citation_ids
    artifacts = ReviewArtifacts(
        approved_rule_version="v1.0",
        citation_ids=(),
        approved_excerpt="text",
    )

    result = service.transition_status(
        program_id="prog-001",
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-a",
        approved_version="v1.0",
        artifacts=artifacts,
    )

    assert not result.success
    assert result.error_code == "incomplete_artifacts"


def test_no_artifacts_blocks_verified() -> None:
    """No artifacts at all blocks verified transition."""
    persistence = _InMemoryPersistence()
    persistence.seed("prog-001", "candidate")
    service = ReviewService(persistence)

    result = service.transition_status(
        program_id="prog-001",
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-a",
        approved_version="v1.0",
        artifacts=None,
    )

    assert not result.success
    assert result.error_code == "incomplete_artifacts"


# ---------------------------------------------------------------------------
# Candidate artifact completeness
# ---------------------------------------------------------------------------


def test_check_artifacts_complete() -> None:
    """Complete artifacts pass readiness check."""
    artifacts = ReviewArtifacts(
        approved_rule_version="v1.0",
        citation_ids=("cite-001",),
        approved_excerpt="依據條例辦理",
    )
    check = check_candidate_artifacts("prog-001", artifacts)

    assert check.is_ready_for_review
    assert check.missing_artifacts == ()


def test_check_artifacts_incomplete() -> None:
    """Incomplete artifacts report what's missing."""
    artifacts = ReviewArtifacts(
        approved_rule_version=None,
        citation_ids=(),
        approved_excerpt=None,
    )
    check = check_candidate_artifacts("prog-001", artifacts)

    assert not check.is_ready_for_review
    assert "approved_rule_version" in check.missing_artifacts
    assert "citations" in check.missing_artifacts
    assert "approved_excerpt" in check.missing_artifacts


def test_check_artifacts_none() -> None:
    """None artifacts means nothing is ready."""
    check = check_candidate_artifacts("prog-001", None)
    assert not check.is_ready_for_review


# ---------------------------------------------------------------------------
# Pipeline submit_for_review integration
# ---------------------------------------------------------------------------


def test_pipeline_submit_for_review_with_service() -> None:
    """Pipeline can submit for review when ReviewService is configured."""
    persistence = _InMemoryPersistence()
    persistence.seed("prog-001", "under_review")
    service = ReviewService(persistence)

    fetcher = LocalFixtureFetcher()
    pipeline = CurationPipeline(
        fetcher=fetcher,
        review_service=service,
        now=T0,
    )

    result = pipeline.submit_for_review(
        program_id="prog-001",
        reviewer_ref="reviewer-a",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("cite-001",),
            approved_excerpt="依據條例",
        ),
    )

    assert result.success


def test_pipeline_submit_without_service_fails() -> None:
    """Without ReviewService, submit_for_review returns error."""
    pipeline = CurationPipeline(now=T0)

    result = pipeline.submit_for_review(
        program_id="prog-001",
        reviewer_ref="reviewer-a",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("cite-001",),
            approved_excerpt="text",
        ),
    )

    assert not result.success
    assert result.error_code == "no_review_service"


# ---------------------------------------------------------------------------
# Machine outputs restricted to candidate/under_review
# ---------------------------------------------------------------------------


def test_machine_allowed_statuses_exclude_verified() -> None:
    """Machine processes can only produce candidate or under_review."""
    assert "verified" not in MACHINE_ALLOWED_STATUSES
    assert MACHINE_ALLOWED_STATUSES == frozenset({"candidate", "under_review"})


def test_validate_transition_blocks_all_forbidden_actors() -> None:
    """Every forbidden actor type is blocked from verified transitions."""
    for actor in FORBIDDEN_ACTORS:
        error = validate_transition(
            program_id="prog-001",
            from_status="candidate",
            to_status="verified",
            actor_type=actor,
            artifacts=ReviewArtifacts(
                approved_rule_version="v1.0",
                citation_ids=("cite-001",),
                approved_excerpt="text",
            ),
        )
        assert error == "forbidden_actor"
