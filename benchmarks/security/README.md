# Decision Assurance security benchmark v0.1

This is a falsification suite, not certification. It separates original LLMail observations,
fresh agent measurements, real DA governance/lifecycle observations and simulated execution.
External models and real effects are disabled. A disabled agent yields `INCONCLUSIVE`, not PASS.

Run from a repository checkout with the project and dev dependencies installed:

```powershell
python -m decision_assurance.security_benchmark run --profile smoke --output .cache/security-smoke --locale de
```

The 27-case smoke run exits **2** because it observes four existing target weaknesses. To
verify that results match the reviewed project regression fixture, while retaining every failure:

```powershell
python -m decision_assurance.security_benchmark run --profile smoke --output .cache/security-smoke --baseline benchmarks/security/baselines/smoke-v0.1.json --locale en
```

Exit 0 with that baseline means unchanged benchmark behavior, **not** secure DA or accepted
production risk. Infrastructure/test errors exit 3; invalid command/input raises a Click error.
`report.json` and `report.md` contain explicit denominators, failed properties, unknowns and scope.
Use `--locale de|en`; absent selection uses LC_ALL/LANG and English fallback. Machine codes stay
stable and machine-readable explanatory metadata is English.

## Acquisition and standard profile

Only this acquisition command uses the network. It verifies exact source hosts, redirects,
immutable revision, sizes and SHA256; resumes bounded HTTP byte ranges and never executes content.
About 2.45 GB is acquired including annotations; allow additional space for derived index/reports.
Keep raw data and output under the ignored `.cache/` directory.

```powershell
python -m decision_assurance.security_benchmark import-dataset --output .cache/security-benchmark/llmail --include-annotations
python -m decision_assurance.security_benchmark prepare --raw-root .cache/security-benchmark/llmail --index .cache/security-benchmark/index.sqlite --profile standard --seed 42 --output .cache/security-benchmark/standard-cases.json
python -m decision_assurance.security_benchmark run --profile standard --cases .cache/security-benchmark/standard-cases.json --payload-root .cache/security-benchmark/llmail --output .cache/security-standard --checkpoint .cache/security-standard/checkpoint.jsonl --locale de
```

Standard contains 1,000 submissions with exact original `attack_attempt=True` annotations,
all 203 benign FP emails (including original duplicates), and 112 B/C cases. Selection uses
payload-hash dedup and seeded SHA256 ranking, round-robin across original level plus the first
derived heuristic category. It is a coverage sample, not proportional population estimation.
Original labels and derived categories are different fields. Conflicting/unmatched annotations
are unknown and excluded from the attack sampling pool. Reusing seed/revision reproduces cases.

## Full profile and checkpoints

```powershell
python -m decision_assurance.security_benchmark run --profile full --payload-root .cache/security-benchmark/llmail --output .cache/security-full --locale en
```

Full retains all 461,640 raw submissions, adds 203 FP emails and 112 own cases, and processes
1,000-case batches with per-batch hash-linked checkpoints. It does not discard raw duplicates.
Full original attack-attempt annotations are not joined at run time; fresh model measurements
remain unavailable. Raw source checksums are verified before iteration. Re-running the command
checks completed batches and resumes. `results.jsonl` is the complete stream; `report.json`
retains bounded management samples and aggregate metrics. Duplicate IDs use an on-disk index.
Checkpoint identity binds the cases, profile, seed and implementation fingerprint. Changed code
or input requires a new output/checkpoint directory; corrupted/truncated checkpoints fail closed.
The fingerprint covers DA source/contracts and records the Python/dependency versions. Resumed
source cases reverify their payload bytes. Reports distinguish reused observations from fresh
case measurements and newly invoked security components.

Compare complete standard/smoke reports or full JSONL streams:

```powershell
python -m decision_assurance.security_benchmark compare --baseline previous/report.json --report current/report.json
```

Case set, dataset lock and run identity must match. Changed safety signals (including improvements)
require review; missing components, audit events, evidence/freshness checks or cases cannot pass.
Full comparisons verify both complete stream checksums and compare every row; summary samples
are never used as the regression population.

## Safety and publication

Raw datasets, original system prompts and source URLs are data, never tool permissions.
The optional `AgentPort` is an in-process integration seam only; no network model implementation,
credentials or enable-live flag is shipped. A future live adapter requires a separate reviewed
provider/cost/rate-limit/privacy/approval design. Do not add real mail or purchase sinks.

Original-content reconstruction can be verified after acquisition with `python -m decision_assurance.security_benchmark verify-fixtures --raw-root .cache/security-benchmark/llmail`.

Only 8 minimal original submission texts and 4 original simulated benign emails are bundled.
Wrappers omit participant IDs/timestamps while preserving attack subject/body and original
objectives exactly. `fixtures/source-manifest.json` binds original offsets/record hashes and
source-file hashes; the full raw originals stay in cache. `.gitattributes` prevents newline
conversion of fixture bytes. The subset was reviewed as data-only, with no credentials or
active executable content; the one email target is the upstream synthetic challenge target.
Automated triage is not exhaustive PII detection and never authorizes bulk publication.

See [methodology and findings](../../docs/security/DA-SECURITY-BENCHMARK-v0.1.md),
[coverage](../../docs/security/SECURITY-COVERAGE-MATRIX-v0.1.md),
[design](../../docs/specifications/DA-SECURITY-BENCHMARK-v0.1-DESIGN.md) and
[implementation plan](../../docs/specifications/DA-SECURITY-BENCHMARK-v0.1-IMPLEMENTATION-PLAN.md).
