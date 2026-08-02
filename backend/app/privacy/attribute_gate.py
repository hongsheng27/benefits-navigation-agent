"""屬性值進入 state 之前的最後一道檢查。

## 這道閘門檢查什麼

欄位**代號**的 allowlist 由狀態機在 `_record_answers` 裡強制執行，不靠這個閘門。
這裡負責的是代號合法之後的下一個問題：**值本身對不對**。

```
送 {"deceased_insurance_type": "任意一段很長的自由文字"}
  → 代號在登記表上，通過第一道檢查
  → 但型別是 code，那段文字不在五個選項裡
  → 這道閘門拒絕
```

沒有這道檢查，任何一段自由文字都能藉著合法代號被存進 `state.attributes`，
再經 `SessionSnapshot.attributes` 原值回到前端。那正是 ADR-0007 要防的事，
而 `AttributeValue` 的 `str` 沒有長度上限，所以能塞的量沒有實際限制。

## 四種型別各自檢查什麼

| 型別 | 檢查 |
| --- | --- |
| `code` | 值必須是 `option_ids` 裡的一個 |
| `band` | 同 `code`。級距在契約上就是一組有序的代號 |
| `boolean` | 值必須是 `True` 或 `False`；`"true"` 這種字串不算 |
| `integer` | 值必須是整數，**且不能是 `bool`** |

最後那一條容易漏：Python 的 `True` 是 `int` 的子類別，`isinstance(True, int)`
會回 `True`。不特別擋的話，`{"child_count": true}` 會被當成合法整數存進去。

## 為什麼不合法就拒絕整筆

跟代號檢查一致。部分接受會讓使用者以為答案都收到了，其實少了一題；
靜默丟棄會讓前端送錯值的 bug 在畫面上看起來像正常運作。

## 目前沒有做範圍檢查

`integer` 不檢查上下限，所以人數送 `999999999` 在型別上仍然合法。登記表目前
沒有地方放範圍，而且三筆種子欄位都還是 draft，加了也不知道填什麼。
等登記表有正式內容時再決定要不要加 `min_value` / `max_value`。
"""

from typing import Any

from app.orchestration.state import AttributeValue
from app.schemas.session import AttributeValueKind


class InvalidAttributeValueError(ValueError):
    """一或多個欄位的值不符合登記表的宣告。

    帶的是**欄位代號**，不是使用者填的值。這一點是刻意的：錯誤會流到 HTTP 回應
    與紀錄檔，而那兩個地方都不得出現使用者輸入。

    `field_ids` 排序後才存，讓同一組違規欄位永遠得到同一個順序。
    """

    def __init__(self, field_ids: tuple[str, ...]) -> None:
        ordered = tuple(sorted(field_ids))
        super().__init__(f"值不符合欄位宣告：{', '.join(ordered)}")
        self.field_ids = ordered


def _is_valid(
    value: AttributeValue, kind: AttributeValueKind, options: tuple[str, ...]
) -> bool:
    """單一值對單一欄位宣告的檢查。"""
    match kind:
        case AttributeValueKind.CODE | AttributeValueKind.BAND:
            return isinstance(value, str) and value in options
        case AttributeValueKind.BOOLEAN:
            return isinstance(value, bool)
        case AttributeValueKind.INTEGER:
            # bool 是 int 的子類別，必須先排除，否則 True 會通過整數檢查。
            return isinstance(value, int) and not isinstance(value, bool)

    return False


class RegistryBackedPrivacyGate:
    """依欄位登記表驗證值的型別與選項。

    實作 `app.orchestration.protocols.PrivacyGate`，可以直接取代
    `PassThroughPrivacyGate`。
    """

    def validate_attributes(
        self,
        answers: dict[str, AttributeValue],
        registry: Any,
    ) -> dict[str, AttributeValue]:
        """回傳可以寫進 state 的答案，或在有任何一個值不合法時拋出例外。

        `registry` 的型別是 `app.orchestration.field_registry.FieldRegistry`，
        這裡標成 `Any` 是為了跟 protocol 的簽章一致 —— 那邊避開這條 import 是為了
        不讓模組相依圖更難拆。

        代號不在登記表上的情況這裡不處理，狀態機已經先擋掉了。真的遇到（例如有人
        直接呼叫這個方法）就一併算成不合法，因為沒有宣告可以對照。
        """
        invalid: list[str] = []

        for field_id, value in answers.items():
            definition = registry.get(field_id)
            if definition is None:
                invalid.append(field_id)
                continue

            if not _is_valid(value, definition.value_kind, definition.option_ids):
                invalid.append(field_id)

        if invalid:
            raise InvalidAttributeValueError(tuple(invalid))

        # 複製一份，避免呼叫端之後改動同一個 dict。
        return dict(answers)
