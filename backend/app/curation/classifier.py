"""Local/mock page classifier (Req 10.7, 11.9, 11.10, 16.5-16.8).

Classifies discovered pages into document types using an injectable client.
Before owner-approved live LLM access, the default classifier uses simple
heuristic rules (keyword matching) — no network, no credentials, no LLM.

## Key constraints

- Must NOT produce eligibility status or verified state
- Must NOT produce real unapproved excerpts or inferred metadata
- Outputs are always `candidate` or `under_review`
- Zero LLM calls in the local path
- Zero network calls in the local path
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Protocol

# Document types matching the SQLite schema
DOCUMENT_TYPES: Final[frozenset[str]] = frozenset(
    {
        "benefit_page",
        "application_page",
        "legal_text",
        "news",
        "statistics",
        "budget",
        "procurement",
        "index",
        "other",
    }
)

# Classification result statuses — only candidate/under_review allowed
CLASSIFICATION_STATUSES: Final[frozenset[str]] = frozenset(
    {"candidate", "under_review"}
)


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Result of classifying a page.

    `document_type` is the predicted type. `confidence` is a 0-1 score from
    the classifier. `review_status` is always candidate or under_review.
    """

    url: str
    document_type: str
    confidence: float
    review_status: str = "candidate"
    keywords_matched: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.document_type not in DOCUMENT_TYPES:
            raise ValueError(
                f"document_type must be one of {DOCUMENT_TYPES}, "
                f"got '{self.document_type}'"
            )
        if self.review_status not in CLASSIFICATION_STATUSES:
            raise ValueError(
                f"review_status must be one of {CLASSIFICATION_STATUSES}, "
                f"got '{self.review_status}'"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


class ClassifierPort(Protocol):
    """Protocol for page classification — injectable for local/mock/live."""

    def classify(self, url: str, title: str, content: str) -> ClassificationResult:
        """Classify a page. Must not raise."""
        ...

    @property
    def llm_call_count(self) -> int:
        """Number of LLM calls made. Must be 0 for local classifiers."""
        ...

    @property
    def network_call_count(self) -> int:
        """Number of network calls made. Must be 0 for local classifiers."""
        ...


# Keyword patterns for heuristic classification
_BENEFIT_KEYWORDS: Final[tuple[str, ...]] = (
    "給付",
    "補助",
    "津貼",
    "年金",
    "保險金",
    "benefit",
    "allowance",
    "subsidy",
    "申請資格",
    "受益人",
)

_APPLICATION_KEYWORDS: Final[tuple[str, ...]] = (
    "申請",
    "辦理",
    "應備文件",
    "表單下載",
    "application",
    "apply",
    "form",
    "how to",
)

_LEGAL_KEYWORDS: Final[tuple[str, ...]] = (
    "法規",
    "條例",
    "辦法",
    "要點",
    "規定",
    "law",
    "regulation",
    "statute",
    "第.*條",
)

_NEWS_KEYWORDS: Final[tuple[str, ...]] = (
    "新聞",
    "公告",
    "最新消息",
    "發布日期",
    "news",
    "announcement",
)

_INDEX_KEYWORDS: Final[tuple[str, ...]] = (
    "目錄",
    "索引",
    "分類",
    "總覽",
    "index",
    "catalog",
    "directory",
)


@dataclass(slots=True)
class LocalKeywordClassifier:
    """Heuristic keyword-based classifier for local/fixture use.

    Zero LLM, zero network. Uses simple keyword matching to guess document type.
    Results are always `candidate` because heuristics cannot verify content.
    """

    _llm_calls: int = field(default=0, init=False)
    _network_calls: int = field(default=0, init=False)
    _classify_count: int = field(default=0, init=False)

    def classify(self, url: str, title: str, content: str) -> ClassificationResult:
        """Classify using keyword heuristics."""
        self._classify_count += 1
        text = f"{title} {content}".lower()

        best_type = "other"
        best_confidence = 0.0
        best_keywords: tuple[str, ...] = ()

        for doc_type, keywords in _TYPE_KEYWORDS.items():
            matched = tuple(kw for kw in keywords if re.search(kw, text))
            if matched:
                confidence = min(len(matched) / 3.0, 0.9)  # Cap at 0.9
                if confidence > best_confidence:
                    best_type = doc_type
                    best_confidence = confidence
                    best_keywords = matched

        # If nothing matched well, it's "other" with low confidence
        if best_confidence < 0.1:
            best_confidence = 0.1

        return ClassificationResult(
            url=url,
            document_type=best_type,
            confidence=round(best_confidence, 2),
            review_status="candidate",
            keywords_matched=best_keywords,
        )

    @property
    def llm_call_count(self) -> int:
        return self._llm_calls

    @property
    def network_call_count(self) -> int:
        return self._network_calls

    @property
    def classify_count(self) -> int:
        return self._classify_count


_TYPE_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "benefit_page": _BENEFIT_KEYWORDS,
    "application_page": _APPLICATION_KEYWORDS,
    "legal_text": _LEGAL_KEYWORDS,
    "news": _NEWS_KEYWORDS,
    "index": _INDEX_KEYWORDS,
}
