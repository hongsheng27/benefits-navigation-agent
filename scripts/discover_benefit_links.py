"""List child-link candidates from the two reviewed benefit entry pages."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.services.link_discovery import (
    LinkCandidate,
    discover_links,
    load_discovery_terms,
)
from scripts.import_government_oid import DEFAULT_DATABASE_PATH

DEFAULT_SOURCE_IDS = ("my_egov", "taipei_funeral_services")
DEFAULT_DICTIONARY_PATH = (
    REPO_ROOT / "data" / "benefit_discovery" / "death_benefit_keywords.v0.2.json"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "data" / "local" / "discovered_links" / "first_round.json"
)


def _load_entry_document(
    connection: sqlite3.Connection,
    source_id: str,
) -> tuple[str, Path]:
    row = connection.execute(
        """
        SELECT d.canonical_url, d.storage_ref
        FROM source_registry AS r
        JOIN document_discoveries AS x
          ON x.source_id = r.source_id
        JOIN source_documents AS d
          ON d.document_id = x.document_id
        WHERE r.source_id = ?
          AND x.discovery_method = 'entry_page'
          AND d.storage_ref IS NOT NULL
        ORDER BY d.retrieved_at DESC
        LIMIT 1
        """,
        (source_id,),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"No fetched entry page found for source_id: {source_id}. "
            "Run scripts/sync_benefit_sources.py first."
        )
    return str(row[0]), Path(row[1])


def discover_registered_source_links(
    database_path: Path,
    source_ids: tuple[str, ...],
    dictionary_path: Path,
) -> list[LinkCandidate]:
    discovery_terms = load_discovery_terms(dictionary_path)
    candidates: list[LinkCandidate] = []
    with sqlite3.connect(database_path) as connection:
        for source_id in source_ids:
            source_page_url, storage_path = _load_entry_document(
                connection,
                source_id,
            )
            html = storage_path.read_text(encoding="utf-8", errors="replace")
            candidates.extend(
                discover_links(
                    html,
                    source_id=source_id,
                    source_page_url=source_page_url,
                    discovery_terms=discovery_terms,
                )
            )
    return candidates


def write_candidate_report(
    output_path: Path,
    candidates: list[LinkCandidate],
) -> None:
    source_counts = Counter(candidate.source_id for candidate in candidates)
    priority_counts = Counter(candidate.priority for candidate in candidates)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "method": "main_content_links_only",
            "content_element_id": "CCMS_Content",
            "downloaded_child_pages": False,
            "used_ai": False,
        },
        "summary": {
            "candidate_count": len(candidates),
            "official_host_count": sum(
                candidate.official_host for candidate in candidates
            ),
            "source_counts": dict(sorted(source_counts.items())),
            "priority_counts": {
                priority: priority_counts.get(priority, 0)
                for priority in ("high", "medium", "review")
            },
        },
        "candidates": [candidate.as_json() for candidate in candidates],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract links from the main content of already downloaded entry "
            "pages. This command does not download child pages or call AI."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help=f"SQLite database path (default: {DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=DEFAULT_SOURCE_IDS,
        help="Source to inspect; repeat to inspect more than one source.",
    )
    parser.add_argument(
        "--dictionary",
        type=Path,
        default=DEFAULT_DICTIONARY_PATH,
        help=f"Discovery dictionary (default: {DEFAULT_DICTIONARY_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"Candidate report path (default: {DEFAULT_OUTPUT_PATH})",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    source_ids = tuple(args.source or DEFAULT_SOURCE_IDS)
    try:
        candidates = discover_registered_source_links(
            args.database,
            source_ids,
            args.dictionary,
        )
        write_candidate_report(args.output, candidates)
    except (OSError, ValueError, sqlite3.Error, json.JSONDecodeError) as exc:
        parser.exit(1, f"Link discovery failed: {exc}\n")

    source_counts = Counter(candidate.source_id for candidate in candidates)
    priority_counts = Counter(candidate.priority for candidate in candidates)
    print(f"Candidate report: {args.output}")
    print(f"Total links: {len(candidates)}")
    print(
        "Official hosts: "
        f"{sum(candidate.official_host for candidate in candidates)}"
    )
    for source_id in source_ids:
        print(f"{source_id}: {source_counts.get(source_id, 0)}")
    print(
        "Priorities: "
        f"high={priority_counts.get('high', 0)}, "
        f"medium={priority_counts.get('medium', 0)}, "
        f"review={priority_counts.get('review', 0)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
