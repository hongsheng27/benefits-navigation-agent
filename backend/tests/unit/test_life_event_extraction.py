"""事件辨識的單元測試。

重點不是「認得多少種說法」，而是「認不出來的時候會不會亂猜」。前一版寫死回傳
`spouse_death`，實測輸入長照問題會展開喪葬給付；這裡的測試就是要讓那種行為
再也回不來。
"""

from __future__ import annotations

import pytest

from app.orchestration.life_event_extraction import (
    DEFAULT_EXTRACTOR,
    LIFE_EVENT_CODES,
    KeywordLifeEventExtractor,
)


@pytest.fixture
def extractor() -> KeywordLifeEventExtractor:
    return KeywordLifeEventExtractor()


# ---------------------------------------------------------------------------
# 認得出來的情況
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "長照，長輩中風需要照顧怎麼辦",
        "我媽媽中風了需要人照顧",
        "阿嬤最近生活無法自理",
        "想申請長期照顧服務",
        "爸爸失智了怎麼辦",
        "需要喘息服務",
        "長輩臥床要申請輔具",
        "打1966要準備什麼",
    ],
)
def test_long_term_care_is_recognised(
    extractor: KeywordLifeEventExtractor, text: str
) -> None:
    assert extractor.extract(text) == "long_term_care"


@pytest.mark.parametrize(
    "text",
    [
        "我先生上週過世了",
        "配偶身故要辦什麼",
        "老婆走了，接下來要做什麼",
        "太太往生了",
    ],
)
def test_spouse_death_is_recognised(
    extractor: KeywordLifeEventExtractor, text: str
) -> None:
    assert extractor.extract(text) == "spouse_death"


@pytest.mark.parametrize(
    "text",
    ["父親過世要辦什麼", "媽媽走了", "家父身故", "爸爸去世了"],
)
def test_parent_death_is_recognised(
    extractor: KeywordLifeEventExtractor, text: str
) -> None:
    assert extractor.extract(text) == "parent_death"


# ---------------------------------------------------------------------------
# 不亂猜（這一組才是重點）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "我想問房屋貸款",
        "請問停車費怎麼繳",
        "我要報稅",
        "你好",
        "？？？",
    ],
)
def test_unrelated_text_returns_none(
    extractor: KeywordLifeEventExtractor, text: str
) -> None:
    """認不出來就說認不出來，不回一個看起來很像的代號。"""
    assert extractor.extract(text) is None


def test_empty_and_whitespace_return_none(
    extractor: KeywordLifeEventExtractor,
) -> None:
    assert extractor.extract("") is None
    assert extractor.extract("   \n\t ") is None


def test_relation_word_alone_is_not_a_death_event(
    extractor: KeywordLifeEventExtractor,
) -> None:
    """「我先生中風了」有「先生」，但那不代表他過世了。

    這是舊版最容易犯、後果也最嚴重的錯：把一個需要照顧的家庭導向喪葬給付。
    """
    assert extractor.extract("我先生中風了") == "long_term_care"
    assert extractor.extract("我太太需要人照顧") == "long_term_care"
    assert extractor.extract("爸爸行動不便") == "long_term_care"


def test_death_word_alone_is_not_enough(
    extractor: KeywordLifeEventExtractor,
) -> None:
    """只有死亡詞、沒有關係詞，分不出是誰過世，所以不猜。"""
    assert extractor.extract("家人剛過世") is None
    assert extractor.extract("有人往生了") is None


def test_tie_between_two_events_returns_none(
    extractor: KeywordLifeEventExtractor,
) -> None:
    """兩件事分數一樣時不猜。猜錯的一半會把人帶到完全不相干的方案。"""
    # 關係詞與死亡詞各一（2 分）對上照顧類一個詞（1 分）→ 前者勝，不是平手。
    assert extractor.extract("我先生過世後我要照顧婆婆") == "spouse_death"
    # 兩個死亡事件同時出現，各 2 分 → 平手 → None。
    assert extractor.extract("我先生和我父親都過世了") is None


# ---------------------------------------------------------------------------
# 封閉集合
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "長照，長輩中風需要照顧怎麼辦",
        "我先生上週過世了",
        "父親過世要辦什麼",
        "我想問房屋貸款",
    ],
)
def test_output_is_always_a_known_code_or_none(
    extractor: KeywordLifeEventExtractor, text: str
) -> None:
    """輸出只能是清單裡的代號，或 None。不會生出沒人見過的字串。"""
    result = extractor.extract(text)
    assert result is None or result in LIFE_EVENT_CODES


def test_default_extractor_is_usable() -> None:
    assert DEFAULT_EXTRACTOR.extract("長照怎麼申請") == "long_term_care"


def test_extraction_is_deterministic(extractor: KeywordLifeEventExtractor) -> None:
    """同一句話跑幾次都一樣。之後換 LLM 時這條會需要重新思考。"""
    text = "長照，長輩中風需要照顧怎麼辦"
    results = {extractor.extract(text) for _ in range(20)}
    assert results == {"long_term_care"}
