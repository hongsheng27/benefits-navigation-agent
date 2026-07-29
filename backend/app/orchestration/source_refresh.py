"""On-demand refresh 的流程組裝（提案第 9 節）。

流程是「**先用已知資料回答，再更新候選資料**」，不是「等網路爬完才回答」：

1. 先取得目前本機資料的 coverage 狀態並交還呼叫端 —— 不等待新的 crawl、附件處理或
   LLM 分析
2. 把與這個事件 `domain_tags` 相關的來源交給 `SourceRefreshService` 排入背景 refresh
3. 到期判斷與 same-day dedup 都在 service 裡，因為「多久該重抓一次」是來源表的欄位，
   不在 `CoverageMetadata` 契約裡（見 `protocols.LocalSourceRecord`）
4. refresh 失敗不阻塞也不撤銷目前的回應

## 為什麼失敗要吞掉

這一步是**加值**，不是回答使用者所必需的。來源刷新掛掉時，使用者該拿到的仍然是
「依目前本機資料能給的答案」。讓它往上拋會把一個背景維護動作變成使用者看得到的錯誤。

吞掉不等於不留痕跡：失敗會記一筆紀錄，但只有事件代號、來源數量與例外**類別**。
例外訊息可能引用值，所以走 `exc_info` 由格式器只取類別與堆疊。

## 8/1 前沒有真正的背景工作

`LocalSourceRefreshService` 的「佇列」就是一個 list。這一批只做介面加本機同步佇列，
沒有引入任何第三方任務佇列，也沒有建立任何 AWS 資源。換成雲端佇列的步驟寫在
`docs/aws_migration_guide.md`。
"""

import logging
from datetime import UTC, datetime

from app.observability.logging import log_event
from app.orchestration.data_contracts import CoverageMetadata
from app.orchestration.protocols import (
    RefreshReceipt,
    RefreshRequest,
    SourceRefreshService,
)


def refresh_after_response(
    service: SourceRefreshService,
    event_id: str,
    *,
    now: datetime | None = None,
) -> tuple[tuple[CoverageMetadata, ...], RefreshReceipt | None]:
    """回報目前 coverage 狀態，並以非阻塞方式排入 refresh。

    回傳 `(coverage, receipt)`。`receipt` 為 `None` 表示沒有送出請求（沒有相關來源）
    或請求失敗 —— 兩種情況都不影響已經取得的 coverage。
    """
    requested_at = now if now is not None else datetime.now(UTC)

    coverage = tuple(service.get_coverage_status(event_id))
    if not coverage:
        # 沒有登記相關來源就沒有東西可以刷新。不猜「全部來源都相關」。
        return coverage, None

    request = RefreshRequest(
        event_id=event_id,
        source_ids=tuple(entry.source_id for entry in coverage),
        requested_at=requested_at,
    )

    try:
        receipt = service.request_on_demand_refresh(request)
    except Exception:
        log_event(
            "source_refresh_failed",
            level=logging.WARNING,
            exc_info=True,
            life_event=event_id,
            source_count=len(coverage),
        )
        return coverage, None

    log_event(
        "source_refresh_requested",
        life_event=event_id,
        source_count=len(coverage),
        outcome="accepted" if receipt.accepted else "skipped",
    )
    return coverage, receipt
