# Repository Instructions

These instructions apply to AI coding agents working in this repository,
including Codex and Kiro.

## Project Context

- Read `README.md` before making architecture or implementation decisions.
- Treat choices marked as `待決策` in `README.md` as unresolved. Do not silently
  lock in an optional framework, AWS service, or deployment approach.
- Record an agreed architectural decision under `docs/decisions/` when the team
  selects among documented alternatives.
- Keep LLM responsibilities separate from deterministic eligibility rules.
- Never add real credentials, personally identifiable information, or private
  user data to the repository.
- This repository is **public**. Before every `git push`, run a secrets scan
  to ensure no API keys, AWS credentials, tokens, `.env` files, or private
  keys are staged. Use the following check:

  ```bash
  git diff --cached --name-only | xargs grep -lE \
    '(AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{20,}|password\s*=\s*["\x27].+["\x27]|AWS_SECRET_ACCESS_KEY|PRIVATE.KEY)' \
    2>/dev/null && echo "BLOCKED: secrets detected" && exit 1 || echo "OK: no secrets found"
  ```

  If any match is found, do not push. Remove the secret, use environment
  variables or `.env` (which is gitignored), and re-stage.

- Keep large raw government PDFs and local extraction artifacts out of Git
  unless the team explicitly decides otherwise.

## Working With Existing Changes

- Run `git status` before editing or staging files.
- Treat existing modifications as user-owned unless the current task clearly
  created them.
- Preserve unrelated changes and do not stage, revert, or delete them.
- Keep each change focused on the requested task.

## Owner Visibility and Approval Gates

For any change beyond straightforward documentation or boilerplate, remain
read-only until the owner approves an implementation plan.

Before the first file write:

1. Explain the goal and intended outcome in plain language.
2. List the files expected to be added, changed, or deleted and explain why.
3. Describe any effect on architecture, APIs, schemas, workflow, privacy,
   eligibility rules, retrieval grounding, evaluation logic, or deployment.
4. Identify unresolved decisions, assumptions, risks, and likely conflicts with
   other contributors' work.
5. State the narrowest relevant verification commands that will be run.
6. Wait for explicit owner approval before editing.

If the approved scope changes during implementation, stop before making the
out-of-scope change, explain the new impact, and obtain approval again. Keep
implementation batches small enough for the owner to review and understand.

After implementation:

1. Do not stage, commit, push, or open a pull request unless explicitly
   requested.
2. Show the resulting `git status` and summarize `git diff --stat`.
3. Explain every changed file and its purpose in beginner-friendly language.
4. Report the exact tests, linters, formatters, or validations that were run
   and their results.
5. Report any remaining risks, unresolved decisions, possible team conflicts,
   and uncommitted changes.

## Verification

- Run the narrowest relevant tests, linters, formatters, or validation commands
  available for the files changed.
- Always run `git diff --check` before proposing a commit.
- If the project does not yet have an applicable automated check, inspect the
  diff and state that no automated test was available.
- Do not claim a check passed unless it was actually run.

## Commit Workflow

Only create a commit when the user explicitly requests one.

When asked to commit:

1. Read and follow `CONTRIBUTING.md` as the source of truth for commit format.
2. Run `git status` and inspect staged and unstaged changes.
3. Identify unrelated dirty changes.
4. Stage only the files that belong to the requested task.
5. Run the relevant verification commands.
6. Use the Conventional Commit format defined in `CONTRIBUTING.md`.
7. Show the proposed commit message before committing unless the user has
   already approved that exact message or explicitly authorized immediate
   commit creation.
8. Prefer non-interactive Git commands.
9. Do not amend, rebase, push, force-push, or delete branches unless explicitly
   requested.
10. After committing, report the commit hash, subject, checks performed, and
    any remaining uncommitted changes.

## Commit Message Quality

- Write the subject and body in English.
- Use an imperative subject and keep it under 72 characters when reasonable.
- Use the narrowest applicable scope from `CONTRIBUTING.md`.
- For meaningful multi-file changes, add a body with concrete bullet points.
- Start body bullets with imperative verbs such as `Add`, `Update`, `Document`,
  `Validate`, `Refactor`, or `Ignore`.
- Avoid vague messages such as `update files`, `fix stuff`, or `misc changes`.

## Learn-by-Building Boundary

- AI agents may implement schemas, prompts, tool contracts, workflow
  transitions, eligibility rules, PII handling, retrieval grounding, and
  evaluation logic after the implementation plan is approved. Keep these
  changes small, explicit, and verifiable.
- AI agents may directly create boilerplate, folder structure, configuration,
  basic CLI parsing, straightforward documentation, and CRUD scaffolding after
  explaining their purpose.

## AWS Development Strategy

Live AWS environments and cloud resources may be used for hackathon preparation
and execution. Never commit AWS credentials or account-specific secrets.

### Local and AWS Implementations

- Use live AWS services when they help the team validate or deliver the
  feature.
- Keep local mocks or alternatives when they make core business logic easier
  to test and demonstrate:
  - Local SQLite instead of RDS or DynamoDB.
  - Local folder instead of S3.
  - Stub or mock environment variables for AWS APIs.
- All migration instructions must be centralized in a single file:
  `docs/aws_migration_guide.md`.

### Migration Guide Requirements

Every time a feature is added or modified that uses or will migrate to an AWS
service, the AI **must immediately update** `docs/aws_migration_guide.md` as
part of the same task. The guide must be organized by feature or file path and
specify:

1. Which local mock code to remove or comment out.
2. Which AWS SDK or API connection to uncomment or insert.
3. The exact environment variables (`.env`) that teammates need to fill in.

Do not scatter migration notes across multiple files. This single guide is the
source of truth for the on-site transition.

## Code Review Rules

Every pull request receives an AI auto review before merge. The reviewer's job
is to protect the team from unsafe or broken changes while keeping noise low.
Most contributors are domain experts, not engineers, and their changes are
AI-assisted; assume good intent, verify everything.

The auto reviewer reads the pull request diff and repository context only. It
does not run commands. Running `make check` is the author's responsibility
(and CI's, once configured), never the reviewer's.

### Merge Gate

Merging is a human action; the team's merge checklist lives in
`docs/team-guide.md`. What agents must know:

- Authors may merge their own pull request after `make check` passes.
- Resolve any blocking findings that the auto review reports before merging.
- Agents do not press merge themselves unless the user explicitly asks.

### Blocking Findings (request changes)

Only three red lines block a merge. Each is either irreversible once merged
or breaks the product's core thesis:

1. Secrets or credentials of any kind: API keys, AWS credentials, tokens,
   `.env` files, private keys. This repository is public; a leaked key cannot
   be un-leaked.
2. PII or private user data, including realistic-looking test data such as
   national ID numbers or real names attached to case details.
3. LLM code performing eligibility determination. Eligibility must be decided
   by the deterministic rules engine (`backend/app/rules/`). LLM output may
   gather input for the rules engine or explain its result, never replace it.

### Not Blocking (comment only, never block)

Mention these briefly so the author can follow up, but do not request
changes for them:

- AWS-dependent features without a matching `docs/aws_migration_guide.md`
  update.
- Committed build output, caches, or local artifacts (`frontend/dist/`,
  `__pycache__/`, `tmp/`, large raw PDFs) — suggest removing them.
- Tests skipped, deleted, or weakened — note it for post-hackathon cleanup.
- Unrelated changes mixed into the PR.
- Style, naming, or formatting concerns already enforced by the formatter and
  linter.
- Refactor or performance suggestions that do not change behavior.
- Real AWS service usage (S3, RDS, DynamoDB, Bedrock, AgentCore, etc.) by any
  team member. Do not flag AWS connections; only the three red lines above
  apply, and those apply in full.

### Review Output Format

- List each blocking finding as `file:line — what is wrong — how to fix it`.
- Write findings in Traditional Chinese with technical terms kept in English,
  in plain language a non-engineer can act on.
- Do not restate the diff, pad with praise, or speculate beyond the diff.
- Judge only from the diff and repository context. Never state that tests or
  checks passed or failed — the reviewer does not run them. If the PR
  description is missing the `make check` result, flag that instead.

### Pull Request Requirements (for coding agents opening PRs)

- One PR is one coherent task; split unrelated work into separate PRs.
- The PR title follows the Conventional Commit format in `CONTRIBUTING.md`.
- The description states, in plain language: what changed, why, and which
  verification commands were run with their results.
- Run `make check` locally before requesting review, or state why it was not
  possible.
