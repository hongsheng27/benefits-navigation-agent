"""把事件關係圖 JSON 寫進 SQLite 的 graph_nodes / graph_edges / graph_edge_conditions。

## 執行順序有硬性相依

`graph_edge_conditions.field_id` 以外鍵指向 `field_registry`，`graph_nodes.program_id`
指向 `benefit_programs`。所以：

    1. uv run python scripts/seed_field_registry.py     ← 先跑這支
    2. uv run python scripts/seed_entitlement_graph.py  ← 才跑這支

順序反了會直接被外鍵擋下來 —— 這是好事，總比寫進一個指向不存在欄位的條件好。

## 為什麼方案列也在這裡建

`graph_nodes` 的 benefit_program 節點需要一筆對應的 `benefit_programs`。這支腳本會
把 JSON 裡宣告的方案補上，狀態一律 `candidate`、所有事實欄位留空 —— 沒有人審過的
數字不該存在（Req 15.2）。已經存在的方案不會被覆寫。

## 為什麼是 upsert 而不是砍掉重建

邊與節點都被 `ON DELETE RESTRICT` 保護。刪一條邊等於改變「哪些項目會出現」，那是
需要審查的變動，不是重跑腳本的副作用。這支腳本只新增與更新，不刪除；JSON 裡消失
的邊會被列出來提醒，但留在資料庫裡。

## 用法

    uv run python scripts/seed_entitlement_graph.py --dry-run
    uv run python scripts/seed_entitlement_graph.py --database data/local/xxx.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_GRAPH_PATH = REPO_ROOT / "data" / "entitlement_graph" / "graph.v0.1.json"
DEFAULT_DATABASE_PATH = REPO_ROOT / "data" / "local" / "government_oid.db"

# 與 migration 0003 的 CHECK 一致。寫在這裡是為了在碰資料庫之前就擋掉打錯的值。
NODE_TYPES = frozenset(
    {
        "life_event",
        "insurance_system",
        "benefit_program",
        "agency",
        "document_requirement",
    }
)
EDGE_TYPES = frozenset(
    {"triggers", "belongs_to", "requires", "produces", "administered_by"}
)
# 展開時方案必須是這幾種狀態才看得到（見 graph_repository._VISIBLE_STATUSES）。
SEEDABLE_PROGRAM_STATUSES = frozenset({"candidate", "under_review"})


@dataclass(frozen=True, slots=True)
class GraphSeedResult:
    """一次 seed 做了什麼。"""

    programs_inserted: tuple[str, ...] = ()
    nodes_inserted: tuple[str, ...] = ()
    nodes_updated: tuple[str, ...] = ()
    edges_inserted: tuple[str, ...] = ()
    edges_updated: tuple[str, ...] = ()
    conditions_written: int = 0
    orphan_edges: tuple[str, ...] = ()


@dataclass(slots=True)
class _Graph:
    """JSON 讀進來之後的形狀。"""

    programs: list[dict] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)


def load_graph(path: Path) -> _Graph:
    """讀 JSON 並做結構檢查。錯誤在這裡就爆，不留到寫資料庫的時候。"""
    raw = json.loads(path.read_text(encoding="utf-8"))
    graph = _Graph(
        programs=list(raw.get("programs", [])),
        nodes=list(raw.get("nodes", [])),
        edges=list(raw.get("edges", [])),
    )
    _validate(graph)
    return graph


def _validate(graph: _Graph) -> None:
    node_ids = {node["node_id"] for node in graph.nodes}
    program_ids = {program["program_id"] for program in graph.programs}

    if len(node_ids) != len(graph.nodes):
        raise ValueError("node_id 重複")

    for program in graph.programs:
        status = program.get("program_status", "candidate")
        if status not in SEEDABLE_PROGRAM_STATUSES:
            raise ValueError(
                f"方案 {program['program_id']} 的狀態是 {status!r}。"
                f"seed 只能建立 {sorted(SEEDABLE_PROGRAM_STATUSES)} —— "
                "升級成 verified 必須經人工審查。"
            )

    for node in graph.nodes:
        if node["node_type"] not in NODE_TYPES:
            raise ValueError(f"未知的 node_type: {node['node_type']!r}")
        is_program = node["node_type"] == "benefit_program"
        has_program_id = node.get("program_id") is not None
        if is_program != has_program_id:
            raise ValueError(
                f"節點 {node['node_id']}：benefit_program 必須帶 program_id，"
                "其他型別必須留 null"
            )
        if has_program_id and node["program_id"] not in program_ids:
            # 允許指向 JSON 沒宣告、但資料庫已存在的方案；這裡只提醒。
            print(
                f"  ⚠ 節點 {node['node_id']} 指向 {node['program_id']}，"
                "但這份 JSON 沒有宣告它。假設資料庫裡已經有了。"
            )

    edge_ids: set[str] = set()
    for edge in graph.edges:
        if edge["edge_type"] not in EDGE_TYPES:
            raise ValueError(f"未知的 edge_type: {edge['edge_type']!r}")
        if edge["edge_id"] in edge_ids:
            raise ValueError(f"edge_id 重複: {edge['edge_id']}")
        edge_ids.add(edge["edge_id"])
        for endpoint in ("from_node_id", "to_node_id"):
            if edge[endpoint] not in node_ids:
                raise ValueError(
                    f"邊 {edge['edge_id']} 的 {endpoint} 指向未定義的節點 "
                    f"{edge[endpoint]!r}"
                )
        for condition in edge.get("conditions", []):
            if not condition.get("expected_value_json"):
                raise ValueError(
                    f"邊 {edge['edge_id']} 的條件 {condition['condition_id']} "
                    "缺 expected_value_json"
                )
            json.loads(condition["expected_value_json"])  # 格式錯就爆


def seed(connection: sqlite3.Connection, graph: _Graph) -> GraphSeedResult:
    """寫入資料庫。回傳這次做了什麼。"""
    now = datetime.now(UTC).isoformat()
    programs_inserted = _seed_programs(connection, graph, now)
    nodes_inserted, nodes_updated = _seed_nodes(connection, graph)
    edges_inserted, edges_updated, conditions = _seed_edges(connection, graph)

    known_edge_ids = {edge["edge_id"] for edge in graph.edges}
    stored_edge_ids = {
        str(row[0]) for row in connection.execute("SELECT edge_id FROM graph_edges")
    }
    orphans = tuple(sorted(stored_edge_ids - known_edge_ids))

    return GraphSeedResult(
        programs_inserted=programs_inserted,
        nodes_inserted=nodes_inserted,
        nodes_updated=nodes_updated,
        edges_inserted=edges_inserted,
        edges_updated=edges_updated,
        conditions_written=conditions,
        orphan_edges=orphans,
    )


def _seed_programs(
    connection: sqlite3.Connection, graph: _Graph, now: str
) -> tuple[str, ...]:
    inserted: list[str] = []
    for program in graph.programs:
        program_id = program["program_id"]
        existing = connection.execute(
            "SELECT program_id FROM benefit_programs WHERE program_id = ?",
            (program_id,),
        ).fetchone()
        if existing is not None:
            # 已經存在就不動。方案內容的變更要走審查，不是 seed 的工作。
            continue
        connection.execute(
            """
            INSERT INTO benefit_programs (
                program_id, canonical_name, program_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                program_id,
                program["canonical_name"],
                program.get("program_status", "candidate"),
                now,
                now,
            ),
        )
        inserted.append(program_id)
    return tuple(inserted)


def _seed_nodes(
    connection: sqlite3.Connection, graph: _Graph
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    inserted: list[str] = []
    updated: list[str] = []
    for node in graph.nodes:
        row = (node["node_type"], node["display_name"], node.get("program_id"))
        existing = connection.execute(
            "SELECT node_type, display_name, program_id FROM graph_nodes "
            "WHERE node_id = ?",
            (node["node_id"],),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO graph_nodes (
                    node_id, node_type, display_name, program_id
                ) VALUES (?, ?, ?, ?)
                """,
                (node["node_id"], *row),
            )
            inserted.append(node["node_id"])
            continue

        if tuple(existing) == row:
            continue
        if str(existing[0]) != row[0]:
            raise ValueError(
                f"節點 {node['node_id']} 的 node_type 從 {existing[0]!r} 變成 "
                f"{row[0]!r}。改型別會改變展開行為，請走審查流程。"
            )
        connection.execute(
            "UPDATE graph_nodes SET display_name = ?, program_id = ? WHERE node_id = ?",
            (row[1], row[2], node["node_id"]),
        )
        updated.append(node["node_id"])
    return tuple(inserted), tuple(updated)


def _seed_edges(
    connection: sqlite3.Connection, graph: _Graph
) -> tuple[tuple[str, ...], tuple[str, ...], int]:
    inserted: list[str] = []
    updated: list[str] = []
    conditions_written = 0

    for edge in graph.edges:
        row = (
            edge["from_node_id"],
            edge["to_node_id"],
            edge["edge_type"],
            int(edge.get("canonical_order", 0)),
        )
        existing = connection.execute(
            "SELECT from_node_id, to_node_id, edge_type, canonical_order "
            "FROM graph_edges WHERE edge_id = ?",
            (edge["edge_id"],),
        ).fetchone()

        if existing is None:
            connection.execute(
                """
                INSERT INTO graph_edges (
                    edge_id, from_node_id, to_node_id, edge_type, canonical_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (edge["edge_id"], *row),
            )
            inserted.append(edge["edge_id"])
        elif tuple(existing) != row:
            if tuple(existing)[:3] != row[:3]:
                raise ValueError(
                    f"邊 {edge['edge_id']} 的端點或型別改變了。那等於換一條邊，"
                    "請用新的 edge_id 並走審查流程。"
                )
            connection.execute(
                "UPDATE graph_edges SET canonical_order = ? WHERE edge_id = ?",
                (row[3], edge["edge_id"]),
            )
            updated.append(edge["edge_id"])

        conditions_written += _seed_conditions(connection, edge)

    return tuple(inserted), tuple(updated), conditions_written


def _seed_conditions(connection: sqlite3.Connection, edge: dict) -> int:
    """同步一條邊的條件。條件是「哪些項目會出現」的一部分，所以不刪除。"""
    written = 0
    for condition in edge.get("conditions", []):
        existing = connection.execute(
            "SELECT 1 FROM graph_edge_conditions WHERE edge_id = ? "
            "AND condition_id = ?",
            (edge["edge_id"], condition["condition_id"]),
        ).fetchone()
        if existing is not None:
            continue
        connection.execute(
            """
            INSERT INTO graph_edge_conditions (
                edge_id, condition_id, field_id, operator,
                expected_value_type, expected_value_json, condition_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                edge["edge_id"],
                condition["condition_id"],
                condition["field_id"],
                condition["operator"],
                condition["expected_value_type"],
                condition["expected_value_json"],
                int(condition.get("condition_order", 0)),
            ),
        )
        written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH_PATH)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只讀 JSON 並檢查結構，不碰資料庫",
    )
    args = parser.parse_args()

    graph = load_graph(args.graph)
    print(f"讀到關係圖：{args.graph}")
    print(
        f"  方案 {len(graph.programs)}、節點 {len(graph.nodes)}、邊 {len(graph.edges)}"
    )
    for node in graph.nodes:
        print(f"    [{node['node_type']:18s}] {node['node_id']}")
    for edge in graph.edges:
        conditions = edge.get("conditions", [])
        suffix = f"（{len(conditions)} 個條件）" if conditions else ""
        print(
            f"    {edge['from_node_id']} --{edge['edge_type']}--> "
            f"{edge['to_node_id']} {suffix}"
        )

    if args.dry_run:
        print("\n--dry-run：結構檢查通過，沒有寫入任何東西。")
        return 0

    if not args.database.exists():
        print(f"資料庫不存在：{args.database}", file=sys.stderr)
        return 1

    with closing(sqlite3.connect(args.database)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            result = seed(connection, graph)
        except Exception:
            connection.rollback()
            raise
        connection.commit()

    print(
        f"\n✓ 方案新增 {len(result.programs_inserted)}、"
        f"節點新增 {len(result.nodes_inserted)}／更新 {len(result.nodes_updated)}、"
        f"邊新增 {len(result.edges_inserted)}／更新 {len(result.edges_updated)}、"
        f"條件寫入 {result.conditions_written}。"
    )
    if result.orphan_edges:
        print(
            f"  ⚠ 資料庫裡有 JSON 沒宣告的邊：{list(result.orphan_edges)}\n"
            "    腳本不會刪除它們。刪邊會改變哪些項目會出現，請走審查流程。"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
