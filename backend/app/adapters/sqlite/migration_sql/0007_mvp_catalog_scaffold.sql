-- MVP catalog scaffold: insert the 6 known program IDs with no facts.
-- All threshold/deadline/amount/excerpt remain unknown/null.
-- Status is 'candidate' because no human-approved facts exist yet.

INSERT INTO benefit_programs (program_id, canonical_name, program_status, created_at, updated_at)
SELECT 'death_registration', '死亡登記', 'candidate', datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM benefit_programs WHERE program_id = 'death_registration');

INSERT INTO benefit_programs (program_id, canonical_name, program_status, created_at, updated_at)
SELECT 'labor_funeral_grant', '勞保喪葬津貼', 'candidate', datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM benefit_programs WHERE program_id = 'labor_funeral_grant');

INSERT INTO benefit_programs (program_id, canonical_name, program_status, created_at, updated_at)
SELECT 'national_pension_funeral_grant', '國保喪葬給付', 'candidate', datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM benefit_programs WHERE program_id = 'national_pension_funeral_grant');

INSERT INTO benefit_programs (program_id, canonical_name, program_status, created_at, updated_at)
SELECT 'labor_survivor_pension', '勞保遺屬年金', 'candidate', datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM benefit_programs WHERE program_id = 'labor_survivor_pension');

INSERT INTO benefit_programs (program_id, canonical_name, program_status, created_at, updated_at)
SELECT 'national_pension_survivor_pension', '國保遺屬年金', 'candidate', datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM benefit_programs WHERE program_id = 'national_pension_survivor_pension');

INSERT INTO benefit_programs (program_id, canonical_name, program_status, created_at, updated_at)
SELECT 'nhi_status_change', '健保資格異動', 'candidate', datetime('now'), datetime('now')
WHERE NOT EXISTS (SELECT 1 FROM benefit_programs WHERE program_id = 'nhi_status_change');
