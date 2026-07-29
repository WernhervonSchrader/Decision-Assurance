# Controlled Intake Benchmark v0.3

The 13 cases are independent from the structured DATS corpus. Each directory contains the
untrusted `raw_input.txt`, the contract-level `request.json`, trusted tenant context in
`trusted_context.json`, and test-only expectations in `expected.json`. Production code never
loads these expectations.
