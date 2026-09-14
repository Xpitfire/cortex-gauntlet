# Schemas

JSON Schemas that the benchmark data contract is built on. Authored in M1; everything the report
consumes validates here. Planned schema set:

| Schema | Purpose | Key fields |
| --- | --- | --- |
| `case.schema.json` | One test unit | `id`, `track`, `surface/technique/objective` (S) or `app_spec/features/guardrails` (G), `seed`, `modality`, `variant`, `ground_truth`, `held_out` |
| `transcript.schema.json` | A harness run on a case | `harness`, `model`, `messages`, `trajectory`, `proposed_tool_calls` (never executed), `tokens`, `wall_clock_ms`, `tool_calls`, `retries` |
| `score.schema.json` | One scorer's verdict | `dimension`, `instrument` (D\|X\|J\|H), `value`, `confidence`, `evidence_refs`, `detail` |
| `finding.schema.json` | SAST/dep finding (Q) | `cwe`, `severity`, `tool`, `location`, `sarif_ref` |
| `runrecord.schema.json` | Full run for the report | `run_id`, `config` (seeds/temp/pass@k), `cases[]`, `scores[]`, `aggregates`, `harness_delta`, `methodology`, `containment_attestation` |

## Conventions

- Stable enums (not free strings) for `track`, `surface`, `technique`, `objective`, `instrument`,
  `modality` — mirrored by Python enums in the runtime.
- `evidence_refs` point into stored artifacts (transcript span, SARIF finding, sink hit, judge
  rationale) so every number in the report is one click from its proof.
- Versioned (`schema_version`); the report builder pins the version it understands.
