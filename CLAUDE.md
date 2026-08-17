# Claude Code — Decision Assurance Project Instructions

@AGENTS.md
@docs/governance/DA-INDEPENDENT-REVIEW-POLICY.md

## Claude-specific loading rule

The imported `AGENTS.md` remains the repository-wide engineering operating standard.

The imported `DA-INDEPENDENT-REVIEW-POLICY.md` is the normative review method whenever the task asks for an independent architecture, security, contract, remediation-closure, implementation-readiness, implementation or evidence review.

When acting as an independent reviewer:

- inspect the declared primary artifacts directly;
- do not rely on a remediation summary as evidence;
- do not silently resolve missing normative behavior;
- distinguish review verdict from Decision Assurance runtime outcomes;
- keep `NOT TESTED` distinct from evidence or `PASS`;
- resolve conflicting reviewer claims against primary artifacts rather than by model preference;
- do not modify files unless the task explicitly changes from review to remediation;
- do not approve your own remediation as an independent review.

For high-risk review work, use a fresh Claude Code context/session when practical and disclose the review basis in the output.
