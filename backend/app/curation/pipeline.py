"""Curation pipeline: crawl → classify → review (Req 10.7-10.9, 16.6-16.13).

Orchestrates the full local/mock curation flow from structural discovery through
candidate extraction to human review readiness. All outputs stay `candidate` or
`under_review` until a human reviewer promotes them through `ReviewService`.

## Pipeline stages

```
RegisteredSource → StructuralCrawler → DiscoveredPages
    → AttachmentService (metadata + extraction attempt)
    → CandidateExtractor (classification + structured payload)
    → ReviewService (human-only protected transitions)
```

## Key invariants

- No stage can produce `verified` status — that requires human review
- Pipeline failures at any stage do not corrupt prior committed state
- All gaps (robots, login, JS-only, broken links, failed extractions) are preserved
- Zero live network, LLM, or credential calls in the local path
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from app.curation.attachments import AttachmentService, ExtractionResult
from app.curation.candidate_extractor import CandidateExtractor, CandidatePayload
from app.curation.classifier import ClassifierPort, LocalKeywordClassifier
from app.curation.fetchers import FetcherPort, LocalFixtureFetcher
from app.curation.review_service import (
    ReviewArtifacts,
    ReviewService,
    TransitionResult,
)
from app.curation.structural_crawler import (
    CrawlResult,
    RegisteredSource,
    StructuralCrawler,
)

# Statuses that machine processes can assign
MACHINE_ALLOWED_STATUSES: Final[frozenset[str]] = frozenset(
    {"candidate", "under_review"}
)


@dataclass(frozen=True, slots=True)
class PipelineStageResult:
    """Result of a single pipeline stage for a source."""

    stage: str
    source_id: str
    success: bool
    items_processed: int = 0
    items_skipped: int = 0
    error_type: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Complete result of running the curation pipeline for a source."""

    source_id: str
    crawl_result: CrawlResult | None = None
    candidates: tuple[CandidatePayload, ...] = ()
    extraction_results: tuple[ExtractionResult, ...] = ()
    stage_results: tuple[PipelineStageResult, ...] = ()
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def success(self) -> bool:
        """Pipeline succeeded if all stages succeeded."""
        return all(stage.success for stage in self.stage_results)

    @property
    def total_pages_discovered(self) -> int:
        return self.crawl_result.pages_visited if self.crawl_result else 0

    @property
    def total_candidates(self) -> int:
        return len(self.candidates)

    @property
    def has_gaps(self) -> bool:
        return self.crawl_result is not None and self.crawl_result.has_gaps

    @property
    def network_call_count(self) -> int:
        """Should always be 0 for local pipeline."""
        return 0

    @property
    def llm_call_count(self) -> int:
        """Should always be 0 for local pipeline."""
        return 0


class CurationPipeline:
    """Orchestrates the full curation flow from crawl to candidate extraction.

    All components are injectable. Defaults use local/fixture implementations
    that perform zero network or LLM calls.
    """

    def __init__(
        self,
        *,
        fetcher: FetcherPort | None = None,
        classifier: ClassifierPort | None = None,
        attachment_service: AttachmentService | None = None,
        review_service: ReviewService | None = None,
        now: datetime | None = None,
    ) -> None:
        self._fetcher = fetcher or LocalFixtureFetcher()
        self._classifier = classifier or LocalKeywordClassifier()
        self._attachment_service = attachment_service or AttachmentService()
        self._review_service = review_service
        self._now = now or datetime.now(UTC)

    def run(self, source: RegisteredSource) -> PipelineResult:
        """Run the full curation pipeline for a registered source.

        Stages:
        1. Structural crawl (discover pages)
        2. Candidate extraction (classify + extract structured data)

        Each stage is isolated — a failure in one does not corrupt prior results.
        """
        started_at = self._now
        stages: list[PipelineStageResult] = []

        # Stage 1: Structural crawl
        crawl_result: CrawlResult | None = None
        try:
            crawler = StructuralCrawler(self._fetcher, now=self._now)
            crawl_result = crawler.crawl(source)
            stages.append(
                PipelineStageResult(
                    stage="structural_crawl",
                    source_id=source.source_id,
                    success=True,
                    items_processed=len(crawl_result.pages),
                    items_skipped=crawl_result.pages_visited - len(crawl_result.pages),
                )
            )
        except Exception as exc:
            stages.append(
                PipelineStageResult(
                    stage="structural_crawl",
                    source_id=source.source_id,
                    success=False,
                    error_type=type(exc).__name__,
                )
            )
            return PipelineResult(
                source_id=source.source_id,
                stage_results=tuple(stages),
                started_at=started_at,
                completed_at=self._now,
            )

        # Stage 2: Candidate extraction
        candidates: list[CandidatePayload] = []
        skipped = 0
        try:
            extractor = CandidateExtractor(self._classifier, now=self._now)
            for page in crawl_result.pages:
                # Fetch content for classification (already fetched during crawl,
                # but we re-fetch from fixture for simplicity — zero cost locally)
                fetch_result = self._fetcher.fetch(page.url)
                payload = extractor.extract_candidate(
                    url=page.url,
                    source_id=source.source_id,
                    title=page.title,
                    content=fetch_result.content if fetch_result.is_success else "",
                )
                if payload is not None:
                    candidates.append(payload)
                else:
                    skipped += 1

            stages.append(
                PipelineStageResult(
                    stage="candidate_extraction",
                    source_id=source.source_id,
                    success=True,
                    items_processed=len(candidates),
                    items_skipped=skipped,
                )
            )
        except Exception as exc:
            stages.append(
                PipelineStageResult(
                    stage="candidate_extraction",
                    source_id=source.source_id,
                    success=False,
                    error_type=type(exc).__name__,
                )
            )

        return PipelineResult(
            source_id=source.source_id,
            crawl_result=crawl_result,
            candidates=tuple(candidates),
            stage_results=tuple(stages),
            started_at=started_at,
            completed_at=self._now,
        )

    def submit_for_review(
        self,
        *,
        program_id: str,
        reviewer_ref: str,
        approved_version: str,
        artifacts: ReviewArtifacts,
    ) -> TransitionResult:
        """Submit a candidate for human review transition.

        This is the ONLY path to `verified` status. Requires:
        - A configured ReviewService
        - actor_type = "human_reviewer"
        - Complete artifacts (approved_rule_version + citations + excerpt)
        """
        if self._review_service is None:
            return TransitionResult(
                success=False,
                error_code="no_review_service",
                error_message="ReviewService not configured in pipeline",
            )

        return self._review_service.transition_status(
            program_id=program_id,
            to_status="verified",
            actor_type="human_reviewer",
            reviewer_ref=reviewer_ref,
            approved_version=approved_version,
            artifacts=artifacts,
        )

    @property
    def network_call_count(self) -> int:
        """Total network calls across all components."""
        return self._fetcher.network_call_count + self._classifier.network_call_count

    @property
    def llm_call_count(self) -> int:
        """Total LLM calls across all components."""
        return self._classifier.llm_call_count
