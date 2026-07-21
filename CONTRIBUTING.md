# Contributing to 接住

This document records the repository's engineering and commit conventions.
Keep it practical and update it when the workflow changes.

## Commit Message Convention

Use Conventional Commit-style messages:

```text
<type>(<scope>): <summary>

<body>
```

### Types

```text
feat      New product or engineering capability
fix       Bug fix
docs      Documentation-only change
refactor  Internal restructure without behavior change
test      Tests or test fixtures
chore     Tooling, config, dependency, or maintenance work
data      Official source data, fixtures, seed data, or metadata
```

### Scopes

Prefer the narrowest module-level scope that describes the change:

```text
repo
frontend
backend
api
schemas
agent
orchestration
tools
rag
rules
privacy
data
evaluation
infra
docs
```

Add a new scope only when an existing scope cannot describe the module clearly.

### Summary Rules

- Use English.
- Use imperative style.
- Keep the summary under 72 characters when reasonable.
- Do not end the summary with a period.
- Describe one coherent change.

Examples:

```text
feat(frontend): add guided benefit intake flow
feat(orchestration): add guarded workflow transitions
fix(rules): handle missing insurance status
docs(architecture): document the privacy boundary
data(sources): add survivor pension source metadata
refactor(agent): isolate tool selection from eligibility rules
```

Avoid vague messages:

```text
update files
fix bug
finish frontend
misc changes
```

## Commit Body

Use a commit body when the commit includes meaningful implementation work,
multiple files, or a project milestone.

The body should:

- Use bullet points.
- Start each bullet with an imperative verb such as `Add`, `Update`, `Document`,
  `Validate`, `Refactor`, or `Ignore`.
- Describe concrete artifacts or behavior, not vague outcomes.
- Keep each bullet focused on one action.
- Avoid duplicating the subject line.
- Include verification or documentation work when it is part of the commit.

Good example:

```text
feat(rag): add official source retrieval pipeline

- Add document metadata filtering by benefit and agency
- Add citation mapping for retrieved government sources
- Add retrieval fixtures for survivor pension rules
- Validate grounded responses with integration cases
- Document the ingestion and retrieval flow
```

Weak example:

```text
feat(rag): add RAG

- Add RAG stuff
- Update files
- Fix scripts
```

The body should let a future reader understand the change without opening the
diff first.

## Commit Scope

Each commit should represent one coherent unit of work.

- Do not mix unrelated frontend, backend, data, or documentation changes.
- Do not commit real credentials, `.env` files, PII, or local temporary files.
- Do not commit large raw PDFs unless the team explicitly decides they belong
  in Git; store them in S3 or local `tmp/` by default.
- Keep official source metadata, deterministic rules, and small evaluation
  fixtures reviewable in Git.
- Run the relevant tests or validation checks before committing.

## AI-Assisted Commit Flow

When asking an AI agent to commit:

```text
1. Run git status first.
2. Identify unrelated dirty changes.
3. Stage only files relevant to the current task.
4. Do not stage unrelated deletions or user changes.
5. Show the proposed commit message before amending or committing, unless the user already approved it.
6. Prefer non-interactive git commands.
7. Run relevant checks before committing.
8. After commit, report the commit hash and remaining unstaged changes.
```

## Learn-by-Building Workflow

For implementation work intended to help a teammate learn the codebase:

```text
Important core logic:
The owner should implement or review closely.

Boilerplate:
AI may implement directly after explaining its purpose.
```

Core logic includes:

```text
Pydantic schemas and shared contracts
Agent prompts and tool schemas
Workflow transitions and safety guards
Eligibility rules
PII handling and cloud-field allowlists
Citation grounding and RAG retrieval logic
Evaluation cases and scoring logic
```

Boilerplate includes:

```text
__init__.py files
Folder structure
Dependency and configuration files
Basic CLI argument parsing
Simple documentation updates
CRUD scaffolding
```
