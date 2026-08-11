# DATS Gold Dataset v0.1

**Status:** Accepted project baseline
**Operating profile:** Development benchmark evidence

## Decision

The ten approved DATS scenarios form one reusable, versioned package inside the public Decision
Assurance repository. The package, not `tests/`, is the normative source for tasks and expected
results. A separate repository is deferred until the dataset requires independent releases,
citations or external contribution governance.

The OWASP *State of Agentic AI Security and Governance 2.01* report is registered as an external
primary source. It informs threat coverage and future cases but does not supply or endorse DATS
labels. The repository stores a source record and authoritative link, not a binary copy whose
redistribution terms have not been separately verified.

## Verification matrix

| Requirement | Risk | Control | Test or gate | Status |
| --- | --- | --- | --- | --- |
| Stable reuse | callers copy ad-hoc fixtures | pinned catalog and one file per case | catalog contract and CLI | PASS |
| Normative result | ambiguous outcome vocabulary | normalized three-state gate plus legacy outcome | exact regression | PASS |
| Provenance | synthetic cases appear externally validated | explicit synthetic marker | schema test | PASS |
| Source attribution | OWASP mapping is overstated | external source record and non-endorsement marker | source contract | PASS |
| Integrity | case substitution or traversal | ID/path match and root confinement | negative traversal test | PASS |
| Actor independence | self-approval passes | DATS-009 | benchmark gate | PASS |
| Evidence governance | fabricated, stale, mismatched, conflicting or missing evidence | DATS-002–006 | benchmark gate | PASS |
| Deterministic constraint | model output overrides hard policy | DATS-007 | benchmark gate | PASS |
| Human review | threshold or uncertainty silently passes | DATS-008 and DATS-010 | benchmark gate | PASS |
| Multilingual equivalence | translation changes semantics | locale-neutral codes; English seed | DE/EN paired corpus | NOT TESTED |
| Multitenancy/privacy | corpus leaks tenant or personal data | synthetic tenant-neutral inputs | contract and review | PASS |
| External E2E | local result is called deployment evidence | development-only evidence label | CI/release review | NOT TESTED |

## Versioning rule

Accepted results are append-only in meaning. Any semantic change to an input, expected result,
scoring rule or case membership creates a new dataset version. Typographic corrections may retain
the version only when they cannot affect execution or interpretation.

## Residual limits

The corpus is small, synthetic, English-only and owned by the project whose engine it evaluates. It
detects deterministic regression but does not establish external validity, domain completeness,
production reliability, OWASP certification or legal compliance. A future release requires an
independent maintainer to approve expected-result changes.
