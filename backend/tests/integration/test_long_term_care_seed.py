"""長照情境的端到端種子測試。

把三樣東西串起來驗證：事件辨識 → 題庫 → 關係圖展開。

這一組測試存在的理由是「長照」是第一個從零建起來的領域。之後再加新領域時，
照著同一條路走一遍，這裡的斷言就是驗收條件。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from backend.app.adapters.sqlite.graph_repository import (
    SqliteEntitlementGraphRepository,
)
from backend.app.adapters.sqlite.migrations import migrate_database
from backend.app.orchestration.field_registry import FieldRegistry
from backend.app.orchestration.life_event_extraction import (
    LIFE_EVENT_CODES,
    KeywordLifeEventExtractor,
)

# 這一行刻意用 `app.` 而不是 `backend.app.`：adapter 內部是以 `app.` 匯入這個例外
# 的，而 pyproject 的 `pythonpath = [".", ".."]` 讓兩條路徑各自產生一份模組物件。
# 用錯前綴會拿到「長得一樣但不是同一個」的類別，pytest.raises 就攔不到。
from app.orchestration.data_errors import InvalidEventIdError

REPO_ROOT = Path(__file__).resolve().parents[3]
FIELDS_JSON = REPO_ROOT / "data" / "eligibility_fields" / "fields.v0.1.json"
GRAPH_JSON = REPO_ROOT / "data" / "entitlement_graph" / "graph.v0.1.json"

if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

from scripts.seed_entitlement_graph import load_graph  # noqa: E402
from scripts.seed_entitlement_graph import seed as seed_graph  # noqa: E402
from scripts.seed_field_registry import seed as seed_fields  # noqa: E402

LTC_FIELD_IDS = frozenset(
    {
        "care_recipient_age_band",
        "daily_activity_assistance_need",
        "has_dementia_diagnosis",
        "is_indigenous",
        "has_disability_certificate",
        "has_completed_care_assessment",
        "employs_foreign_caregiver",
        "residence_city_code",
    }
)


@pytest.fixture
def seeded_database(tmp_path: Path) -> Path:
    """跑完 migration 與兩支 seed 的資料庫。

    順序不能反：關係圖的邊條件以外鍵指向題庫。
    """
    database = tmp_path / "ltc.db"
    migrate_database(database)

    registry = FieldRegistry.from_json(FIELDS_JSON)
    definitions = tuple(
        registry.get(field_id)  # type: ignore[misc]
        for field_id in sorted(registry.all_field_ids())
    )
    graph = load_graph(GRAPH_JSON)

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        seed_fields(connection, definitions)
        seed_graph(connection, graph)
        connection.commit()
    return database


def _repo(database: Path) -> SqliteEntitlementGraphRepository:
    return SqliteEntitlementGraphRepository(lambda: sqlite3.connect(database))


# ---------------------------------------------------------------------------
# 事件代號
# ---------------------------------------------------------------------------


def test_the_original_question_now_resolves_to_long_term_care() -> None:
    """一開始那句話。以前會得到配偶過世。"""
    extractor = KeywordLifeEventExtractor()
    assert extractor.extract("長照，長輩中風需要照顧怎麼辦") == "long_term_care"


def test_graph_life_event_nodes_match_the_extractor_vocabulary() -> None:
    """關係圖裡的事件節點必須是抽取器認得的代號。

    兩邊各改一次就會走鐘：抽取器回一個圖上沒有的代號，展開會拋
    invalid_event_id；圖上有但抽取器不認得的代號則永遠到不了。
    """
    graph = load_graph(GRAPH_JSON)
    event_nodes = {
        node["node_id"] for node in graph.nodes if node["node_type"] == "life_event"
    }
    assert event_nodes <= LIFE_EVENT_CODES, (
        f"圖上有抽取器不認得的事件代號：{sorted(event_nodes - LIFE_EVENT_CODES)}"
    )
    assert "long_term_care" in event_nodes


# ---------------------------------------------------------------------------
# 題庫
# ---------------------------------------------------------------------------


def test_all_long_term_care_fields_are_registered(seeded_database: Path) -> None:
    with closing(sqlite3.connect(seeded_database)) as connection:
        stored = {
            str(row[0])
            for row in connection.execute("SELECT field_id FROM field_registry")
        }
    assert LTC_FIELD_IDS <= stored


def test_sensitive_fields_are_classified_as_such(seeded_database: Path) -> None:
    """健康、族群、居住地都不是「一般」欄位。標錯會讓後續處理少一層保護。"""
    expected_sensitive = {
        "daily_activity_assistance_need",
        "has_dementia_diagnosis",
        "is_indigenous",
        "has_disability_certificate",
        "residence_city_code",
    }
    with closing(sqlite3.connect(seeded_database)) as connection:
        rows = dict(
            connection.execute(
                "SELECT field_id, pii_classification FROM field_registry"
            )
        )
    for field_id in expected_sensitive:
        assert rows[field_id] == "eligibility_sensitive", field_id
    # 沒有任何欄位該是直接識別資訊。
    assert "direct_identifier" not in rows.values()


def test_every_field_states_why_it_is_needed(seeded_database: Path) -> None:
    """新增欄位是隱私決策，理由不能空白。"""
    with closing(sqlite3.connect(seeded_database)) as connection:
        rows = connection.execute(
            "SELECT field_id, why_needed FROM field_registry"
        ).fetchall()
    for field_id, why in rows:
        assert why and why.strip(), field_id


def test_city_options_cover_all_twenty_two(seeded_database: Path) -> None:
    with closing(sqlite3.connect(seeded_database)) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM field_allowed_values WHERE field_id = ?",
            ("residence_city_code",),
        ).fetchone()[0]
    assert count == 22


# ---------------------------------------------------------------------------
# 關係圖展開
# ---------------------------------------------------------------------------


def test_unanswered_field_shows_both_paths(seeded_database: Path) -> None:
    """還沒回答時兩條路都顯示，並標出缺哪個欄位。不猜。"""
    items = _repo(seeded_database).expand_from_event("long_term_care", {})

    ids = {item.item_id for item in items}
    assert ids == {"ltc_needs_assessment", "ltc_service_after_assessment"}
    for item in items:
        assert item.missing_field_ids == ("has_completed_care_assessment",)


def test_not_yet_assessed_sees_only_the_application(seeded_database: Path) -> None:
    items = _repo(seeded_database).expand_from_event(
        "long_term_care", {"has_completed_care_assessment": False}
    )

    assert [item.item_id for item in items] == ["ltc_needs_assessment"]
    assert items[0].missing_field_ids == ()


def test_already_assessed_sees_only_the_follow_up(seeded_database: Path) -> None:
    """已經評估過的人不該再看到「申請評估」—— 那是不適用，不是不合格。"""
    items = _repo(seeded_database).expand_from_event(
        "long_term_care", {"has_completed_care_assessment": True}
    )

    assert [item.item_id for item in items] == ["ltc_service_after_assessment"]


def test_ordering_relations_are_available(seeded_database: Path) -> None:
    """前置關係讓清單排得出順序，而不是把項目藏起來。"""
    repository = _repo(seeded_database)

    prerequisites = repository.get_prerequisites("ltc_service_after_assessment")
    assert [relation.target_id for relation in prerequisites] == [
        "ltc_needs_assessment"
    ]

    produces = repository.get_produces("ltc_needs_assessment")
    assert [relation.target_id for relation in produces] == [
        "ltc_service_after_assessment"
    ]


def test_prerequisite_does_not_remove_the_item(seeded_database: Path) -> None:
    """關鍵行為：前置沒完成，項目照樣出現，只是帶著「要先辦」的關係。"""
    items = _repo(seeded_database).expand_from_event("long_term_care", {})

    follow_up = next(
        item for item in items if item.item_id == "ltc_service_after_assessment"
    )
    assert follow_up.prerequisites, "前置關係要被帶出來"
    assert follow_up.item_id in {item.item_id for item in items}, "但項目不能消失"


def test_unknown_event_id_is_rejected(seeded_database: Path) -> None:
    with pytest.raises(InvalidEventIdError):
        _repo(seeded_database).expand_from_event("not_a_real_event", {})


# ---------------------------------------------------------------------------
# 治理：沒有人審過，就不該有任何事實
# ---------------------------------------------------------------------------


def test_seeded_programs_are_candidates_with_no_facts(
    seeded_database: Path,
) -> None:
    """seed 建出來的方案只有名字。金額、期限、規則都要等人工審查。"""
    with closing(sqlite3.connect(seeded_database)) as connection:
        rows = connection.execute(
            """
            SELECT program_id, program_status, amount_min, amount_max,
                   claimant_rule_text, deadline_rule_text
            FROM benefit_programs
            WHERE program_id IN ('ltc_needs_assessment',
                                 'ltc_service_after_assessment')
            """
        ).fetchall()

    assert len(rows) == 2
    for program_id, status, amount_min, amount_max, claimant, deadline in rows:
        assert status == "candidate", program_id
        assert amount_min is None and amount_max is None, program_id
        assert claimant == "" and deadline == "", program_id


def test_seeds_are_idempotent(seeded_database: Path) -> None:
    """重跑不會產生重複，也不會改變展開結果。"""
    before = _repo(seeded_database).expand_from_event("long_term_care", {})

    registry = FieldRegistry.from_json(FIELDS_JSON)
    definitions = tuple(
        registry.get(field_id)  # type: ignore[misc]
        for field_id in sorted(registry.all_field_ids())
    )
    with closing(sqlite3.connect(seeded_database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        field_result = seed_fields(connection, definitions)
        graph_result = seed_graph(connection, load_graph(GRAPH_JSON))
        connection.commit()

    assert field_result.inserted == ()
    assert graph_result.nodes_inserted == ()
    assert graph_result.edges_inserted == ()
    assert graph_result.conditions_written == 0

    after = _repo(seeded_database).expand_from_event("long_term_care", {})
    assert [item.item_id for item in after] == [item.item_id for item in before]


def test_foreign_keys_hold_after_seeding(seeded_database: Path) -> None:
    with closing(sqlite3.connect(seeded_database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == []


def test_edge_conditions_reference_registered_fields(
    seeded_database: Path,
) -> None:
    """邊條件用到的欄位一定要在題庫裡 —— 這是外鍵擋的，這裡確認它真的擋著。"""
    with closing(sqlite3.connect(seeded_database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        used = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT field_id FROM graph_edge_conditions"
            )
        }
        registered = {
            str(row[0])
            for row in connection.execute("SELECT field_id FROM field_registry")
        }
    assert used <= registered
    assert "has_completed_care_assessment" in used
