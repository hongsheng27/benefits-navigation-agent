"""Fetch long-term care pages using a headless browser (Playwright) for JS-rendered sites.

Usage (on EC2 or local Mac):
    pip install playwright boto3 psycopg[binary]
    python -m playwright install chromium --with-deps
    python scripts/fetch_ltc_rendered.py

This version renders JavaScript before capturing HTML content,
solving the problem of government sites that are SPAs.
"""

from __future__ import annotations

import hashlib
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[0] / ".." / "backend"))

try:
    import boto3
    import psycopg
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: Install dependencies:")
    print("  pip install playwright boto3 'psycopg[binary]'")
    print("  python -m playwright install chromium --with-deps")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

S3_BUCKET = "benefits-nav-documents-1251"
S3_PREFIX = "source_documents/"
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

# Same URL list as fetch_ltc_documents.py
LTC_URLS: list[tuple[str, str, str, str, str]] = [
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/mp-201.html",
     "benefit_page", "長照服務專線 1966 首頁"),
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/cp-6572-69919-207.html",
     "benefit_page", "長照十年計畫 2.0"),
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/cp-6533-70777-207.html",
     "application_page", "申請長照服務（含服務對象、CMS 等級、給付額度及部分負擔）"),
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/np-6449-207.html",
     "benefit_page", "長照服務項目總覽"),
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/cp-6451-69935-207.html",
     "benefit_page", "居家服務、日間照顧、家庭托顧及小規模多機能"),
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/lp-6457-207.html",
     "benefit_page", "住宿式機構服務"),
    ("mohw", "衛生福利部", "https://1966.gov.tw/LTC/np-6450-207.html",
     "benefit_page", "照顧、交通、輔具與喘息四大給付分類"),
    ("mohw", "衛生福利部", "https://www.mohw.gov.tw/cp-84-177-1.html",
     "benefit_page", "衛福部長照專區"),
    ("mohw", "衛生福利部社會及家庭署", "https://www.sfaa.gov.tw/sfaa/menus/5db",
     "benefit_page", "老人福利"),
    ("mohw", "衛生福利部社會及家庭署", "https://www.sfaa.gov.tw/sfaa/page/5e9",
     "benefit_page", "身心障礙福利簡介"),
    ("mol", "勞動部", "https://www.mol.gov.tw/1607/2458/2462/",
     "benefit_page", "勞動部外籍勞工專區"),
    ("mol", "勞動部", "https://www.wda.gov.tw/News_Content.aspx?n=C4D0B39B6E12E61F&sms=CDA642B408087F65&s=2B75C7B5B7036AFF",
     "benefit_page", "照顧服務員訓練"),
    ("vac", "國軍退除役官兵輔導委員會", "https://www.vac.gov.tw/cp-2088-5066-1.html",
     "benefit_page", "申請入住榮家資訊簡要表"),
    ("vac", "國軍退除役官兵輔導委員會", "https://www.vac.gov.tw/np-1897-1.html",
     "benefit_page", "就醫服務"),
    ("vac", "國軍退除役官兵輔導委員會", "https://www.vac.gov.tw/np-1898-1.html",
     "benefit_page", "就養服務"),
    ("mof", "財政部", "https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/individual-income-tax/exemption-scope/filling/Q93kjbx",
     "legal_text", "長照特別扣除額（每人每年 18 萬元）"),
    ("cip", "原住民族委員會", "https://www.cip.gov.tw/zh-tw/news/data-list/7661900BAFAAA37D/index.html?cumid=7661900BAFAAA37D",
     "benefit_page", "原住民族長照專區"),
    ("ndc", "國家發展委員會", "https://www.ndc.gov.tw/Content_List.aspx?n=2688C8F5935982DC",
     "benefit_page", "高齡化政策專區"),
]


def load_env() -> None:
    for env_path in [Path(__file__).resolve().parents[1] / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def get_pg_conninfo() -> str:
    host = os.environ.get("RDS_HOST", "")
    port = os.environ.get("RDS_PORT", "5432")
    database = os.environ.get("RDS_DATABASE", "benefits_navigation")
    username = os.environ.get("RDS_USERNAME", "benefits_admin")
    password = os.environ.get("RDS_PASSWORD", "")
    sslmode = os.environ.get("RDS_SSLMODE", "require")
    if not host:
        print("ERROR: RDS_HOST not set.")
        sys.exit(1)
    return (
        f"host={host} port={port} dbname={database} "
        f"user={username} password={password} sslmode={sslmode}"
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    load_env()

    print("=" * 60)
    print("Long-Term Care Document Fetcher (Rendered with Playwright)")
    print("=" * 60)

    s3 = boto3.client("s3", region_name=AWS_REGION)
    pg_conn = psycopg.connect(get_pg_conninfo())
    now = utc_now()

    success_count = 0
    skip_count = 0
    fail_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )

        for source_id, publisher, url, doc_type, title in LTC_URLS:
            print(f"\n  [{source_id}] {title}")

            # Check if already exists
            with pg_conn.cursor() as cur:
                cur.execute(
                    "SELECT document_id FROM source_documents WHERE canonical_url = %s",
                    (url,),
                )
                existing = cur.fetchone()

            if existing:
                # Re-fetch to update content (since previous fetch was JS-only)
                doc_id = existing[0]
                print(f"    Exists in DB ({doc_id[:8]}...), re-fetching rendered content...")
            else:
                doc_id = str(uuid.uuid4())

            # Navigate and wait for content to render
            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(2000)  # Extra 2s for lazy-loaded content
                rendered_html = page.content()
            except Exception as exc:
                print(f"    WARN: Failed to render {url}: {exc}")
                fail_count += 1
                continue

            content_bytes = rendered_html.encode("utf-8")
            doc_hash = content_hash(content_bytes)
            obj_key = f"{S3_PREFIX}{source_id}/{doc_id}.html"

            # Upload rendered HTML to S3
            try:
                s3.put_object(
                    Bucket=S3_BUCKET,
                    Key=obj_key,
                    Body=content_bytes,
                    ContentType="text/html; charset=utf-8",
                    Metadata={
                        "source_id": source_id,
                        "canonical_url": url,
                        "fetched_at": now,
                        "rendered": "true",
                    },
                )
                print(f"    → S3: {obj_key} ({len(content_bytes)} bytes)")
            except Exception as exc:
                print(f"    ERROR S3: {exc}")
                fail_count += 1
                continue

            # Upsert in RDS
            try:
                with pg_conn.cursor() as cur:
                    if existing:
                        cur.execute(
                            """
                            UPDATE source_documents
                            SET current_content_hash = %s,
                                storage_ref = %s,
                                retrieved_at = %s::TIMESTAMPTZ,
                                last_seen_at = %s::TIMESTAMPTZ,
                                review_status = 'candidate',
                                updated_at = %s::TIMESTAMPTZ
                            WHERE document_id = %s
                            """,
                            (doc_hash, obj_key, now, now, now, doc_id),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO source_documents (
                                document_id, canonical_url, title, document_type,
                                jurisdiction_code, publisher_name, publisher_oid,
                                current_content_hash, storage_ref, http_status,
                                first_seen_at, last_seen_at, retrieved_at,
                                review_status, simplified_script_detected,
                                created_at, updated_at
                            ) VALUES (
                                %s, %s, %s, %s,
                                'TW', %s, NULL,
                                %s, %s, 200,
                                %s::TIMESTAMPTZ, %s::TIMESTAMPTZ, %s::TIMESTAMPTZ,
                                'candidate', FALSE,
                                %s::TIMESTAMPTZ, %s::TIMESTAMPTZ
                            )
                            """,
                            (
                                doc_id, url, title, doc_type,
                                publisher, doc_hash, obj_key,
                                now, now, now, now, now,
                            ),
                        )
                pg_conn.commit()
                print(f"    → RDS: {doc_id[:8]}...")
                success_count += 1
            except Exception as exc:
                print(f"    ERROR RDS: {exc}")
                pg_conn.rollback()
                fail_count += 1

        browser.close()

    print(f"\n{'='*60}")
    print(f"Done: {success_count} rendered+stored, {skip_count} skipped, {fail_count} failed")
    print(f"{'='*60}")
    pg_conn.close()


if __name__ == "__main__":
    main()
