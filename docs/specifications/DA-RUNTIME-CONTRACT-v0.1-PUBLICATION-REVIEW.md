# Runtime draft publication review — 2026-10-08

Base fb301524 plus the three existing local document amendments. This is documentation-only review by Codex/root, the same task actor; independence is not established. Publication is a draft, implementation remains NOT AUTHORIZED and every proposed runtime test is NOT TESTED.

Remediation design: preserve v0.2 unchanged and explicitly bound the interoperable subset; do not coerce signed source values. Define a separate Runtime event envelope rather than silently aliasing required existing v1 fields. Options of changing v0.2 or accepting ambiguous hashes are rejected. All three changes are proposals requiring future design approval, not release acceptance.

| Finding | Severity | File | Concrete remedy | Status |
|---|---|---|---|---|
| PUB-RTC-001 | Major specification | DA-RUNTIME-CONTRACT-v0.1.md §4.3 | Replace undefined constraint_set_ref with the defined constraint_set_digest. | CLOSED in draft |
| PUB-RTC-002 | Major compatibility | specification §4.3/4.4 | Distinguish new Runtime timestamps from exact imported v0.2 timestamps; explicitly refuse source numeric values outside the lossless integer subset instead of silently coercing or claiming all v0.2 documents are representable. | CLOSED as bounded draft compatibility |
| PUB-RTC-004 | Major specification | specification §4.1/4.4 | Align approval_refs with the lossless nonce mapping; copied nonce remains a reference and grants no authority. Remove unsupported current independent-review status claims. | CLOSED in draft |
| PUB-RTC-003 | Major event contract | specification §6; ADR event model | Give the pseudonymous envelope its own 0.1.0 version and exact field list. Existing v1 requires tenant_id/actor_id and stays unchanged; parsers must not assume aliases. | CLOSED in draft |

Specification review: no Decision PASS automatically becomes organizational approval or execution. Actor/capability separation, tenant/current action/approval binding, atomic consume-reserve, EFFECT_UNKNOWN reconciliation, immutable audit chain, retention/hold/delete CAS and deployment non-bypassability remain explicit requirements. No future test result is asserted. The new compatibility subset and envelope must be approved before implementation.

Code/security review: no executable, schema, migration or dependency changes in this package. Security controls remain design obligations, not demonstrated deployed controls. Relative links/fences and full staged diff/secret scan are publication checks only. Future E2E, PostgreSQL, OIDC, localization, source-hash fixtures and unsupported-value negatives remain required.
