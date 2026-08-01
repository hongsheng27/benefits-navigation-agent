"""Coverage snapshot 的建構與誠實呈現（Req 12.1-12.13）。

Coverage 回報的是**數得出來的進度**，不是內容完整性保證。robots.txt、只有
JavaScript 的頁面、需要登入、失效連結與掃描檔都會造成缺口，而缺口的存在正是
「不能宣稱完整」的理由。

## 這個模組負責三件事

1. **建構 snapshot**：把來源紀錄依 scope 篩選，套上同一個 `observed_at`，
   算出 per-source 與 aggregate 計數（`CoverageSnapshot.__post_init__` 會拒絕
   算錯的組合，所以這裡的工作是把輸入整理成它接受的形狀）。
2. **保留失敗歷史**：來源變成 `error` 時，`last_crawled_at` 仍然保留上一次成功的
   時間（Req 12.12、12.13）。抹掉它會讓「曾經抓到過、現在壞了」看起來像
   「從來沒抓過」，而這兩件事對使用者的意義完全不同。
3. **擋掉完整性宣稱**：`find_completeness_claims` 掃描一段將要送出的文字，
   回報命中的禁用詞（Req 12.6-12.8）。

## 為什麼 scope 之外的來源要直接排除，而不是標記

`Req 12.10`：回應不得宣稱 scope 之外的覆蓋。如果把 scope 外的來源放進 snapshot
再標記「不在範圍內」，任何忘記檢查那個標記的下游都會把它算進總數。直接不放進去
之後，錯誤的算法就算不出錯誤的數字。

## 為什麼禁用詞是清單，不是判斷

自動判斷一句話有沒有暗示「完整」需要語意理解，那會把一個確定性檢查變成猜測。
清單會有漏網之魚，但它不會漏掉**已知**的說法，而且新增一個詞是一行改動。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Final

from app.orchestration.data_contracts import CoverageMetadata
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    LocalSourceRecord,
)

GAP_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "robots_policy",
        "login_required",
        "javascript_only",
        "broken_link",
        "scanned_attachment",
        "connection_error",
    }
)
"""已知的缺口類別。與 `source_coverage_state.last_gap_category` 的 CHECK 一致。"""


FORBIDDEN_CLAIM_TERMS: Final[tuple[str, ...]] = (
    "完整",
    "全部",
    "所有福利",
    "無遺漏",
    "零遺漏",
    "保證",
    "涵蓋全",
    "complete",
    "completeness",
    "comprehensive",
    "exhaustive",
    "all indexed",
    "all benefits",
    "fully indexed",
    "zero omission",
    "zero omissions",
    "no omissions",
    "no gaps",
    "guaranteed",
    "guarantee",
)
"""任何 coverage 回應都不得出現的詞（Req 12.6-12.8）。

中文與英文都列，因為回應會同時經過兩種語言的模板。比對不分大小寫。
"""

_CLAIM_PATTERN: Final[re.Pattern[str]] = re.compile(
    "|".join(re.escape(term) for term in FORBIDDEN_CLAIM_TERMS),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def select_scoped_records(
    records: Sequence[LocalSourceRecord],
    scope: CoverageScope,
) -> tuple[LocalSourceRecord, ...]:
    """依 scope 篩出來源，並以 `source_id` 排序讓結果可重現。

    `source_ids` 與 `domain_tags` 都有值時取交集；只有一個時以該維度篩選。
    兩者皆空時回空 tuple —— 不把「未指定」猜成「所有來源」（Req 12.10）。
    """
    requested_source_ids = frozenset(scope.source_ids)
    requested_domain_tags = frozenset(scope.domain_tags)
    if not requested_source_ids and not requested_domain_tags:
        return ()

    matched = [
        record
        for record in records
        if not (requested_source_ids and record.source_id not in requested_source_ids)
        and not (
            requested_domain_tags
            and not (requested_domain_tags & frozenset(record.domain_tags))
        )
    ]
    matched.sort(key=lambda record: record.source_id)
    return tuple(matched)


def build_snapshot(
    records: Sequence[LocalSourceRecord],
    scope: CoverageScope,
    observed_at: datetime,
) -> CoverageSnapshot:
    """把來源紀錄組成一份 scope 內、共用同一觀測時間的 snapshot。

    每個 `CoverageMetadata` 都拿到同一個 `observed_at`（Req 12.4）。錯誤來源的
    `last_crawled_at` 原樣保留，因為它記錄的是最後一次成功，不是最後一次嘗試
    （Req 12.12）。
    """
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")

    scoped = select_scoped_records(records, scope)
    seen: set[str] = set()
    for record in scoped:
        if record.source_id in seen:
            raise ValueError("coverage sources must have unique source_ids")
        seen.add(record.source_id)

    sources = tuple(
        CoverageMetadata(
            source_id=record.source_id,
            crawl_status=record.crawl_status,
            # Failure history: preserved across an error, never reset to None.
            last_crawled_at=record.last_crawled_at,
            indexed_document_count=record.indexed_document_count,
            domain_tags=record.domain_tags,
            observed_at=observed_at,
        )
        for record in scoped
    )

    return CoverageSnapshot(
        scope=scope,
        observed_at=observed_at,
        registered_source_count=len(sources),
        crawled_source_count=sum(s.crawl_status == "crawled" for s in sources),
        pending_crawl_source_count=sum(
            s.crawl_status == "pending_crawl" for s in sources
        ),
        error_source_count=sum(s.crawl_status == "error" for s in sources),
        indexed_document_count=sum(s.indexed_document_count for s in sources),
        sources=sources,
        gap_categories=collect_gap_categories(scoped),
    )


def collect_gap_categories(
    records: Sequence[LocalSourceRecord],
) -> tuple[str, ...]:
    """收集去重、排序後的缺口類別。

    只看 `error` 來源：`pending_crawl` 是「還沒輪到」，不是缺口，把它算成缺口會
    讓待辦看起來像故障。未知的類別直接拒絕，不靜默丟掉 —— 靜默丟掉會讓一個
    真實缺口從回應裡消失（Req 12.6、12.7）。
    """
    categories: set[str] = set()
    for record in records:
        if record.crawl_status != "error":
            continue
        category = record.gap_category
        if category is None:
            raise ValueError("error sources require a gap_category")
        if category not in GAP_CATEGORIES:
            raise ValueError(f"unsupported gap_category: {category}")
        categories.add(category)
    return tuple(sorted(categories))


def merge_failure_history(
    previous: LocalSourceRecord | None,
    current: LocalSourceRecord,
) -> LocalSourceRecord:
    """來源轉成 `error` 時，補回上一次成功的抓取時間與已索引文件數。

    Crawl 失敗不會讓已經索引的內容消失，所以把計數歸零是不誠實的；上一次成功的
    時間同理（Req 12.12、12.13）。已經有值的欄位不覆寫。
    """
    if previous is None or current.crawl_status != "error":
        return current

    last_crawled_at = current.last_crawled_at or previous.last_crawled_at
    indexed = current.indexed_document_count or previous.indexed_document_count
    return replace(
        current,
        last_crawled_at=last_crawled_at,
        indexed_document_count=indexed,
    )


# ---------------------------------------------------------------------------
# Honest response checks
# ---------------------------------------------------------------------------


def find_completeness_claims(text: str) -> tuple[str, ...]:
    """回報 `text` 裡命中的禁用詞，去重排序。沒有命中時回空 tuple。"""
    return tuple(sorted({match.lower() for match in _CLAIM_PATTERN.findall(text)}))


def assert_no_completeness_claims(text: str) -> None:
    """命中禁用詞時拋出 `ValueError`，讓不誠實的文案在測試就爆掉。"""
    claims = find_completeness_claims(text)
    if claims:
        raise ValueError(f"coverage response contains completeness claims: {claims}")


def describe_coverage(snapshot: CoverageSnapshot) -> str:
    """把 snapshot 轉成一句只陳述可觀測進度的說明。

    刻意沒有形容詞：只有數字、觀測時間與已知缺口類別。任何「大部分」「幾乎」
    之類的字都會讓讀者推論出這裡沒有的保證。
    """
    parts = [
        f"observed_at={snapshot.observed_at.isoformat()}",
        f"registered={snapshot.registered_source_count}",
        f"crawled={snapshot.crawled_source_count}",
        f"pending_crawl={snapshot.pending_crawl_source_count}",
        f"error={snapshot.error_source_count}",
        f"indexed_documents={snapshot.indexed_document_count}",
    ]
    if snapshot.gap_categories:
        parts.append(f"gap_categories={','.join(snapshot.gap_categories)}")
    return " ".join(parts)
