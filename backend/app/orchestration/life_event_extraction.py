"""從一句話辨識人生事件代號。

## 為什麼要有這個模組

在這之前，`state_machine._receive_life_event` 不管使用者打什麼都回
`"spouse_death"`。實測輸入「長照，長輩中風需要照顧怎麼辦」會展開死亡登記、
喪葬給付與遺屬年金 —— 一個家人剛中風的人會看到系統跟他談喪葬。

那不是「還沒做完」，是**自信地答錯**。這個模組把它換成「認得就回代號，認不出
就說認不出」。

## 封閉集合，不是自由生成

`LIFE_EVENT_CODES` 是唯一合法的輸出集合。之後換成 LLM 時，模型也只能從這個集合
裡**選**一個，不能自己造字串（用 enum 約束輸出）。理由是下游要拿這個代號去查
entitlement graph，一個沒人見過的代號查不到東西，卻會讓錯誤發生在離現場很遠的
地方。在這裡就擋掉，錯誤才留在它發生的位置。

## 為什麼死亡類要兩組關鍵字同時命中

「我先生中風了」裡有「先生」。如果只靠關係詞就判定成配偶過世，這句話會被歸到
喪葬類 —— 正是我們要避免的那種錯。所以死亡類要求**關係詞與死亡詞各命中至少
一個**；長照類只有一組詞，命中任一即可。

## 認不出來就回 None

平手也回 `None`。兩個事件分數一樣時猜一個，有一半機率是錯的，而錯的那一半會
把人帶到完全不相干的方案。少回答一次的成本，遠低於答錯一次。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Protocol

LIFE_EVENT_CODES: Final[frozenset[str]] = frozenset(
    {
        "spouse_death",
        "parent_death",
        "long_term_care",
    }
)
"""目前認得的人生事件代號。

新增代號之前要先確認 entitlement graph 有對應的資料，否則使用者會得到
「我聽懂了，但我沒有東西給你」—— 那比聽不懂更令人困惑。
"""


@dataclass(frozen=True, slots=True)
class _EventPattern:
    """一個事件的辨識規則。

    `required_groups` 裡的**每一組**都要至少命中一個詞，這個事件才算成立。
    分數是所有命中詞的總數，用來在多個事件同時成立時比較。
    """

    event_id: str
    required_groups: tuple[tuple[str, ...], ...]

    def score(self, text: str) -> int:
        """回傳命中詞的總數。任何一組完全沒命中就回 0（不成立）。"""
        total = 0
        for group in self.required_groups:
            hits = sum(1 for term in group if term in text)
            if hits == 0:
                return 0
            total += hits
        return total


_DEATH_TERMS: Final[tuple[str, ...]] = (
    "過世",
    "往生",
    "去世",
    "身故",
    "死亡",
    "走了",
    "離世",
    "亡故",
    "喪",
)

_PATTERNS: Final[tuple[_EventPattern, ...]] = (
    _EventPattern(
        event_id="spouse_death",
        required_groups=(
            ("配偶", "老公", "老婆", "先生", "太太", "丈夫", "妻子", "另一半"),
            _DEATH_TERMS,
        ),
    ),
    _EventPattern(
        event_id="parent_death",
        required_groups=(
            ("父親", "母親", "爸爸", "媽媽", "爸", "媽", "雙親", "家父", "家母"),
            _DEATH_TERMS,
        ),
    ),
    _EventPattern(
        event_id="long_term_care",
        required_groups=(
            (
                "長照",
                "長期照顧",
                "長期照護",
                "照顧",
                "照護",
                "失能",
                "失智",
                "中風",
                "臥床",
                "行動不便",
                "生活無法自理",
                "看護",
                "喘息服務",
                "輔具",
                "居家服務",
                "日間照顧",
                "1966",
            ),
        ),
    ),
)

_WHITESPACE = re.compile(r"\s+")


class LifeEventExtractorPort(Protocol):
    """狀態機看得到的抽取器形狀。

    只有一個方法，而且回傳型別是 `str | None` —— 「認不出來」是正常回傳值，
    不是例外。之後換成 LLM 版本時，狀態機一行都不用改。
    """

    def extract(self, text: str) -> str | None:
        """回傳事件代號，認不出來時回 None。不得拋出例外。"""
        ...


@dataclass(frozen=True, slots=True)
class KeywordLifeEventExtractor:
    """關鍵字比對版的抽取器。零網路、零模型呼叫。

    這是過渡實作，不是最終方案：它認不出「我媽最近變得需要人家餵飯」這種沒有
    出現任何關鍵字的說法。但它**不會**把這句話錯認成配偶過世，這是它相對於前一
    版寫死回傳值的全部價值。
    """

    def extract(self, text: str) -> str | None:
        """比對關鍵字。認不出來或平手時回 None。"""
        normalized = _WHITESPACE.sub("", text)
        if not normalized:
            return None

        scores = [
            (pattern.score(normalized), pattern.event_id) for pattern in _PATTERNS
        ]
        matched = [(score, event_id) for score, event_id in scores if score > 0]
        if not matched:
            return None

        best_score = max(score for score, _ in matched)
        winners = [event_id for score, event_id in matched if score == best_score]
        if len(winners) != 1:
            # 平手就不猜。例如「我先生過世後要照顧婆婆」同時像兩件事，
            # 這時候請使用者說清楚，比替他決定好。
            return None

        winner = winners[0]
        # 防呆：模式表與代號集合各改一邊時，這裡會擋下來。
        if winner not in LIFE_EVENT_CODES:
            return None
        return winner


DEFAULT_EXTRACTOR: Final[KeywordLifeEventExtractor] = KeywordLifeEventExtractor()
"""預設的抽取器。呼叫端可以注入別的實作（例如之後的 LLM 版）。"""
