---
name: da-independent-review
description: Perform an independent Decision Assurance architecture, security, contract, remediation-closure, implementation-readiness, implementation, or evidence review. Use when asked for PASS/FAIL review, finding closure, authorization to implement, cross-contract validation, or adjudication between conflicting reviewers. Do not use this skill to remediate during the same independent review.
---

# Decision Assurance Independent Review

Before reviewing, read and follow:

`docs/governance/DA-INDEPENDENT-REVIEW-POLICY.md`

Also read the repository-root `AGENTS.md` and all applicable versioned specifications, contracts, schemas, ADRs and evidence artifacts for the declared scope.

## Required operating mode

Default to read-only review.

Do not change files, commit, push, merge or remediate unless the user explicitly changes the task from independent review to remediation.

Do not approve remediation produced by the same review actor/session as an independent review.

## Required sequence

1. Record repository/worktree, branch, base/head or uncommitted diff basis, and exact scope.
2. Locate the canonical source of any original findings. If it is unavailable, disclose that fact and do not pretend reconstructed findings are authoritative original findings.
3. Identify the applicable normative source hierarchy.
4. Check cross-contract fields, enums, event names, state transitions and digest/canonicalization semantics against primary artifacts.
5. Check actor/capability consistency, least privilege, tenant binding, authorization and fail-closed behavior.
6. Check required predecessor integrity bindings and mix-and-match resistance.
7. Check concurrency/race semantics relevant to authorization, execution, retry, hold/delete and replay.
8. Check append-only/audit invariants and privacy lifecycle compatibility where applicable.
9. Separate controls from required evidence classes and observed evidence.
10. Treat `NOT TESTED` as no test evidence.
11. Distinguish intentionally disabled capabilities from implementation-blocking unknowns.
12. Apply the policy definitions for Major, Minor, CLOSED, PARTIALLY CLOSED and OPEN.
13. Issue a review verdict and a separate implementation-authorization decision.

## Conflicting reviews

When reviewers disagree, do not vote and do not average confidence.

Build a disputed-claim table and resolve each claim against the authoritative primary artifact. If the primary artifacts conflict, keep the conflict open as a finding.

## Required output

Use these sections:

### Review basis

State exact repository state, scope and canonical findings source.

### Controls

State which read-only checks were actually performed and which evidence was actually observed.

### Findings closure matrix

Use:

| Finding | Severity | Prior status | Current status | Primary artifact and section | Reason |
|---|---|---|---|---|---|

### New findings

Separate Major, Minor and editorial observations.

### Implementation-blocking unknowns

List them explicitly or state `None`.

### Disabled capabilities

List each intentionally disabled capability and its activation condition.

### Verdict

Use exactly one:

`VERDICT: PASS`

`VERDICT: PASS WITH MINOR FINDINGS`

`VERDICT: FAIL`

Then separately state exactly one:

`AUTHORIZE IMPLEMENTATION = YES`

`AUTHORIZE IMPLEMENTATION = NO`

Implementation authorization never implies deployment, Controlled Pilot, production or regulatory approval.
