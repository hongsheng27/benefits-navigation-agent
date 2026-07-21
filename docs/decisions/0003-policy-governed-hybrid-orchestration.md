# ADR-0003: Use Policy-Governed Hybrid Orchestration

- Status: Accepted
- Date: 2026-07-21

## Context

Benefit navigation combines a predictable policy process with flexible natural
language input. Eligibility evaluation, privacy boundaries, required fields,
and human confirmation need deterministic control. Life-event understanding,
question phrasing, and grounded explanations benefit from model-driven semantic
reasoning.

A fully fixed workflow would be reliable but could behave like a rigid form. A
fully autonomous agent would add unnecessary uncertainty to a policy-sensitive
process.

## Options Considered

1. A fully predefined workflow with no agent-directed steps.
2. A model-directed agent loop that controls tools and task completion.
3. A policy-governed workflow with bounded agentic steps.

## Decision

Use a policy-governed hybrid orchestration model.

The explicit state machine owns:

- The current workflow state
- Valid state transitions
- Required fields and transition guards
- The tools allowed in each state
- Iteration and timeout limits
- Error and fallback behavior
- Human confirmation and escalation
- Completion criteria

Agentic or LLM-powered steps may:

- Interpret a natural-language life event
- Extract approved de-identified eligibility attributes
- Recommend the next missing field from an allowlist
- Form retrieval queries within the current benefit scope
- Explain deterministic results using retrieved official sources

The deterministic rule engine exclusively produces eligibility statuses:

- `eligible`
- `ineligible`
- `needs_information`
- `needs_human_review`

The Agent must not override eligibility results, expand its own permissions, or
bypass privacy checks and human confirmation.

## Consequences

### Positive

- Preserve predictable and testable policy behavior.
- Retain conversational flexibility where natural language is valuable.
- Make state transitions, tool calls, and decision ownership observable.
- Allow the Agent implementation to change without rewriting eligibility rules.

### Negative

- Require explicit contracts between workflow, Agent, and rule engine modules.
- Require tests for both deterministic transitions and bounded model behavior.
- Add more orchestration code than a fully autonomous agent loop.

## Non-decisions

This ADR does not decide:

- Strands Agents versus direct Bedrock tool use
- The exact state model and transition table
- The Bedrock chat model
- AgentCore Runtime deployment
- Retrieval and vector storage implementation

## Reference

- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
