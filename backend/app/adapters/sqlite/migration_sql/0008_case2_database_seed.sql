-- Database-backed vertical slice for the current spouse-death and Case 2 flows.
-- All seeded programs and excerpts remain candidate data. Nothing in this
-- migration may create an approved eligibility rule or a verified citation.

INSERT OR IGNORE INTO graph_nodes (node_id, node_type, display_name, program_id)
VALUES
    ('spouse_death', 'life_event', '配偶過世', NULL),
    ('parent_death', 'life_event', '父母過世', NULL),
    ('child_death', 'life_event', '子女過世', NULL),
    ('sibling_death', 'life_event', '兄弟姊妹過世', NULL),
    ('other_relative_death', 'life_event', '親人過世', NULL),
    ('job_loss', 'life_event', '失業／被資遣', NULL),
    ('unpaid_leave', 'life_event', '無薪假／收入驟減', NULL),
    ('occupational_injury', 'life_event', '職業災害', NULL),
    ('youth_employment_hardship', 'life_event', '青年就業困難', NULL),
    ('low_income_hardship', 'life_event', '低收入／生活困頓', NULL),
    ('serious_illness', 'life_event', '重大傷病', NULL),
    ('disability_onset', 'life_event', '身心障礙／失能', NULL),
    ('long_term_care_need', 'life_event', '長照需求', NULL),
    ('caregiver_burden', 'life_event', '家庭照顧負擔', NULL),
    ('mental_health_crisis', 'life_event', '精神健康危機', NULL),
    ('elderly_living_hardship', 'life_event', '老人生活困難', NULL),
    ('pregnancy', 'life_event', '懷孕', NULL),
    ('childbirth', 'life_event', '生育／生產', NULL),
    ('childcare_hardship', 'life_event', '育兒生活困難', NULL),
    ('school_expense_hardship', 'life_event', '就學費用困難', NULL),
    ('divorce', 'life_event', '離婚／分居', NULL),
    ('single_parent_hardship', 'life_event', '單親家庭困境', NULL),
    ('domestic_violence', 'life_event', '家庭暴力', NULL),
    ('special_family_circumstances', 'life_event', '特殊境遇家庭', NULL),
    ('housing_insecurity', 'life_event', '居住不穩／迫遷', NULL),
    ('natural_disaster', 'life_event', '天然災害受災', NULL),
    ('fire_or_accident', 'life_event', '火災或重大意外', NULL),
    ('new_immigrant_hardship', 'life_event', '新住民生活困難', NULL),
    ('indigenous_welfare_need', 'life_event', '原住民福利諮詢', NULL),
    ('incarceration_family', 'life_event', '家屬入監', NULL),
    ('missing_family_member', 'life_event', '家人失蹤', NULL),
    ('veteran_support_need', 'life_event', '榮民／退伍軍人支持', NULL),
    ('youth_independence_hardship', 'life_event', '少年自立困難', NULL);

UPDATE benefit_programs
SET summary = CASE program_id
    WHEN 'death_registration' THEN '先完成戶政死亡登記，再依個別身分確認後續給付與資格異動。'
    WHEN 'labor_funeral_grant' THEN '亡者若有勞工保險，可向勞保局確認喪葬給付。'
    WHEN 'national_pension_funeral_grant' THEN '亡者若有國民年金，可向勞保局確認國保喪葬給付。'
    WHEN 'labor_survivor_pension' THEN '亡者若有勞工保險，遺屬可向勞保局確認遺屬年金或津貼。'
    WHEN 'national_pension_survivor_pension' THEN '亡者若有國民年金，遺屬可確認國保遺屬年金。'
    WHEN 'nhi_status_change' THEN '完成死亡登記後，可確認健保資格與依附眷屬是否需要異動。'
    ELSE summary
END,
updated_at = datetime('now')
WHERE program_id IN (
    'death_registration',
    'labor_funeral_grant',
    'national_pension_funeral_grant',
    'labor_survivor_pension',
    'national_pension_survivor_pension',
    'nhi_status_change'
)
AND trim(summary) = '';

INSERT OR IGNORE INTO benefit_programs (
    program_id, canonical_name, summary, program_status, created_at, updated_at
)
VALUES
    (
        'occupational_injury_recognition_follow_up',
        '追蹤職業災害認定',
        '若職災認定仍在處理或尚未申請，可先向受理窗口確認進度與補件需求。',
        'candidate', datetime('now'), datetime('now')
    ),
    (
        'occupational_accident_disability_benefit',
        '職災保險失能給付',
        '工作事故造成失能且具有相關投保身分時，可向勞保局確認職災保險失能給付。',
        'candidate', datetime('now'), datetime('now')
    ),
    (
        'disability_assessment',
        '身心障礙鑑定',
        '尚未取得身心障礙證明時，可先向戶籍地公所確認鑑定申請與指定醫療院所。',
        'candidate', datetime('now'), datetime('now')
    ),
    (
        'long_term_care_assessment',
        '長照需求評估',
        '可透過 1966 或所在地照管中心申請長照需求評估，再確認適用服務。',
        'candidate', datetime('now'), datetime('now')
    ),
    (
        'caregiver_support_services',
        '家庭照顧者支持與喘息服務',
        '家庭主要照顧者可詢問喘息、支持團體及心理支持等地方服務。',
        'candidate', datetime('now'), datetime('now')
    ),
    (
        'caregiver_employment_support',
        '照顧者就業支持',
        '若照顧已影響工時或工作，可向公立就業服務單位詢問就業與職訓支持。',
        'candidate', datetime('now'), datetime('now')
    ),
    (
        'caregiver_support_contact',
        '支持專線與人工協助',
        '可先透過 1966 或所在地家庭照顧者支持據點確認服務窗口。',
        'candidate', datetime('now'), datetime('now')
    );

INSERT OR IGNORE INTO graph_nodes (node_id, node_type, display_name, program_id)
SELECT 'program:' || program_id, 'benefit_program', canonical_name, program_id
FROM benefit_programs
WHERE program_id IN (
    'death_registration',
    'labor_funeral_grant',
    'national_pension_funeral_grant',
    'labor_survivor_pension',
    'national_pension_survivor_pension',
    'nhi_status_change',
    'occupational_injury_recognition_follow_up',
    'occupational_accident_disability_benefit',
    'disability_assessment',
    'long_term_care_assessment',
    'caregiver_support_services',
    'caregiver_employment_support',
    'caregiver_support_contact'
);

INSERT OR IGNORE INTO field_registry (
    field_id, data_type, prompt_label, why_needed, pii_classification, active
)
VALUES
    ('deceased_insurance_type', 'enum', '過世者生前的投保身分', '投保身分決定可能相關的給付制度', 'eligibility_sensitive', 1),
    ('disability_cause', 'enum', '造成失能的原因', '失能原因用來區分職災與其他方向', 'eligibility_sensitive', 1),
    ('occupational_injury_recognition', 'enum', '職業災害認定進度', '認定進度用來整理後續追蹤方向', 'eligibility_sensitive', 1),
    ('care_recipient_insurance_type', 'enum', '被照顧者投保身分', '投保身分用來篩選可能相關的職災給付', 'eligibility_sensitive', 1),
    ('disability_assessment_status', 'enum', '身心障礙鑑定進度', '鑑定進度用來整理身障服務方向', 'eligibility_sensitive', 1),
    ('current_care_arrangement', 'enum', '目前照顧安排', '照顧安排用來整理照顧者支持方向', 'eligibility_sensitive', 1),
    ('caregiver_employment_impact', 'enum', '照顧對工作的影響', '工作影響用來整理就業支持方向', 'eligibility_sensitive', 1);

INSERT OR IGNORE INTO graph_edges (
    edge_id, from_node_id, to_node_id, edge_type, canonical_order
)
VALUES
    ('spouse_death:death_registration', 'spouse_death', 'program:death_registration', 'triggers', 0),
    ('spouse_death:labor_funeral_grant', 'spouse_death', 'program:labor_funeral_grant', 'triggers', 1),
    ('spouse_death:national_pension_funeral_grant', 'spouse_death', 'program:national_pension_funeral_grant', 'triggers', 2),
    ('spouse_death:labor_survivor_pension', 'spouse_death', 'program:labor_survivor_pension', 'triggers', 3),
    ('spouse_death:national_pension_survivor_pension', 'spouse_death', 'program:national_pension_survivor_pension', 'triggers', 4),
    ('spouse_death:nhi_status_change', 'spouse_death', 'program:nhi_status_change', 'triggers', 5),
    ('occupational_injury:recognition', 'occupational_injury', 'program:occupational_injury_recognition_follow_up', 'triggers', 0),
    ('occupational_injury:disability_benefit', 'occupational_injury', 'program:occupational_accident_disability_benefit', 'triggers', 1),
    ('occupational_injury:disability_assessment', 'occupational_injury', 'program:disability_assessment', 'triggers', 2),
    ('long_term_care_need:assessment', 'long_term_care_need', 'program:long_term_care_assessment', 'triggers', 0),
    ('long_term_care_need:caregiver_services', 'long_term_care_need', 'program:caregiver_support_services', 'triggers', 1),
    ('long_term_care_need:employment_support', 'long_term_care_need', 'program:caregiver_employment_support', 'triggers', 2),
    ('long_term_care_need:support_contact', 'long_term_care_need', 'program:caregiver_support_contact', 'triggers', 3);

INSERT OR IGNORE INTO graph_edge_conditions (
    edge_id, condition_id, field_id, operator,
    expected_value_type, expected_value_json, condition_order
)
VALUES
    ('spouse_death:labor_funeral_grant', 'insurance_labor', 'deceased_insurance_type', 'equals', 'string', '"labor_insurance"', 0),
    ('spouse_death:national_pension_funeral_grant', 'insurance_national', 'deceased_insurance_type', 'equals', 'string', '"national_pension"', 0),
    ('spouse_death:labor_survivor_pension', 'insurance_labor', 'deceased_insurance_type', 'equals', 'string', '"labor_insurance"', 0),
    ('spouse_death:national_pension_survivor_pension', 'insurance_national', 'deceased_insurance_type', 'equals', 'string', '"national_pension"', 0),
    ('occupational_injury:recognition', 'cause_occupational', 'disability_cause', 'equals', 'string', '"cause_occupational_injury"', 0),
    ('occupational_injury:recognition', 'recognition_incomplete', 'occupational_injury_recognition', 'not_equals', 'string', '"injury_recognized"', 1),
    ('occupational_injury:disability_benefit', 'cause_occupational', 'disability_cause', 'equals', 'string', '"cause_occupational_injury"', 0),
    ('occupational_injury:disability_benefit', 'has_insurance', 'care_recipient_insurance_type', 'not_equals', 'string', '"no_insurance"', 1),
    ('occupational_injury:disability_assessment', 'assessment_incomplete', 'disability_assessment_status', 'not_equals', 'string', '"disability_certificate_obtained"', 0),
    ('long_term_care_need:caregiver_services', 'not_fully_hired', 'current_care_arrangement', 'not_equals', 'string', '"hired_caregiver"', 0),
    ('long_term_care_need:employment_support', 'employment_affected', 'caregiver_employment_impact', 'not_equals', 'string', '"no_employment_change"', 0);

INSERT OR IGNORE INTO source_documents (
    document_id, canonical_url, title, document_type, publisher_name,
    first_seen_at, last_seen_at, retrieved_at, review_status, created_at, updated_at
)
VALUES
    ('candidate:occupational_accident_overview', 'https://www.bli.gov.tw/#candidate-occupational-accident', '職業災害認定與職災保險說明', 'benefit_page', '勞動部勞工保險局', datetime('now'), datetime('now'), NULL, 'candidate', datetime('now'), datetime('now')),
    ('candidate:disability_assessment_overview', 'https://www.mohw.gov.tw/#candidate-disability-assessment', '身心障礙鑑定辦理說明', 'benefit_page', '衛生福利部', datetime('now'), datetime('now'), NULL, 'candidate', datetime('now'), datetime('now')),
    ('candidate:long_term_care_1966', 'https://1966.gov.tw/#candidate-long-term-care', '長期照顧服務（1966）諮詢說明', 'benefit_page', '衛生福利部／1966 長照服務專線', datetime('now'), datetime('now'), NULL, 'candidate', datetime('now'), datetime('now')),
    ('candidate:caregiver_support', 'https://1966.gov.tw/#candidate-caregiver-support', '家庭照顧者支持與喘息服務說明', 'benefit_page', '衛生福利部／地方政府家庭照顧者支持據點', datetime('now'), datetime('now'), NULL, 'candidate', datetime('now'), datetime('now'));

INSERT OR IGNORE INTO evidence_excerpts (
    evidence_id, document_id, excerpt, review_status, created_at, updated_at
)
VALUES
    ('candidate:evidence:occupational_accident', 'candidate:occupational_accident_overview', '候選資料：發生職業災害時，可依規定確認職業災害認定，以及職災保險傷病、失能等給付；實際條件以主管機關最新公告為準。', 'candidate', datetime('now'), datetime('now')),
    ('candidate:evidence:disability_assessment', 'candidate:disability_assessment_overview', '候選資料：申請身心障礙鑑定，通常需向戶籍地公所提出申請，並依通知至指定醫療機構辦理鑑定。', 'candidate', datetime('now'), datetime('now')),
    ('candidate:evidence:long_term_care', 'candidate:long_term_care_1966', '候選資料：可撥打 1966 洽詢長照服務與需求評估；實際服務與補助須經照管中心評估。', 'candidate', datetime('now'), datetime('now')),
    ('candidate:evidence:caregiver_support', 'candidate:caregiver_support', '候選資料：家庭照顧者可洽詢喘息、支持團體、心理支持與相關諮詢資源，服務內容依所在地公告為準。', 'candidate', datetime('now'), datetime('now'));

INSERT OR IGNORE INTO program_evidence_links (
    program_id, evidence_id, evidence_role, review_status
)
VALUES
    ('occupational_injury_recognition_follow_up', 'candidate:evidence:occupational_accident', 'overview', 'candidate'),
    ('occupational_accident_disability_benefit', 'candidate:evidence:occupational_accident', 'overview', 'candidate'),
    ('disability_assessment', 'candidate:evidence:disability_assessment', 'overview', 'candidate'),
    ('long_term_care_assessment', 'candidate:evidence:long_term_care', 'overview', 'candidate'),
    ('caregiver_support_services', 'candidate:evidence:caregiver_support', 'overview', 'candidate'),
    ('caregiver_employment_support', 'candidate:evidence:caregiver_support', 'overview', 'candidate'),
    ('caregiver_support_contact', 'candidate:evidence:caregiver_support', 'overview', 'candidate');
