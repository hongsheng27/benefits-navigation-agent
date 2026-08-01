"""Local attachment metadata and extraction handling (Req 10.7, 11.9, 12.6, 16.1).

Stores attachment metadata (filename, hash, storage ref, status, method, time).
Failed or pending attachments preserve their gap category — never pretends
extraction succeeded when it didn't. Does not commit large raw files to Git.

## Design

Attachments are metadata records that track the lifecycle of a document's
binary artifacts (PDFs, images, etc.). The actual extraction (OCR, PDF parsing)
is a future concern that plugs into the `ExtractionHandler` protocol.

Before owner-approved live extraction, the default handler is a no-op that
records `pending` status — honest about what hasn't been done yet.

## Allowed statuses

- `pending`: Not yet processed
- `extracted`: Successfully extracted content
- `failed`: Extraction attempted but failed (gap preserved)
- `not_applicable`: File type doesn't need extraction
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Final, Protocol

EXTRACTION_STATUSES: Final[frozenset[str]] = frozenset(
    {"pending", "extracted", "failed", "not_applicable"}
)

STORAGE_BACKENDS: Final[frozenset[str]] = frozenset({"local", "s3"})

# Media types that typically need extraction
EXTRACTABLE_MEDIA_TYPES: Final[frozenset[str]] = frozenset(
    {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "image/tiff",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    }
)


@dataclass(frozen=True, slots=True)
class AttachmentMetadata:
    """Metadata for a single attachment.

    Does NOT contain the binary content itself — only tracking information.
    """

    attachment_id: str
    document_id: str
    filename: str
    media_type: str
    source_url: str
    storage_backend: str | None = None
    storage_ref: str | None = None
    content_hash: str | None = None
    extraction_status: str = "pending"
    extraction_method: str | None = None
    extracted_at: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.extraction_status not in EXTRACTION_STATUSES:
            raise ValueError(
                f"extraction_status must be one of {EXTRACTION_STATUSES}, "
                f"got '{self.extraction_status}'"
            )
        if (
            self.storage_backend is not None
            and self.storage_backend not in STORAGE_BACKENDS
        ):
            raise ValueError(
                f"storage_backend must be one of {STORAGE_BACKENDS} or None, "
                f"got '{self.storage_backend}'"
            )

    @property
    def needs_extraction(self) -> bool:
        """Whether this attachment type typically requires extraction."""
        return self.media_type in EXTRACTABLE_MEDIA_TYPES

    @property
    def has_gap(self) -> bool:
        """Whether this attachment represents an unresolved gap."""
        return self.extraction_status in ("pending", "failed")


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Result of attempting to extract content from an attachment."""

    attachment_id: str
    status: str
    method: str | None = None
    error_type: str | None = None
    extracted_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.status not in EXTRACTION_STATUSES:
            raise ValueError(f"status must be one of {EXTRACTION_STATUSES}")
        if self.status == "failed" and not self.error_type:
            raise ValueError("failed results require an error_type")
        if self.status == "extracted" and not self.method:
            raise ValueError("extracted results require a method")


class ExtractionHandler(Protocol):
    """Protocol for attachment content extraction.

    The local/mock implementation does nothing (preserves pending status).
    Future implementations may do PDF parsing, OCR, etc.
    """

    def extract(self, attachment: AttachmentMetadata) -> ExtractionResult:
        """Attempt to extract content. Must not raise."""
        ...

    @property
    def network_call_count(self) -> int:
        """Number of actual network/service calls made."""
        ...

    @property
    def llm_call_count(self) -> int:
        """Number of LLM calls made for extraction."""
        ...


@dataclass(slots=True)
class LocalExtractionHandler:
    """No-op extraction handler for local/fixture use.

    Honestly records that extraction has not been performed. Does NOT
    pretend content was extracted when it wasn't.
    """

    _call_count: int = field(default=0, init=False)

    def extract(self, attachment: AttachmentMetadata) -> ExtractionResult:
        """Mark as not_applicable for non-extractable types, pending otherwise."""
        self._call_count += 1
        if not attachment.needs_extraction:
            return ExtractionResult(
                attachment_id=attachment.attachment_id,
                status="not_applicable",
            )
        # Honest: we haven't actually extracted anything
        return ExtractionResult(
            attachment_id=attachment.attachment_id,
            status="pending",
        )

    @property
    def network_call_count(self) -> int:
        return 0

    @property
    def llm_call_count(self) -> int:
        return 0


class AttachmentService:
    """Manages attachment metadata and extraction lifecycle."""

    def __init__(self, handler: ExtractionHandler | None = None) -> None:
        self._handler = handler or LocalExtractionHandler()
        self._attachments: dict[str, AttachmentMetadata] = {}

    def register_attachment(
        self,
        *,
        attachment_id: str,
        document_id: str,
        filename: str,
        media_type: str,
        source_url: str,
        content_bytes: bytes | None = None,
        storage_backend: str | None = "local",
        storage_ref: str | None = None,
    ) -> AttachmentMetadata:
        """Register an attachment with its metadata.

        Computes content hash if bytes are provided. Does NOT store the
        binary content itself (that's the storage backend's job).
        """
        content_hash = (
            hashlib.sha256(content_bytes).hexdigest() if content_bytes else None
        )

        metadata = AttachmentMetadata(
            attachment_id=attachment_id,
            document_id=document_id,
            filename=filename,
            media_type=media_type,
            source_url=source_url,
            storage_backend=storage_backend,
            storage_ref=storage_ref,
            content_hash=content_hash,
        )
        self._attachments[attachment_id] = metadata
        return metadata

    def attempt_extraction(self, attachment_id: str) -> ExtractionResult:
        """Attempt to extract content from a registered attachment.

        Returns the extraction result. On failure, the gap is preserved.
        """
        metadata = self._attachments.get(attachment_id)
        if metadata is None:
            raise LookupError(f"Attachment not found: {attachment_id}")

        result = self._handler.extract(metadata)

        # Update metadata with extraction result
        updated = AttachmentMetadata(
            attachment_id=metadata.attachment_id,
            document_id=metadata.document_id,
            filename=metadata.filename,
            media_type=metadata.media_type,
            source_url=metadata.source_url,
            storage_backend=metadata.storage_backend,
            storage_ref=metadata.storage_ref,
            content_hash=metadata.content_hash,
            extraction_status=result.status,
            extraction_method=result.method,
            extracted_at=(
                result.extracted_at.isoformat() if result.extracted_at else None
            ),
        )
        self._attachments[attachment_id] = updated
        return result

    def get_attachment(self, attachment_id: str) -> AttachmentMetadata | None:
        """Retrieve attachment metadata by ID."""
        return self._attachments.get(attachment_id)

    def get_document_attachments(
        self, document_id: str
    ) -> tuple[AttachmentMetadata, ...]:
        """All attachments for a document."""
        return tuple(
            a for a in self._attachments.values() if a.document_id == document_id
        )

    def get_gaps(self) -> tuple[AttachmentMetadata, ...]:
        """All attachments with unresolved gaps (pending or failed)."""
        return tuple(a for a in self._attachments.values() if a.has_gap)

    @property
    def network_call_count(self) -> int:
        return self._handler.network_call_count

    @property
    def llm_call_count(self) -> int:
        return self._handler.llm_call_count
