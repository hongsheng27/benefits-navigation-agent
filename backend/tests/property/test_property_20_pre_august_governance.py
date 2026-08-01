"""Property 20: Pre-August local/mock governance.

**Validates: Requirements 15.2-15.4, 16.1-16.13**

For any combination of curation pipeline operations before the deadline:

1. All paths have zero live HTTP/network calls.
2. All paths have zero credential lookups.
3. All paths have zero live LLM calls.
4. Non-human actors cannot perform protected transitions (→ verified).
5. Machine outputs can only be `candidate` or `under_review`.
6. Human reviewer with complete artifacts CAN perform protected transitions.
"""

from __future__ import annotations

from datetime import UTC, datetime

from hypothesis import given, settings
from hypothesis import strategies as st

from app.curation.attachments import (
    AttachmentMetadata,
    LocalExtractionHandler,
)
from app.curation.candidate_extractor import ALLOWED_STATUSES, CandidateExtractor
from app.curation.classifier import CLASSIFICATION_STATUSES, LocalKeywordClassifier
from app.curation.fetchers import LocalFixtureFetcher
from app.curation.pipeline import MACHINE_ALLOWED_STATUSES, CurationPipeline
from app.curation.review_service import (
    FORBIDDEN_ACTORS,
    ReviewArtifacts,
    ReviewService,
    validate_transition,
)
from app.curation.structural_crawler import (
    ALLOWED_DISCOVERY_STATUSES,
    RegisteredSource,
    StructuralCrawler,
)

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_source_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-", min_size=3, max_size=12
)

_titles = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz給付申請補助條例辦法", min_size=1, max_size=20
)

_contents = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz給付申請補助津貼年金條例辦法規定 ",
    min_size=5,
    max_size=100,
)

_urls = st.builds(
    lambda path: f"https://synth.example.gov.tw/{path}",
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789/-", min_size=1, max_size=20),
)

_actor_types = st.sampled_from(sorted(FORBIDDEN_ACTORS))

_observed_at = st.datetimes(
    min_value=datetime(2026, 1, 1),
    max_value=datetime(2026, 7, 31),
    timezones=st.just(UTC),
)

_media_types = st.sampled_from(
    [
        "application/pdf",
        "image/png",
        "text/html",
        "application/msword",
        "text/plain",
    ]
)


class _InMemoryPersistence:
    def __init__(self, statuses: dict[str, str] | None = None) -> None:
        self._statuses = statuses or {}
        self._records: list = []

    def persist_transition(self, record) -> None:
        self._statuses[record.program_id] = record.to_status
        self._records.append(record)

    def get_current_status(self, program_id: str) -> str | None:
        return self._statuses.get(program_id)


# ---------------------------------------------------------------------------
# Property 20.1 — All paths: zero live network calls
# ---------------------------------------------------------------------------


@given(title=_titles, content=_contents)
@settings(max_examples=200, deadline=5000)
def test_classifier_zero_network_calls(title: str, content: str) -> None:
    """The local classifier never makes network calls regardless of input."""
    classifier = LocalKeywordClassifier()
    classifier.classify("https://synth.example.gov.tw/page", title, content)

    assert classifier.network_call_count == 0


@given(title=_titles, content=_contents)
@settings(max_examples=200, deadline=5000)
def test_extractor_zero_network_calls(title: str, content: str) -> None:
    """The candidate extractor never makes network calls."""
    classifier = LocalKeywordClassifier()
    extractor = CandidateExtractor(classifier)

    extractor.extract_candidate(
        url="https://synth.example.gov.tw/page",
        source_id="synth-src",
        title=title,
        content=content,
    )

    assert extractor.network_call_count == 0


@given(media_type=_media_types)
@settings(max_examples=100, deadline=5000)
def test_attachment_handler_zero_network_calls(media_type: str) -> None:
    """The local extraction handler never makes network calls."""
    handler = LocalExtractionHandler()
    meta = AttachmentMetadata(
        attachment_id="att-prop",
        document_id="doc-prop",
        filename="test.bin",
        media_type=media_type,
        source_url="https://synth.example.gov.tw/file",
    )
    handler.extract(meta)

    assert handler.network_call_count == 0


@given(observed_at=_observed_at)
@settings(max_examples=100, deadline=5000)
def test_pipeline_zero_network_calls(observed_at: datetime) -> None:
    """The full pipeline makes zero network calls."""
    source = RegisteredSource(
        source_id="synth-prop",
        name="Property Test Source",
        entry_url="https://synth.example.gov.tw/entry",
        canonical_host="synth.example.gov.tw",
        enabled=True,
    )
    fetcher = LocalFixtureFetcher(
        default_content="<html><head><title>Test</title></head><body>給付</body></html>"
    )
    pipeline = CurationPipeline(fetcher=fetcher, now=observed_at)

    pipeline.run(source)

    assert pipeline.network_call_count == 0


# ---------------------------------------------------------------------------
# Property 20.2 — All paths: zero LLM calls
# ---------------------------------------------------------------------------


@given(title=_titles, content=_contents)
@settings(max_examples=200, deadline=5000)
def test_classifier_zero_llm_calls(title: str, content: str) -> None:
    """The local classifier never makes LLM calls."""
    classifier = LocalKeywordClassifier()
    classifier.classify("https://synth.example.gov.tw/page", title, content)

    assert classifier.llm_call_count == 0


@given(media_type=_media_types)
@settings(max_examples=100, deadline=5000)
def test_attachment_handler_zero_llm_calls(media_type: str) -> None:
    """The local extraction handler never makes LLM calls."""
    handler = LocalExtractionHandler()
    meta = AttachmentMetadata(
        attachment_id="att-llm",
        document_id="doc-llm",
        filename="test.bin",
        media_type=media_type,
        source_url="https://synth.example.gov.tw/file",
    )
    handler.extract(meta)

    assert handler.llm_call_count == 0


@given(observed_at=_observed_at)
@settings(max_examples=100, deadline=5000)
def test_pipeline_zero_llm_calls(observed_at: datetime) -> None:
    """The full pipeline makes zero LLM calls."""
    source = RegisteredSource(
        source_id="synth-llm",
        name="LLM Test Source",
        entry_url="https://synth.example.gov.tw/entry",
        canonical_host="synth.example.gov.tw",
        enabled=True,
    )
    fetcher = LocalFixtureFetcher(
        default_content="<html><head><title>Page</title></head><body>補助</body></html>"
    )
    pipeline = CurationPipeline(fetcher=fetcher, now=observed_at)

    pipeline.run(source)

    assert pipeline.llm_call_count == 0


# ---------------------------------------------------------------------------
# Property 20.3 — Non-human actors cannot perform protected transitions
# ---------------------------------------------------------------------------


@given(actor_type=_actor_types, source_id=_source_ids)
@settings(max_examples=200, deadline=5000)
def test_forbidden_actors_blocked_from_verified(
    actor_type: str, source_id: str
) -> None:
    """No forbidden actor type can transition to verified, regardless of artifacts."""
    error = validate_transition(
        program_id=source_id,
        from_status="candidate",
        to_status="verified",
        actor_type=actor_type,
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("cite-001",),
            approved_excerpt="依據條例",
        ),
    )
    assert error == "forbidden_actor"


@given(actor_type=_actor_types, source_id=_source_ids)
@settings(max_examples=200, deadline=5000)
def test_forbidden_actors_blocked_via_service(actor_type: str, source_id: str) -> None:
    """Non-human actors are blocked even through the ReviewService."""
    persistence = _InMemoryPersistence({source_id: "under_review"})
    service = ReviewService(persistence)

    result = service.transition_status(
        program_id=source_id,
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


# ---------------------------------------------------------------------------
# Property 20.4 — Machine outputs can only be candidate/under_review
# ---------------------------------------------------------------------------


@given(title=_titles, content=_contents)
@settings(max_examples=200, deadline=5000)
def test_classifier_output_always_candidate_or_under_review(
    title: str, content: str
) -> None:
    """Classifier output status is always in the allowed set."""
    classifier = LocalKeywordClassifier()
    result = classifier.classify("https://synth.example.gov.tw/page", title, content)

    assert result.review_status in CLASSIFICATION_STATUSES
    assert result.review_status in MACHINE_ALLOWED_STATUSES


@given(title=_titles, content=_contents)
@settings(max_examples=200, deadline=5000)
def test_extractor_output_always_candidate_or_under_review(
    title: str, content: str
) -> None:
    """Extractor output (when not None) is always candidate/under_review."""
    classifier = LocalKeywordClassifier()
    extractor = CandidateExtractor(classifier, min_confidence=0.0)

    payload = extractor.extract_candidate(
        url="https://synth.example.gov.tw/page",
        source_id="synth-src",
        title=title,
        content=content,
    )

    if payload is not None:
        assert payload.review_status in ALLOWED_STATUSES
        assert payload.review_status != "verified"


@given(observed_at=_observed_at)
@settings(max_examples=100, deadline=5000)
def test_pipeline_output_always_candidate_or_under_review(
    observed_at: datetime,
) -> None:
    """All pipeline candidates are candidate/under_review."""
    source = RegisteredSource(
        source_id="synth-status",
        name="Status Test Source",
        entry_url="https://synth.example.gov.tw/entry",
        canonical_host="synth.example.gov.tw",
        enabled=True,
    )
    fetcher = LocalFixtureFetcher(
        default_content="<html><head><title>給付</title></head><body>補助申請</body></html>"
    )
    pipeline = CurationPipeline(fetcher=fetcher, now=observed_at)

    result = pipeline.run(source)
    for candidate in result.candidates:
        assert candidate.review_status in MACHINE_ALLOWED_STATUSES
        assert candidate.review_status != "verified"


# ---------------------------------------------------------------------------
# Property 20.5 — Human reviewer with complete artifacts CAN transition
# ---------------------------------------------------------------------------


@given(source_id=_source_ids)
@settings(max_examples=100, deadline=5000)
def test_human_reviewer_can_verify_with_complete_artifacts(
    source_id: str,
) -> None:
    """Human reviewer with complete artifacts succeeds at verified transition."""
    persistence = _InMemoryPersistence({source_id: "under_review"})
    service = ReviewService(persistence)

    result = service.transition_status(
        program_id=source_id,
        to_status="verified",
        actor_type="human_reviewer",
        reviewer_ref="reviewer-prop",
        approved_version="v1.0",
        artifacts=ReviewArtifacts(
            approved_rule_version="v1.0",
            citation_ids=("cite-001",),
            approved_excerpt="依據勞保條例",
        ),
    )

    assert result.success
    assert result.audit_record is not None
    assert result.audit_record.to_status == "verified"


# ---------------------------------------------------------------------------
# Property 20.6 — Discovery statuses are restricted
# ---------------------------------------------------------------------------


@given(observed_at=_observed_at)
@settings(max_examples=100, deadline=5000)
def test_discovered_pages_always_in_allowed_statuses(
    observed_at: datetime,
) -> None:
    """Structural crawler produces pages only in allowed discovery statuses."""
    source = RegisteredSource(
        source_id="synth-disc",
        name="Discovery Test",
        entry_url="https://synth.example.gov.tw/entry",
        canonical_host="synth.example.gov.tw",
        enabled=True,
    )
    fetcher = LocalFixtureFetcher(
        default_content="<html><head><title>Page</title></head><body>content</body></html>"
    )
    crawler = StructuralCrawler(fetcher, now=observed_at)

    result = crawler.crawl(source)
    for page in result.pages:
        assert page.review_status in ALLOWED_DISCOVERY_STATUSES
        assert page.review_status != "verified"
