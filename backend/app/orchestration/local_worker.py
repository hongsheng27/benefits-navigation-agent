"""本機 refresh worker 的非阻塞邊界（提案第 9 節、Req 11.10、16.1）。

這個模組是 request thread 與背景工作之間的**分界線**，不是 crawler。它刻意
不做網路請求、不處理附件、不呼叫 LLM —— 那些是 Task 12 的工作，而且必須在
request lifecycle 之外執行。

## 為什麼分界線本身要有型別

`Req 11.10` 要求「排除在 request lifecycle 內同步執行 network crawl 或 LLM」。
這種要求如果只寫在文件裡，違反它的程式碼在測試裡看起來跟正確的一樣。把邊界做成
一個物件之後，測試可以直接問它：request path 上呼叫了幾次 `submit`（應該有）、
幾次 `drain`（應該是零）。

`submit()` 只把工作放進佇列，它的成本與工作內容無關，所以 worker 再慢也不會拖慢
回應。真正執行工作的是 `drain()`，那是背景迴圈的入口，**不得**由 request thread
呼叫。

## 為什麼 worker 失敗要吞掉

`Req 11.8`：refresh job 失敗必須保留原始回應與 committed state。handler 丟出例外
時 `drain()` 記一筆 `WorkerOutcome(status="failed")` 就繼續，不往上拋、也不碰任何
已提交的資料。例外訊息可能引用值，所以只留類別名稱（見 `observability.logging`）。

## 產出一律是候選資料

`Req 11.9`：worker 的產出只能存成 `candidate` 或 `under_review`。`LocalRefreshJob`
本身就沒有任何可以寫回資料治理狀態的欄位（見 `protocols.LocalRefreshJob`），
`WorkerOutcome` 也只帶得動 `RESULT_STATUSES` 裡的兩個值。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from app.observability.logging import log_event
from app.orchestration.protocols import LocalRefreshJob, RefreshRequest

RESULT_STATUSES: Final[frozenset[str]] = frozenset({"candidate", "under_review"})
"""Worker 產出唯一允許的資料治理狀態（Req 11.9）。"""

WORKER_STATUSES: Final[frozenset[str]] = frozenset({"completed", "failed"})
"""`drain()` 之後一筆工作可能的結果。"""


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    """一筆背景工作跑完之後的結果。

    刻意不帶任何回傳內容：這個 worker 不產生資料，只回報它有沒有跑完。真正的
    抓取結果之後會由 crawler 寫進 candidate 資料表，經人工審查才會升級。
    """

    job_id: str
    source_id: str
    status: str
    result_status: str = "candidate"
    error_type: str | None = None

    def __post_init__(self) -> None:
        if self.status not in WORKER_STATUSES:
            raise ValueError("unsupported worker status")
        if self.result_status not in RESULT_STATUSES:
            raise ValueError("worker results must stay candidate or under_review")
        if self.status == "failed" and not self.error_type:
            raise ValueError("failed outcomes require an error_type")
        if self.status == "completed" and self.error_type is not None:
            raise ValueError("completed outcomes cannot carry an error_type")


class RefreshWorkerPort(Protocol):
    """狀態機看得到的 worker 形狀。

    只有 `submit`。request path 拿不到 `drain`，所以它在型別上就沒有辦法同步執行
    背景工作。
    """

    def submit(self, job: LocalRefreshJob) -> None:
        """把一筆工作交給背景執行。必須立刻回來，且不得拋出例外。"""
        ...


@dataclass(slots=True)
class LocalRefreshWorker:
    """離線用的 refresh worker：一個可獨立測試的佇列。

    `handler` 是之後真正執行抓取的地方；預設是 `None`，代表「收下工作但什麼都不做」。
    這讓整條流程在 crawler 完成之前就能端到端測試，而且不會不小心連上網路。

    若未來經 owner 核准換成雲端 queue，`RefreshWorkerPort` 與這裡的 local test path
    都維持不變（Req 16.1）。
    """

    handler: Callable[[LocalRefreshJob], None] | None = None
    result_status: str = "candidate"
    _queue: list[LocalRefreshJob] = field(default_factory=list, init=False)
    _outcomes: list[WorkerOutcome] = field(default_factory=list, init=False)
    submit_count: int = field(default=0, init=False)
    drain_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.result_status not in RESULT_STATUSES:
            raise ValueError("worker results must stay candidate or under_review")

    # ------------------------------------------------------------------
    # Request-thread side — must stay O(1) and exception-free
    # ------------------------------------------------------------------

    def submit(self, job: LocalRefreshJob) -> None:
        """排入一筆工作。不執行 handler，所以呼叫成本與工作內容無關。"""
        self._queue.append(job)
        self.submit_count += 1

    def submit_request(
        self, request: RefreshRequest, job_id: str
    ) -> tuple[LocalRefreshJob, ...]:
        """把一個 `RefreshRequest` 拆成每個來源一筆工作並排入。"""
        jobs = tuple(
            LocalRefreshJob(
                job_id=job_id,
                source_id=source_id,
                event_id=request.event_id,
                requested_at=request.requested_at,
            )
            for source_id in request.source_ids
        )
        for job in jobs:
            self.submit(job)
        return jobs

    @property
    def pending_jobs(self) -> tuple[LocalRefreshJob, ...]:
        """還沒被 `drain()` 處理的工作。"""
        return tuple(self._queue)

    @property
    def outcomes(self) -> tuple[WorkerOutcome, ...]:
        """已經處理完的工作結果，含失敗。"""
        return tuple(self._outcomes)

    # ------------------------------------------------------------------
    # Background side — never called from a request thread
    # ------------------------------------------------------------------

    def drain(self) -> tuple[WorkerOutcome, ...]:
        """執行並清空佇列。單一工作失敗不影響其餘工作，也不往上拋。"""
        self.drain_count += 1
        drained = tuple(self._queue)
        self._queue.clear()

        outcomes: list[WorkerOutcome] = []
        for job in drained:
            outcomes.append(self._run(job))
        self._outcomes.extend(outcomes)
        return tuple(outcomes)

    def _run(self, job: LocalRefreshJob) -> WorkerOutcome:
        if self.handler is None:
            return WorkerOutcome(
                job_id=job.job_id,
                source_id=job.source_id,
                status="completed",
                result_status=self.result_status,
            )
        try:
            self.handler(job)
        except Exception as exc:  # noqa: BLE001 — 失敗必須被隔離（Req 11.8）
            log_event(
                "refresh_worker_failed",
                level=logging.WARNING,
                life_event=job.event_id,
                source_count=1,
                outcome="failed",
                error_type=type(exc).__name__,
            )
            return WorkerOutcome(
                job_id=job.job_id,
                source_id=job.source_id,
                status="failed",
                result_status=self.result_status,
                error_type=type(exc).__name__,
            )
        return WorkerOutcome(
            job_id=job.job_id,
            source_id=job.source_id,
            status="completed",
            result_status=self.result_status,
        )


@dataclass(slots=True)
class NullRefreshWorker:
    """什麼都不收的 worker。用在明確關掉背景刷新的組裝。"""

    submit_count: int = field(default=0, init=False)

    def submit(self, job: LocalRefreshJob) -> None:
        """丟棄工作。只記一個計數，方便測試確認呼叫確實發生過。"""
        del job
        self.submit_count += 1


def drain_all(
    worker: LocalRefreshWorker,
    *,
    max_rounds: int = 1,
) -> Sequence[WorkerOutcome]:
    """背景迴圈的最小入口。刻意獨立於 request path 之外。"""
    if max_rounds < 1:
        raise ValueError("max_rounds must be at least 1")
    outcomes: list[WorkerOutcome] = []
    for _ in range(max_rounds):
        if not worker.pending_jobs:
            break
        outcomes.extend(worker.drain())
    return tuple(outcomes)
