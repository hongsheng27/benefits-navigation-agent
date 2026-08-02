"""依前端提供的官方摘錄／申請步驟，回答諮詢後的說明問題。

這支任務**不做資格判定**。模型只能根據請求裡的參考資料說明期限、文件、窗口等，
不能宣布使用者是否 eligible。問題與摘錄只活在這次呼叫的 `user_content`，
不寫入 session、不進紀錄檔。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from app.llm.port import (
    LanguageModelError,
    LanguageModelPort,
    LlmRequest,
    LlmTask,
    validate_portable_schema,
)
from app.observability.logging import log_event

SCHEMA_NAME = "answer_with_references"

INSTRUCTION = """你是「接住」的說明助理。使用者剛看完補助相關摘錄或申請步驟，正在追問。

硬性規則：
1. 只能依據下方「參考資料」回答。資料沒寫的就明說不知道或建議洽官方窗口，禁止編造條號、金額、期限。
2. 絕對不可判定使用者是否符合資格、可不可以領、申請會不會過。若被問到，要說明資格由規則引擎與受理機關認定，你只做說明。
3. 不可要求或複述身分證字號、真實姓名、地址等個資；若使用者貼了，請他刪除並改問一般流程問題。
4. 用繁體中文、白話回覆。有多個步驟時，每一個步驟請各自成段，格式如：
   **步驟 1：標題**
   說明文字
   條列請用「- 」開頭並換行。重點提醒也請獨立成段。不要把全部步驟黏在同一行。
5. 只輸出工具參數裡的 answer 欄位，不要額外解釋。"""


@dataclass(frozen=True)
class ReferenceExcerpt:
    """一筆給模型看的參考資料。"""

    title: str
    body: str
    source_url: str | None = None


class ExplanationUnavailableError(RuntimeError):
    """模型無法完成說明。訊息不得包含使用者問題或摘錄原文。"""


def build_schema() -> dict:
    """輸出 schema：單一 answer 字串。"""
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer"],
        "properties": {
            "answer": {
                "type": "string",
                "description": "給使用者看的白話說明，不得判定資格",
            },
        },
    }
    validate_portable_schema(schema)
    return schema


def build_user_content(
    question: str,
    references: Sequence[ReferenceExcerpt],
    *,
    panel_kind: str,
) -> str:
    """組出單次請求的使用者內容。呼叫端用完即丟。"""
    blocks: list[str] = [
        f"面板類型：{panel_kind}",
        "問題：",
        question.strip(),
        "",
        "參考資料（只能依據這些內容回答；若不足請明說）：",
    ]
    if not references:
        blocks.append("（沒有提供參考資料）")
    else:
        for index, item in enumerate(references, start=1):
            url_line = f"來源：{item.source_url}" if item.source_url else "來源：（未提供）"
            blocks.extend(
                [
                    "---",
                    f"[{index}] 標題：{item.title.strip()}",
                    url_line,
                    "內容：",
                    item.body.strip(),
                ]
            )
    return "\n".join(blocks)


def answer_with_references(
    question: str,
    references: Sequence[ReferenceExcerpt],
    *,
    model: LanguageModelPort,
    panel_kind: str,
) -> str:
    """依參考資料回答問題。失敗時拋 `ExplanationUnavailableError`。"""
    request = LlmRequest(
        task=LlmTask.ANSWER_WITH_REFERENCES,
        instruction=INSTRUCTION,
        user_content=build_user_content(
            question, references, panel_kind=panel_kind
        ),
        output_schema=build_schema(),
        schema_name=SCHEMA_NAME,
        max_output_tokens=1024,
        temperature=0.0,
    )
    try:
        result = model.generate_structured(request)
    except LanguageModelError as error:
        root = error.__cause__
        log_event(
            "grounded_explanation_failed",
            level=logging.WARNING,
            exc_info=True,
            tool=LlmTask.ANSWER_WITH_REFERENCES.value,
            error_type=type(root).__name__ if root is not None else type(error).__name__,
        )
        msg = "語言模型目前無法處理諮詢後說明"
        raise ExplanationUnavailableError(msg) from error

    answer = result.payload.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        log_event(
            "grounded_explanation_rejected",
            level=logging.WARNING,
            tool=LlmTask.ANSWER_WITH_REFERENCES.value,
        )
        msg = "模型回覆缺少可用的說明文字"
        raise ExplanationUnavailableError(msg)

    log_event(
        "grounded_explanation_completed",
        level=logging.INFO,
        tool=LlmTask.ANSWER_WITH_REFERENCES.value,
    )
    return answer.strip()
