# Suite: security (Track S — Sentinel)

Adversarial cases = **surface × technique × objective** (+ modality). See
`../../docs/attack-taxonomy.md` and `../../docs/scoring-and-judging.md`.

## Planned manifest (M1→M2)

- `cases/` — authored seed cases (one malicious intent + ground-truth label each).
- `transforms/` — technique transforms (encoding, leetspeak, payload-split, zero-width,
  many-shot, low-resource, past-tense, ASCII art, social-engineering).
- `modality/` — image (FigStep + realistic surfaces) and audio (TTS) renderers.
- `benign/` — over-refusal control cases (legitimate look-alikes per objective).
- `vendor/<source>/PROVENANCE.md` — vendored external sets (AgentDojo, RedCode, CyberSecEval,
  FigStep/SafeBench, AJailBench, …) per `../../docs/reuse-map.md`.

## Scoring

L0 deterministic (canary + structural) → L1 sandbox side-effect → L2 LLM-judge rubric.
Metrics: ASR, Refusal, Utility-under-attack, Over-refusal — sliced by every axis.

## M1 smoke target

~20 cases: 4 techniques × 3 objectives, `direct_turn` + `repo_file` surfaces, text only.
