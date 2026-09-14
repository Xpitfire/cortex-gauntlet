# Harness Adapters

Each adapter implements the Inspect AI **Solver** interface and returns a normalized
`Transcript` for a `Case`, so tracks/scorers are harness-agnostic. Authored M1 (one) → M3 (all).

| Adapter | Drives | Notes |
| --- | --- | --- |
| `claude_code` | Claude Code harness | Product scaffold; reported separately from raw API |
| `codex_cli` | OpenAI Codex CLI | Reuse OpenClaw `cortex-codex-app-server.sh` bootstrap |
| `codex_cloud` | Codex cloud | Same contract, hosted execution |
| `opencode` | OpenCode — open-source CLI agent (sst/opencode) | OSS alternative; drives `opencode run` |
| `raw_api` | Anthropic/OpenAI API, minimal 2-tool scaffold | Isolates **model** from harness |
| `cortex_wrapped` | Cortex harness over a model | The thesis subject for **harness delta** |

## Contract

- `run(case, sandbox) -> Transcript` — uniform across adapters.
- Declare capabilities: tools, multimodal (image/audio), max context.
- **Normalize token/attempt budget** so comparisons are fair (a known leaderboard confounder).
- All tool execution goes through the sandbox's **capture-only shims** (no payload runs).
- Record cost/efficiency: tokens, wall-clock, tool-calls, retries.

## Comparison

`cortex_wrapped` vs `raw_api`/`codex_cli`/`claude_code` on the same model/case/seed yields the
**harness delta** — the headline cross-cut in every report.
