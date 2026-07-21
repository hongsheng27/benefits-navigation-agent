# ADR-0004: Trial Strands for the Bounded Agent Runner

- Status: Trial / Reversible
- Date: 2026-07-21

## Context

The policy-governed hybrid architecture needs a bounded agent loop for selected
semantic tasks. Strands Agents provides model integration, tool registration,
tool execution, conversation handling, hooks, and tracing, and integrates with
Amazon Bedrock. Implementing these mechanics directly would require additional
custom loop and error-handling code.

The project must retain control over workflow state, eligibility decisions,
privacy, and tool permissions. It must also be possible to leave Strands if the
framework adds more Hackathon risk than value.

## Options Considered

1. Use Strands Agents with Amazon Bedrock.
2. Call Bedrock directly for every model interaction and implement a small
   custom tool loop where required.
3. Use another agent framework.

## Trial Decision

Use Strands Agents with Amazon Bedrock as the initial implementation of a
project-owned `AgentRunner` interface.

The intended implementations are:

```text
AgentRunner
├── StrandsAgentRunner       # Primary trial implementation
├── DirectBedrockAgentRunner # Fallback when needed
└── MockAgentRunner          # Local tests and deterministic fixtures
```

The state machine will pass a project-owned request containing the task,
de-identified context, allowed tools, and execution limits. The runner will
return a project-owned structured result. Strands-specific request, state, tool,
and response types must remain inside the adapter.

Core tools will delegate to ordinary application services. Eligibility rules,
retrieval logic, schemas, session state, FastAPI routes, and workflow
transitions must not import Strands.

Direct Bedrock calls may still be used for single-call structured tasks that do
not benefit from an agent loop.

## Trial Validation

Before treating this decision as fully accepted, complete a small spike that
demonstrates:

- One Bedrock model invocation through Strands
- Two mock tools with unambiguous schemas
- A strict tool allowlist
- A maximum of three loop iterations
- Project-owned structured output validation
- One tool failure or invalid-input case
- Trace visibility sufficient to debug tool selection

## Exit Conditions

Replace `StrandsAgentRunner` with a direct Bedrock implementation if any of the
following remains unresolved after the spike:

- Tool use cannot be constrained reliably.
- Structured output is not stable enough for the application contract.
- Framework behavior obscures prompts, responses, or tool failures.
- AWS account, model, or dependency compatibility blocks the demo path.
- Latency or context growth is unreasonable for the bounded task.
- The team cannot explain and debug the underlying loop before the Hackathon.

## Consequences

### Positive

- Avoid reimplementing standard agent-loop mechanics initially.
- Follow an AWS-aligned path for Bedrock and possible AgentCore deployment.
- Retain framework portability through the project-owned interface.
- Support mock implementations for local and deterministic testing.

### Negative

- Add a framework and learning requirement to the backend.
- Require adapter discipline to prevent Strands types from leaking inward.
- Require a spike before relying on the integration for the demo.

## Non-decisions

This ADR does not decide:

- The Bedrock model ID
- AgentCore Runtime deployment
- The final tool list
- Session persistence or memory
- RAG and vector storage implementation

## References

- [Strands Agents](https://github.com/strands-agents/harness-sdk)
- [Strands Agent Loop](https://strandsagents.com/latest/documentation/docs/user-guide/concepts/agents/agent-loop/)
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
