"""不連網路的語言模型實作。**這是預設值。**

存在的理由有三個，而且都是實務問題，不是為了測試好看：

1. **隊友沒有金鑰。** 如果測試會真的連線，沒有金鑰的人跑測試會全部失敗。
2. **測試不該花錢也不該變慢。** 每跑一次測試就打一次真實 API，額度會被測試吃掉，
   而且整套測試從幾秒變成幾分鐘。
3. **行為要可重現。** 真實模型同樣的輸入可能給不同的答案，那種測試會間歇性失敗，
   而間歇性失敗的測試最後都會被關掉。

所以 `advance()` 的預設注入是這個實作，真實連線只在明確傳入 adapter 時發生 ——
與 `orchestration/protocols.py` 的離線實作是同一個作法。

## 它不會假裝自己聽得懂

`FakeLanguageModel` **不做任何語意判斷**。它不看 `user_content`，只看「這個任務被登記了
什麼回答」。沒登記就拋 `LanguageModelUnavailableError`，不編一個答案。

這件事很重要：一個會「大概猜一下」的假實作，會讓測試在真實模型接上之前就通過，
於是我們以為做完了。誠實地說「這裡沒有答案」才會讓缺口留在檯面上。

## 它仍然會檢查 schema

雖然不連網路，`generate_structured` 還是會跑 `validate_portable_schema()`。
理由是：schema 的可攜性問題（用了 Bedrock 不支援的寫法）應該在**離線測試**就被抓到，
而不是等到接上真實廠商。如果假實作跳過檢查，那道規則等於只在有金鑰的人身上生效。
"""

from collections.abc import Mapping
from typing import Any

from app.llm.port import (
    FinishReason,
    LanguageModelUnavailableError,
    LlmRequest,
    LlmResult,
    LlmTask,
    validate_portable_schema,
)


class FakeLanguageModel:
    """回預先登記的答案。答案由建構參數帶入。

    刻意沒有內建任何任務的答案：測試要驗證某個任務，就自己把那個任務的答案傳進來。
    那份答案同時也是測試的「假設宣告」—— 讀測試的人看得到它預期模型回什麼。
    """

    def __init__(
        self,
        responses: Mapping[LlmTask, Mapping[str, Any]] | None = None,
    ) -> None:
        self._responses = dict(responses or {})
        self._calls: list[LlmRequest] = []

    def generate_structured(self, request: LlmRequest) -> LlmResult:
        """回登記好的答案。沒登記就拋錯，不猜。

        送進來的請求會被記下來（`calls()`），讓測試可以檢查「指示裡有沒有夾帶不該有的
        東西」—— 例如把使用者原文塞進 `instruction`。
        """
        # 即使不連網路也要檢查，否則可攜性規則只對有金鑰的人生效。
        validate_portable_schema(request.output_schema)

        self._calls.append(request)

        payload = self._responses.get(request.task)
        if payload is None:
            msg = (
                f"FakeLanguageModel 沒有登記 {request.task.value} 的回答。"
                "測試需要它的話請在建構時傳入，這個實作不會編造答案。"
            )
            raise LanguageModelUnavailableError(msg)

        return LlmResult(
            task=request.task,
            payload=dict(payload),
            finish_reason=FinishReason.STOP,
        )

    def calls(self) -> tuple[LlmRequest, ...]:
        """目前收到過的請求，依順序。給測試與本機除錯用。"""
        return tuple(self._calls)


class UnavailableLanguageModel:
    """一律失敗的實作，用來測「模型壞掉時系統怎麼反應」。

    需要它是因為失敗路徑跟成功路徑一樣重要，而且兩個任務的失敗行為刻意不同：
    聽懂事件失敗不准猜（猜錯後面七步全錯），白話解釋失敗要照樣顯示結果
    （說明是附加的）。沒有一個穩定會失敗的實作，那兩條路測不到。
    """

    def generate_structured(self, request: LlmRequest) -> LlmResult:
        """永遠拋 `LanguageModelUnavailableError`。"""
        msg = f"UnavailableLanguageModel 依設計拒絕 {request.task.value}"
        raise LanguageModelUnavailableError(msg)
