"""Generic eligibility rule engine.

Reads structured fields from program_rule_fields and evaluates user
attributes against them. No per-program custom code is needed — adding a
new program only requires filling in its structured fields.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EligibilityResult:
    program_id: str
    program_name: str
    status: str  # eligible, ineligible, needs_information, needs_human_review
    amount: int | None = None
    amount_label: str = ""
    missing_inputs: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    source_url: str = ""


def _parse_field_value(field_type: str, raw_value: str) -> Any:
    """Convert stored string to typed value."""
    if field_type == "integer":
        return int(raw_value) if raw_value else None
    if field_type == "number":
        return float(raw_value) if raw_value else None
    if field_type == "boolean":
        return raw_value.lower() in ("true", "1", "yes")
    if field_type == "json":
        return json.loads(raw_value) if raw_value else None
    # text, date
    return raw_value


def load_program_rules(
    connection: sqlite3.Connection,
    program_id: str,
) -> dict[str, Any]:
    """Load all rule fields for a program as a typed dict."""
    rows = connection.execute(
        """SELECT field_name, field_type, field_value
           FROM program_rule_fields
           WHERE program_id = ?""",
        (program_id,),
    ).fetchall()
    return {
        row[0]: _parse_field_value(row[1], row[2])
        for row in rows
    }


def load_all_program_rules(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    """Load rule fields for all programs."""
    rows = connection.execute(
        """SELECT program_id, field_name, field_type, field_value
           FROM program_rule_fields"""
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        pid = row[0]
        if pid not in result:
            result[pid] = {}
        result[pid][row[1]] = _parse_field_value(row[2], row[3])
    return result


def _evaluate_amount(
    rules: dict[str, Any],
    user_attrs: dict[str, Any],
) -> tuple[int | None, str, list[str]]:
    """Determine amount based on conditions. Returns (amount, label, missing)."""
    conditions = rules.get("amount_conditions")
    if not conditions:
        # Simple min/max
        min_amt = rules.get("min_amount")
        max_amt = rules.get("max_amount")
        if min_amt == max_amt and min_amt is not None:
            return min_amt, "", []
        if min_amt is not None and max_amt is not None:
            return None, f"{min_amt}~{max_amt}", []
        return None, "", []

    # Evaluate conditions
    for cond_item in conditions:
        cond_str = cond_item.get("condition", "")
        if _evaluate_condition(cond_str, user_attrs):
            return cond_item["amount"], cond_item.get("label", ""), []

    # Check if we're missing inputs needed for condition evaluation
    missing = _missing_inputs_for_conditions(conditions, user_attrs)
    if missing:
        return None, "", missing

    return None, "不符合任何金額條件", []


def _evaluate_condition(condition_str: str, user_attrs: dict[str, Any]) -> bool:
    """Evaluate a simple condition string like 'remains_type=ash AND source=X'."""
    if not condition_str:
        return True

    parts = [p.strip() for p in condition_str.split(" AND ")]
    for part in parts:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip()
        value = value.strip()
        user_value = user_attrs.get(key)
        if user_value is None:
            return False
        if str(user_value) != value:
            return False
    return True


def _missing_inputs_for_conditions(
    conditions: list[dict[str, Any]],
    user_attrs: dict[str, Any],
) -> list[str]:
    """Find input fields referenced in conditions but missing from user."""
    needed: set[str] = set()
    for cond_item in conditions:
        cond_str = cond_item.get("condition", "")
        parts = [p.strip() for p in cond_str.split(" AND ")]
        for part in parts:
            if "=" in part:
                key = part.split("=", 1)[0].strip()
                needed.add(key)
    return [k for k in sorted(needed) if k not in user_attrs]


def evaluate_program(
    program_id: str,
    program_name: str,
    rules: dict[str, Any],
    user_attrs: dict[str, Any],
    source_url: str = "",
) -> EligibilityResult:
    """Evaluate a single program's eligibility against user attributes.

    This is the generic engine — it reads structured fields and applies
    standard logic. No per-program code needed.
    """
    missing_inputs: list[str] = []
    reasons: list[str] = []

    # 1. Check jurisdiction
    # (Filtering by jurisdiction is done at query time, not here)

    # 2. Check city registration requirement
    requires_reg = rules.get("requires_city_registration", False)
    if requires_reg:
        registered = user_attrs.get("registered_in_city")
        if registered is None:
            missing_inputs.append("registered_in_city")
        elif not registered:
            return EligibilityResult(
                program_id=program_id,
                program_name=program_name,
                status="ineligible",
                reasons=["需設籍該縣市"],
                source_url=source_url,
            )

    # 3. Check remains type
    eligible_types = rules.get("eligible_remains_types")
    if eligible_types:
        user_type = user_attrs.get("remains_type")
        if user_type is None:
            missing_inputs.append("remains_type")
        elif user_type not in eligible_types:
            return EligibilityResult(
                program_id=program_id,
                program_name=program_name,
                status="ineligible",
                reasons=[f"不適用此骨灰骸類型: {user_type}"],
                source_url=source_url,
            )

    # 4. Check deceased status (for service programs like joint funeral)
    eligible_statuses = rules.get("eligible_deceased_statuses")
    if eligible_statuses:
        user_status = user_attrs.get("deceased_status")
        if user_status is None:
            missing_inputs.append("deceased_status")
        elif user_status not in eligible_statuses:
            # Check if fee reduction applies
            if rules.get("fee_reduction_for_unqualified"):
                reasons.append("不符合免費資格，但可減半收費")
            else:
                return EligibilityResult(
                    program_id=program_id,
                    program_name=program_name,
                    status="ineligible",
                    reasons=["亡者身分不符合申請資格"],
                    source_url=source_url,
                )

    # 5. Check eco burial requirement
    eco_required = rules.get("eco_burial_required", False)
    if eco_required:
        eco_done = user_attrs.get("eco_burial_completed")
        if eco_done is None:
            missing_inputs.append("eco_burial_completed")
        elif not eco_done:
            reasons.append("需完成環保葬後才能申請")

    # 6. Check deadline
    deadline_days = rules.get("application_deadline_days")
    if deadline_days is not None:
        starts_from = rules.get("deadline_starts_from", "")
        days_key = f"days_since_{starts_from}" if starts_from else None
        if days_key:
            user_days = user_attrs.get(days_key)
            if user_days is None:
                missing_inputs.append(days_key)
            elif user_days > deadline_days:
                return EligibilityResult(
                    program_id=program_id,
                    program_name=program_name,
                    status="ineligible",
                    reasons=[f"已超過申請期限 ({deadline_days} 天)"],
                    source_url=source_url,
                )

    # 7. Check application period
    period_start = rules.get("application_period_start")
    period_end = rules.get("application_period_end")
    if period_start or period_end:
        current_date = user_attrs.get("current_date")
        if current_date:
            if period_start and current_date < period_start:
                return EligibilityResult(
                    program_id=program_id,
                    program_name=program_name,
                    status="ineligible",
                    reasons=[f"尚未開放申請（開始日期: {period_start}）"],
                    source_url=source_url,
                )
            if period_end and current_date > period_end:
                return EligibilityResult(
                    program_id=program_id,
                    program_name=program_name,
                    status="ineligible",
                    reasons=[f"申請期間已截止（截止日期: {period_end}）"],
                    source_url=source_url,
                )

    # 8. Determine amount
    amount, amount_label, amount_missing = _evaluate_amount(rules, user_attrs)
    missing_inputs.extend(amount_missing)

    # Final decision
    if missing_inputs:
        return EligibilityResult(
            program_id=program_id,
            program_name=program_name,
            status="needs_information",
            amount=amount,
            amount_label=amount_label,
            missing_inputs=list(set(missing_inputs)),
            reasons=reasons,
            source_url=source_url,
        )

    return EligibilityResult(
        program_id=program_id,
        program_name=program_name,
        status="eligible",
        amount=amount,
        amount_label=amount_label,
        reasons=reasons,
        source_url=source_url,
    )


def evaluate_all_programs(
    connection: sqlite3.Connection,
    user_attrs: dict[str, Any],
    jurisdiction: str | None = None,
) -> list[EligibilityResult]:
    """Evaluate all programs (optionally filtered by jurisdiction)."""
    # Load programs
    query = "SELECT program_id, canonical_name, jurisdiction_code FROM benefit_programs"
    params: list[Any] = []
    if jurisdiction:
        query += " WHERE jurisdiction_code = ?"
        params.append(jurisdiction)

    programs = connection.execute(query, params).fetchall()
    all_rules = load_all_program_rules(connection)

    results: list[EligibilityResult] = []
    for prog in programs:
        pid, name, _ = prog
        rules = all_rules.get(pid, {})
        if not rules:
            continue
        result = evaluate_program(pid, name, rules, user_attrs)
        results.append(result)

    return results
