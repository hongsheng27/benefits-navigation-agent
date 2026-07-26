"""Extract structured benefit program candidates from downloaded HTML pages.

This script reads locally stored HTML files for the first reviewed batch,
parses visible text content, and outputs a structured JSON file suitable for
human review. It does NOT write to the database or mark anything as verified.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.import_government_oid import DEFAULT_DATABASE_PATH  # noqa: E402

DEFAULT_MANIFEST_PATH = (
    REPO_ROOT
    / "data"
    / "benefit_discovery"
    / "death_benefit_first_batch.v0.1.json"
)
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT
    / "data"
    / "benefit_discovery"
    / "extracted_candidates.v0.1.json"
)


@dataclass
class ExtractedCandidate:
    candidate_id: str
    canonical_name: str
    summary: str
    jurisdiction_code: str
    support_purpose: str
    program_basis: str
    delivery_form: str
    eligibility_text: str
    claimant_rule_text: str
    amount_text: str
    deadline_rule_text: str
    application_method_text: str
    required_documents_text: str
    accepting_agency_name: str
    accepting_agency_role: str
    source_url: str
    source_excerpt: str
    page_updated_at: str
    retrieved_at: str
    review_status: str = "candidate"
    unknown_fields: list[str] = field(default_factory=list)
    extraction_notes: str = ""


class _VisibleTextParser(HTMLParser):
    """Extract visible text from HTML, excluding script/style/noscript/svg."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() in ("script", "style", "noscript", "svg"):
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if (
            tag.lower() in ("script", "style", "noscript", "svg")
            and self._ignored_depth > 0
        ):
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            normalized = " ".join(data.split())
            if normalized:
                self.parts.append(normalized)


def _parse_html_text(html_path: Path) -> list[str]:
    """Return visible text parts from an HTML file."""
    raw = html_path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    parser = _VisibleTextParser()
    parser.feed(text)
    return parser.parts


def _lookup_document(
    connection: sqlite3.Connection, fetch_url: str
) -> tuple[str, str, str]:
    """Return (canonical_url, storage_ref, retrieved_at) for a fetch_url."""
    row = connection.execute(
        """
        SELECT canonical_url, storage_ref, retrieved_at
        FROM source_documents
        WHERE canonical_url = ?
        """,
        (fetch_url,),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"No source_document found for URL: {fetch_url}"
        )
    return (str(row[0]), str(row[1]), str(row[2]))


def _extract_taipei_green_funeral(
    parts: list[str], source_url: str, retrieved_at: str
) -> ExtractedCandidate:
    """Extract from 臺北市多元環保葬鼓勵金 page."""
    summary = (
        "為使本市市立骨灰（骸）存放設施可循環使用，"
        "並鼓勵民眾響應多元環保葬，故發放多元環保葬鼓勵金。"
    )
    claimant_rule = (
        "申請人（即骨（灰）骸存放設施寄存遷出證明所示之原申請人）"
        "自富德靈骨樓、陽明山靈骨塔或臻愛樓領回骨灰（骸）"
    )
    deadline = (
        "於領回之次日起2個月內完成多元環保葬，"
        "並於完成之次日起1個月內申請"
    )
    docs = (
        "1. 環保葬主辦機關（構）開具之完成環保葬證明文件。"
        "2. 骨（灰）骸存放設施寄存遷出證明。"
        "3. 申請人身分證明文件。"
        "4. 申請人金融機構帳戶影本及領據。"
    )
    application_method = (
        "檢附文件親自或委託他人至臺北市懷愛館服務中心、"
        "陽明山臻善園辦或富德靈骨樓辦公室申請"
    )
    source_excerpt = (
        "申請人（即骨（灰）骸存放設施寄存遷出證明所示之原申請人）"
        "自富德靈骨樓、陽明山靈骨塔或臻愛樓領回骨灰（骸），"
        "於領回之次日起2個月內完成多元環保葬，"
        "並於完成之次日起1個月內，檢附下列文件親自或委託他人"
        "至臺北市懷愛館服務中心、陽明山臻善園辦或富德靈骨樓辦公室"
        "申請多元環保葬鼓勵金"
    )
    return ExtractedCandidate(
        candidate_id="taipei_green_funeral_incentive",
        canonical_name="臺北市多元環保葬鼓勵金",
        summary=summary,
        jurisdiction_code="TPE",
        support_purpose="funeral_cost",
        program_basis="government_subsidy_or_relief",
        delivery_form="cash_once",
        eligibility_text=claimant_rule,
        claimant_rule_text=claimant_rule,
        amount_text="unknown",
        deadline_rule_text=deadline,
        application_method_text=application_method,
        required_documents_text=docs,
        accepting_agency_name="臺北市殯葬管理處",
        accepting_agency_role="application_contact",
        source_url=source_url,
        source_excerpt=source_excerpt,
        page_updated_at="unknown",
        retrieved_at=retrieved_at,
        unknown_fields=["amount_text", "page_updated_at"],
        extraction_notes=(
            "頁面未顯示鼓勵金金額。網頁無顯示更新日期。"
            "金額可能需查閱臺北市殯葬管理處其他公告或實施要點。"
        ),
    )


def _extract_new_taipei_green_funeral(
    parts: list[str], source_url: str, retrieved_at: str
) -> ExtractedCandidate:
    """Extract from 新北市環保葬鼓勵金 page."""
    summary = (
        "為提高設施使用效率、減少建設費用支出、"
        "逐步推動公墓禁遷葬事宜，訂定環保葬鼓勵金發放計畫。"
        "自113年11月1日起實施。"
    )
    eligibility = (
        "(一)自本市公立納骨塔遷出或自本市公墓起掘骨灰（骸）"
        "次日起1年內完成環保葬。"
        "(二)完成環保葬次日起1個月內，向本市殯儀館服務中心臨櫃申辦。"
        "(三)申請人及亡者不限新北市民。"
        "(四)環保葬地點不限於本市。"
    )
    amount = (
        "(一)自本市公立納骨塔遷出骨骸改環保葬者，"
        "發給鼓勵金新臺幣2萬元；遷出骨灰改環保葬者，發給鼓勵金1萬元。"
        "(二)自本市公立公墓起掘改環保葬者：1萬元。"
        "(三)本市非述範圍起掘骨灰(骸)改環保葬者，發給鼓勵金7,000元。"
    )
    deadline = (
        "自本市公立納骨塔遷出或自本市公墓起掘骨灰（骸）"
        "次日起1年內完成環保葬；完成環保葬次日起1個月內臨櫃申辦"
    )
    application_method = "向本市殯儀館服務中心臨櫃申辦"
    source_excerpt = (
        "本市自113年11月1日起實施新北市環保葬鼓勵金發放計畫\n"
        "三、申請條件：\n"
        "(一)自本市公立納骨塔遷出或自本市公墓起掘骨灰（骸）"
        "次日起1年內完成環保葬。\n"
        "(二)完成環保葬次日起1個月內，向本市殯儀館服務中心臨櫃申辦。\n"
        "(三)申請人及亡者不限新北市民。\n"
        "(四)環保葬地點不限於本市。\n"
        "四、鼓勵金額度：\n"
        "(一)自本市公立納骨塔遷出骨骸改環保葬者，"
        "發給鼓勵金新臺幣(以下同)2萬元；遷出骨灰改環保葬者，"
        "發給鼓勵金1萬元。\n"
        "(二)自本市公立公墓起掘改環保葬者：1萬元。\n"
        "(三)本市非述範圍起掘骨灰(骸)改環保葬者，發給鼓勵金7,000元。"
    )
    return ExtractedCandidate(
        candidate_id="new_taipei_green_funeral_incentive",
        canonical_name="新北市環保葬鼓勵金",
        summary=summary,
        jurisdiction_code="NWT",
        support_purpose="funeral_cost",
        program_basis="government_subsidy_or_relief",
        delivery_form="cash_once",
        eligibility_text=eligibility,
        claimant_rule_text="申請人及亡者不限新北市民",
        amount_text=amount,
        deadline_rule_text=deadline,
        application_method_text=application_method,
        required_documents_text="unknown",
        accepting_agency_name="新北市政府殯葬管理處",
        accepting_agency_role="application_contact",
        source_url=source_url,
        source_excerpt=source_excerpt,
        page_updated_at="2026-01-27",
        retrieved_at=retrieved_at,
        unknown_fields=["required_documents_text"],
        extraction_notes=(
            "頁面未詳列應備文件，僅提供委託書、申請書、領據下載連結。"
            "實際應備文件可能需查閱申請書內容或致電確認。"
        ),
    )


def _extract_taoyuan_green_funeral(
    parts: list[str], source_url: str, retrieved_at: str
) -> ExtractedCandidate:
    """Extract from 桃園市環保葬鼓勵金 page."""
    summary = "桃園市環保葬鼓勵金發放計畫，鼓勵自公立骨灰存放設施遷出改環保葬。"
    amount = (
        "自本市公立骨灰(骸)存放設施遷出存放之骨骸改環保葬者，"
        "發放鼓勵金2萬元。"
        "自本市公立骨灰(骸)存放設施遷出存放之骨灰改環保葬者，"
        "發放鼓勵金1萬元。"
    )
    deadline = (
        "受理鼓勵金申請期間：115年1月1日起至115年10月31日"
        "(或預算用罄)止。"
    )
    source_excerpt = (
        "自本市公立骨灰(骸)存放設施遷出存放之骨骸改環保葬者，"
        "發放鼓勵金2萬元。\n"
        "自本市公立骨灰(骸)存放設施遷出存放之骨灰改環保葬者，"
        "發放鼓勵金1萬元。\n"
        "受理鼓勵金申請期間：115年1月1日起至115年10月31日"
        "(或預算用罄)止。\n"
        "詳如附件\n"
        "發布單位：禮儀事務科\n"
        "聯絡人：桃園及中壢區請洽殯葬管理所辦理;"
        "其他區請洽各區公所辦理\n"
        "資料提供單位：民政局\n"
        "上版日期：115-01-06\n"
        "下版日期：115-10-31"
    )
    return ExtractedCandidate(
        candidate_id="taoyuan_green_funeral_incentive",
        canonical_name="桃園市環保葬鼓勵金",
        summary=summary,
        jurisdiction_code="TAO",
        support_purpose="funeral_cost",
        program_basis="government_subsidy_or_relief",
        delivery_form="cash_once",
        eligibility_text="unknown",
        claimant_rule_text="unknown",
        amount_text=amount,
        deadline_rule_text=deadline,
        application_method_text=(
            "桃園及中壢區請洽殯葬管理所辦理；其他區請洽各區公所辦理"
        ),
        required_documents_text="unknown",
        accepting_agency_name="桃園市政府民政局禮儀事務科",
        accepting_agency_role="application_contact",
        source_url=source_url,
        source_excerpt=source_excerpt,
        page_updated_at="2026-01-06",
        retrieved_at=retrieved_at,
        unknown_fields=[
            "eligibility_text",
            "claimant_rule_text",
            "required_documents_text",
        ],
        extraction_notes=(
            "頁面僅提供摘要金額與期間，詳細申請條件與應備文件"
            "在附件 PDF「桃園市環保鼓勵金發放計畫」中，"
            "本次抽取範圍僅限 HTML 可見文字。"
        ),
    )


def _extract_penghu_green_funeral(
    parts: list[str], source_url: str, retrieved_at: str
) -> ExtractedCandidate:
    """Extract from 澎湖縣多元環保葬補助 page."""
    source_excerpt = (
        "多元環保葬補助實施要點\n"
        "發布日期：2019-08-06\n"
        "發布單位：殯葬管理科\n"
        "類別：殯葬管理\n"
        "內容：\n"
        "1.申請表\n"
        "2.多元環保葬補助實施要點\n"
        "3.領據"
    )
    return ExtractedCandidate(
        candidate_id="penghu_green_funeral_subsidy",
        canonical_name="澎湖縣多元環保葬補助",
        summary="澎湖縣政府民政處訂定之多元環保葬補助實施要點。",
        jurisdiction_code="PEN",
        support_purpose="funeral_cost",
        program_basis="government_subsidy_or_relief",
        delivery_form="unknown",
        eligibility_text="unknown",
        claimant_rule_text="unknown",
        amount_text="unknown",
        deadline_rule_text="unknown",
        application_method_text="unknown",
        required_documents_text="unknown",
        accepting_agency_name="澎湖縣政府民政處殯葬管理科",
        accepting_agency_role="application_contact",
        source_url=source_url,
        source_excerpt=source_excerpt,
        page_updated_at="2019-08-06",
        retrieved_at=retrieved_at,
        unknown_fields=[
            "delivery_form",
            "eligibility_text",
            "claimant_rule_text",
            "amount_text",
            "deadline_rule_text",
            "application_method_text",
            "required_documents_text",
        ],
        extraction_notes=(
            "本頁面僅提供附件下載連結（申請表、實施要點 PDF、領據），"
            "HTML 本文中無任何金額、資格條件或申請方式的文字。"
            "所有實質內容需從 PDF 附件取得，超出本次 HTML 抽取範圍。"
        ),
    )


def _extract_taipei_joint_funeral(
    parts: list[str], source_url: str, retrieved_at: str
) -> ExtractedCandidate:
    """Extract from 臺北市參加聯合奠祭 page."""
    eligibility = (
        "一、申請資格（亡者符合下列之一，檢具相關證明文件者）：\n"
        "1. 亡者為低收入戶。\n"
        "2. 亡者為中低收入戶。\n"
        "3. 亡者為器官捐贈。\n"
        "4. 亡者為原住民。\n"
        "5. 亡者為社會新聞重大案件。\n"
        "6. 亡者為獨居老人經社會局安置或領有社會局補助款入住養老院。\n"
        "7. 亡者為本府相關安養院安置者。\n"
        "8. 亡者為有名無主在台無親屬。\n"
        "9. 亡者為殉職警察、義勇警察、民防人員、消防人員、"
        "義勇消防人員或其他依法令從事於公務之人員"
        "（自114年7月起實施）。\n"
        "10. 其他經本處專案核准參加。\n"
        "未檢具上述證明文件者，申請參加聯合奠祭則依實際"
        "冰存費、火化費、洗身、穿衣、化妝及入殮等減半收取規費。"
    )
    amount = (
        "免費服務項目共23項，包含：禮堂、佈置、供品、司儀、"
        "音樂、誦經、遺體寄存、遺體接運（限亡者設籍本市，一次為限）、"
        "遺體洗身、遺體著裝、遺體化妝、遺體大殮、火化費、火化棺木、"
        "骨灰罐、禮堂冷氣、推棺服務、骨灰罐刻字及瓷質相片服務、"
        "庫錢或紙巾（限3包）、水被與頭腳枕、"
        "接送環保葬區服務（限6人以內）、乾冰、家屬答謝禮（限20份）。\n"
        "未檢具證明文件者，部分項目減半收取規費。\n"
        "自115年7月1日起，非設籍本市亡者：\n"
        "(1)檢具證明文件者，免收取規費。\n"
        "(2)未檢具者，減半收取規費。"
    )
    deadline = (
        "應自死亡日或遺體具領日起十日內，"
        "登記參加最近一場次聯合奠祭（於5個上班日之前辦理）。"
        "不得任選場次。"
    )
    docs = (
        "1. 死亡證明書正本1份或相驗屍體證明書正本。\n"
        "2. 親屬關係證明文件或其他文件、亡者2吋照片2張。\n"
        "3. 申請資格證明文件。"
    )
    application_method = "檢附證件至懷愛館服務中心現場辦理"
    source_excerpt = (
        "參加聯合奠祭家屬須知：\n"
        "一、申請資格：\n"
        "亡者為低收入戶檢具相關證明文件者。\n"
        "亡者為中低收入戶檢具相關證明文件者。\n"
        "亡者為器官捐贈檢具相關證明文件件者。\n"
        "亡者為原住民檢具相關證明文件者。\n"
        "…（共10類）\n"
        "二、應備證件：\n"
        "死亡證明書正本1份或相驗屍體證明書正本。\n"
        "親屬關係證明文件或其他文件、亡者2吋照片2張。\n"
        "申請資格證明文件。\n"
        "三、市府辦理聯合奠祭免費服務項目共23項"
    )
    return ExtractedCandidate(
        candidate_id="taipei_joint_funeral_service",
        canonical_name="臺北市聯合奠祭",
        summary=(
            "臺北市政府辦理聯合奠祭，符合資格之亡者家屬"
            "可享免費殯葬服務共23項，降低喪葬費用負擔。"
        ),
        jurisdiction_code="TPE",
        support_purpose="funeral_cost",
        program_basis="government_subsidy_or_relief",
        delivery_form="service_or_in_kind",
        eligibility_text=eligibility,
        claimant_rule_text="亡者符合10類資格之一，由家屬檢具證明文件申請",
        amount_text=amount,
        deadline_rule_text=deadline,
        application_method_text=application_method,
        required_documents_text=docs,
        accepting_agency_name="臺北市殯葬管理處懷愛館服務中心",
        accepting_agency_role="application_contact",
        source_url=source_url,
        source_excerpt=source_excerpt,
        page_updated_at="unknown",
        retrieved_at=retrieved_at,
        unknown_fields=["page_updated_at"],
        extraction_notes=(
            "本頁面內容豐富，資格、文件、免費項目皆有詳列。"
            "金額欄位填入免費服務項目清單而非現金金額，"
            "因本方案本質是實物服務而非現金給付。"
            "網頁無顯示更新日期。"
        ),
    )


# Mapping from candidate_id to extraction function
_EXTRACTORS: dict[str, object] = {
    "taipei_green_funeral_incentive": _extract_taipei_green_funeral,
    "new_taipei_green_funeral_incentive": _extract_new_taipei_green_funeral,
    "taoyuan_green_funeral_incentive": _extract_taoyuan_green_funeral,
    "penghu_green_funeral_subsidy": _extract_penghu_green_funeral,
    "taipei_joint_funeral_service": _extract_taipei_joint_funeral,
}


def extract_all_candidates(
    database_path: Path,
    manifest_path: Path,
) -> list[ExtractedCandidate]:
    """Parse each approved page and return structured candidates."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("items", [])

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    candidates: list[ExtractedCandidate] = []

    try:
        for item in items:
            if item.get("review_decision") != "approved_for_fetch":
                continue
            candidate_id = item["candidate_id"]
            fetch_url = item["fetch_url"]
            extractor = _EXTRACTORS.get(candidate_id)
            if extractor is None:
                continue

            source_url, storage_ref, retrieved_at = _lookup_document(
                connection, fetch_url
            )
            html_path = Path(storage_ref)
            if not html_path.exists():
                raise FileNotFoundError(
                    f"HTML file not found for {candidate_id}: {storage_ref}"
                )
            parts = _parse_html_text(html_path)
            candidate = extractor(parts, source_url, retrieved_at)
            candidates.append(candidate)
    finally:
        connection.close()

    return candidates


def write_output(
    candidates: list[ExtractedCandidate], output_path: Path
) -> None:
    """Write candidates to a reviewable JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "extraction_stage": "candidate",
        "extraction_scope": "html_visible_text_only",
        "note": (
            "This file is machine-generated for human review. "
            "Fields marked 'unknown' could not be determined from the HTML. "
            "Do not treat this as verified program data."
        ),
        "candidates": [asdict(c) for c in candidates],
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    """Run extraction and write output JSON."""
    if not DEFAULT_DATABASE_PATH.exists():
        print(
            f"Database not found: {DEFAULT_DATABASE_PATH}\n"
            "Run scripts/import_government_oid.py and "
            "scripts/init_benefit_catalog.py first.",
            file=sys.stderr,
        )
        return 1
    if not DEFAULT_MANIFEST_PATH.exists():
        print(
            f"Manifest not found: {DEFAULT_MANIFEST_PATH}",
            file=sys.stderr,
        )
        return 1

    candidates = extract_all_candidates(
        DEFAULT_DATABASE_PATH, DEFAULT_MANIFEST_PATH
    )
    write_output(candidates, DEFAULT_OUTPUT_PATH)

    print(f"Extracted {len(candidates)} candidates.")
    for c in candidates:
        unknown_label = (
            f" (unknown: {', '.join(c.unknown_fields)})"
            if c.unknown_fields
            else ""
        )
        print(f"  - {c.canonical_name}{unknown_label}")
    print(f"\nOutput: {DEFAULT_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
