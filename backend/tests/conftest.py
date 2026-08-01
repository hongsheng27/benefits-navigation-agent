"""整套測試共用的設定。

## 為什麼需要這個檔案

`Settings` 會讀 repository 根目錄的 `.env`。所以在有 `BEDROCK_MODEL_ID` 的人的
機器上，`create_app()` 會建出一個真的 adapter，於是整合
測試會真的打網路 —— 我們在 2026-07-30 實際撞到這件事：測試從 3 秒變成 46 秒，
而且七個失敗。

三個問題，每一個都足以構成理由：

1. **測試會花錢。** 每跑一次測試就消耗一次額度。
2. **測試會不穩。** 網路與模型都可能出錯，而間歇性失敗的測試最後都會被關掉。
3. **結果取決於誰在跑。** 有金鑰的人和沒金鑰的人跑出不同的結果，
   那讓「測試通過」失去意義。

所以下面那個 fixture 是 `autouse`：**它讓整套測試在結構上不可能用到真實模型**，
不需要每個測試自己記得。要驗證真實模型請用手動腳本，不要放進測試。
"""

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _no_live_language_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """把語言模型的金鑰清成空的，讓每個測試都拿到離線實作。

    設成環境變數而不是改 `.env`：`pydantic-settings` 的優先順序是環境變數高於
    `.env` 檔案，所以這樣就能覆蓋掉本機設定，而且不會動到開發者的檔案。

    `get_settings` 有 `lru_cache`，所以前後都要清一次 —— 前面清是為了不要沿用
    某個更早的呼叫留下的快取，後面清是為了不要把這個空金鑰留給下一個測試。
    """
    monkeypatch.setenv("BEDROCK_MODEL_ID", "")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
