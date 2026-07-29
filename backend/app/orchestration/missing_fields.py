"""缺漏欄位的計算與主題分組。

給定「有哪些候選項目」和「使用者已經回答了哪些條件」，算出還缺哪些欄位、
按主題分成幾組問題卡。

## 為什麼按主題分組而不是按項目

同一個欄位常常同時被多個項目需要。例如「過世者投保身分」同時決定喪葬給付和遺屬年金。
如果按項目分組追問，使用者會被問兩次同樣的問題。

按主題分組就不會有這個問題：每個欄位只出現一次，放在它所屬的主題裡。

## 輸出格式

回傳的是 `QuestionGroupView` 清單，可以直接塞進 `SessionSnapshot` 回給前端。
前端拿到之後用代號對照自己的文案。
"""

from app.orchestration.field_registry import FieldDefinition, FieldRegistry
from app.orchestration.state import ItemStatus, SessionState
from app.schemas.session import AttributeValueKind, QuestionGroupView, QuestionView


def compute_question_groups(
    state: SessionState,
    registry: FieldRegistry,
) -> tuple[QuestionGroupView, ...]:
    """從目前狀態算出還需要問的問題，按主題分組。

    邏輯：
    1. 找出所有「還在等欄位」的候選項目（status 是 PENDING 或 NEEDS_INFORMATION）
    2. 從登記表查這些項目需要哪些欄位
    3. 減去使用者已經回答過的
    4. 剩下的就是要問的
    5. 按主題分組

    回傳空的 tuple 表示不需要再問了。
    """
    # 找出還在等的項目代號。
    active_item_ids = frozenset(
        item.item_id
        for item in state.items
        if item.status in {ItemStatus.PENDING, ItemStatus.NEEDS_INFORMATION}
    )

    if not active_item_ids:
        return ()

    # 從登記表查這些項目需要哪些欄位。
    needed_fields = registry.fields_for_items(active_item_ids)

    # 減去已經回答的。
    answered = frozenset(state.attributes.keys())
    missing = [f for f in needed_fields if f.field_id not in answered]

    if not missing:
        return ()

    # 按主題分組，保持登記表裡的順序。
    topics_order = registry.topics()
    by_topic: dict[str, list[FieldDefinition]] = {}
    for f in missing:
        by_topic.setdefault(f.topic_id, []).append(f)

    # 只留有缺漏欄位的主題。
    active_topics = [t for t in topics_order if t in by_topic]
    total = len(active_topics)

    groups: list[QuestionGroupView] = []
    for idx, topic_id in enumerate(active_topics, start=1):
        fields = by_topic[topic_id]
        questions = tuple(
            QuestionView(
                field_id=f.field_id,
                value_kind=AttributeValueKind(f.value_kind.value),
                option_ids=f.option_ids,
                required=f.required,
                purpose_id=f"{f.field_id}.purpose",
                unlocks_item_ids=tuple(
                    iid for iid in f.used_by if iid in active_item_ids
                ),
            )
            for f in fields
        )
        groups.append(
            QuestionGroupView(
                topic_id=topic_id,
                questions=questions,
                group_index=idx,
                group_total=total,
            )
        )

    return tuple(groups)
