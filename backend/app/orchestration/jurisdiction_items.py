"""依所在地收斂地方型補助候選。

全國項目一律保留；地方項目只在 `applicant_jurisdiction` 對得上時加入。
資料來自 benefit discovery 候選，標成 candidate，不做資格判定。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.orchestration.data_contracts import CandidateItem, GraphRelation

_DEATH_REGISTRATION = GraphRelation(
    item_id="death_registration",
    display_name="死亡登記",
    order=0,
)

# jurisdiction_code → 地方方案（與 data/benefit_discovery 對齊）
_LOCAL_ITEMS: dict[str, tuple[CandidateItem, ...]] = {
    "TPE": (
        CandidateItem(
            item_id="taipei_green_funeral_incentive",
            display_name="臺北市多元環保葬鼓勵金",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
        CandidateItem(
            item_id="taipei_joint_funeral_service",
            display_name="臺北市聯合奠祭",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
    ),
    "NWT": (
        CandidateItem(
            item_id="new_taipei_green_funeral_incentive",
            display_name="新北市環保葬鼓勵金",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
    ),
    "TAO": (
        CandidateItem(
            item_id="taoyuan_green_funeral_incentive",
            display_name="桃園市環保葬鼓勵金",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
    ),
    "PEN": (
        CandidateItem(
            item_id="penghu_green_funeral_subsidy",
            display_name="澎湖縣多元環保葬補助",
            program_status="candidate",
            relevance_score=None,
            missing_field_ids=(),
            prerequisites=(_DEATH_REGISTRATION,),
            produces=(),
        ),
    ),
}

LOCAL_ITEM_IDS: frozenset[str] = frozenset(
    item.item_id for items in _LOCAL_ITEMS.values() for item in items
)


def local_items_for_attributes(
    user_attributes: Mapping[str, Any],
) -> tuple[CandidateItem, ...]:
    """依 applicant_jurisdiction 回傳地方方案；未答或 unsure/OTHER_TW 則不回。"""
    code = user_attributes.get("applicant_jurisdiction")
    if not isinstance(code, str):
        return ()
    if code in {"unsure", "OTHER_TW"}:
        return ()
    return _LOCAL_ITEMS.get(code, ())
