---
inclusion: auto
---

# Project Rules (Auto-loaded)

These rules apply to every Kiro session in this workspace.

## Before Any Work

1. Read `AGENTS.md` — it defines approval gates, commit rules, and AWS
   timeline restrictions.
2. Read `README.md` — it defines architecture, tech stack, and file structure.
3. Read `CONTRIBUTING.md` before creating any commit.

## Key Constraints

- This repository is **PUBLIC**. Never commit secrets (API keys, AWS
  credentials, tokens, `.env` files, private keys).
- Run a secrets scan before every `git push`.
- AWS resources are unavailable until August 1st. Use local mocks only.
- All AWS migration notes go in `docs/aws_migration_guide.md` (single source
  of truth).
- Do not modify `main` branch directly.
- Do not commit or push without explicit user approval.
- LLM must not determine eligibility — only the deterministic Rule Engine can.
- All benefit program data must have traceable official source URLs.
