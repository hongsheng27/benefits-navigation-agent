"""Analyze fetched documents with Bedrock Claude and populate RDS.

Usage:
    python3.13 scripts/analyze_documents.py

This script:
1. Reads unanalyzed documents from RDS (review_status='candidate').
2. Fetches HTML content from S3.
3. Detects and downloads attachments (PDF links) to S3.
4. Calls Bedrock Claude Sonnet 4 to extract structured benefit information.
5. Writes extracted programs, rules, fields, and graph edges to RDS.

All extracted data is marked 'candidate' (unverified) until human review.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[0] / ".." / "backend"))

try:
    import boto3
    import psycopg
except ImportError:
    print("ERROR: Install dependencies: pip install boto3 'psycopg[binary]'")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

S3_BUCKET = "benefits-nav-documents-1251"
S3_PREFIX = "source_documents/"
S3_ATTACHMENT_PREFIX = "attachments/"
AWS_REGION = os.environ.get("AWS_REGION", "us-west-2")
BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
MAX_HTML_CHARS = 80000  # Truncate HTML to fit context window

# Life events we currently support
KNOWN_LIFE_EVENTS = [
    "long_term_care",
    "death_of_family_member",
    "disability",
    "retirement",
    "childbirth",
    "unemployment",
]

ANALYSIS_PROMPT = """你是一個台灣社會福利資料分析專家。請分析以下政府官方網頁內容，並萃取出所有可辨識的福利方案或行政服務。

請用以下 JSON 格式回答。如果頁面內容不包含具體的福利方案（例如只是一般性政策說明或目錄頁），回傳空的 programs 陣列即可。

```json
{
  "programs": [
    {
      "canonical_name": "方案的正式名稱",
      "summary": "一句話描述這個方案",
      "life_event": "對應的人生事件代號（從已知清單選）",
      "support_purpose": "支持目的（選一）",
      "program_basis": "方案法律基礎（選一）",
      "delivery_form": "給付形式（選一）",
      "responsible_agency": "主管機關名稱",
      "eligibility_rules": {
        "type": "all_of 或 any_of",
        "conditions": [
          {
            "field_id": "欄位代號（英文 snake_case）",
            "field_label": "欄位中文名稱",
            "data_type": "integer/boolean/enum/text/date",
            "operator": ">=, <=, ==, !=, in, not_in",
            "value": "期望值",
            "source_text": "原文依據（引用頁面原文）"
          }
        ]
      },
      "amount": {
        "min": null,
        "max": null,
        "period": "monthly/yearly/once",
        "currency": "TWD",
        "description": "金額描述"
      },
      "application_method": "申請方式描述",
      "required_documents": ["需要的文件清單"],
      "source_excerpts": ["引用的關鍵原文段落（每段限 200 字內）"]
    }
  ],
  "detected_attachments": [
    {
      "url": "附件的完整 URL",
      "filename": "檔名",
      "description": "附件內容描述"
    }
  ]
}
```

可用的 life_event 代號：
- long_term_care（長期照顧需求）
- death_of_family_member（親人過世）
- disability（身心障礙）
- retirement（退休）
- childbirth（生育）
- unemployment（失業）

support_purpose 可選值：
- funeral_cost, one_time_death_support, survivor_livelihood
- care_subsidy, medical_subsidy, living_allowance
- tax_deduction, service_provision, training_subsidy

program_basis 可選值：
- government_subsidy_or_relief, social_assistance, social_insurance
- survivor_pension_or_pension, legal_compensation
- employer_statutory_payment, other_or_unknown

delivery_form 可選值：
- cash_once, cash_recurring, reimbursement
- fee_waiver, service_or_in_kind, unknown

重要規則：
1. 只萃取**明確記載在頁面上的資訊**，不要推測或補充。
2. 如果金額不明確，amount 的 min/max 設為 null。
3. eligibility_rules 只放頁面上明確寫出的條件。
4. field_id 用英文 snake_case（例如 age, cms_level, has_tw_residency）。
5. 如果頁面是目錄頁或概述頁，沒有具體方案，回傳空 programs 陣列。
6. detected_attachments 列出頁面中所有 PDF/DOCX 附件連結。

以下是要分析的頁面內容：

來源機關：{publisher_name}
頁面標題：{title}
頁面網址：{url}

---
{content}
---

請直接回傳 JSON，不要加 markdown code block。"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env() -> None:
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


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def strip_html_tags(html: str) -> str:
    """Very basic HTML to text conversion."""
    # Remove script/style
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Replace common tags with spaces/newlines
    html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</(p|div|tr|li|h[1-6])>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<[^>]+>', ' ', html)
    # Clean up whitespace
    html = re.sub(r'[ \t]+', ' ', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


def call_bedrock(bedrock_client, content: str, publisher_name: str, title: str, url: str) -> dict:
    """Call Bedrock Claude to analyze document content."""
    # Truncate content if too long
    if len(content) > MAX_HTML_CHARS:
        content = content[:MAX_HTML_CHARS] + "\n\n[... 內容已截斷 ...]"

    prompt = ANALYSIS_PROMPT.format(
        publisher_name=publisher_name,
        title=title,
        url=url,
        content=content,
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    })

    response = bedrock_client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body.encode(),
    )

    raw_bytes = response["body"].read()
    response_body = json.loads(raw_bytes)
    text = response_body["content"][0]["text"]

    # Parse JSON from response
    text = text.strip()
    # Remove markdown code blocks if present
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
    # Find the JSON object boundaries
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        text = text[first_brace:last_brace + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"    WARN: JSON parse error: {e}")
        print(f"    Raw response (first 300 chars): {text[:300]}")
        return {"programs": [], "detected_attachments": []}


def download_attachment(url: str, s3_client, source_id: str) -> tuple[str, str, int] | None:
    """Download an attachment and upload to S3. Returns (s3_key, hash, size) or None."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
    })
    try:
        with urlopen(req, timeout=30, context=ctx) as resp:
            content = resp.read()
    except Exception as exc:
        print(f"    WARN: Failed to download attachment {url}: {exc}")
        return None

    if not content:
        return None

    file_hash = hashlib.sha256(content).hexdigest()
    # Extract filename from URL
    filename = url.split("/")[-1].split("?")[0] or "attachment"
    att_id = str(uuid.uuid4())
    s3_key = f"{S3_ATTACHMENT_PREFIX}{source_id}/{att_id}_{filename}"

    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            Metadata={"source_url": url, "fetched_at": utc_now()},
        )
        return s3_key, file_hash, len(content)
    except Exception as exc:
        print(f"    WARN: Failed to upload attachment to S3: {exc}")
        return None


def write_program_to_rds(
    conn: psycopg.Connection,
    program: dict,
    document_id: str,
    source_id: str,
) -> str | None:
    """Write an extracted program and its rules/fields to RDS. Returns program_id."""
    now = utc_now()
    program_id = str(uuid.uuid4())

    canonical_name = program.get("canonical_name", "")
    if not canonical_name:
        return None

    # Insert benefit_programs
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO benefit_programs (
                    program_id, canonical_name, summary, support_purpose,
                    program_basis, delivery_form, jurisdiction_code,
                    program_status, status_note,
                    expense_proof_requirement,
                    claimant_rule_text, deadline_rule_text, mutual_exclusion_text,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, 'TW',
                    'candidate', 'Auto-extracted by Bedrock, pending review',
                    'unknown', '', '', '',
                    %s::TIMESTAMPTZ, %s::TIMESTAMPTZ
                )
                ON CONFLICT DO NOTHING
                """,
                (
                    program_id,
                    canonical_name,
                    program.get("summary", ""),
                    program.get("support_purpose"),
                    program.get("program_basis"),
                    program.get("delivery_form"),
                    now, now,
                ),
            )

            # Insert graph node for this program
            node_id = f"prog_{program_id[:8]}"
            cur.execute(
                """
                INSERT INTO graph_nodes (node_id, node_type, display_name, program_id)
                VALUES (%s, 'benefit_program', %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (node_id, canonical_name, program_id),
            )

            # Insert graph edge from life event to program
            life_event = program.get("life_event", "long_term_care")
            if life_event in KNOWN_LIFE_EVENTS:
                edge_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO graph_edges (edge_id, from_node_id, to_node_id, edge_type, canonical_order)
                    SELECT %s, %s, %s, 'triggers', COALESCE(MAX(canonical_order), 0) + 1
                    FROM graph_edges WHERE from_node_id = %s AND edge_type = 'triggers'
                    ON CONFLICT DO NOTHING
                    """,
                    (edge_id, life_event, node_id, life_event),
                )

            # Insert field_registry entries and rule structure
            rules = program.get("eligibility_rules", {})
            conditions = rules.get("conditions", [])

            if conditions:
                # Create rule definition
                rule_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO rule_definitions (rule_id, program_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (rule_id, program_id),
                )

                # Create rule version
                rule_version_id = str(uuid.uuid4())
                root_node_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO rule_versions (
                        rule_version_id, rule_id, version, dsl_version,
                        approval_status, is_current, root_node_id, created_at
                    ) VALUES (%s, %s, '1.0', '1', 'candidate', FALSE, %s, %s::TIMESTAMPTZ)
                    ON CONFLICT DO NOTHING
                    """,
                    (rule_version_id, rule_id, root_node_id, now),
                )

                # Create root node (all_of or any_of)
                rule_type = rules.get("type", "all_of")
                if rule_type not in ("all_of", "any_of"):
                    rule_type = "all_of"
                cur.execute(
                    """
                    INSERT INTO rule_nodes (node_id, rule_version_id, parent_node_id, node_type, child_order)
                    VALUES (%s, %s, NULL, %s, 0)
                    ON CONFLICT DO NOTHING
                    """,
                    (root_node_id, rule_version_id, rule_type),
                )

                # Create condition nodes and field registry entries
                for i, cond in enumerate(conditions):
                    field_id = cond.get("field_id", f"field_{i}")
                    field_label = cond.get("field_label", field_id)
                    data_type = cond.get("data_type", "text")
                    if data_type not in ("text", "integer", "number", "boolean", "date", "enum"):
                        data_type = "text"

                    # Ensure field exists in registry
                    cur.execute(
                        """
                        INSERT INTO field_registry (field_id, data_type, prompt_label, why_needed, pii_classification, active)
                        VALUES (%s, %s, %s, %s, 'none', TRUE)
                        ON CONFLICT (field_id) DO NOTHING
                        """,
                        (field_id, data_type, field_label,
                         f"判斷 {canonical_name} 資格所需"),
                    )

                    # Create condition node
                    cond_node_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO rule_nodes (node_id, rule_version_id, parent_node_id, node_type, child_order)
                        VALUES (%s, %s, %s, 'condition', %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (cond_node_id, rule_version_id, root_node_id, i),
                    )

                    # Create condition details
                    operator = cond.get("operator", "==")
                    value = cond.get("value", "")
                    source_text = cond.get("source_text", "")
                    expected_json = json.dumps(value, ensure_ascii=False)

                    # Determine expected_value_type
                    if isinstance(value, bool):
                        evt = "boolean"
                    elif isinstance(value, int):
                        evt = "integer"
                    elif isinstance(value, float):
                        evt = "number"
                    else:
                        evt = "string"

                    cond_id = str(uuid.uuid4())
                    cur.execute(
                        """
                        INSERT INTO rule_conditions (
                            condition_id, node_id, field_id, operator,
                            expected_value_type, expected_value_json,
                            label, source_reference
                        ) VALUES (%s, %s, %s, %s, %s, %s::JSONB, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            cond_id, cond_node_id, field_id, operator,
                            evt, expected_json,
                            field_label, source_text or "auto-extracted",
                        ),
                    )

                    # Add to required fields
                    cur.execute(
                        """
                        INSERT INTO rule_required_fields (rule_version_id, field_id, canonical_order)
                        VALUES (%s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (rule_version_id, field_id, i),
                    )

            # Link document as evidence
            evidence_id = str(uuid.uuid4())
            excerpts = program.get("source_excerpts", [])
            excerpt_text = "\n".join(excerpts[:3])  # First 3 excerpts

            cur.execute(
                """
                INSERT INTO evidence_excerpts (
                    evidence_id, document_id, excerpt, review_status, created_at, updated_at
                ) VALUES (%s, %s, %s, 'candidate', %s::TIMESTAMPTZ, %s::TIMESTAMPTZ)
                ON CONFLICT DO NOTHING
                """,
                (evidence_id, document_id, excerpt_text, now, now),
            )

            cur.execute(
                """
                INSERT INTO program_evidence_links (program_id, evidence_id, evidence_role, review_status)
                VALUES (%s, %s, 'discovery', 'candidate')
                ON CONFLICT DO NOTHING
                """,
                (program_id, evidence_id),
            )

        conn.commit()
        return program_id

    except Exception as exc:
        print(f"    ERROR writing program to RDS: {exc}")
        conn.rollback()
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    load_env()

    print("=" * 60)
    print("Document Analysis Pipeline (Bedrock Claude Sonnet 4)")
    print(f"Model: {BEDROCK_MODEL_ID}")
    print("=" * 60)

    # Connect
    s3 = boto3.client("s3", region_name=AWS_REGION)
    bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
    pg_conn = psycopg.connect(get_pg_conninfo())

    # Get unanalyzed documents
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_id, canonical_url, title, publisher_name, storage_ref
            FROM source_documents
            WHERE review_status = 'candidate'
              AND storage_ref IS NOT NULL
            ORDER BY created_at
            """
        )
        documents = cur.fetchall()

    print(f"\nFound {len(documents)} documents to analyze.\n")

    total_programs = 0
    total_attachments = 0

    for doc_id, url, title, publisher, storage_ref in documents:
        print(f"─── [{publisher}] {title}")
        print(f"    URL: {url}")

        # Read HTML from S3
        try:
            obj = s3.get_object(Bucket=S3_BUCKET, Key=storage_ref)
            html_bytes = obj["Body"].read()
            html_text = html_bytes.decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"    ERROR reading from S3: {exc}")
            continue

        # Strip HTML to plain text for LLM
        plain_text = strip_html_tags(html_text)
        if len(plain_text) < 50:
            print(f"    SKIP: Content too short ({len(plain_text)} chars)")
            continue

        print(f"    Content: {len(plain_text)} chars")

        # Determine source_id from URL
        source_id = "mohw"  # default
        if "mol.gov.tw" in url or "wda.gov.tw" in url:
            source_id = "mol"
        elif "vac.gov.tw" in url:
            source_id = "vac"
        elif "mof.gov.tw" in url or "etax.nat.gov.tw" in url:
            source_id = "mof"
        elif "cip.gov.tw" in url:
            source_id = "cip"
        elif "ndc.gov.tw" in url:
            source_id = "ndc"
        elif "sfaa.gov.tw" in url:
            source_id = "mohw"

        # Call Bedrock
        print(f"    Analyzing with Bedrock...")
        try:
            result = call_bedrock(bedrock, plain_text, publisher, title, url)
        except Exception as exc:
            print(f"    ERROR calling Bedrock: {exc}")
            continue

        programs = result.get("programs", [])
        attachments = result.get("detected_attachments", [])

        print(f"    Found: {len(programs)} programs, {len(attachments)} attachments")

        # Download attachments
        for att in attachments:
            att_url = att.get("url", "")
            if not att_url:
                continue
            # Make absolute URL
            if not att_url.startswith("http"):
                att_url = urljoin(url, att_url)
            print(f"    Downloading attachment: {att_url[:70]}...")
            dl_result = download_attachment(att_url, s3, source_id)
            if dl_result:
                s3_key, file_hash, size = dl_result
                print(f"      → S3: {s3_key} ({size} bytes)")
                total_attachments += 1

                # Record in document_attachments
                att_id = str(uuid.uuid4())
                filename = att.get("filename", att_url.split("/")[-1])
                now = utc_now()
                with pg_conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO document_attachments (
                            attachment_id, document_id, filename, media_type,
                            source_url, storage_backend, storage_ref, content_hash,
                            extraction_status, review_status, created_at, updated_at
                        ) VALUES (%s, %s, %s, 'application/pdf', %s, 's3', %s, %s,
                                  'pending', 'candidate', %s::TIMESTAMPTZ, %s::TIMESTAMPTZ)
                        ON CONFLICT DO NOTHING
                        """,
                        (att_id, doc_id, filename, att_url, s3_key, file_hash, now, now),
                    )
                pg_conn.commit()

        # Write programs
        for prog in programs:
            prog_id = write_program_to_rds(pg_conn, prog, doc_id, source_id)
            if prog_id:
                print(f"    ✓ Program: {prog.get('canonical_name')} → {prog_id[:8]}...")
                total_programs += 1

        # Mark document as analyzed (under_review)
        with pg_conn.cursor() as cur:
            cur.execute(
                "UPDATE source_documents SET review_status = 'under_review', updated_at = %s::TIMESTAMPTZ WHERE document_id = %s",
                (utc_now(), doc_id),
            )
        pg_conn.commit()

    # Summary
    print("\n" + "=" * 60)
    print(f"Analysis complete:")
    print(f"  Documents analyzed: {len(documents)}")
    print(f"  Programs extracted: {total_programs}")
    print(f"  Attachments downloaded: {total_attachments}")
    print(f"  All data marked 'candidate' — requires human review")
    print("=" * 60)

    pg_conn.close()


if __name__ == "__main__":
    main()
