# ADR-0005: Split Client and Server Session State

- Status: Accepted
- Date: 2026-07-21

## Context

The product needs conversational workflow state while minimizing the personal
information sent to cloud services. Keeping all state on the backend would
conflict with the privacy boundary. Keeping all state on the client would make
workflow transitions untrusted, recovery difficult, and server-side debugging
and evaluation less reliable.

Natural-language input may contain direct identifiers even when the product
does not request them, so the transport boundary must be explicit.

## Options Considered

1. Store raw user input, direct identifiers, and workflow state on the backend.
2. Keep all session and workflow state on the client.
3. Split state between client-held direct identifiers and authoritative,
   de-identified backend workflow state.

## Decision

Use split client and server session state.

The client owns direct identifiers, including:

- Name
- National identification number
- Address
- Phone number
- Email address
- Any other fields used only to identify or contact the person

Before transmission, the client will warn users not to enter direct identifiers
and will detect and mask obvious structured PII patterns. The client sends only
sanitized text and explicitly allowlisted eligibility attributes.

The backend owns the authoritative workflow state, including:

- A random session identifier that does not encode personal information
- Current workflow state and transition history
- Normalized life event
- Allowlisted de-identified eligibility attributes
- Missing fields
- Candidate benefit identifiers
- Eligibility results and rule versions
- Official-source citations and checklist state

The backend must validate all incoming attributes and transitions. Client-sent
workflow state is not trusted. Defense-in-depth redaction must run before
content is written to logs, traces, model prompts, or persistent storage.

## Consequences

### Positive

- Minimize direct identifiers sent to cloud services.
- Keep security-sensitive workflow transitions authoritative on the backend.
- Preserve backend observability and session recovery options.
- Make the privacy boundary visible and testable.

### Negative

- Require client-side sanitization and shared field contracts.
- Require careful classification of direct and quasi-identifying attributes.
- Cannot guarantee that free text never contains missed PII, so layered
  validation, redaction, UX guidance, and testing remain necessary.
- Require synchronization between client presentation state and backend
  workflow state.

## Non-decisions

This ADR does not decide:

- Memory, DynamoDB, or AgentCore Memory for backend persistence
- The exact allowlisted eligibility fields
- Session retention and deletion periods
- The PII detection library or implementation
- Authentication and authorization
- Whether a future document-filling feature handles direct identifiers locally
