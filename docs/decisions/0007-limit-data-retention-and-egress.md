# ADR-0007: Limit Data Retention and Egress

- Status: Accepted
- Date: 2026-07-25

## Context

ADR-0005 keeps direct identifiers on the client. `docs/positioning.md` establishes
that 接住 provides navigation rather than form filling, so the product never needs
a name or a national ID to evaluate eligibility.

Client-side masking is best-effort. The client is user-controlled, and free-text
detection cannot reliably identify Chinese personal names, which have no format
signal. The backend must therefore assume that incoming free text may still
contain identifiers.

The remaining risk is not interception. It is our own persistence: user text can
survive in session state, application logs, traces, and model invocation records
long after it has stopped being useful.

## Options Considered

1. Accept free text, store it with the session, and redact identifiers before
   writing logs.
2. Accept free text, discard it after attribute extraction, and never write user
   text to logs.
3. Reject free text entirely and collect only structured fields.

Option 1 keeps redaction as the only defense, which fails wherever detection
fails. Option 3 removes the natural-language entry point that motivates the
product.

## Decision

Adopt option 2, expressed as three rules.

### 1. Do not retain free text

Free text is accepted only in `UNDERSTAND_EVENT`. Once extraction produces
approved de-identified attributes, the original text is discarded.

It must not be written to session state, persisted storage, or the response
returned to the client. Only extracted attributes on the allowlist survive the
request.

No later workflow state consumes the original text, so retaining it has no
functional benefit.

### 2. Do not log user text

Application logs, traces, and metrics record structured fields only: state
transitions, tool names, rule identifiers, latency, and error codes.

User-supplied text is never a log field, including in error paths and exception
messages. Redacting before logging is explicitly rejected as insufficient,
because detection is best-effort and name detection is unreliable. Not writing
the field removes the failure mode instead of narrowing it.

### 3. Do not add third-party runtime dependencies to the frontend

The frontend must not load analytics, error-reporting, font, or tag-manager code
at runtime. Such services commonly capture form contents and DOM snapshots,
which would move user text to a third party outside this boundary.

Current runtime dependencies are `react` and `react-dom`. Adding another runtime
dependency requires review against this ADR. Build-time and development-only
dependencies are unaffected.

## Consequences

### Positive

- Reduces the window in which unmasked text exists to a single request.
- Removes logs as a leak path by construction rather than by filtering.
- Supports an accurate public claim that the system does not retain user text.
- A live demo leaves no stored user input behind.

### Negative

- Debugging cannot replay the original user text. Failures must be diagnosed
  from state transitions and extracted attributes.
- Extraction quality problems are harder to investigate after the fact.
- Frontend error-reporting services that would speed up debugging are
  unavailable.

## Non-decisions

This ADR does not decide:

- Whether the client shows a pre-send preview and confirmation
- Whether a branded `Sanitized` type enforces sanitization at compile time
- `session_id` lifetime and deletion policy
- Bedrock model invocation logging configuration, which must be verified in the
  competition account rather than assumed
- Browser-level mitigations such as `autocomplete` and `spellcheck` attributes

## Reference

- [ADR-0005: Split Client and Server Session State](0005-split-client-server-session-state.md)
- [Product positioning](../positioning.md)
