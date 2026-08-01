"""Current-data-first 的組裝層（Req 11.1、11.8-11.10、16.1）。

`source_refresh.refresh_after_response` 已經做到「先取 snapshot、再排 refresh」。
這一層再加一件事：把接受的請求交給 `RefreshWorkerPort`，並且保證**交付本身**
也不會把 request path 變慢或變成錯誤來源。

## 順序是契約的一部分

```
1. snapshot = service.get_coverage_status(scope)   ← request-start committed state
2. receipt  = service.request_on_demand_refresh(...)   ← 只排隊，不執行
3. worker.submit(job)                              ← 只入列，不執行
4. 回傳 snapshot（永遠是第 1 步那一份）
```

第 4 步回傳的 snapshot 一定是第 1 步取得的物件，即使第 2、3 步之後資料變了。
這就是 `Req 11.1`「先使用 request 開始時的 committed state 建立回應」的具體形式：
不是「盡量早一點取」，而是**取一次、之後不再讀**。

## 為什麼 worker 交付也要 try/except

`Req 11.8` 要求 refresh job 失敗保留原始回應。佇列滿了、worker 被換成會丟例外的
實作、序列化失敗 —— 這些都發生在 request thread 上。任何一個往上拋，使用者就會
因為一個背景維護動作看到錯誤。所以這裡吞掉並記一筆只含類別名稱的紀錄。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from app.observability.logging import log_event
from app.orchestration.local_worker import RefreshWorkerPort
from app.orchestration.protocols import (
    CoverageScope,
    CoverageSnapshot,
    LocalRefreshJob,
    RefreshReceipt,
    RefreshRequest,
    SourceRefreshService,
)
from app.orchestration.source_refresh import refresh_after_response


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    """一次 current-data-first 流程的結果。

    `snapshot` 一定是 request 開始時的那一份。`receipt` 為 `None` 表示沒有送出
    請求或請求失敗，兩者都不影響 `snapshot`。
    """

    snapshot: CoverageSnapshot
    receipt: RefreshReceipt | None
    enqueued_jobs: tuple[LocalRefreshJob, ...] = ()

    @property
    def refresh_enqueued(self) -> bool:
        """這次請求有沒有真的排入背景工作。"""
        return self.receipt is not None and self.receipt.accepted


def respond_then_refresh(
    service: SourceRefreshService,
    event_id: str,
    coverage_scope: CoverageScope,
    *,
    worker: RefreshWorkerPort | None = None,
    now: datetime | None = None,
) -> RefreshOutcome:
    """取得目前 coverage snapshot，再以非阻塞方式排入 refresh。

    這個函式**不會**執行任何 network crawl、附件處理或 LLM 呼叫（Req 11.10）。
    worker 的延遲或失敗都不改變回傳的 snapshot（Req 11.8）。
    """
    requested_at = now if now is not None else datetime.now(UTC)

    # 第 1 步：committed state。之後不再讀，所以後續步驟改不動這份回應。
    snapshot, receipt = refresh_after_response(
        service,
        event_id,
        coverage_scope,
        now=requested_at,
    )

    if worker is None or receipt is None or not receipt.accepted:
        return RefreshOutcome(snapshot=snapshot, receipt=receipt)

    request = RefreshRequest(
        event_id=event_id,
        source_ids=tuple(entry.source_id for entry in snapshot.sources),
        requested_at=requested_at,
    )
    jobs = _submit_jobs(worker, request, receipt.job_id)
    return RefreshOutcome(snapshot=snapshot, receipt=receipt, enqueued_jobs=jobs)


def _submit_jobs(
    worker: RefreshWorkerPort,
    request: RefreshRequest,
    job_id: str,
) -> tuple[LocalRefreshJob, ...]:
    """把請求拆成每個來源一筆工作交給 worker。交付失敗只記錄，不往上拋。"""
    submitted: list[LocalRefreshJob] = []
    for source_id in request.source_ids:
        job = LocalRefreshJob(
            job_id=job_id,
            source_id=source_id,
            event_id=request.event_id,
            requested_at=request.requested_at,
        )
        try:
            worker.submit(job)
        except Exception:
            # Req 11.8：背景交付失敗不得改變已經取得的回應。
            log_event(
                "refresh_worker_submit_failed",
                level=logging.WARNING,
                exc_info=True,
                life_event=request.event_id,
                source_count=len(request.source_ids),
                outcome="submit_failed",
            )
            continue
        submitted.append(job)

    if submitted:
        log_event(
            "refresh_worker_submitted",
            life_event=request.event_id,
            source_count=len(submitted),
            outcome="queued",
        )
    return tuple(submitted)
