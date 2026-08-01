"""Local/mock page candidate extraction (Req 10.7, 11.9, 15.2, 15.3, 16.5-16.8).

Uses the classifier to produce structured candidate/under_review payloads from
discovered pages. Does NOT produce:
- Eligibility status
- Verified state
- Real unapproved excerpts
- Inferred metadata

## Design

The extractor takes classified pages and produces `CandidatePayload` — a structured
representation of what was found. These payloads are always `candidate` or
`under_review` and require human review before they can influence eligibility.

The extraction pipeline is:
1. Classifier determines document_type
2. Extractor produces structured payload based on type
3. Payload stays candidate until human review promotes it
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final

from app.curation.classifier import ClassifierPort

# Only these statuses are allowed for extracted candidates
ALLOWED_STATUSES: Final[frozenset[str]] = frozenset({"candidate", "under_review"})


@dataclass(frozen=True, slots=True)
class CandidatePayload:
    """Structured candidate extracted from a classified page.

    Always `candidate` or `under_review` — never `verified`.
    Does not contain eligibility status or real excerpts.
    """

    url: str
    source_id: str
    document_type: str
    title: str
    classification_confidence: float
    review_status: str = "candidate"
    extracted_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Structured fields — all optional, filled only from page structure
    publisher_name: str = ""
    jurisdiction_code: str = ""
    keywords_matched: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.review_status not in ALLOWED_STATUSES:
            raise ValueError(
                f"review_status must be one of {ALLOWED_STATUSES}, "
                f"got '{self.review_status}'"
            )


@dataclass(frozen=True, slots=True)
class ExtractionBatchResult:
    """Result of extracting candidates from a batch of pages."""

    source_id: str
    payloads: tuple[CandidatePayload, ...]
    skipped_count: int
    llm_call_count: int
    network_call_count: int

    @property
    def candidate_count(self) -> int:
        return len(self.payloads)


class CandidateExtractor:
    """Extracts structured candidate payloads from discovered pages.

    Uses the classifier to determine document type, then produces a
    structured payload. All outputs are `candidate` — no automatic verification.
    """

    def __init__(
        self,
        classifier: ClassifierPort,
        *,
        min_confidence: float = 0.2,
        now: datetime | None = None,
    ) -> None:
        self._classifier = classifier
        self._min_confidence = min_confidence
        self._now = now or datetime.now(UTC)

    def extract_candidate(
        self,
        *,
        url: str,
        source_id: str,
        title: str,
        content: str,
    ) -> CandidatePayload | None:
        """Extract a single candidate from a page.

        Returns None if the classification confidence is below threshold.
        The result is always `candidate` — never verified.
        """
        classification = self._classifier.classify(url, title, content)

        if classification.confidence < self._min_confidence:
            return None

        return CandidatePayload(
            url=url,
            source_id=source_id,
            document_type=classification.document_type,
            title=title,
            classification_confidence=classification.confidence,
            review_status="candidate",
            extracted_at=self._now,
            keywords_matched=classification.keywords_matched,
        )

    def extract_batch(
        self,
        pages: list[tuple[str, str, str, str]],
        source_id: str,
    ) -> ExtractionBatchResult:
        """Extract candidates from a batch of (url, title, content, source_id) tuples.

        Pages below confidence threshold are skipped (counted in `skipped_count`).
        """
        payloads: list[CandidatePayload] = []
        skipped = 0

        for url, title, content, _ in pages:
            result = self.extract_candidate(
                url=url,
                source_id=source_id,
                title=title,
                content=content,
            )
            if result is None:
                skipped += 1
            else:
                payloads.append(result)

        return ExtractionBatchResult(
            source_id=source_id,
            payloads=tuple(payloads),
            skipped_count=skipped,
            llm_call_count=self._classifier.llm_call_count,
            network_call_count=self._classifier.network_call_count,
        )

    @property
    def llm_call_count(self) -> int:
        return self._classifier.llm_call_count

    @property
    def network_call_count(self) -> int:
        return self._classifier.network_call_count
