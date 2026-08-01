"""Unit tests for attachment handling (Task 12.2, 12.5).

Covers:
- Metadata registration with hash computation
- Extraction status lifecycle
- Gap preservation for failed/pending attachments
- Local handler makes zero network/LLM calls
- Storage backend validation
"""

from __future__ import annotations

import pytest

from app.curation.attachments import (
    AttachmentMetadata,
    AttachmentService,
    ExtractionResult,
    LocalExtractionHandler,
)

# ---------------------------------------------------------------------------
# Metadata registration
# ---------------------------------------------------------------------------


def test_register_attachment_stores_metadata() -> None:
    """Registering an attachment stores all metadata fields."""
    service = AttachmentService()
    meta = service.register_attachment(
        attachment_id="att-001",
        document_id="doc-001",
        filename="benefit_rules.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/rules.pdf",
        storage_backend="local",
        storage_ref="/data/attachments/att-001.pdf",
    )

    assert meta.attachment_id == "att-001"
    assert meta.document_id == "doc-001"
    assert meta.filename == "benefit_rules.pdf"
    assert meta.media_type == "application/pdf"
    assert meta.extraction_status == "pending"


def test_register_with_content_computes_hash() -> None:
    """Providing content bytes triggers hash computation."""
    service = AttachmentService()
    content = b"fake PDF content"
    meta = service.register_attachment(
        attachment_id="att-002",
        document_id="doc-001",
        filename="form.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/form.pdf",
        content_bytes=content,
    )

    assert meta.content_hash is not None
    assert len(meta.content_hash) == 64  # SHA-256 hex


def test_register_without_content_no_hash() -> None:
    """Without content bytes, hash is None."""
    service = AttachmentService()
    meta = service.register_attachment(
        attachment_id="att-003",
        document_id="doc-001",
        filename="report.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/report.pdf",
    )

    assert meta.content_hash is None


# ---------------------------------------------------------------------------
# Extraction lifecycle
# ---------------------------------------------------------------------------


def test_local_handler_marks_extractable_as_pending() -> None:
    """Local handler honestly reports extraction not done for PDFs."""
    handler = LocalExtractionHandler()
    meta = AttachmentMetadata(
        attachment_id="att-004",
        document_id="doc-001",
        filename="rules.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/rules.pdf",
    )

    result = handler.extract(meta)
    assert result.status == "pending"
    assert result.method is None


def test_local_handler_marks_non_extractable_as_not_applicable() -> None:
    """Non-extractable types are marked not_applicable."""
    handler = LocalExtractionHandler()
    meta = AttachmentMetadata(
        attachment_id="att-005",
        document_id="doc-001",
        filename="page.html",
        media_type="text/html",
        source_url="https://example.gov.tw/page.html",
    )

    result = handler.extract(meta)
    assert result.status == "not_applicable"


def test_attempt_extraction_updates_metadata() -> None:
    """After extraction attempt, the metadata reflects the new status."""
    service = AttachmentService()
    service.register_attachment(
        attachment_id="att-006",
        document_id="doc-001",
        filename="doc.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/doc.pdf",
    )

    result = service.attempt_extraction("att-006")
    updated = service.get_attachment("att-006")
    assert updated is not None
    assert updated.extraction_status == result.status


def test_extraction_of_unknown_attachment_raises() -> None:
    """Cannot extract from a non-registered attachment."""
    service = AttachmentService()
    with pytest.raises(LookupError, match="not found"):
        service.attempt_extraction("nonexistent")


# ---------------------------------------------------------------------------
# Gap preservation
# ---------------------------------------------------------------------------


def test_pending_attachments_reported_as_gaps() -> None:
    """Pending extraction = unresolved gap."""
    service = AttachmentService()
    service.register_attachment(
        attachment_id="att-gap-1",
        document_id="doc-001",
        filename="scan.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/scan.pdf",
    )

    gaps = service.get_gaps()
    assert len(gaps) == 1
    assert gaps[0].attachment_id == "att-gap-1"
    assert gaps[0].has_gap is True


def test_non_extractable_no_gap_after_processing() -> None:
    """After processing, non-extractable types are not gaps."""
    service = AttachmentService()
    service.register_attachment(
        attachment_id="att-html",
        document_id="doc-001",
        filename="index.html",
        media_type="text/html",
        source_url="https://example.gov.tw/index.html",
    )
    service.attempt_extraction("att-html")

    gaps = service.get_gaps()
    # text/html is not extractable, so after processing it's not_applicable
    assert all(g.attachment_id != "att-html" for g in gaps)


# ---------------------------------------------------------------------------
# Zero network/LLM calls
# ---------------------------------------------------------------------------


def test_local_handler_zero_calls() -> None:
    """Local extraction handler makes no network or LLM calls."""
    service = AttachmentService()
    service.register_attachment(
        attachment_id="att-zero",
        document_id="doc-001",
        filename="file.pdf",
        media_type="application/pdf",
        source_url="https://example.gov.tw/file.pdf",
    )
    service.attempt_extraction("att-zero")

    assert service.network_call_count == 0
    assert service.llm_call_count == 0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_invalid_extraction_status_rejected() -> None:
    """Invalid extraction status raises ValueError."""
    with pytest.raises(ValueError, match="extraction_status"):
        AttachmentMetadata(
            attachment_id="bad",
            document_id="doc-001",
            filename="test.pdf",
            media_type="application/pdf",
            source_url="https://example.gov.tw/test.pdf",
            extraction_status="verified",
        )


def test_invalid_storage_backend_rejected() -> None:
    """Invalid storage backend raises ValueError."""
    with pytest.raises(ValueError, match="storage_backend"):
        AttachmentMetadata(
            attachment_id="bad",
            document_id="doc-001",
            filename="test.pdf",
            media_type="application/pdf",
            source_url="https://example.gov.tw/test.pdf",
            storage_backend="azure",
        )


def test_failed_result_requires_error_type() -> None:
    """Failed extraction results must have an error_type."""
    with pytest.raises(ValueError, match="error_type"):
        ExtractionResult(attachment_id="att-1", status="failed")


def test_extracted_result_requires_method() -> None:
    """Extracted results must have a method."""
    with pytest.raises(ValueError, match="method"):
        ExtractionResult(attachment_id="att-1", status="extracted")
