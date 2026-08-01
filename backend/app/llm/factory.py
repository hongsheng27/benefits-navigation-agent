"""決定這次要用哪一個語言模型實作。

選擇順序：

1. 有 `BEDROCK_MODEL_ID` → Bedrock Converse（比賽日正式路徑）
2. 否則 → 離線示範實作

**沒有金鑰／模型不是錯誤。** 隊友沒有你的憑證時仍要能跑前端與整合測試。

## 為什麼執行中失敗不會偷偷換實作

這裡只在**啟動組裝時**做一次選擇。如果 Bedrock 在執行中失敗，
**不會**偷偷改用示範實作 —— 那會把「我們沒看懂」變成另一個
看起來正常但可能錯誤的結果。失敗就是失敗，走 `event_not_recognized`。
"""

import logging

from app.config import Settings
from app.llm.bedrock import BedrockLanguageModel
from app.llm.port import LanguageModelPort
from app.observability.logging import log_event
from app.orchestration.demo_fixtures import demo_language_model


def build_language_model(settings: Settings) -> LanguageModelPort:
    """依設定挑一個實作。

    會記一筆紀錄檔，因為「今天跑的是真模型還是示範資料」是除錯時第一個要問的問題。
    只記模型代號，不記金鑰或任何憑證片段。
    """
    if settings.has_bedrock_language_model():
        log_event(
            "language_model_selected",
            model_id=settings.bedrock_model_id,
        )
        return BedrockLanguageModel(
            model_id=settings.bedrock_model_id,
            region_name=(
                settings.aws_default_region.strip() or settings.aws_region.strip()
            ),
        )

    log_event(
        "language_model_selected",
        level=logging.WARNING,
        model_id="demo_fixture",
    )
    return demo_language_model()
