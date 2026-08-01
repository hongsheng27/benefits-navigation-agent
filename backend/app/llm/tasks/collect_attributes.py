"""從使用者一句話抽出欄位登記表上的去識別化屬性（T21b 風格）。

每輪最多確定一個欄位（Bedrock schema 較穩）；可搭配關鍵字備援一次補多欄。
模型不可判定資格。原文只活在 `user_content`。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from app.llm.port import (
    LanguageModelError,
    LanguageModelPort,
    LlmRequest,
    LlmTask,
    validate_portable_schema,
)
from app.observability.logging import log_event
from app.orchestration.field_registry import FieldDefinition, FieldRegistry
from app.orchestration.state import AttributeValue

SCHEMA_NAME = "attribute_collection"
NONE_FIELD = "none"

INSTRUCTION = """你是「接住」的資料蒐集助理。使用者正在用自然語言回答資格相關問題。

硬性規則：
1. 從使用者這句話判斷能否填入「待填欄位」之一；value 必須是該欄位允許的代號，或 boolean 的 true/false。
2. 若無法有把握填任何一欄，field_id 設為 none，value 設空字串，confident 設 false。
3. 絕對不可判定是否符合補助資格。
4. next_question 用繁體中文、一句正面問句引導下一個待填欄位（例如「這次是否屬於非自願離職？」）；不要複述用途說明；若資訊已夠可給空字串。
5. 只輸出工具參數。"""


@dataclass(frozen=True)
class CollectedAttributes:
    """一次抽取結果。"""

    attributes: dict[str, AttributeValue]
    unsure_field_ids: tuple[str, ...]
    next_question: str


class AttributeCollectionError(RuntimeError):
    """模型無法完成屬性抽取。訊息不得包含使用者原文。"""


_JURISDICTION_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("台北", "臺北", "北市"), "TPE"),
    (("新北",), "NWT"),
    (("桃園",), "TAO"),
    (("澎湖",), "PEN"),
    (("其他縣市", "外縣市"), "OTHER_TW"),
    (("不確定", "不清楚", "不知道在哪"), "unsure"),
)

_INSURANCE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("勞保", "勞工保險", "勞工保險局"), "labor_insurance"),
    (("國保", "國民年金"), "national_pension"),
    (("農保", "農民保險"), "farmers_insurance"),
    (("公教", "公保", "公務員"), "civil_service_insurance"),
    (("沒有保險", "沒投保", "不確定有沒有保險"), "none_or_unsure"),
)

_AGE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("未滿25", "不到25", "二十歲", "二十四"), "under_25"),
    (("65歲以上", "超過65", "七十歲"), "65_or_above"),
    (("55到65", "55至65", "六十歲"), "55_to_65"),
    (("25到55", "25至55", "三十歲", "四十歲", "五十歲"), "25_to_55"),
)


def build_schema(fields: Sequence[FieldDefinition]) -> dict[str, Any]:
    """每輪抽出單一欄位的可攜 schema。"""
    field_ids = [f.field_id for f in fields] + [NONE_FIELD]
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["field_id", "value", "confident", "next_question"],
        "properties": {
            "field_id": {
                "type": "string",
                "enum": field_ids,
                "description": "抽出的欄位代號；無法抽出時用 none",
            },
            "value": {
                "type": "string",
                "description": "選項代號，或 true/false；不確定時空字串",
            },
            "confident": {
                "type": "boolean",
                "description": "是否有把握填入 field_id/value",
            },
            "next_question": {
                "type": "string",
                "description": "下一句繁中問題；無需再問時給空字串",
            },
        },
    }
    validate_portable_schema(schema)
    return schema


def build_user_content(reply: str, fields: Sequence[FieldDefinition]) -> str:
    lines = ["使用者回覆：", reply.strip(), "", "待填欄位："]
    if not fields:
        lines.append("（無）")
    else:
        for field in fields:
            options = (
                f"選項：{', '.join(field.option_ids)}"
                if field.option_ids
                else f"型別：{field.value_kind.value}"
            )
            lines.append(
                f"- {field.field_id}：用途說明（勿當問句）={field.purpose}（{options}）"
            )
    return "\n".join(lines)


def heuristic_extract(
    reply: str, fields: Sequence[FieldDefinition]
) -> dict[str, AttributeValue]:
    """離線／備援：用高信心關鍵字抽出屬性。"""
    wanted = {f.field_id: f for f in fields}
    found: dict[str, AttributeValue] = {}
    if "applicant_jurisdiction" in wanted:
        for keywords, code in _JURISDICTION_KEYWORDS:
            if any(k in reply for k in keywords):
                found["applicant_jurisdiction"] = code
                break
    if "deceased_insurance_type" in wanted:
        for keywords, code in _INSURANCE_KEYWORDS:
            if any(k in reply for k in keywords):
                found["deceased_insurance_type"] = code
                break
    if "has_dependent_children" in wanted:
        if any(k in reply for k in ("有小孩", "有未成年", "有子女", "有啊")):
            found["has_dependent_children"] = True
        elif any(k in reply for k in ("沒有小孩", "沒小孩", "無子女", "沒有未成年")):
            found["has_dependent_children"] = False
    if "applicant_age_band" in wanted:
        for keywords, code in _AGE_KEYWORDS:
            if any(k in reply for k in keywords):
                found["applicant_age_band"] = code
                break
    return found


def _coerce_value(
    field: FieldDefinition, raw: str
) -> AttributeValue | None:
    if field.value_kind.value == "boolean":
        lowered = raw.strip().lower()
        if lowered in {"true", "1", "yes", "是"}:
            return True
        if lowered in {"false", "0", "no", "否"}:
            return False
        return None
    value = raw.strip()
    if not value:
        return None
    if field.option_ids and value not in field.option_ids:
        return None
    return value


def collect_attributes_from_reply(
    reply: str,
    *,
    fields: Sequence[FieldDefinition],
    model: LanguageModelPort,
    registry: FieldRegistry,
) -> CollectedAttributes:
    """從一句回覆抽出屬性。"""
    heuristics = heuristic_extract(reply, fields)
    if not fields:
        return CollectedAttributes(
            attributes={}, unsure_field_ids=(), next_question=""
        )

    request = LlmRequest(
        task=LlmTask.COLLECT_ATTRIBUTES,
        instruction=INSTRUCTION,
        user_content=build_user_content(reply, fields),
        output_schema=build_schema(fields),
        schema_name=SCHEMA_NAME,
        max_output_tokens=256,
        temperature=0.0,
    )

    model_attrs: dict[str, AttributeValue] = {}
    next_question = ""
    unsure: list[str] = []
    try:
        result = model.generate_structured(request)
        field_id = result.payload.get("field_id")
        value = result.payload.get("value")
        confident = result.payload.get("confident") is True
        next_raw = result.payload.get("next_question")
        next_question = next_raw.strip() if isinstance(next_raw, str) else ""
        if (
            confident
            and isinstance(field_id, str)
            and field_id != NONE_FIELD
            and isinstance(value, str)
            and registry.has(field_id)
        ):
            field = next((f for f in fields if f.field_id == field_id), None)
            if field is not None:
                coerced = _coerce_value(field, value)
                if coerced is not None:
                    model_attrs[field_id] = coerced
                else:
                    unsure.append(field_id)
        elif isinstance(field_id, str) and field_id != NONE_FIELD:
            unsure.append(field_id)
    except LanguageModelError as error:
        root = error.__cause__
        log_event(
            "attribute_collection_failed",
            level=logging.WARNING,
            exc_info=True,
            tool=LlmTask.COLLECT_ATTRIBUTES.value,
            error_type=type(root).__name__ if root is not None else type(error).__name__,
        )
        if not heuristics:
            msg = "語言模型目前無法抽取資格屬性"
            raise AttributeCollectionError(msg) from error

    merged = {**model_attrs, **heuristics}
    # heuristics 覆蓋同鍵時以 heuristics 為準（離線備援較穩）
    merged = {**model_attrs}
    merged.update(heuristics)

    log_event(
        "attribute_collection_completed",
        level=logging.INFO,
        tool=LlmTask.COLLECT_ATTRIBUTES.value,
        extracted_field_names=sorted(merged.keys()),
        missing_field_names=unsure,
    )
    return CollectedAttributes(
        attributes=merged,
        unsure_field_ids=tuple(dict.fromkeys(unsure)),
        next_question=next_question,
    )
