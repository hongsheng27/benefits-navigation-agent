"""驗證每個接縫的離線實作。

這些實作刻意很小，測試的重點只有「行為符合宣告」：pass-through 真的什麼都不改，
fixture 真的只回它有資料的東西，而沒有資料時回空而不是編一個出來。

全部不需要 SQLite —— 那是提案第 10 節檢查清單的一項要求：workflow 的測試要能獨立
執行。
"""

from datetime import UTC, datetime, timedelta

from app.orchestration.data_contracts import (
    Citation,
    EligibilityDecision,
    EligibilityStatus,
)
from app.orchestration.field_registry import FieldRegistry
from app.orchestration.protocols import (
    FixtureEligibilityService,
    FixtureEntitlementGraphRepository,
    FixtureEvidenceRepository,
    LocalSourceRecord,
    LocalSourceRefreshService,
    PassThroughPrivacyGate,
    RefreshRequest,
)

_NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _decision(item_id: str, status: EligibilityStatus) -> EligibilityDecision:
    """組一筆最小的判定結果。金額全空，因為這裡測的是狀態流向。"""
    return EligibilityDecision(
        item_id=item_id,
        status=status,
        amount_min=None,
        amount_max=None,
        amount_period=None,
        amount_currency=None,
        reasons=(),
    )


# ---------------------------------------------------------------------------
# PrivacyGate
# ---------------------------------------------------------------------------


def test_pass_through_gate_returns_the_same_answers() -> None:
    """離線的閘門不改任何值。"""
    gate = PassThroughPrivacyGate()
    answers = {"deceased_insurance_type": "labor_insurance", "count": 2}

    result = gate.validate_attributes(answers, FieldRegistry(()))

    assert result == answers


def test_pass_through_gate_does_not_alias_the_input() -> None:
    """回傳的是複本，所以之後改動其中一邊不會波及另一邊。"""
    gate = PassThroughPrivacyGate()
    answers = {"has_dependent_children": True}

    result = gate.validate_attributes(answers, FieldRegistry(()))
    result["has_dependent_children"] = False

    assert answers["has_dependent_children"] is True


# ---------------------------------------------------------------------------
# EntitlementGraphRepository
# ---------------------------------------------------------------------------


def test_fixture_graph_expands_the_mvp_event() -> None:
    """MVP 情境（配偶過世）回四筆候選方案。"""
    repository = FixtureEntitlementGraphRepository()

    items = repository.expand_from_event("spouse_death", {})

    assert [item.item_id for item in items] == [
        "death_registration",
        "funeral_benefit",
        "survivor_pension",
        "health_insurance_change",
    ]


def test_fixture_graph_marks_everything_as_candidate_only() -> None:
    """寫死的示範資料沒有經過人工審查，所以只能是候選。

    依提案第 14 節：crawler 與 LLM 只能建立候選資料。標成 verified 會是假的。
    """
    repository = FixtureEntitlementGraphRepository()

    items = repository.expand_from_event("spouse_death", {})

    assert {item.program_status for item in items} == {"candidate"}


def test_fixture_graph_does_not_invent_a_relevance_score() -> None:
    """離線 fixture 沒有算相關性，填一個數字會讓下游以為有排序依據。"""
    repository = FixtureEntitlementGraphRepository()

    items = repository.expand_from_event("spouse_death", {})

    assert all(item.relevance_score is None for item in items)


def test_fixture_graph_returns_nothing_for_an_unknown_event() -> None:
    """沒有資料就回空，不猜一組項目 —— 猜錯會讓使用者白跑一趟。"""
    repository = FixtureEntitlementGraphRepository()

    assert repository.expand_from_event("unmapped_event", {}) == ()


def test_fixture_graph_answers_both_directions() -> None:
    """雙向遍歷：喪葬給付要先辦死亡登記，死亡登記解鎖喪葬給付。"""
    repository = FixtureEntitlementGraphRepository()

    prerequisites = repository.get_prerequisites("funeral_benefit")
    produces = repository.get_produces("death_registration")

    assert [relation.item_id for relation in prerequisites] == ["death_registration"]
    assert "funeral_benefit" in [relation.item_id for relation in produces]


def test_fixture_graph_returns_nothing_for_an_unknown_item() -> None:
    repository = FixtureEntitlementGraphRepository()

    assert repository.get_prerequisites("not_a_real_item") == ()
    assert repository.get_produces("not_a_real_item") == ()


def test_fixture_graph_lists_programs_by_system() -> None:
    repository = FixtureEntitlementGraphRepository()

    items = repository.get_programs_by_system("labor_insurance")

    assert [item.item_id for item in items] == ["funeral_benefit", "survivor_pension"]
    assert repository.get_programs_by_system("not_a_real_system") == ()


# ---------------------------------------------------------------------------
# EligibilityService
# ---------------------------------------------------------------------------


def test_fixture_eligibility_service_needs_human_review_without_rules() -> None:
    """沒有已核准的條件時不得產生完整資格結論（提案第 8 節）。"""
    service = FixtureEligibilityService()

    decision = service.evaluate("funeral_benefit", {})

    assert decision.status == "needs_human_review"
    assert decision.reasons == ()


def test_fixture_eligibility_service_returns_the_supplied_decision() -> None:
    """判定結果由建構參數帶入，代表「資料層已經有已核准的規則」。"""
    approved = _decision("funeral_benefit", "eligible")
    service = FixtureEligibilityService(decisions={"funeral_benefit": approved})

    assert service.evaluate("funeral_benefit", {}) is approved


def test_fixture_eligibility_service_evaluates_many_in_order() -> None:
    service = FixtureEligibilityService(
        decisions={"funeral_benefit": _decision("funeral_benefit", "eligible")}
    )

    decisions = service.evaluate_many(["survivor_pension", "funeral_benefit"], {})

    assert [decision.item_id for decision in decisions] == [
        "survivor_pension",
        "funeral_benefit",
    ]
    assert [decision.status for decision in decisions] == [
        "needs_human_review",
        "eligible",
    ]


def test_fixture_eligibility_service_has_no_required_fields_by_default() -> None:
    service = FixtureEligibilityService()

    assert service.get_required_fields("funeral_benefit") == ()


# ---------------------------------------------------------------------------
# EvidenceRepository
# ---------------------------------------------------------------------------


def test_fixture_evidence_repository_is_empty_by_default() -> None:
    """編造一份「官方依據」比沒有依據更糟：使用者會拿著它去問承辦人。"""
    repository = FixtureEvidenceRepository()

    assert repository.get_citations("funeral_benefit") == ()


def test_fixture_evidence_repository_returns_the_supplied_citations() -> None:
    citation = Citation(
        document_id="doc_1",
        title="〈條例名稱〉",
        publisher="〈機關〉",
        published_at="2026-01-01",
        effective_at="2026-02-01",
        url="https://example.gov.tw/rule",
        excerpt="〈引用段落〉",
        retrieved_at="2026-07-28",
    )
    repository = FixtureEvidenceRepository(citations={"funeral_benefit": [citation]})

    assert repository.get_citations("funeral_benefit") == (citation,)


# ---------------------------------------------------------------------------
# SourceRefreshService
# ---------------------------------------------------------------------------


def _service() -> LocalSourceRefreshService:
    """一份本機來源表：一個還沒抓過、一個剛抓過。"""
    return LocalSourceRefreshService(
        sources=(
            LocalSourceRecord(
                source_id="src_pending",
                crawl_status="pending_crawl",
                domain_tags=("funeral",),
                check_frequency_days=7,
            ),
            LocalSourceRecord(
                source_id="src_fresh",
                crawl_status="crawled",
                domain_tags=("funeral",),
                check_frequency_days=7,
                last_crawled_at=_NOW - timedelta(days=1),
                indexed_document_count=3,
            ),
            LocalSourceRecord(
                source_id="src_other_topic",
                crawl_status="pending_crawl",
                domain_tags=("housing",),
                check_frequency_days=7,
            ),
        ),
        event_domain_tags={"spouse_death": ("funeral",)},
    )


def test_coverage_is_filtered_by_the_event_domain_tags() -> None:
    """只回與這個事件相關的來源，並依代號排序讓順序可預期。"""
    coverage = _service().get_coverage_status("spouse_death")

    assert [entry.source_id for entry in coverage] == ["src_fresh", "src_pending"]


def test_coverage_is_empty_for_an_event_without_tags() -> None:
    """「不知道相關的是哪些」不等於「全部都相關」。"""
    assert _service().get_coverage_status("unmapped_event") == ()


def test_only_due_sources_are_queued() -> None:
    """還沒抓過的排入，剛抓過又還沒到期的不排。"""
    service = _service()

    receipt = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src_pending", "src_fresh"),
            requested_at=_NOW,
        )
    )

    assert receipt.accepted is True
    assert [job.source_id for job in service.pending_jobs()] == ["src_pending"]


def test_a_source_past_its_check_frequency_is_due() -> None:
    service = _service()

    receipt = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src_fresh",),
            requested_at=_NOW + timedelta(days=8),
        )
    )

    assert receipt.accepted is True


def test_nothing_due_is_accepted_false_without_dedup() -> None:
    """沒有來源到期與今天已經跑過是兩件事，收據要能區分。"""
    service = _service()

    receipt = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src_fresh",),
            requested_at=_NOW,
        )
    )

    assert (receipt.accepted, receipt.deduplicated) == (False, False)


def test_an_unknown_source_is_never_queued() -> None:
    service = _service()

    receipt = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("not_a_real_source",),
            requested_at=_NOW,
        )
    )

    assert receipt.accepted is False
    assert service.pending_jobs() == ()


def test_a_queued_job_cannot_promote_a_program_status() -> None:
    """本機佇列只記錄工作。crawl 或 LLM 的產出不得自動標為 verified。"""
    service = _service()
    service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src_pending",),
            requested_at=_NOW,
        )
    )

    job = service.pending_jobs()[0]

    assert not hasattr(job, "program_status")
    assert not hasattr(job, "status")


def test_the_same_source_and_event_is_not_triggered_twice_in_a_day() -> None:
    """Same-day dedup：鍵是 `source_id + event_id + 日期`（提案第 9 節第 4 項）。"""
    service = _service()
    request = RefreshRequest(
        event_id="spouse_death",
        source_ids=("src_pending",),
        requested_at=_NOW,
    )

    first = service.request_on_demand_refresh(request)
    second = service.request_on_demand_refresh(
        RefreshRequest(
            event_id="spouse_death",
            source_ids=("src_pending",),
            # 同一天的另一個時間點，仍然算同一天。
            requested_at=_NOW + timedelta(hours=5),
        )
    )

    assert (first.accepted, first.deduplicated) == (True, False)
    assert (second.accepted, second.deduplicated) == (False, True)
    # 只排了一次，不因為兩個請求就抓兩次。
    assert len(service.pending_jobs()) == 1


def test_a_different_event_is_not_deduplicated() -> None:
    """dedup 的鍵包含事件，所以另一個事件仍然可以觸發同一個來源。"""
    service = LocalSourceRefreshService(
        sources=(
            LocalSourceRecord(
                source_id="src_pending",
                crawl_status="pending_crawl",
                domain_tags=("funeral",),
                check_frequency_days=7,
            ),
        ),
        event_domain_tags={"spouse_death": ("funeral",), "parent_death": ("funeral",)},
    )

    for event_id in ("spouse_death", "parent_death"):
        receipt = service.request_on_demand_refresh(
            RefreshRequest(
                event_id=event_id,
                source_ids=("src_pending",),
                requested_at=_NOW,
            )
        )
        assert receipt.accepted is True

    assert len(service.pending_jobs()) == 2


def test_the_next_day_triggers_again() -> None:
    """dedup 只擋同一天，隔天該重抓還是要重抓。"""
    service = _service()
    for offset in (timedelta(0), timedelta(days=1)):
        receipt = service.request_on_demand_refresh(
            RefreshRequest(
                event_id="spouse_death",
                source_ids=("src_pending",),
                requested_at=_NOW + offset,
            )
        )
        assert receipt.accepted is True

    assert len(service.pending_jobs()) == 2
