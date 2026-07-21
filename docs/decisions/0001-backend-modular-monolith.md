# ADR-0001: Use a Modular Monolith for the Backend

- Status: Accepted
- Date: 2026-07-21

## Context

The project has four contributors and a limited Hackathon implementation
window. The backend must let contributors work independently on the API,
orchestration, retrieval, eligibility rules, privacy, and AWS integration while
remaining simple to run, test, debug, and deploy.

## Options Considered

1. Traditional monolith with weak internal boundaries.
2. Modular monolith with one deployment unit and explicit internal modules.
3. Separate API and Agent services.
4. Microservices or one serverless function per capability.

## Decision

Build the backend as a Python modular monolith.

The backend will have explicit module boundaries for:

- API transport
- Shared schemas and domain contracts
- Workflow orchestration
- Agent tools
- Official-document retrieval
- Deterministic eligibility rules
- Privacy controls
- External service adapters
- Observability

These modules will initially run as one deployable application and communicate
through in-process interfaces and function calls rather than internal network
requests.

Managed AWS services such as Amazon Bedrock, S3, or DynamoDB remain external
dependencies and do not change the backend topology decision.

## Consequences

### Positive

- Keep local development, testing, deployment, and debugging simple.
- Allow contributors to work in separate modules with fewer file conflicts.
- Avoid distributed-system concerns during the Hackathon.
- Preserve module boundaries that can support future service extraction.

### Negative

- Deploy and scale the backend modules together initially.
- Allow one module failure to affect the whole backend process.
- Require code review and tests to prevent boundaries from eroding over time.

## Non-decisions

This ADR does not decide:

- FastAPI versus a Lambda handler
- Lambda, container, or AgentCore Runtime deployment
- A custom state machine versus Strands Agents
- Session storage
- The RAG implementation

If operational evidence later justifies independent deployment, the Agent
module may be extracted behind its existing interface without changing the
domain and eligibility modules.
