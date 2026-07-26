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

- Ask the owner to implement or closely review schemas, prompts, tool contracts,
  workflow transitions, eligibility rules, PII handling, retrieval grounding,
  and evaluation logic.
- AI agents may directly create boilerplate, folder structure, configuration,
  basic CLI parsing, straightforward documentation, and CRUD scaffolding after
  explaining their purpose.
