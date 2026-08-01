"""把一段自由文字對應到一組生命事件代號（最多五個）。

這是整條流程的第一步，也是**系統唯一持有使用者原文的地方**。原文送給模型、拿回
代號、然後丟掉：不寫入 `SessionState`、不寫入紀錄檔、不回傳前端（ADR-0007 / T13）。

模型只能從登記表選代號。複合情境用多個代號表達；補助清單仍由後續 expand 聯集決定。
"""

from __future__ import annotations

import logging

from app.llm.port import (
    LanguageModelError,
    LanguageModelPort,
    LlmRequest,
    LlmTask,
    validate_portable_schema,
)
from app.observability.logging import log_event
from app.orchestration.life_event_selection import (
    MAX_CONFIRMED_LIFE_EVENTS,
    normalize_life_event_ids,
)
from app.orchestration.life_events import LifeEventRegistry

UNRECOGNISED = "unrecognised"
"""模型用來表示「對應不到任何已登記事件」的值。"""

SCHEMA_NAME = "life_event_resolution"

_KEYWORD_FALLBACKS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("失業", "被資遣", "裁員", "解雇", "被炒"), "job_loss"),
    (("無薪假", "減班休息"), "unpaid_leave"),
    (("職災", "上班受傷", "做工受傷", "因公受傷"), "occupational_injury"),
    (("我生病", "生病了", "重大傷病", "住院"), "serious_illness"),
    (("長照", "失智", "外籍看護"), "long_term_care_need"),
    (("家暴", "被打", "保護令"), "domestic_violence"),
    (("懷孕", "有喜"), "pregnancy"),
    (("剛生", "生了小孩", "生育給付"), "childbirth"),
    (("單親",), "single_parent_hardship"),
    (("離婚", "分居"), "divorce"),
    (("先生過世", "太太過世", "老公過世", "老婆過世", "配偶過世"), "spouse_death"),
    (("爸爸過世", "媽媽過世", "父親過世", "母親過世"), "parent_death"),
    (("親人過世", "家人過世", "家裡有人過世", "有人過世"), "other_relative_death"),
    (("照顧", "顧家人", "喘息"), "caregiver_burden"),
)

INSTRUCTION = """你的工作是把一段中文描述對應到一組事件代號（可多選）。

規則：
1. `event_ids` 只能使用下面清單裡的代號。若完全無關，回單一元素 `{unrecognised}`。
2. 一段話若同時包含多個生活變故，應全部列出（最多 {max_events} 個），例如「爸爸職災，我失業」→ occupational_injury 與 job_loss。
3. 只有一個變故時只回一個代號。短句也要對，例如「我失業了」→ job_loss。
4. 有講清楚關係時選更精確的代號（「媽媽過世」→ parent_death）。
5. 幾乎只有在聊天、天氣、沒有生活變故時才回 unrecognised。
6. 只輸出工具參數，不要解釋。

可選的事件代號：
{event_lines}"""


class LifeEventNotRecognisedError(RuntimeError):
    """無法把描述對應到已登記的事件。訊息不得包含使用者原文。"""


def build_schema(registry: LifeEventRegistry) -> dict:
    """依登記表產生多事件輸出 schema。"""
    allowed = [*registry.all_event_ids(), UNRECOGNISED]
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["event_ids"],
        "properties": {
            "event_ids": {
                "type": "array",
                "minItems": 1,
                # Bedrock 不支援 maxItems；上限由 normalize_life_event_ids 截斷。
                "items": {
                    "type": "string",
                    "enum": allowed,
                    "description": "事件代號；無法判斷時用 unrecognised",
                },
                "description": (
                    f"對應到的事件代號清單（請勿超過 {MAX_CONFIRMED_LIFE_EVENTS} 個）"
                ),
            },
        },
    }
    validate_portable_schema(schema)
    return schema


def build_instruction(registry: LifeEventRegistry) -> str:
    """組出指示文字。"""
    event_lines = "\n".join(
        f"- {definition.event_id}：{definition.description}"
        for definition in registry.definitions()
    )
    return INSTRUCTION.format(
        event_lines=event_lines,
        unrecognised=UNRECOGNISED,
        max_events=MAX_CONFIRMED_LIFE_EVENTS,
    )


def _keyword_fallback(text: str, registry: LifeEventRegistry) -> tuple[str, ...]:
    """口語備援：可一次命中多個事件。"""
    found: list[str] = []
    for keywords, event_id in _KEYWORD_FALLBACKS:
        if event_id in found:
            continue
        if any(keyword in text for keyword in keywords) and registry.has(event_id):
            found.append(event_id)
    return normalize_life_event_ids(found, registry)


def _extract_event_ids(payload: dict) -> list[str]:
    """相容 event_ids 陣列與舊的單一 event_id。"""
    raw = payload.get("event_ids")
    if raw is None:
        single = payload.get("event_id")
        if isinstance(single, str):
            return [single]
        return []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, str)]
    return []


def resolve_life_event(
    text: str,
    *,
    model: LanguageModelPort,
    registry: LifeEventRegistry,
) -> tuple[str, ...]:
    """把 `text` 對應到一組已登記事件代號。

    成功時回傳 1～5 個代號；失敗拋 `LifeEventNotRecognisedError`。
    """
    request = LlmRequest(
        task=LlmTask.RESOLVE_LIFE_EVENT,
        instruction=build_instruction(registry),
        user_content=text,
        output_schema=build_schema(registry),
        schema_name=SCHEMA_NAME,
        max_output_tokens=256,
    )
    try:
        result = model.generate_structured(request)
    except LanguageModelError as error:
        root = error.__cause__
        log_event(
            "life_event_resolution_failed",
            level=logging.WARNING,
            exc_info=True,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
            error_type=type(root).__name__ if root is not None else type(error).__name__,
        )
        fallback = _keyword_fallback(text, registry)
        if fallback:
            log_event(
                "life_event_resolved",
                level=logging.INFO,
                life_event=fallback[0],
                tool=LlmTask.RESOLVE_LIFE_EVENT.value,
            )
            return fallback
        msg = "語言模型目前無法處理事件辨識"
        raise LifeEventNotRecognisedError(msg) from error

    raw_ids = _extract_event_ids(result.payload)
    if not raw_ids or raw_ids == [UNRECOGNISED] or UNRECOGNISED in raw_ids and len(raw_ids) == 1:
        log_event(
            "life_event_unrecognised",
            level=logging.INFO,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
        )
        fallback = _keyword_fallback(text, registry)
        if fallback:
            log_event(
                "life_event_resolved",
                level=logging.INFO,
                life_event=fallback[0],
                tool=LlmTask.RESOLVE_LIFE_EVENT.value,
            )
            return fallback
        msg = "模型判斷這段描述對應不到任何已登記的事件"
        raise LifeEventNotRecognisedError(msg)

    # 去掉 unrecognised 雜訊後正規化。
    cleaned = [event_id for event_id in raw_ids if event_id != UNRECOGNISED]
    normalized = normalize_life_event_ids(cleaned, registry)
    if not normalized:
        log_event(
            "life_event_resolution_rejected",
            level=logging.WARNING,
            tool=LlmTask.RESOLVE_LIFE_EVENT.value,
        )
        msg = "模型回的事件代號不在登記表上"
        raise LifeEventNotRecognisedError(msg)

    log_event(
        "life_event_resolved",
        level=logging.INFO,
        life_event=normalized[0],
    )
    return normalized
