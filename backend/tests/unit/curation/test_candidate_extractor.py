"""Unit tests for candidate extractor and classifier (Task 12.3, 12.5).

Covers:
- Classifier makes zero LLM/network calls
- Classification results are always candidate/under_review
- Extractor produces candidate payloads only
- Low-confidence pages are skipped
- Batch extraction counts
- No eligibility status or verified state produced
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.curation.candidate_extractor import (
    ALLOWED_STATUSES,
    CandidateExtractor,
    CandidatePayload,
)
from app.curation.classifier import (
    CLASSIFICATION_STATUSES,
    ClassificationResult,
    LocalKeywordClassifier,
)

T0 = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Classifier: zero LLM/network calls
# ---------------------------------------------------------------------------


def test_local_classifier_zero_llm_calls() -> None:
    """Local keyword classifier makes no LLM calls."""
    classifier = LocalKeywordClassifier()
    classifier.classify(
        "https://example.gov.tw/benefit",
        "勞保喪葬給付",
        "申請喪葬給付的條件與金額",
    )

    assert classifier.llm_call_count == 0
    assert classifier.network_call_count == 0


def test_local_classifier_counts_classifications() -> None:
    """Tracks how many classifications were performed."""
    classifier = LocalKeywordClassifier()
    classifier.classify("url1", "Title", "Content")
    classifier.classify("url2", "Title", "Content")

    assert classifier.classify_count == 2


# ---------------------------------------------------------------------------
# Classification results are always candidate/under_review
# ---------------------------------------------------------------------------


def test_classification_result_is_candidate() -> None:
    """Classifier results always have candidate status."""
    classifier = LocalKeywordClassifier()
    result = classifier.classify(
        "https://example.gov.tw/benefits/funeral",
        "喪葬給付申請",
        "被保險人死亡，其遺屬得請領喪葬給付",
    )

    assert result.review_status in CLASSIFICATION_STATUSES
    assert result.review_status == "candidate"


def test_classification_result_rejects_verified() -> None:
    """Cannot create a ClassificationResult with verified status."""
    with pytest.raises(ValueError, match="review_status"):
        ClassificationResult(
            url="https://example.gov.tw/page",
            document_type="benefit_page",
            confidence=0.8,
            review_status="verified",
        )


def test_classification_confidence_bounds() -> None:
    """Confidence must be between 0 and 1."""
    with pytest.raises(ValueError, match="confidence"):
        ClassificationResult(
            url="https://example.gov.tw/page",
            document_type="benefit_page",
            confidence=1.5,
        )


# ---------------------------------------------------------------------------
# Keyword classification heuristics
# ---------------------------------------------------------------------------


def test_benefit_page_classification() -> None:
    """Pages with benefit keywords are classified as benefit_page."""
    classifier = LocalKeywordClassifier()
    result = classifier.classify(
        "https://example.gov.tw/funeral-benefit",
        "喪葬給付",
        "勞保被保險人死亡，符合申請資格的受益人可申請喪葬給付補助",
    )

    assert result.document_type == "benefit_page"
    assert result.confidence > 0.0


def test_legal_text_classification() -> None:
    """Pages with legal keywords are classified as legal_text."""
    classifier = LocalKeywordClassifier()
    result = classifier.classify(
        "https://example.gov.tw/regulation",
        "勞工保險條例",
        "依據勞工保險條例第六十二條之規定辦理",
    )

    assert result.document_type == "legal_text"


def test_unknown_content_classified_as_other() -> None:
    """Content without recognizable keywords is classified as other."""
    classifier = LocalKeywordClassifier()
    result = classifier.classify(
        "https://example.gov.tw/about",
        "About Us",
        "This is a general about page with no keywords",
    )

    assert result.document_type == "other"
    assert result.confidence <= 0.2


# ---------------------------------------------------------------------------
# Candidate extractor: outputs are always candidate
# ---------------------------------------------------------------------------


def test_extractor_produces_candidate_payloads() -> None:
    """Extracted payloads always have candidate status."""
    classifier = LocalKeywordClassifier()
    extractor = CandidateExtractor(classifier, now=T0)

    payload = extractor.extract_candidate(
        url="https://example.gov.tw/funeral-benefit",
        source_id="synth-src-01",
        title="喪葬給付",
        content="被保險人死亡可申請喪葬給付",
    )

    assert payload is not None
    assert payload.review_status == "candidate"
    assert payload.source_id == "synth-src-01"


def test_extractor_skips_low_confidence() -> None:
    """Pages below confidence threshold return None."""
    classifier = LocalKeywordClassifier()
    extractor = CandidateExtractor(classifier, min_confidence=0.5, now=T0)

    payload = extractor.extract_candidate(
        url="https://example.gov.tw/about",
        source_id="synth-src-01",
        title="About",
        content="general content with no keywords",
    )

    assert payload is None


def test_candidate_payload_rejects_verified() -> None:
    """Cannot create a CandidatePayload with verified status."""
    with pytest.raises(ValueError, match="review_status"):
        CandidatePayload(
            url="https://example.gov.tw/page",
            source_id="src-1",
            document_type="benefit_page",
            title="Test",
            classification_confidence=0.8,
            review_status="verified",
        )


# ---------------------------------------------------------------------------
# Batch extraction
# ---------------------------------------------------------------------------


def test_batch_extraction_counts() -> None:
    """Batch extraction reports correct processed and skipped counts."""
    classifier = LocalKeywordClassifier()
    extractor = CandidateExtractor(classifier, min_confidence=0.3, now=T0)

    pages = [
        ("https://example.gov.tw/benefit", "給付申請", "喪葬給付補助條件", "src-1"),
        ("https://example.gov.tw/about", "About", "no keywords here", "src-1"),
        ("https://example.gov.tw/law", "條例", "依法規辦法條例辦理", "src-1"),
    ]

    result = extractor.extract_batch(pages, source_id="synth-src-01")

    assert result.candidate_count + result.skipped_count == 3
    assert result.llm_call_count == 0
    assert result.network_call_count == 0


# ---------------------------------------------------------------------------
# No eligibility or verified state
# ---------------------------------------------------------------------------


def test_extractor_zero_llm_network() -> None:
    """Extractor makes zero LLM and network calls."""
    classifier = LocalKeywordClassifier()
    extractor = CandidateExtractor(classifier, now=T0)

    extractor.extract_candidate(
        url="https://example.gov.tw/benefit",
        source_id="src-1",
        title="給付",
        content="申請給付補助",
    )

    assert extractor.llm_call_count == 0
    assert extractor.network_call_count == 0


def test_all_allowed_statuses_are_non_verified() -> None:
    """The allowed status set does not include verified."""
    assert "verified" not in ALLOWED_STATUSES
    assert ALLOWED_STATUSES == frozenset({"candidate", "under_review"})
