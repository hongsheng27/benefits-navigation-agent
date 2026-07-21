# ADR-0002: Use FastAPI for the HTTP API

- Status: Accepted
- Date: 2026-07-21

## Context

The frontend needs a stable HTTP contract for sessions, messages, and benefit
navigation results. The team already has FastAPI experience, while a raw AWS
Lambda handler would add unfamiliar event formats, packaging, permissions, and
debugging work during a limited Hackathon implementation window.

The API framework must not determine the application, orchestration, rules, or
retrieval architecture.

## Options Considered

1. FastAPI as the primary HTTP framework.
2. Raw AWS Lambda handlers as the application entry points.
3. A framework-neutral core with FastAPI now and an optional Lambda adapter
   added later.

## Decision

Use FastAPI as the primary HTTP transport for the backend.

FastAPI will be responsible for:

- HTTP routing
- Request and response validation
- Dependency wiring at the transport boundary
- HTTP status codes and error mapping
- OpenAPI documentation

Application services and domain logic will use plain Python and Pydantic
contracts without importing FastAPI. Eligibility rules, workflow transitions,
retrieval, and model integration must remain outside route handlers.

A raw Lambda handler is not required for the MVP. If the selected deployment
target later requires one, add it as a thin adapter around the same application
service rather than duplicating business logic.

## Consequences

### Positive

- Use a framework the team can implement and debug quickly.
- Give frontend contributors a documented and testable API contract.
- Keep local development and API testing straightforward.
- Preserve the option to add a different transport adapter later.

### Negative

- Add an ASGI framework dependency to the backend.
- Require an adapter or compatible hosting integration if Lambda is selected
  later.
- Require code review to keep business logic out of route handlers.

## Non-decisions

This ADR does not decide:

- The AWS deployment target
- Whether AgentCore Runtime is used
- Session persistence
- HTTP streaming or Server-Sent Events
- Authentication and authorization
