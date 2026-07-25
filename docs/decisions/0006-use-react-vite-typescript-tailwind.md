# ADR-0006: Use React, Vite, TypeScript, and Tailwind CSS

- Status: Accepted
- Date: 2026-07-25

## Context

The MVP needs a browser interface for life-event input, follow-up questions,
benefit results, official citations, and application checklists. The team needs
a frontend foundation that is quick to run locally, keeps API access behind a
clear boundary, and can grow without deciding the final visual system or
deployment platform yet.

## Options Considered

1. React with Vite and TypeScript.
2. A React meta-framework with server-side rendering.
3. A static HTML and JavaScript application.

For styling, the team considered utility-first CSS, a component framework, and
hand-written CSS.

## Decision

Use React, Vite, TypeScript, and Tailwind CSS for the frontend. Use npm as the
package manager and commit a single npm lockfile.

The initial application will:

- Provide one responsive page with life-event input and mock result states.
- Keep backend requests in `src/api/`.
- Read the backend origin from `VITE_API_BASE_URL`.
- Include linting, type checking, unit tests, and a production build.
- Build a small set of project-owned UI components before adopting a component
  library.

## Consequences

### Positive

- Keep local development and production builds straightforward.
- Use TypeScript at the frontend/backend contract boundary.
- Avoid requiring a server-rendering runtime for the MVP.
- Allow the team to establish its own privacy and accessibility patterns.

### Negative

- Require the team to maintain frontend build tooling and reusable components.
- Require discipline to prevent domain contracts from being duplicated or
  changed independently from the backend.
- Provide no server-side rendering by default.

## Non-decisions

This ADR does not decide:

- The final visual design system or component library
- Client-side routing
- Global state management
- Authentication and authorization
- Frontend hosting or AWS deployment
- Session, message, eligibility, or PII-handling contracts
