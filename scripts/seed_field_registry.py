"""把欄位登記表 JSON 寫進 SQLite 的 `field_registry` 與 `field_allowed_values`。

## 為什麼有兩份登記表

- `data/eligibility_fields/fields.v0.1.json` 是**編寫來源**。狀態機直接讀它，
  用來決定要問使用者什麼、以及拒絕沒登記的欄位代號。
- SQLite 的 `field_registry` 是**資料層的外鍵目標**。`rule_conditions.field_id`
  指向它，所以題庫沒進資料庫，就一條規則都寫不進去。

兩份必須一致。這支腳本讓 JSON 成為唯一的編寫入口，SQLite 那份由它產生，避免
兩邊各改一次而走鐘。

## 為什麼是 upsert 而不是砍掉重建

`field_registry` 被 `rule_conditions`、`rule_required_fields`、
`graph_edge_conditions` 以 `ON DELETE RESTRICT` 引用。已經有規則用到的欄位刪不掉
——這是刻意的：欄位定義改變會讓既有規則的意義改變，那必須經過審查，不能靠重跑
一支腳本就發生。

所以這支腳本只做兩件事：新增沒有的、更新描述性欄位。要停用一個欄位請把 JSON 裡
的 `status` 改成非 `active`，腳本會把 `active` 設成 0，但那一列仍然留著。

## 用法

    uv run python scripts/seed_field_registry.py --database data/local/xxx.db
    uv run python scripts/seed_field_registry.py --dry-run
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.orchestration.field_registry import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    FieldDefinition,
    FieldRegistry,
)

DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "local" / "government_oid.db"

# workflow 的 value_kind → 資料層的 data_type。
# 資料層沒有「級距」這個概念，band 與 code 都是有限選項，所以都落到 enum。
_DATA_TYPE_BY_VALUE_KIND: dict[str, str] = {
    "code": "enum",
    "band": "enum",
    "boolean": "boolean",
    "integer": "integer",
}

# 給規則編寫者看的中文標籤。這**不是**要顯示給使用者的問句 —— 使用者看到的文案
# 由前端依 field_id 決定（見 `schemas.session.QuestionView`）。這裡的標籤只是為了
# 讓審查規則的人不必背代號。
_REVIEW_LABELS: dict[str, str] = {
    "deceased_insurance_type": "亡者的投保身分",
    "has_dependent_children": "是否有未成年子女",
    "applicant_age_band": "申請人年齡級距",
    "care_recipient_age_band": "被照顧者年齡級距",
    "daily_activity_assistance_need": "日常生活需要他人協助的程度",
    "has_dementia_diagnosis": "是否經診斷為失智症",
    "is_indigenous": "是否為原住民族",
    "has_disability_certificate": "是否領有身心障礙證明",
    "has_completed_care_assessment": "是否已完成長照需求評估",
    "employs_foreign_caregiver": "是否已聘僱外籍家庭看護工",
    "residence_city_code": "被照顧者居住縣市",
}


@dataclass(frozen=True, slots=True)
class SeedResult:
    """一次 seed 的結果。給呼叫端與測試檢查用。"""

    inserted: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]
    values_written: int

    @property
    def total(self) -> int:
        return len(self.inserted) + len(self.updated) + len(self.unchanged)


def _row_for(definition: FieldDefinition) -> tuple[str, str, str, str, str, int]:
    data_type = _DATA_TYPE_BY_VALUE_KIND.get(definition.value_kind)
    if data_type is None:
        raise ValueError(
            f"未知的 value_kind: {definition.value_kind!r}"
            f"（欄位 {definition.field_id}）"
        )
    label = _REVIEW_LABELS.get(definition.field_id, definition.field_id)
    active = 1 if definition.status == "active" else 0
    return (
        definition.field_id,
        data_type,
        label,
        definition.purpose,
        definition.pii_classification,
        active,
    )


def seed(
    connection: sqlite3.Connection,
    definitions: tuple[FieldDefinition, ...],
) -> SeedResult:
    """把欄位定義寫進資料庫。回傳這次做了什麼。"""
    inserted: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    values_written = 0

    for definition in definitions:
        row = _row_for(definition)
        existing = connection.execute(
            """
            SELECT field_id, data_type, prompt_label, why_needed,
                   pii_classification, active
            FROM field_registry WHERE field_id = ?
            """,
            (definition.field_id,),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO field_registry (
                    field_id, data_type, prompt_label, why_needed,
                    pii_classification, active
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                row,
            )
            inserted.append(definition.field_id)
        elif tuple(existing) == row:
            unchanged.append(definition.field_id)
        else:
            # data_type 不在更新範圍內：改型別會讓既有規則條件的比較語意改變，
            # 那必須經過審查，不能靠重跑腳本發生。
            if str(existing[1]) != row[1]:
                raise ValueError(
                    f"欄位 {definition.field_id} 的 data_type 從 {existing[1]!r} "
                    f"變成 {row[1]!r}。改型別會改變既有規則的意義，請走審查流程。"
                )
            connection.execute(
                """
                UPDATE field_registry
                SET prompt_label = ?, why_needed = ?,
                    pii_classification = ?, active = ?
                WHERE field_id = ?
                """,
                (row[2], row[3], row[4], row[5], definition.field_id),
            )
            updated.append(definition.field_id)

        values_written += _sync_allowed_values(connection, definition)

    return SeedResult(
        inserted=tuple(inserted),
        updated=tuple(updated),
        unchanged=tuple(unchanged),
        values_written=values_written,
    )


def _sync_allowed_values(
    connection: sqlite3.Connection,
    definition: FieldDefinition,
) -> int:
    """補齊這個欄位的選項。已存在的不動，也不刪除多出來的。

    不刪除是因為 `rule_conditions.expected_value_json` 可能引用某個選項；選項要
    下架應該是一次有意識的審查動作，不是 seed 的副作用。多出來的選項會在下面回報。
    """
    if not definition.option_ids:
        return 0

    existing = {
        str(row[0]): int(row[1])
        for row in connection.execute(
            "SELECT value, canonical_order FROM field_allowed_values "
            "WHERE field_id = ?",
            (definition.field_id,),
        )
    }
    written = 0
    for order, value in enumerate(definition.option_ids):
        if value in existing:
            continue
        connection.execute(
            """
            INSERT INTO field_allowed_values (field_id, value, canonical_order)
            VALUES (?, ?, ?)
            """,
            (definition.field_id, value, order),
        )
        written += 1

    orphans = sorted(set(existing) - set(definition.option_ids))
    if orphans:
        print(
            f"  ⚠ {definition.field_id} 資料庫裡有 JSON 沒有的選項：{orphans}\n"
            f"    腳本不會刪除它們。要下架請確認沒有規則引用後，手動處理。"
        )
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite 路徑（預設 {DEFAULT_DATABASE_PATH}）",
    )
    parser.add_argument(
        "--fields",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
        help="欄位登記表 JSON 路徑",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只讀 JSON 並印出將寫入的內容，不碰資料庫",
    )
    args = parser.parse_args()

    registry = FieldRegistry.from_json(args.fields)
    definitions = tuple(
        registry.get(field_id)  # type: ignore[misc]
        for field_id in sorted(registry.all_field_ids())
    )

    print(f"讀到 {len(definitions)} 個欄位定義：{args.fields}")
    for definition in definitions:
        row = _row_for(definition)
        options = (
            f"{len(definition.option_ids)} 個選項" if definition.option_ids else "—"
        )
        print(
            f"  {definition.field_id:32s} {row[1]:8s} "
            f"{definition.pii_classification:22s} {options}"
        )

    if args.dry_run:
        print("\n--dry-run：沒有寫入任何東西。")
        return 0

    if not args.database.exists():
        print(f"資料庫不存在：{args.database}", file=sys.stderr)
        return 1

    with closing(sqlite3.connect(args.database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            result = seed(connection, definitions)
        except Exception:
            connection.rollback()
            raise
        connection.commit()

    print(
        f"\n✓ 新增 {len(result.inserted)}、更新 {len(result.updated)}、"
        f"未變動 {len(result.unchanged)}，寫入 {result.values_written} 個選項。"
    )
    if result.inserted:
        print(f"  新增：{', '.join(result.inserted)}")
    if result.updated:
        print(f"  更新：{', '.join(result.updated)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
