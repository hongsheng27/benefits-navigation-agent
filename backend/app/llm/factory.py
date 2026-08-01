"""決定這次要用哪一個語言模型實作。

只有一條規則：**有金鑰用 Gemini，沒有金鑰用示範實作。沒有金鑰不是錯誤。**

## 為什麼沒有金鑰不能報錯

隊友沒有你的金鑰。如果缺金鑰會讓後端啟動失敗或每個請求都回錯誤，那麼任何人要看前端
畫面都得先去申請一把金鑰 —— 而前端開發、資料層開發、以及所有跟模型無關的驗證，
其實都不需要模型。

所以缺金鑰時落回示範實作，並且**在回應裡誠實標記**：`implementation.pending` 一直帶著
`life_event_extraction`，前端據此在畫面上顯示那是佔位內容。

## 為什麼不用示範實作當「模型壞掉時的備援」

這裡只在**啟動組裝時**做一次選擇。如果 Gemini 在執行中失敗，
**不會**偷偷改用示範實作 —— 那會把「我們沒看懂」變成「一律回配偶過世」，
使用者拿到一個看起來正常但完全錯誤的結果，而且沒有任何跡象。

失敗就是失敗，走 `event_not_recognized` 請使用者換個說法。
"""

import logging

from app.config import Settings
from app.llm.gemini import GeminiLanguageModel
from app.llm.port import LanguageModelPort
from app.observability.logging import log_event
from app.orchestration.demo_fixtures import demo_language_model


def build_language_model(settings: Settings) -> LanguageModelPort:
    """依設定挑一個實作。

    會記一筆紀錄檔，因為「今天跑的是真模型還是示範資料」是除錯時第一個要問的問題，
    而從行為上分不出來 —— 示範實作會成功回一個看起來正常的代號。

    只記模型代號，不記金鑰，也不記金鑰的任何片段。
    """
    if not settings.has_live_language_model():
        log_event(
            "language_model_selected",
            level=logging.WARNING,
            model_id="demo_fixture",
        )
        return demo_language_model()

    log_event(
        "language_model_selected",
        model_id=settings.gemini_model_id,
    )
    return GeminiLanguageModel(
        api_key=settings.gemini_api_key,
        model_id=settings.gemini_model_id,
    )
