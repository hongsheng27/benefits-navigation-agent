"""Fetch long-term care (長照) related pages from government agencies and store to S3 + RDS.

Usage:
    # From EC2 (with IAM role or AWS credentials configured):
    python3.13 scripts/fetch_ltc_documents.py

    # Dry run (shows URLs without fetching):
    python3.13 scripts/fetch_ltc_documents.py --dry-run

This script:
1. Fetches HTML pages from known long-term care URLs on official government sites.
2. Uploads raw HTML to S3 (benefits-nav-documents-1251/source_documents/).
3. Records metadata in RDS source_documents table.

Prerequisites:
- AWS credentials configured (EC2 instance role or environment variables)
- RDS environment variables set (RDS_HOST, RDS_PASSWORD, etc.)
- S3 bucket exists: benefits-nav-documents-1251
"""

from __future__ import annotations

import hashlib
import os
import ssl
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[0] / ".." / "backend"))

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg not installed. Run: pip install 'psycopg[binary]'")
    sys.exit(1)

try:
    import boto3
except ImportError:
    print("ERROR: boto3 not installed. Run: pip install boto3")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

S3_BUCKET = "benefits-nav-documents-1251"
S3_PREFIX = "source_documents/"
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")

# Long-term care related URLs to fetch from each agency.
# Format: (source_id, publisher_name, url, document_type, title_hint)
LTC_URLS: list[tuple[str, str, str, str, str]] = [
    # 衛生福利部 1966 長照專區
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

    # 衛生福利部社會及家庭署
    ("mohw", "衛生福利部社會及家庭署", "https://www.sfaa.gov.tw/sfaa/menus/5db",
     "benefit_page", "老人福利"),
    ("mohw", "衛生福利部社會及家庭署", "https://www.sfaa.gov.tw/sfaa/page/5e9",
     "benefit_page", "身心障礙福利簡介"),

    # 勞動部 — 外籍看護、長照相關勞動政策
    ("mol", "勞動部", "https://www.mol.gov.tw/1607/2458/2462/",
     "benefit_page", "勞動部外籍勞工專區"),
    ("mol", "勞動部", "https://www.wda.gov.tw/News_Content.aspx?n=C4D0B39B6E12E61F&sms=CDA642B408087F65&s=2B75C7B5B7036AFF",
     "benefit_page", "照顧服務員訓練"),

    # 退輔會 — 榮民長照
    ("vac", "國軍退除役官兵輔導委員會", "https://www.vac.gov.tw/cp-2088-5066-1.html",
     "benefit_page", "申請入住榮家資訊簡要表"),
    ("vac", "國軍退除役官兵輔導委員會", "https://www.vac.gov.tw/np-1897-1.html",
     "benefit_page", "就醫服務"),
    ("vac", "國軍退除役官兵輔導委員會", "https://www.vac.gov.tw/np-1898-1.html",
     "benefit_page", "就養服務"),

    # 財政部 — 長照特別扣除額
    ("mof", "財政部", "https://www.etax.nat.gov.tw/etwmain/tax-info/understanding/tax-q-and-a/national/individual-income-tax/exemption-scope/filling/Q93kjbx",
     "legal_text", "長照特別扣除額（每人每年 18 萬元）"),

    # 原民會 — 原住民族長照
    ("cip", "原住民族委員會", "https://www.cip.gov.tw/zh-tw/news/data-list/7661900BAFAAA37D/index.html?cumid=7661900BAFAAA37D",
     "benefit_page", "原住民族長照專區"),

    # 國發會 — 高齡化對策
    ("ndc", "國家發展委員會", "https://www.ndc.gov.tw/Content_List.aspx?n=2688C8F5935982DC",
     "benefit_page", "高齡化政策專區"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env() -> None:
    """Load .env file if it exists."""
    for env_path in [Path(__file__).resolve().parents[1] / ".env",
                     Path(__file__).resolve().parents[1] / "backend" / ".env"]:
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


def fetch_page(url: str) -> tuple[bytes, int]:
    """Fetch a URL and return (content_bytes, http_status).

    Uses relaxed SSL verification because many Taiwan government sites
    have non-standard certificate configurations.

    First tries direct fetch. If content is too short (likely JS-rendered),
    tries using curl with redirect following.
    """
    ctx = ssl.create_default_context()
    # Taiwan government sites often have certificate chain issues
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    try:
        with urlopen(req, timeout=30, context=ctx) as resp:
            content = resp.read()
            return content, resp.status
    except Exception as exc:
        print(f"    WARN: Failed to fetch {url}: {exc}")
        return b"", 0


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def s3_key(source_id: str, document_id: str) -> str:
    """Build an opaque S3 key for a document."""
    return f"{S3_PREFIX}{source_id}/{document_id}.html"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_env()

    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("Long-Term Care Document Fetcher")
    print(f"Target: S3 bucket={S3_BUCKET}, RDS={os.environ.get('RDS_HOST', '?')}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("=" * 60)

    if dry_run:
        print(f"\n{len(LTC_URLS)} URLs to fetch:")
        for source_id, publisher, url, doc_type, title in LTC_URLS:
            print(f"  [{source_id}] {title}")
            print(f"    {url}")
        print("\nRe-run without --dry-run to execute.")
        return

    # Connect to S3
    print("\n[1/3] Connecting to S3...")
    s3 = boto3.client("s3", region_name=AWS_REGION)

    # Connect to RDS
    print("[2/3] Connecting to RDS...")
    pg_conn = psycopg.connect(get_pg_conninfo())

    # Fetch and store
    print(f"[3/3] Fetching {len(LTC_URLS)} pages...\n")
    now = utc_now()
    success_count = 0
    skip_count = 0
    fail_count = 0

    for source_id, publisher, url, doc_type, title in LTC_URLS:
        print(f"  [{source_id}] {title}")

        # Check if already exists in RDS
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT document_id FROM source_documents WHERE canonical_url = %s",
                (url,),
            )
            existing = cur.fetchone()
            if existing:
                print(f"    → Already in DB, skipping.")
                skip_count += 1
                continue

        # Fetch
        print(f"    Fetching: {url[:80]}...")
        content, http_status = fetch_page(url)
        if not content:
            fail_count += 1
            continue

        doc_id = str(uuid.uuid4())
        doc_hash = content_hash(content)
        obj_key = s3_key(source_id, doc_id)

        # Upload to S3
        try:
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=obj_key,
                Body=content,
                ContentType="text/html",
                Metadata={
                    "source_id": source_id,
                    "canonical_url": url,
                    "fetched_at": now,
                },
            )
            print(f"    → S3: s3://{S3_BUCKET}/{obj_key}")
        except Exception as exc:
            print(f"    ERROR uploading to S3: {exc}")
            fail_count += 1
            continue

        # Record in RDS
        try:
            with pg_conn.cursor() as cur:
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
                        %s, %s, %s,
                        %s::TIMESTAMPTZ, %s::TIMESTAMPTZ, %s::TIMESTAMPTZ,
                        'candidate', FALSE,
                        %s::TIMESTAMPTZ, %s::TIMESTAMPTZ
                    )
                    """,
                    (
                        doc_id, url, title, doc_type,
                        publisher, doc_hash, obj_key, http_status,
                        now, now, now, now, now,
                    ),
                )
            pg_conn.commit()
            print(f"    → RDS: document_id={doc_id[:8]}...")
            success_count += 1
        except Exception as exc:
            print(f"    ERROR inserting to RDS: {exc}")
            pg_conn.rollback()
            fail_count += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"Done: {success_count} fetched, {skip_count} skipped, {fail_count} failed")
    print("=" * 60)

    pg_conn.close()


if __name__ == "__main__":
    main()
