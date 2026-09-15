"""The Docs tab: a research-paper-styled, math-rendered formalization of the Cortex governance layer
and the evaluation metrics used in this study.

Self-contained page (KaTeX for LaTeX, marked for Markdown, inline theme-aware SVG figures, sticky TOC).
The paper separates conditional finite-lattice results from the stochastic runtime and from
historical benchmark measurements. Symbolic identities and finite examples in docs/proofs.py
are checks of selected formulas, not a formal verification of the agent implementation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .paper_results import render_exhibits
from .report_common import COMMON_JS, REPORT_CSS, REPORT_HEAD, navbar

# ---- theme-aware SVG figures (use CSS vars so they adapt to light/dark) ------------------------
_FIG_LOOP = r"""
<svg viewBox="0 0 760 270" xmlns="http://www.w3.org/2000/svg" class="figsvg" role="img"
     aria-label="Operational repair loop: code revisions require fresh validation and may invalidate earlier certificates">
  <defs><marker id="loop-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
    <path d="M0,0 L7,3 L0,6 Z" fill="var(--accent)"/></marker></defs>
  <g fill="var(--card)" stroke="var(--line)" stroke-width="1.5">
    <rect x="12" y="94" width="128" height="76" rx="12"/>
    <rect x="164" y="94" width="128" height="76" rx="12"/>
    <rect x="316" y="94" width="128" height="76" rx="12" stroke="var(--accent)"/>
    <rect x="468" y="94" width="128" height="76" rx="12"/>
    <rect x="620" y="94" width="128" height="76" rx="12"/>
    <rect x="602" y="210" width="146" height="44" rx="10"/>
  </g>
  <g font-size="16" font-weight="700" fill="var(--ink)" text-anchor="middle">
    <text x="76" y="124">Analyze</text><text x="228" y="124">Plan</text>
    <text x="380" y="124">Execute</text><text x="532" y="124">Validate</text>
    <text x="684" y="124">Coordinate</text>
  </g>
  <g font-size="13" fill="var(--muted)" text-anchor="middle">
    <text x="76" y="148">requirements</text><text x="228" y="148">milestones + checks</text>
    <text x="380" y="148">candidate revision</text><text x="532" y="148">fresh evidence</text>
    <text x="684" y="148">decide next step</text>
    <text x="532" y="30">repair + revalidate</text>
    <text x="675" y="237" fill="var(--ink)">accept or stop</text>
  </g>
  <g fill="none" stroke="var(--accent)" stroke-width="2" marker-end="url(#loop-arrow)">
    <path d="M142 132 H162"/><path d="M294 132 H314"/>
    <path d="M446 132 H466"/><path d="M598 132 H618"/>
    <path d="M684 94 V74 Q684 54 664 54 H400 Q380 54 380 74 V94"/>
    <path d="M684 172 V208"/>
  </g>
  <g font-size="14" fill="var(--muted)">
    <text x="12" y="219">Code repairs can invalidate earlier certificates.</text>
    <text x="12" y="242">Re-check changed and dependent requirements.</text>
  </g>
</svg>"""

_FIG_LATTICE = r"""
<svg viewBox="0 0 640 306" xmlns="http://www.w3.org/2000/svg" class="figsvg" role="img"
     aria-label="Illustrative monotone closure under A2; the least fixed point can be a proper subset of all requirements">
  <defs><marker id="closure-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
    <path d="M0,0 L7,3 L0,6 Z" fill="var(--accent)"/></marker></defs>
  <g font-size="14" fill="var(--muted)">
    <text x="80" y="24">certified set size |S<tspan baseline-shift="sub" font-size="70%">k</tspan>|</text>
    <text x="620" y="24" text-anchor="end">fixed monotone Φ · schematic</text>
    <path d="M80 48 V240 H606" fill="none" stroke="var(--muted)" stroke-width="1.5"/>
    <path d="M80 70 H598 M80 128 H598" fill="none" stroke="var(--line)" stroke-dasharray="4 5"/>
    <text x="66" y="75" text-anchor="end">|R|</text>
    <text x="66" y="133" text-anchor="end">|S*|</text>
    <text x="80" y="263" text-anchor="middle">0</text><text x="190" y="263" text-anchor="middle">1</text>
    <text x="300" y="263" text-anchor="middle">2</text><text x="410" y="263" text-anchor="middle">3</text>
    <text x="530" y="263" text-anchor="middle">4</text>
    <text x="350" y="293" text-anchor="middle">operator applications k (illustrative)</text>
    <path d="M594 74 H600 V124 H594" fill="none" stroke="var(--muted)"/>
    <text x="584" y="92" text-anchor="end">unresolved</text>
    <text x="584" y="111" text-anchor="end">requirements</text>
  </g>
  <g fill="none" stroke="var(--accent)" stroke-width="2" marker-end="url(#closure-arrow)">
    <path d="M86 236 L182 195"/><path d="M198 189 L292 153"/><path d="M308 147 L402 130"/>
    <path d="M420 128 H521" stroke-dasharray="5 5"/>
  </g>
  <g fill="var(--accent)" stroke="var(--accent)">
    <circle cx="80" cy="240" r="5"/><circle cx="190" cy="192" r="6"/>
    <circle cx="300" cy="150" r="6"/><circle cx="410" cy="128" r="7"/>
    <circle cx="530" cy="128" r="6" fill="var(--card)" stroke-width="2"/>
  </g>
  <g font-size="14" fill="var(--ink)" text-anchor="middle">
    <text x="97" y="219">∅</text><text x="190" y="177">Φ(∅)</text>
    <text x="300" y="135">Φ²(∅)</text><text x="401" y="111">S* = lfp(Φ)</text>
    <text x="498" y="158">Φ(S*) = S*</text>
    <text x="498" y="180" font-size="13" fill="var(--muted)">closure need not mean PASS</text>
  </g>
</svg>"""

_FIG_VERTEX = r"""
<svg viewBox="0 0 760 356" xmlns="http://www.w3.org/2000/svg" class="figsvg" role="img"
     aria-label="Illustrative VERTEX similarity matrices: bidirectional best matches and a monotone descriptor-alignment path">
  <defs><g id="vertex-grid">
    <g fill="var(--accent)">
      <rect x="0" y="0" width="40" height="40" opacity=".85"/>
      <rect x="40" y="0" width="40" height="40" opacity=".25"/>
      <rect x="80" y="0" width="40" height="40" opacity=".15"/>
      <rect x="120" y="0" width="40" height="40" opacity=".10"/>
      <rect x="0" y="40" width="40" height="40" opacity=".25"/>
      <rect x="40" y="40" width="40" height="40" opacity=".80"/>
      <rect x="80" y="40" width="40" height="40" opacity=".25"/>
      <rect x="120" y="40" width="40" height="40" opacity=".10"/>
      <rect x="0" y="80" width="40" height="40" opacity=".12"/>
      <rect x="40" y="80" width="40" height="40" opacity=".30"/>
      <rect x="80" y="80" width="40" height="40" opacity=".82"/>
      <rect x="120" y="80" width="40" height="40" opacity=".30"/>
      <rect x="0" y="120" width="40" height="40" opacity=".10"/>
      <rect x="40" y="120" width="40" height="40" opacity=".15"/>
      <rect x="80" y="120" width="40" height="40" opacity=".30"/>
      <rect x="120" y="120" width="40" height="40" opacity=".85"/>
    </g>
    <path d="M0 0H160V160H0Z M40 0V160 M80 0V160 M120 0V160 M0 40H160 M0 80H160 M0 120H160"
          fill="none" stroke="var(--line)"/>
    <g font-size="14" fill="var(--muted)" text-anchor="middle">
      <text x="20" y="-12">r₁</text><text x="60" y="-12">r₂</text>
      <text x="100" y="-12">r₃</text><text x="140" y="-12">r₄</text>
      <text x="-18" y="25">c₁</text><text x="-18" y="65">c₂</text>
      <text x="-18" y="105">c₃</text><text x="-18" y="145">c₄</text>
    </g>
  </g></defs>
  <g font-size="16" fill="var(--ink)" font-weight="600" text-anchor="middle">
    <text x="196" y="28">Presence: best matches</text>
    <text x="576" y="28">Order: monotone DTW path</text>
  </g>
  <g font-size="13" fill="var(--muted)" text-anchor="middle">
    <text x="196" y="52">illustrative similarities, not measurements</text>
    <text x="576" y="52">descriptor positions, not elapsed time</text>
    <text x="196" y="281">stronger fill = higher similarity</text>
    <text x="576" y="281">one illustrative admissible path</text>
  </g>
  <use href="#vertex-grid" x="116" y="100"/><use href="#vertex-grid" x="496" y="100"/>
  <g transform="translate(496,100)" fill="var(--card)" stroke="var(--ink)" stroke-width="2.5">
    <polyline points="20,20 60,60 100,60 100,100 140,140" fill="none"/>
    <circle cx="20" cy="20" r="4"/><circle cx="60" cy="60" r="4"/>
    <circle cx="100" cy="60" r="4"/><circle cx="100" cy="100" r="4"/><circle cx="140" cy="140" r="4"/>
  </g>
  <g font-size="14" fill="var(--ink)" text-anchor="middle">
    <text x="380" y="318">Sᵢⱼ = ⟨φ(cᵢ), φ(rⱼ)⟩</text>
    <text x="380" y="343">step cost: (1 − Sᵢⱼ) [1 + λ |(i − 1)/m − (j − 1)/n|]</text>
  </g>
</svg>"""

# Historical counts and stored Wilson intervals from the source named in Section 7.
_SAFETY_ROWS = (
    ("Codex raw", 25, 59, .3061, .5507, "var(--muted)"),
    ("Cortex over Codex", 14, 58, .1496, .3653, "var(--accent)"),
    ("Claude raw", 2, 59, .0093, .1154, "var(--muted)"),
    ("Cortex over Claude", 1, 60, .0029, .0886, "var(--accent)"),
    ("OpenCode", 23, 54, .3033, .5584, "var(--muted)"),
)


def _safety_figure() -> str:
    rows = []
    for index, (label, successes, attempts, low, high, color) in enumerate(_SAFETY_ROWS):
        y = 100 + index * 48
        x = 280 + 500 * successes / attempts
        left, right = 280 + 500 * low, 280 + 500 * high
        rows.append(
            f'<g data-successes="{successes}" data-attempts="{attempts}">'
            f'<text x="16" y="{y + 5}" fill="var(--ink)">{label}</text>'
            f'<path d="M{left} {y}H{right} M{left} {y - 5}V{y + 5} M{right} {y - 5}V{y + 5}" '
            f'fill="none" stroke="{color}" stroke-width="2"/>'
            f'<circle cx="{x}" cy="{y}" r="5" fill="{color}"/>'
            f'<text x="744" y="{y + 5}" text-anchor="end" fill="var(--ink)">'
            f'{100 * successes / attempts:.2f}% · {successes} / {attempts}</text></g>'
        )
    ticks = "".join(
        f'<path d="M{280 + 50 * tick} 82V310" stroke="var(--line)" stroke-dasharray="4 5"/>'
        f'<text x="{280 + 50 * tick}" y="330" text-anchor="middle">{10 * tick}%</text>'
        for tick in range(7)
    )
    return (
        '<svg viewBox="0 0 760 390" xmlns="http://www.w3.org/2000/svg" class="figsvg" role="img" '
        'aria-label="Historical classified attack-success point estimates and stored 95 percent Wilson intervals; unmatched samples, not causal comparisons">'
        '<text x="16" y="26" font-size="16" font-weight="600" fill="var(--ink)">'
        'Historical classified attack success</text>'
        '<text x="16" y="51" font-size="14" fill="var(--muted)">'
        'Points: observed rates · Whiskers: stored 95% Wilson intervals</text>'
        '<g font-size="13" fill="var(--muted)">'
        '<text x="744" y="75" text-anchor="end">ASR · successes / attempts</text>'
        f'{ticks}</g><g font-size="14">{ "".join(rows) }</g>'
        '<text x="430" y="357" text-anchor="middle" font-size="14" fill="var(--muted)">'
        'classified attack-success rate</text>'
        '<text x="380" y="381" text-anchor="middle" font-size="13" fill="var(--muted)">'
        'Unmatched historical case coverage — not a causal or safety guarantee</text></svg>'
    )


# ---- citation metadata for hover preview cards (faithful one/two-sentence summaries of each cited work) -
CITES: dict[str, dict[str, str]] = {
    "1": {"title": "SymbolicAI: A framework for logic-based approaches combining generative models and solvers",
          "meta": "Dinu, Leoveanu-Condrei, Holzleitner, Zellinger & Hochreiter, 2024 · arXiv:2402.00854",
          "url": "https://arxiv.org/abs/2402.00854",
          "abstract": "Presents a relational-trajectory metric: Gaussian-kernel cross-similarity of node "
          "embeddings against a reference distribution, normalized against a fixed random-sequence "
          "baseline."},
    "2": {"title": "The Semantics of Predicate Logic as a Programming Language",
          "meta": "van Emden & Kowalski, 1976 · J. ACM 23(4)",
          "url": "https://dl.acm.org/doi/10.1145/321978.321991",
          "abstract": "Establishes the fixpoint, model-theoretic, and operational semantics of Horn-clause "
          "programs, showing the least fixed point of the immediate-consequence operator T_P is the "
          "program's least Herbrand model — the template for our consequence operator Φ."},
    "3": {"title": "A lattice-theoretical fixpoint theorem and its applications",
          "meta": "Tarski, 1955 · Pacific J. Math 5(2)",
          "url": "https://projecteuclid.org/journals/pacific-journal-of-mathematics/volume-5/issue-2/A-lattice-theoretical-fixpoint-theorem-and-its-applications/pjm/1103044538.full",
          "abstract": "Proves that a monotone map on a complete lattice has a complete lattice of fixed "
          "points, with a least and greatest element — the existence half of Theorem 1."},
    "4": {"title": "Introduction to Metamathematics",
          "meta": "Kleene, 1952 · North-Holland",
          "url": "",
          "abstract": "Introduces the recursion theorem and the construction of least fixed points by "
          "iteration (Kleene iteration), the constructive route to lfp(Φ)."},
    "5": {"title": "Sur les opérations dans les ensembles abstraits (contraction mapping)",
          "meta": "Banach, 1922 · Fund. Math. 3",
          "url": "https://doi.org/10.4064/fm-3-1-133-181",
          "abstract": "The contraction mapping principle: a contraction on a complete metric space has a "
          "unique fixed point reached by iteration — the metric analogue of our lattice argument."},
    "6": {"title": "Neurosymbolic AI: the 3rd wave",
          "meta": "Garcez & Lamb, 2023 · Artif. Intell. Review 56(11)",
          "url": "https://arxiv.org/abs/2012.05876",
          "abstract": "Surveys the integration of neural learning with symbolic reasoning, arguing for it "
          "as the next wave of AI and outlining the open research challenges."},
    "7": {"title": "The Third AI Summer",
          "meta": "Kautz, 2022 · AI Magazine 43(1) (AAAI Engelmore Lecture)",
          "url": "https://doi.org/10.1002/aaai.12036",
          "abstract": "Gives a historical framing of AI's progress and a taxonomy of neurosymbolic "
          "architectures by how neural and symbolic components are combined."},
    "8": {"title": "Human Problem Solving",
          "meta": "Newell & Simon, 1972 · Prentice-Hall",
          "url": "",
          "abstract": "Foundational account of problem solving as search in a problem space using "
          "production-like operators — the cognitive ancestor of the recognize–act completion loop."},
    "9": {"title": "SOAR: An architecture for general intelligence",
          "meta": "Laird, Newell & Rosenbloom, 1987 · Artif. Intell. 33(1)",
          "url": "https://doi.org/10.1016/0004-3702(87)90050-6",
          "abstract": "A general cognitive architecture built on problem-space search and chunking; "
          "a canonical production-system agent."},
    "10": {"title": "An Integrated Theory of the Mind",
           "meta": "Anderson et al., 2004 · Psychological Review 111(4)",
           "url": "https://doi.org/10.1037/0033-295X.111.4.1036",
           "abstract": "Models cognition as interacting modules coordinated by a production system that "
           "repeatedly fires matched rules — the recognize–act cycle our loop instantiates."},
    "11": {"title": "BERTScore: Evaluating Text Generation with BERT",
           "meta": "Zhang et al., 2020 · ICLR",
           "url": "https://arxiv.org/abs/1904.09675",
           "abstract": "A text-generation metric using contextual embeddings and greedy bidirectional "
           "matching to produce precision, recall, and F1 — the basis for VERTEX's presence component."},
    "12": {"title": "Dynamic programming algorithm optimization for spoken word recognition",
           "meta": "Sakoe & Chiba, 1978 · IEEE Trans. ASSP 26(1)",
           "url": "https://doi.org/10.1109/TASSP.1978.1163055",
           "abstract": "The dynamic time warping algorithm: aligns two sequences under monotone warping by "
           "dynamic programming — the basis for VERTEX's order component."},
    "13": {"title": "Probable inference, the law of succession, and statistical inference",
           "meta": "Wilson, 1927 · JASA 22(158)",
           "url": "https://doi.org/10.1080/01621459.1927.10502953",
           "abstract": "Derives the score confidence interval for a binomial proportion by inverting the "
           "normal score test — the interval we report for attack-success rates."},
    "14": {"title": "Bootstrap methods: another look at the jackknife",
           "meta": "Efron, 1979 · Annals of Statistics 7(1)",
           "url": "https://doi.org/10.1214/aos/1176344552",
           "abstract": "Introduces the bootstrap: estimating a statistic's sampling distribution by "
           "resampling the observed data with replacement."},
    "15": {"title": "Evaluating Large Language Models Trained on Code (Codex)",
           "meta": "Chen et al., 2021 · arXiv:2107.03374",
           "url": "https://arxiv.org/abs/2107.03374",
           "abstract": "Evaluates code LLMs and introduces the unbiased pass@k estimator and the HumanEval "
           "benchmark; pass@k underlies our any-seed attack-success estimator."},
    "16": {"title": "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment",
           "meta": "Liu et al., 2023 · EMNLP · arXiv:2303.16634",
           "url": "https://arxiv.org/abs/2303.16634",
           "abstract": "Uses an LLM with chain-of-thought and form-filling to score generated text, improving "
           "correlation with human judgments — methodology for our gated qualitative judges."},
    "17": {"title": "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena",
           "meta": "Zheng et al., 2023 · NeurIPS · arXiv:2306.05685",
           "url": "https://arxiv.org/abs/2306.05685",
           "abstract": "Characterizes position, verbosity, and self-preference biases in LLM judging; "
           "motivates separate validation of Gauntlet's judges. Absolute rubrics avoid pairwise "
           "presentation but do not establish mitigation of the other biases."},
    "18": {"title": "Prometheus 2: an open LM specialized in evaluating other LMs",
           "meta": "Kim et al., 2024 · arXiv:2405.01535",
           "url": "https://arxiv.org/abs/2405.01535",
           "abstract": "An open evaluator language model approximating GPT-4-level judgment for both direct "
           "scoring and pairwise ranking of model outputs."},
    "19": {"title": "Large Language Models Can Self-Improve At Web Agent Tasks",
           "meta": "Patel et al., 2024 · arXiv:2405.20309",
           "url": "https://arxiv.org/abs/2405.20309",
           "abstract": "Studies self-improvement of LLM web agents and evaluation of agent trajectories. "
           "Background for trajectory evaluation, not a proof of this report's scoring formula."},
    "20": {"title": "Compromising real-world LLM apps with indirect prompt injection",
           "meta": "Greshake et al., 2023 · ACM AISec · arXiv:2302.12173",
           "url": "https://arxiv.org/abs/2302.12173",
           "abstract": "Demonstrates indirect prompt-injection attacks that hijack LLM-integrated "
           "applications via poisoned retrieved/tool content — the basis for our indirect attack surfaces."},
    "21": {"title": "Scaling Laws for Agent Harnesses via Effective Feedback Compute",
           "meta": "Zhang, Wang, Xu, Zhu & Che, 2026 · arXiv:2605.29682",
           "url": "https://arxiv.org/abs/2605.29682",
           "abstract": "Introduces Effective Feedback Compute (EFC): a trace-level scaling coordinate "
           "that credits feedback only when it is informative, valid, non-redundant, and retained for "
           "later decisions. EFC predicts agent failure rates far better than raw-compute coordinates "
           "(tokens, tool calls), suggesting harness scaling is governed by how efficiently budget is "
           "converted into durable, task-sufficient feedback."},
    "22": {"title": "Information Value Theory",
           "meta": "Howard, 1966 · IEEE Trans. Systems Science & Cybernetics 2(1)",
           "url": "https://doi.org/10.1109/TSSC.1966.300074",
           "abstract": "Assigns a decision-theoretic value to reducing or eliminating uncertainty by "
           "jointly modeling probabilistic and economic factors; information has positive value only "
           "when it can change a decision — the foundation for crediting only informative feedback."},
    "23": {"title": "Principles of metareasoning",
           "meta": "Russell & Wefald, 1991 · Artificial Intelligence 49(1–3)",
           "url": "https://doi.org/10.1016/0004-3702(91)90015-C",
           "abstract": "Founds rational metareasoning: select computational actions by their value of "
           "computation (VOC), balancing expected utility gain against cost — a basis for resource-"
           "bounded rationality and for a coordinator that decides when further computation is worthwhile."},
    "24": {"title": "Scaling Laws for Neural Language Models",
           "meta": "Kaplan et al., 2020 · arXiv:2001.08361",
           "url": "https://arxiv.org/abs/2001.08361",
           "abstract": "Establishes power-law relationships between model size, dataset size, training "
           "compute, and loss — the origin of the modern scaling-law program."},
    "25": {"title": "Training Compute-Optimal Large Language Models (Chinchilla)",
           "meta": "Hoffmann et al., 2022 · arXiv:2203.15556",
           "url": "https://arxiv.org/abs/2203.15556",
           "abstract": "Shows compute-optimal training balances model size against the number of training "
           "tokens, correcting earlier scaling prescriptions."},
    "26": {"title": "Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters",
           "meta": "Snell et al., 2024 · arXiv:2408.03314",
           "url": "https://arxiv.org/abs/2408.03314",
           "abstract": "Shows that allocating more inference-time compute (search, revision) under an "
           "optimal policy can beat scaling model parameters for reasoning tasks."},
    "27": {"title": "Large Language Monkeys: Scaling Inference Compute with Repeated Sampling",
           "meta": "Brown et al., 2024 · arXiv:2407.21787",
           "url": "https://arxiv.org/abs/2407.21787",
           "abstract": "Finds that coverage (the chance at least one sample is correct) grows predictably "
           "with the number of repeated samples, a simple inference-time scaling axis."},
    "28": {"title": "Let's Verify Step by Step",
           "meta": "Lightman et al., 2024 · ICLR · arXiv:2305.20050",
           "url": "https://arxiv.org/abs/2305.20050",
           "abstract": "Shows process-supervised reward models (rewarding correct intermediate steps) "
           "outperform outcome supervision on reasoning — feedback on the trajectory, not just the result."},
    "29": {"title": "Self-Refine: Iterative Refinement with Self-Feedback",
           "meta": "Madaan et al., 2023 · NeurIPS · arXiv:2303.17651",
           "url": "https://arxiv.org/abs/2303.17651",
           "abstract": "An LLM iteratively critiques and revises its own output with no extra training — a "
           "single-model instance of the execute–validate–repair loop we formalize."},
    "30": {"title": "Reflexion: Language Agents with Verbal Reinforcement Learning",
           "meta": "Shinn et al., 2023 · NeurIPS · arXiv:2303.11366",
           "url": "https://arxiv.org/abs/2303.11366",
           "abstract": "Agents retain verbal self-reflections in episodic memory to inform later attempts."},
    "31": {"title": "ReAct: Synergizing Reasoning and Acting in Language Models",
           "meta": "Yao et al., 2023 · ICLR · arXiv:2210.03629",
           "url": "https://arxiv.org/abs/2210.03629",
           "abstract": "Interleaves reasoning traces with actions and incorporates observations from "
           "the environment into subsequent decisions."},
    "32": {"title": "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?",
           "meta": "Jimenez et al., 2024 · ICLR · arXiv:2310.06770",
           "url": "https://arxiv.org/abs/2310.06770",
           "abstract": "Repository issue-resolution tasks derived from GitHub, evaluated with "
           "task-specific tests on the proposed code changes."},
    "33": {"title": "SWE-bench Verified",
           "meta": "OpenAI, 2024 · human-validated subset",
           "url": "https://openai.com/index/introducing-swe-bench-verified/",
           "abstract": "A 500-instance SWE-bench subset filtered by human annotators for issue clarity "
           "and test validity. Each instance concerns a repository issue, not a prescribed number of agent steps."},
    "34": {"title": "SWE-bench Goes Live!",
           "meta": "Zhang et al., 2025 · arXiv:2505.23419",
           "url": "https://arxiv.org/abs/2505.23419",
           "abstract": "A continuously updated, contamination-resistant SWE-bench variant built from recent "
           "repository activity, addressing data leakage for single-issue resolution."},
    "35": {"title": "Terminal-Bench: Benchmarking Agents on Hard, Realistic Command-Line Tasks",
           "meta": "Merrill et al., 2026 · arXiv:2601.11868 · tbench.ai",
           "url": "https://arxiv.org/abs/2601.11868",
           "abstract": "Evaluates agents on hard command-line tasks in sandboxed environments, "
           "including software, system administration, data, and security tasks with verification tests."},
    "36": {"title": "Commit0: Library Generation from Scratch",
           "meta": "Zhao et al., 2025 · ICLR · arXiv:2412.01769",
           "url": "https://arxiv.org/abs/2412.01769",
           "abstract": "Agents implement Python libraries from API specifications and interactive "
           "unit tests, using static-analysis and execution feedback."},
    "37": {"title": "LiveCodeBench: Holistic and Contamination-Free Evaluation of LLMs for Code",
           "meta": "Jain et al., 2025 · ICLR · arXiv:2403.07974",
           "url": "https://arxiv.org/abs/2403.07974",
           "abstract": "A continuously updated suite of competitive-programming problems covering "
           "code generation, self-repair, execution, and test-output prediction."},
    "38": {"title": "Purple Llama CyberSecEval: Security benchmark for LLM coding assistants",
           "meta": "Bhatt et al., 2023 · arXiv:2312.04724",
           "url": "https://arxiv.org/abs/2312.04724",
           "abstract": "Measures insecure-code generation and compliance with requests to assist cyberattacks."},
    "39": {"title": "AgentDojo: Evaluating Prompt-Injection Attacks and Defenses for LLM Agents",
           "meta": "Debenedetti et al., 2024 · NeurIPS D&B · arXiv:2406.13352",
           "url": "https://arxiv.org/abs/2406.13352",
           "abstract": "A dynamic tool-use environment for evaluating prompt-injection attacks "
           "and defenses alongside completion of legitimate user tasks."},
    "40": {"title": "InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents",
           "meta": "Zhan et al., 2024 · ACL Findings · arXiv:2403.02691",
           "url": "https://arxiv.org/abs/2403.02691",
           "abstract": "Evaluates indirect prompt injection through tool outputs, including "
           "attacks intended to cause harm or exfiltrate data."},
    "41": {"title": "τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World Domains",
           "meta": "Yao et al., 2024 · arXiv:2406.12045",
           "url": "https://arxiv.org/abs/2406.12045",
           "abstract": "Evaluates tool-using agents through multi-turn simulated-user conversations "
           "and final database-state correctness; introduces repeated-trial reliability metrics."},
    "42": {"title": "AgentBench: Evaluating LLMs as Agents",
           "meta": "Liu et al., 2024 · ICLR · arXiv:2308.03688",
           "url": "https://arxiv.org/abs/2308.03688",
           "abstract": "Evaluates agents across eight interactive environments, including operating "
           "systems, databases, knowledge graphs, web tasks, and games."},
    "43": {"title": "GAIA: a benchmark for General AI Assistants",
           "meta": "Mialon et al., 2024 · ICLR · arXiv:2311.12983",
           "url": "https://arxiv.org/abs/2311.12983",
           "abstract": "Real-world assistant questions requiring reasoning, multimodality, browsing, and tool "
           "use, each with a verifiable answer; agents may use multiple reasoning and tool steps."},
    "44": {"title": "WebArena: A Realistic Web Environment for Building Autonomous Agents",
           "meta": "Zhou et al., 2024 · ICLR · arXiv:2307.13854",
           "url": "https://arxiv.org/abs/2307.13854",
           "abstract": "Functionally graded tasks across self-hosted websites for autonomous browsing agents."},
    "45": {"title": "OSWorld: Benchmarking Multimodal Agents in Real Computer Environments",
           "meta": "Xie et al., 2024 · NeurIPS D&B · arXiv:2404.07972",
           "url": "https://arxiv.org/abs/2404.07972",
           "abstract": "Execution-based evaluation of multimodal GUI agents on open-ended desktop "
           "and web tasks in real computer environments."},
    "46": {"title": "Jailbroken: How Does LLM Safety Training Fail?",
           "meta": "Wei, Haghtalab & Steinhardt, 2023 · NeurIPS · arXiv:2307.02483",
           "url": "https://arxiv.org/abs/2307.02483",
           "abstract": "Attributes jailbreak success to competing objectives and mismatched generalization; "
           "demonstrates limitations of safety training, not a guarantee of Cortex hook coverage."},
    "47": {"title": "COMET: A Neural Framework for MT Evaluation",
           "meta": "Rei, Stewart, Farinha & Lavie, 2020 · EMNLP · arXiv:2009.09025",
           "url": "https://arxiv.org/abs/2009.09025",
           "abstract": "A learned machine-translation evaluator using source, hypothesis and reference. "
           "This cited paper does not establish reference-free VERTEX-QE accuracy."},
    "48": {"title": "SUPERT: Unsupervised Evaluation for Multi-Document Summarization",
           "meta": "Gao, Zhao & Eger, 2020 · ACL · arXiv:2005.03724",
           "url": "https://arxiv.org/abs/2005.03724",
           "abstract": "Builds a pseudo-reference from salient source sentences and scores semantic overlap "
           "with it; background for pseudo-reference evaluation."},
    "49": {"title": "MAUVE: Measuring the Gap Between Neural and Human Text",
           "meta": "Pillutla et al., 2021 · NeurIPS · arXiv:2102.01454",
           "url": "https://arxiv.org/abs/2102.01454",
           "abstract": "Compares generated and reference text distributions via divergence frontiers. "
           "A descriptor union is not an implementation of this distributional metric."},
    "50": {"title": "Minimum Bayes-Risk Decoding for Statistical MT",
           "meta": "Kumar & Byrne, 2004 · NAACL-HLT",
           "url": "https://aclanthology.org/N04-1022/",
           "abstract": "Selects translations by expected utility under a specified risk objective. "
           "The benchmark's fixed-threshold peer union is not this decoding algorithm."},
    "51": {"title": "Maximum Likelihood Estimation of Observer Error-Rates (EM)",
           "meta": "Dawid & Skene, 1979 · J. R. Stat. Soc. C 28(1)",
           "url": "https://www.jstor.org/stable/2346806",
           "abstract": "Estimates observer error rates and latent labels using an EM model. "
           "It does not prove consistency of arbitrary leave-one-out descriptor consensus."},
    "52": {"title": "Representation Learning with Contrastive Predictive Coding",
           "meta": "van den Oord, Li & Vinyals, 2018 · arXiv:1807.03748",
           "url": "https://arxiv.org/abs/1807.03748",
           "abstract": "Introduces a contrastive predictive objective and a mutual-information bound "
           "under sampling assumptions; not an active calibration in this benchmark."},
    "53": {"title": "Snorkel: Rapid Training Data Creation with Weak Supervision",
           "meta": "Ratner et al., 2017 · VLDB 11(3) · arXiv:1711.10160",
           "url": "https://arxiv.org/abs/1711.10160",
           "abstract": "Models weak labeling sources and their dependencies to create probabilistic labels. "
           "The benchmark's source-agreement heuristic does not implement this label model."},
    "54": {"title": "A Mathematical Theory of Communication",
           "meta": "Shannon, 1948 · Bell System Technical Journal 27",
           "url": "https://ieeexplore.ieee.org/document/6773024",
           "abstract": "Founds information theory: the self-information of an event of probability p is "
           "−log2 p bits — the surprisal and risk-bit diagnostics of Section 5.6."},
}

# ---- the paper (Markdown + LaTeX; $…$ inline, $$…$$ display; __FIG_*__ placeholders) ------------
_PAPER = r"""
# Cortex: A Fixed-Point Theory of Governed Coding Agents

**Conditional semantics and an evaluation methodology for governed coding agents.**

<div class="byline">Cortex Research · Technical report · {generated}</div>

<div class="authors">
  <span class="author">Marius-Constantin Dinu</span><span class="sep">·</span><span class="author">Florian Zeba</span>
  <div class="affil">Alpha Omega Labs</div>
</div>

<div class="share">
  <span class="share-label">Share</span>
  <a class="share-btn" data-share="x" aria-label="Share on X" title="Share on X" href="#"><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
  <a class="share-btn" data-share="linkedin" aria-label="Share on LinkedIn" title="Share on LinkedIn" href="#"><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0z"/></svg></a>
  <a class="share-btn" data-share="facebook" aria-label="Share on Facebook" title="Share on Facebook" href="#"><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg></a>
  <a class="share-btn" data-share="whatsapp" aria-label="Share on WhatsApp" title="Share on WhatsApp" href="#"><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></a>
  <button class="share-btn" data-share="copy" aria-label="Copy link" title="Copy link"><svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg></button>
</div>

## Abstract

A *coding agent* combines a large language model (LLM) with a harness that plans, edits,
and executes code. We study **Cortex**, a supervisory layer for pre-execution governance,
requirement tracking, and iterative validation and repair. We formalize requirement closure
on a finite lattice. For a fixed requirement set and a sound, monotone validation rule
with persistent evidence, exhaustive iteration reaches the least fixed point with no more
strict increases than there are requirements. Fair consequence scheduling reaches the
same closure. A separate stochastic model bounds expected completion time under a uniform
positive-progress assumption. These results depend on their stated assumptions; artifact
repair, fallible validation, and finite execution budgets do not satisfy them automatically.

We define Gauntlet's trajectory-similarity and build-gated scores, attack-success estimators,
Wilson intervals, and case-cluster bootstrap summaries. Effective-feedback accounting
counts newly certified requirements, rather than estimating their information value or
utility. The five evaluation families support raw-versus-governed comparisons.
We report retained benchmark observations, including rescoring of existing artifacts;
constructed outcomes are excluded. Unequal observation sets and incomplete provenance
prevent causal claims about governance or measured long-horizon scaling.

## 1. Introduction

An LLM coding harness turns model output into tool calls, file changes, and shell commands.
Task competence and execution control are distinct properties: a capable agent can follow
malicious instructions <sup><a href="#ref-46">46</a>,<a href="#ref-20">20</a></sup>, while a
restricted agent can still leave requirements unresolved on a long task
<sup><a href="#ref-21">21</a></sup>.

**Cortex** configures governance and orchestration around a base harness. Governance applies
pre-execution checks and capability/dependency policies. Orchestration analyzes instructions,
tracks requirements, and coordinates validation and repair within a resource budget.
Action filtering alone does not establish planning competence or complete request-level
safety. Validation may use executable checks, fixed rules, or model-based judgments;
their reliability is a separate evaluation question. We study these contracts through
the **Gauntlet** benchmark framework.

Inference-time sampling, search, and revision trade additional computation for task
performance <sup><a href="#ref-26">26</a>,<a href="#ref-27">27</a></sup>, complementing
training-time scaling laws <sup><a href="#ref-24">24</a>,<a href="#ref-25">25</a></sup>.
The effective-feedback perspective <sup><a href="#ref-21">21</a></sup> motivates tracking
valid, nonredundant feedback that remains useful after later edits, rather than counting
only tokens or tool calls. Our requirement count is an operational measure of retained
progress. Classical value of information <sup><a href="#ref-22">22</a></sup> and value of
computation <sup><a href="#ref-23">23</a></sup> also require beliefs, utilities, and costs;
a ledger update does not determine either value.

We address *(i) what an idealized supervisory layer guarantees under stated assumptions* and
*(ii) how its implemented behavior can be evaluated*. The least fixed point in (i) is the
closure of a specified validation rule, which may leave required work unresolved. The metrics
and comparison protocol in (ii) do not establish that a particular implementation satisfies
the theorem's hypotheses or that historical arm differences isolate governance alone.

### Contributions

- A typed action-filter model and a conditional finite-lattice model of requirement closure
  (Sections 3–4).
- A proof of finite closure, oracle-relative soundness, and fair-schedule independence under
  explicit assumptions (Theorem 1), plus accounting and conditional hitting-time bounds
  (Propositions 1–2).
- Definitions and domain restrictions for the implemented evaluation metrics (Section 5).
- A five-family evaluation protocol, with implementation and historical-evidence limitations
  made explicit rather than treated as experimental conclusions (Sections 6–9).

## 2. Related Work and Theoretical Lineage

**Neurosymbolic and cognitive computation.** Combining neural generation with symbolic
constraints is one form of neurosymbolic integration
<sup><a href="#ref-6">6</a>,<a href="#ref-7">7</a></sup>.
Validation–repair cycles also resemble the repeated rule application of classical
cognitive architectures: the problem-space account of Newell and Simon
<sup><a href="#ref-8">8</a></sup>, SOAR <sup><a href="#ref-9">9</a></sup>, and ACT-R
<sup><a href="#ref-10">10</a></sup>. Section 4 isolates a finite consequence operator,
rather than modeling a complete cognitive architecture.

**Fixed-point semantics.** Our convergence argument rests on the least-fixed-point semantics of monotone
operators: van Emden & Kowalski's immediate-consequence operator and its least fixed point as the
meaning of a logic program <sup><a href="#ref-2">2</a></sup>, the Knaster–Tarski lattice fixed-point
theorem <sup><a href="#ref-3">3</a></sup>, and Kleene iteration <sup><a href="#ref-4">4</a></sup>. Where
an operator is a contraction on a metric space, Banach's theorem <sup><a href="#ref-5">5</a></sup> gives
uniqueness and a rate; we use the lattice formulation because the requirement state space is naturally a
finite complete lattice.

**Evaluation.** Capability over trajectories is scored by VERTEX, defined in Section 5.1: embedding
cross-similarity against a reference descriptor set, with a presence component (BERTScore-style
bidirectional matching <sup><a href="#ref-11">11</a></sup>) and an order component (distance-decayed
dynamic time warping <sup><a href="#ref-12">12</a></sup>), each affinely recalibrated against the
matrix's mean-similarity baseline. Embedding comparison also appears in trajectory
evaluation <sup><a href="#ref-1">1</a>,<a href="#ref-19">19</a></sup>. Gauntlet applies
this construction to extracted descriptors, whose order need not represent an observed
execution trajectory. For integers $1\le k\le n$, the any-seed attack-success estimate
uses $\mathrm{pass}@k$ <sup><a href="#ref-15">15</a></sup>. Under independent trials
with common success probability $p\in[0,1]$, it is unbiased for $1-(1-p)^k$.
Success rates carry Wilson intervals <sup><a href="#ref-13">13</a></sup> and
bootstrap summaries <sup><a href="#ref-14">14</a></sup>.
The optional rubric judge draws on G-Eval <sup><a href="#ref-16">16</a></sup>,
MT-Bench <sup><a href="#ref-17">17</a></sup>, and Prometheus
<sup><a href="#ref-18">18</a></sup>. Their bias analyses motivate judge validation but do not establish
the validity of Gauntlet's judges. Safety draws on the
jailbreak <sup><a href="#ref-46">46</a></sup> and real-world prompt-injection
<sup><a href="#ref-20">20</a></sup> literatures.

**Scaling, test-time compute, and effective feedback.** Training scaling laws relate compute,
data, and loss <sup><a href="#ref-24">24</a>,<a href="#ref-25">25</a></sup>; inference-time
search and revision trade compute for accuracy <sup><a href="#ref-26">26</a>,<a href="#ref-27">27</a></sup>.
Effective-feedback work <sup><a href="#ref-21">21</a></sup> motivates measuring usable feedback.
We count newly certified requirements, as formalized in Section 4.3.
This finite-set accounting identity neither derives an empirical scaling law nor establishes
that equal counts represent equal information or utility.

**Iterative feedback, verification, and metareasoning.** ReAct interleaves reasoning and
interaction <sup><a href="#ref-31">31</a></sup>; Self-Refine and Reflexion study feedback
and revision <sup><a href="#ref-29">29</a>,<a href="#ref-30">30</a></sup>.
Process supervision is a distinct approach to evaluating intermediate reasoning steps
<sup><a href="#ref-28">28</a></sup>. Repository issue resolution is studied in benchmarks
such as SWE-bench <sup><a href="#ref-32">32</a></sup>; it is not the common evaluation
setting of all these methods. Our theorem concerns any operator satisfying its assumptions.
An implementation requires a separate conformance argument. Value of information
<sup><a href="#ref-22">22</a></sup> and rational metareasoning
<sup><a href="#ref-23">23</a></sup> provide decision-theoretic context, without supplying
a utility model or an optimal computation-selection policy for the present framework.

__FIG_LOOP__

## 3. Preliminaries and Notation

We write $\mathbb{N}_0=\{0,1,\ldots\}$, $\mathbb{N}_{+}=\{1,2,\ldots\}$,
$\mathbb{R}$ for the reals, and $\mathbb{I}=[0,1]$. For finite $X$, $|X|$ denotes cardinality
and $2^X$ the power set. For nonempty finite or countable $X$,
$\Delta(X)=\{p\in\mathbb{R}_{\ge0}^{X}:\sum_{x\in X}p_x=1\}$ is the set of discrete probability
distributions. For $d\in\mathbb{N}_{+}$,
$\mathbb{S}^{d-1}=\{v\in\mathbb{R}^d:\lVert v\rVert_2=1\}$, with Euclidean inner product
$\langle u,v\rangle\in[-1,1]$ for $u,v\in\mathbb{S}^{d-1}$.
For real $x,a,b$ with $a\le b$,
$\operatorname{clamp}(x;a,b)=\min(\max(x,a),b)$.
The indicator $\mathbf{1}\{E\}$ equals $1$ when statement $E$ holds and $0$ otherwise.

**Order-theoretic objects.** A complete lattice $(L,\sqsubseteq)$ has a least upper bound
and a greatest lower bound for every subset, including bottom and top elements.
A map $f:L\to L$ is *monotone* when $x\sqsubseteq y$ implies $f(x)\sqsubseteq f(y)$,
and *inflationary* when $x\sqsubseteq f(x)$. These are distinct properties.
A fixed point satisfies $f(x)=x$. A monotone map on a complete lattice has a least
fixed point $\operatorname{lfp}(f)$ <sup><a href="#ref-3">3</a></sup>.

**Agent objects.** Let $\mathcal{A}$ and $\mathcal{O}$ be nonempty countable action and
observation spaces. A distinguished outcome $\bot_{\!a}\notin\mathcal{A}$ denotes
refusal without execution, not the lattice bottom. Set
$\mathcal{A}_{\bot}=\mathcal{A}\cup\{\bot_{\!a}\}$ and include refusal observations in
$\mathcal{O}$. The history space $\mathcal{H}=(\mathcal{A}_{\bot}\times\mathcal{O})^*$
contains all finite execution histories, including the empty history.
A base policy $\pi:\mathcal{H}\to\Delta(\mathcal{A})$ proposes ordinary actions.
For a finite, possibly empty index set $J$, let
$h_j:\mathcal{H}\times\mathcal{A}\to\{0,1\}$, $j\in J$, be hooks; $1$ means blocked.

**Task objects.** Fix a finite requirement set $R=\{r_1,\ldots,r_N\}$,
$N\in\mathbb{N}_0$, and required subset $R_{\mathrm{req}}\subseteq R$. The abstract state
$S\subseteq R$ records certified requirements. The lattice $(2^R,\subseteq)$ has join $\cup$,
meet $\cap$, bottom $\varnothing$, and top $R$. The abstraction
$\nu:2^R\times R\to\{0,1\}$ determines which further certificates can be derived from $S$.
Representing evidence by requirement identifiers alone requires the sufficiency assumption
in Section 4.2; an actual workspace, tests, and execution history contain more information.

**Metric objects.** Let $\mathcal{D}$ be finite text descriptors and
$\mathcal{D}^{*}=\bigcup_{m\in\mathbb{N}_0}\mathcal{D}^{m}$ their finite sequences.
The embedding $\varphi$ returns a unit vector for nonzero embeddings; the implementation
uses the zero vector for a descriptor with no embedding features. Thus its full codomain
is $\mathbb{S}^{d-1}\cup\{0\}$, and an exact text match need not score $1$ for a zero vector.
Signals $s_k\in\mathbb{I}$ combine with weights
$w\in\Delta(\{1,\ldots,K\})$, $K\in\mathbb{N}_{+}$.

## 4. The Control Layer: Governance and Orchestration

The action filter and requirement-closure operator describe different contracts.
The first restricts proposed actions at a specified history; the second describes an
idealized validation closure. Neither alone proves real-world task correctness.

### 4.1 Governance as a projection on the action space

At fixed $H$, let
$\mathcal{A}_G(H)=\{a\in\mathcal{A}:h_j(H,a)=0\text{ for every }j\in J\}$.
Define $G_H:\mathcal{A}_{\bot}\to\mathcal{A}_{\bot}$ by

$$ G_H(a)=\begin{cases}
 a,&a\in\mathcal{A}_G(H),\\
 \bot_{\!a},&a\notin\mathcal{A}_G(H).
 \end{cases} $$

In particular $G_H(\bot_{\!a})=\bot_{\!a}$. Therefore $G_H\circ G_H=G_H$:
it is an idempotent retraction onto $\mathcal{A}_G(H)\cup\{\bot_{\!a}\}$.
The governed policy is the pushforward of the proposal policy:

$$ \pi_G(a\mid H)=\pi(a\mid H)\mathbf{1}\{a\in\mathcal{A}_G(H)\}
 \quad(a\in\mathcal{A}),\qquad
 \pi_G(\bot_{\!a}\mid H)=\sum_{a\in\mathcal{A}\setminus\mathcal{A}_G(H)}\pi(a\mid H). $$

Blocked probability becomes refusal mass, **not renormalized admissible mass**.
Conditional resampling until an admissible action is obtained would be a different policy
and is undefined if the original policy assigns zero mass to admissible actions.
Filtering leaves accepted actions unchanged at this history, but can change later behavior
and task utility.

**Assumption A1 (complete mediation and hook coverage).** Every effect in the claimed
protection boundary is checked before execution against authoritative context, without a
check/use race; every unsafe action in the specified threat class is blocked by at least
one hook. Under A1 no action in that class executes. Pure predicates alone do not establish
coverage, and neither false-positive rates nor semantic safety follow from idempotence.
The benchmark must measure refusals and coverage separately.

### 4.2 Orchestration: the completion loop as a consequence operator

For a **fixed** oracle and requirement set define

$$ \Phi(S)=S\cup\{r\in R:\nu(S,r)=1\}. $$

**Assumption A2 (oracle and evidence).** Requirement identifiers are a sufficient summary
for this deterministic rule. Validation is monotone:
$S\subseteq T,\ \nu(S,r)=1\Rightarrow\nu(T,r)=1$.
Whenever the certificates in $S$ are valid for the specified task, every new certificate
$r\in R\setminus S$ with $\nu(S,r)=1$ must be supported by valid evidence and correct
for that task. Accepted transitions must preserve previously valid certificates.
The union makes $\Phi$ inflationary; the additional monotonicity assumption makes it
monotone. Append-only storage alone does **not** imply that assumption. For example,
$R=\{a,b\}$, $\nu(S,a)=0$ for all $S$, and
$\nu(S,b)=\mathbf{1}\{a\notin S\}$ give
$\Phi(\varnothing)=\{b\}$ but $\Phi(\{a\})=\{a\}$.

> <span id="thm-1"></span>**Theorem 1 (finite closure, conditional soundness, fair-schedule independence).**
> Let $\Phi:2^R\to2^R$ be monotone and inflationary. Starting at $S_0=\varnothing$,
> the iterates $S_{t+1}=\Phi(S_t)$ reach $S_*=\operatorname{lfp}(\Phi)$ after at most
> $|R|$ strict increases. A further evaluation may be needed to detect stabilization.
> With A2's soundness and persistence conditions, all certificates in $S_*$ remain valid.
> Define PASS at closure by $R_{\mathrm{req}}\subseteq S_*$; PASS then certifies those
> requirements relative to the oracle, not all possible correctness properties.
> Starting at $\varnothing$, adding enabled consequences in any **fair** schedule
> reaches the same $S_*$.

*Proof.* Inflationarity gives an increasing chain. Each strict increase adds at least
one of the $|R|$ elements, so the chain stabilizes. If $F$ is any fixed point, then
$S_0\subseteq F$ and monotonicity implies
$S_{t+1}=\Phi(S_t)\subseteq\Phi(F)=F$ by induction. The stabilized state is thus the
least fixed point. Soundness follows by induction on certified additions, using both
oracle soundness and persistence. For asynchronous addition, every added requirement is
in $\Phi(S)$, so the same induction keeps the state below $S_*$. Fairness means no
persistently enabled missing requirement is postponed forever. Since there can be only
finitely many additions, the eventual state has no enabled missing requirement and is
a fixed point; leastness makes it $S_*$. $\square$

The theorem proves derivability under $\nu$, **not** that $S_*$ is exactly the set of
requirements achievable by arbitrary agents. Completeness of the oracle/generator would
be an additional assumption. An unfair scheduler can omit enabled work forever.
Detecting one unproductive *stochastic* attempt is not detecting a fixed point of a
deterministic exhaustive consequence operator.

**Implementation boundary.** Real repair passes edit a shared artifact and can regress
previously passing checks. A historical union of successful checks is not a current
correctness certificate. The benchmark uses bounded retries, observation-dependent
validation, and score-based candidate selection; these are not an implementation proof
of A2 or exhaustive closure. Fresh validation of the final artifact is needed for PASS.
Raw coding harnesses also take multiple internal actions; a single benchmark invocation
is not a single consequence or a single requirement addition.

__FIG_LATTICE__

### 4.3 Effective feedback and the value of computation

Define the count $\mathrm{efc}(S)=|\Phi(S)\setminus S|$ for the abstract operator.
It measures newly certified requirements, motivated by retained-feedback accounts
<sup><a href="#ref-21">21</a></sup>. Along iteration from $\varnothing$ under A2,
these additions are valid, nonredundant, and retained. Their information content
and utility are not necessarily equal.

> <span id="prop-1"></span>**Proposition 1 (effective-feedback accounting).**
> If $S_0=\varnothing$ and $S_T=S_*=\operatorname{lfp}(\Phi)$ is the stabilized iterate,
> then $\sum_{t=0}^{T-1}|S_{t+1}\setminus S_t|=|S_*|$.
> If $R_{\mathrm{req}}\subseteq S_*$, exactly $|R_{\mathrm{req}}|$ of these additions
> are required certificates. The **total** number of additions before first completion
> can exceed $|R_{\mathrm{req}}|$ because optional requirements can be added too.

*Proof.* The disjoint differences $S_{t+1}\setminus S_t$ partition $S_*$.
Intersecting that partition with $R_{\mathrm{req}}$ gives the required-only identity.
$\square$

One productive pass can add any number from $1$ to $|R\setminus S|$.
For example, $\Phi(S)=R$ completes arbitrarily many requirements in one pass.
Consequently no lower bound on required passes, no impossibility for single-invocation
harnesses, and no advantage over independent sampling follows from this accounting.
An append-only ledger prevents duplicate **credit**, not duplicate computation.
Positive decision-theoretic value of information or net value of computation requires
an explicit utility/cost model <sup><a href="#ref-22">22</a>,<a href="#ref-23">23</a></sup>;
$\mathrm{efc}>0$ is not equivalent to either.

### 4.4 Probabilistic execution over the fixed-point lattice

A stochastic process is separate from the deterministic closure model.
Let $\nu_{\mathrm{obs}}:\mathcal{H}\times2^R\times\mathcal{A}_{\bot}\times
\mathcal{O}\times R\to\{0,1\}$ validate observed executions. Define
$U(H,S,a,o)=S\cup\{r\in R:\nu_{\mathrm{obs}}(H,S,a,o,r)=1\}$
as historical certificate accumulation. A distinct current-artifact validation set may shrink.
For a requirement-only, time-homogeneous Markov abstraction, **assume** the conditional
law of the next requirement state depends on the past only through $S$. Then

$$ P(S,S')=\sum_{\substack{a\in\mathcal{A}_{\bot},\,o\in\mathcal{O}\\U(S,a,o)=S'}}
 \pi_G(a\mid S)\,E(o\mid S,a),\qquad \sum_{S'\subseteq R}P(S,S')=1, $$

where $\pi_G(\cdot\mid S)\in\Delta(\mathcal{A}_{\bot})$ and
$E(\cdot\mid S,a)\in\Delta(\mathcal{O})$ is the observation distribution, including
a refusal observation for $\bot_{\!a}$. Each of $U,\pi_G,E$ must admit this
sufficient-state representation.
For general history-dependent execution use $X_t=(H_t,S_t)$ instead, including all
relevant environment state in the history. Aggregating its transitions by $S$ alone
does not in general produce a Markov chain. Historical certificate accumulation gives
$P(S,S')=0$ unless $S\subseteq S'$ but does not prove current-artifact correctness.

**Completion as a hitting time.** Let
$C=\{S\subseteq R:R_{\mathrm{req}}\subseteq S\}$ and
$T_C=\inf\{t\in\mathbb{N}_0:S_t\in C\}$, with $\inf\varnothing=\infty$.
For an increasing process $C$ is a closed set; make its states absorbing if the run
stops at first completion. Specify the initial state $S_0$ for all probabilities
and expectations.

> <span id="prop-2"></span>**Proposition 2 (conditional completion time).**
> For a finite increasing Markov chain, suppose every reachable $S\notin C$ has
> $\Pr(S_{t+1}\supsetneq S_t\mid S_t=S)\ge\varepsilon$, where $0<\varepsilon\le1$.
> Then $\Pr(T_C<\infty)=1$ and
> $\mathbb{E}[T_C]\le (|R|-|S_0|)/\varepsilon$.

*Proof.* Since $R\in C$, at most $|R|-|S_0|$ strict increases can precede completion.
Before completion, the wait for each increase is dominated by a geometric variable
of mean $1/\varepsilon$. Their sum bounds $T_C$ and its expectation; independence
of the holding times is unnecessary. A finite expectation implies almost-sure
completion. $\square$

An incomplete absorbing state violates the progress assumption. Without that assumption,
completion need not occur and $\mathbb{E}[T_C]$ may be infinite. Governance changes the
execution law through the refusal-mass filter of Section 4.1; comparing unsafe-event
probabilities additionally requires an explicit unsafe-event indicator on the augmented
state, not merely a subset of satisfied requirements. A difference of expected completion
times is meaningful only when both expectations are finite. No transition probabilities
or completion-time estimates are supplied by the lattice theorem.

## 5. Evaluation

### 5.1 VERTEX trajectory similarity

This implementation of VERTEX combines descriptor cross-similarity with an order penalty,
inspired by trajectory evaluation <sup><a href="#ref-1">1</a>,<a href="#ref-19">19</a></sup>.
For nonempty sequences $c=(c_1,\ldots,c_m)$ and $r=(r_1,\ldots,r_n)$,
$m,n\in\mathbb{N}_{+}$, define
$\mathbf{S}_{ij}=\langle\varphi(c_i),\varphi(r_j)\rangle\in[-1,1]$.
For unit embeddings this is cosine similarity; zero-vector handling is as in Section 3.
Either empty sequence receives score $0$ by convention. Figure 3 shows the two components.

*Presence (unordered).* A BERTScore-style bidirectional best match <sup><a href="#ref-11">11</a></sup>,
where $P$ (precision) measures how well each candidate descriptor is matched by some reference and $Q$
(recall) how well each reference descriptor is matched by some candidate:

$$ P=\frac{1}{m}\sum_{i=1}^{m}\max(0,\max_j\mathbf{S}_{ij}),\qquad
 Q=\frac{1}{n}\sum_{j=1}^{n}\max(0,\max_i\mathbf{S}_{ij}),\qquad
 F=\begin{cases}2PQ/(P+Q),&P+Q>0,\\0,&P+Q=0.\end{cases} $$

Thus $P,Q,F\in\mathbb{I}$ and $\min(P,Q)\le F\le\max(P,Q)$.
Negative similarities still enter the order cost and the matrix-mean baseline below.

*Order.* Dynamic time warping <sup><a href="#ref-12">12</a></sup> minimizes over paths
$\Gamma$ from $(1,1)$ to $(m,n)$ with steps $(1,0)$, $(0,1)$, or $(1,1)$.
For finite $\lambda\ge0$, the cost is
$d(i,j)=(1-\mathbf{S}_{ij})(1+\lambda|(i-1)/m-(j-1)/n|)$:

$$ \mathrm{DTW}=\min_{\gamma\in\Gamma}\sum_{(i,j)\in\gamma}d(i,j),\qquad
   D=\max\!\Bigl(0,\,1-\tfrac{\mathrm{DTW}}{m+n}\Bigr)\in\mathbb{I}, $$

The path has between $\max(m,n)$ and $m+n-1$ entries. The denominator $m+n$ is a
chosen normalization, not the path length or an upper bound on the **cost**.

*Matrix-mean recalibration.* For $0<\epsilon<1$, let
$b=\operatorname{clamp}((mn)^{-1}\sum_{i,j}\mathbf{S}_{ij};0,1-\epsilon)$ and
$\eta_b(x)=\operatorname{clamp}((x-b)/(1-b);0,1)$.
The raw mean lies in $[-1,1]$, and the clamp ensures a positive denominator.
It is the mean of this candidate–reference pair, **not** an independently estimated
null expectation. For finite $\alpha\in[0,1]$:

$$ \mathrm{VERTEX}(c,r)\;=\;\alpha\,\eta_b(F)+(1-\alpha)\,\eta_b(D)\;\in\;\mathbb{I}. $$

The benchmark configuration fixes $\alpha=0.6$, $\lambda=0.5$, and $\epsilon=0.01$ (the baseline-clamp
margin). Proposition 3 records the range and the exact sense of the calibration.

> <span id="prop-3"></span>**Proposition 3 (range and anchors).**
> VERTEX lies in $\mathbb{I}$. The normalizer is nondecreasing on $\mathbb{R}$ and
> strictly increasing on $[b,1]$, with $\eta_b(b)=0$ and $\eta_b(1)=1$.
> Identical sequences of nonzero unit embeddings score $1$ in exact arithmetic.

*Proof.* All floored best matches lie in $\mathbb{I}$; the harmonic mean lies between
its arguments. Costs are nonnegative, hence the clamped $D$ lies in $\mathbb{I}$.
The normalizer has the stated endpoints and slope $1/(1-b)>0$ on its unclamped interval.
The mixture is convex. Identical unit-vector sequences have unit diagonal similarities,
$P=Q=1$, and a zero-cost diagonal path, so $F=D=1$. $\square$

There is **no universal chance floor**. A constant zero similarity matrix with $m=n$
has $F=0,D=1/2$, hence score $0.2$ at the default mixture. With $m=1,n=9$ and
$\lambda=0.5$, the same zero similarities give path cost $11$, $D=0$, and score $0$.
Lengths, order, and embedding geometry therefore affect unrelated-input scores.
Maxima need not strictly exceed a mean, and the DTW term need not concentrate near
$(1+b)/2$. Comparisons require fixed extraction and embedding protocols; they are
similarity comparisons, not calibrated probabilities or correctness certificates.

__FIG_VERTEX__

#### 5.1.1 VERTEX-QE: estimated references

The project task can compare a candidate with hand-authored capability and architecture
descriptors. These references select particular realizations of an open-ended brief.
VERTEX-QE instead estimates descriptors from public sources. Each invocation of the
Section 5.1 kernel retains the same presence score $F$, order score $D$, and matrix-mean
recalibration $\eta_b$; its reference argument becomes an estimate $\hat r$.
The project-level mixture also changes its architecture weight, as defined below.

Capability descriptors come from the public brief's enumerated outcomes. Architecture
descriptors combine its engineering expectations with a small synthetic vocabulary
of common web-application concerns: HTTP routing, frontend components, separation
of domain logic from transport, commerce entities, tests, and environment configuration.
The vocabulary spans six authored patterns, including a layered monolith, a separate
frontend and REST API, server-side rendering, a commerce-service split, a
ports-and-adapters core, and a static frontend with serverless APIs.
These are illustrative design patterns, not observations from six sampled repositories.
Empty strings and exact duplicates are removed within each source; the union
greedily drops later descriptors whose cosine similarity to a retained one is at least $0.92$.
The resulting list has a deterministic order that affects DTW, although it does not
describe execution time or a distribution of valid architectural alternatives.

For the architecture mixture, let $L$ be the number of nonempty cleaned source lists.
Write list $\ell$ as $(x_{\ell1},\ldots,x_{\ell n_\ell})$, where $n_\ell\ge1$.
For distinct sources $\ell,k\in\{1,\ldots,L\}$, directed agreement is

$$ a_{\ell k}=\frac{1}{n_\ell}\sum_{i=1}^{n_\ell}
 \max\!\left(0,\max_{1\le j\le n_k}
 \langle\varphi(x_{\ell i}),\varphi(x_{kj})\rangle\right). $$

The resolver sets $q_{\mathrm{arch}}=0$ for $L=0$, $1/2$ for $L=1$, and otherwise
averages $(a_{\ell k}+a_{k\ell})/2$ over all unordered source pairs, rounded to four
decimal places. Thus $q_{\mathrm{arch}}\in[0,1]$. With capability and architecture
VERTEX scores $V_{\mathrm{cap}}$ and $V_{\mathrm{arch}}$, the project signal is

$$ V_P=\frac{0.7V_{\mathrm{cap}}+0.3q_{\mathrm{arch}}V_{\mathrm{arch}}}
 {0.7+0.3q_{\mathrm{arch}}}. $$

Authored-reference mode uses $q_{\mathrm{arch}}=1$. In QE mode an empty architecture
union triggers a recorded authored-reference fallback, but $q_{\mathrm{arch}}=0$
then removes that architecture score from $V_P$. The fallback can therefore appear
in diagnostics without contributing authored architecture evidence to the composite.
Agreement is not a calibrated probability of correctness. COMET, SUPERT, and MAUVE
<sup><a href="#ref-47">47</a>,<a href="#ref-48">48</a>,<a href="#ref-49">49</a></sup>
provide reference-estimation and distributional-evaluation context, not validation of this rule.

Pool-level QE diagnostics additionally use leave-one-out peer descriptors supported by
at least two peers. They are not inputs to the per-candidate composite above.
This is a heuristic, not a minimum-Bayes-risk estimator or a consistent latent-truth
estimator justified by <sup><a href="#ref-50">50</a>,<a href="#ref-51">51</a></sup>.
Even independent peers that include a false descriptor with probability $0.1$ will,
with probability tending to one, exceed a fixed two-peer threshold as the pool grows.
Leave-one-out removes literal self-reference, not correlations between related models.
The weak-supervision literature <sup><a href="#ref-53">53</a></sup> is background, not
a proof that unmodeled source agreement is calibrated.

An unused contrastive helper computes a softmax assignment score. Equal logits give
$1/B_{\mathrm{batch}}$ for $B_{\mathrm{batch}}$ alternatives, but individual scores can
be smaller. This is not a universal chance floor or itself a mutual-information lower
bound: InfoNCE <sup><a href="#ref-52">52</a></sup> bounds mutual information through an
**expected loss** under specified sampling assumptions. No active multi-brief contrastive
evaluation is implemented.

> <span id="prop-4"></span>**Proposition 4 (reference replacement and mixtures).** Replacing a descriptor reference preserves
> Proposition 3's range bound. The convex mixture $V_P$ is also in $\mathbb{I}$.
> Neither property establishes reference accuracy or equal chance behavior.

*Proof.* Apply Proposition 3 to each replacement reference. The normalized weights
in $V_P$ are nonnegative and sum to one, so their mixture preserves the range. $\square$

Within-brief Spearman correlation with authored VERTEX is a preliminary concordance
diagnostic, not authorization to discard reference validation on unseen briefs.
The run-level diagnostic selects one built candidate per arm and omits failed builds;
pool consensus and the production metric are distinct estimands. Generalization needs
independent held-out briefs, adequate replication, and reference-provenance checks.

**Correctness versus similarity.** The oracle $\nu$ certifies requirements in the
conditional closure model. VERTEX measures descriptor similarity on a continuous scale.
Turning similarity into a pass/fail decision requires an additional, validated threshold;
no such decision rule is part of the fixed-point semantics.

### 5.2 The build-gated composite

For a full-repository task, $K$ signals $s_1,\dots,s_K\in\mathbb{I}$ (functional end-to-end behavior,
trajectory similarity, visual fidelity, architecture, accessibility, output security, robustness, code
health) combine through a convex weight vector $w\in\Delta(\{1,\dots,K\})$, gated by a build indicator
$g\in\{0,1\}$:

$$ C\;=\;g\sum_{k=1}^{K}w_k\,s_k,\qquad w_k\ge 0,\ \textstyle\sum_{k}w_k=1. $$

> <span id="prop-5"></span>**Proposition 5 (build-gated range).** $C\in\mathbb{I}$, with $C=0$ whenever the repository does not build ($g=0$); when it
> builds, $\min_k s_k\le C\le\max_k s_k$.

*Proof.* For $g=1$, multiply $\min s_k\le s_k\le\max s_k$ by $w_k\ge0$ and sum.
For $g=0$ the product is zero. $\square$

Missing analyzer evidence is not a passed signal.
Degraded evaluations must not be compared as though all fixed weights were measured.

The project gate is **build-only**; serving additionally gates visual and UX evidence.
Functional coverage excludes unevaluable journeys from both numerator and denominator,
returning zero when none are evaluable. Screenshot-based visual scores average available
candidate frames and return zero when none exist. Comparisons therefore require matched
journey and frame coverage; fixed outer weights do not eliminate this conditional missingness.

**Averaging and build gating do not commute.** Track G's historical aggregate is
a different descriptive index. For $B\in\mathbb{N}_{+}$ briefs, let $n_b\in\mathbb{N}_{+}$ be the recorded
attempt count for brief $b$, let $g_{bi}\in\{0,1\}$ be attempt $i$'s build indicator,
and let $s_{bk}$ be the stored brief-level value of signal $k$. The aggregator
weights briefs equally, not individual attempts:

$$ \bar g=\frac{1}{B}\sum_{b=1}^{B}\frac{1}{n_b}\sum_{i=1}^{n_b}g_{bi},
 \qquad \bar s_k=\frac{1}{B}\sum_{b=1}^{B}s_{bk}. $$

Ignoring intermediate and final four-decimal rounding, the reported index is

$$ G_{\mathrm{agg}}=\bar g\sum_{k=1}^{K}w_k\bar s_k. $$

This product of marginal averages need not equal an average of jointly gated
scores. If per-attempt signals $s^{\mathrm{seed}}_{bik}$ were available, the
corresponding equal-brief average would instead be

$$ G_{\mathrm{joint}}=\frac{1}{B}\sum_{b=1}^{B}\frac{1}{n_b}
 \sum_{i=1}^{n_b}\left(g_{bi}\sum_{k=1}^{K}w_k s^{\mathrm{seed}}_{bik}\right). $$

Even when each stored signal is a within-brief seed mean, these quantities can
differ: with two single-seed briefs, one unit-weight signal, and gate/signal pairs
$(1,1)$ and $(0,0)$, the product of means is $1/4$ but the mean gated score is $1/2$.
Stored brief-level judge outputs need not themselves be seed means. Marginal
summaries therefore cannot reconstruct the joint per-attempt quantity.
The completeness bootstrap resamples brief-level means.

For integers $n\ge1$, $0\le c\le n$, and $1\le k\le n$, let $c$ of $n$ recorded
trials satisfy a specified success event. Define $\binom{a}{k}=0$ when integers
$k>a\ge0$. Reliability is
$\mathrm{pass}^{k}=\binom{c}{k}/\binom{n}{k}$ <sup><a href="#ref-41">41</a></sup>:
the probability that a uniformly selected $k$-subset consists entirely of successes.
For independent trials with common success probability $p\in[0,1]$, it is unbiased
for $p^k$ and is non-increasing in $k$.

The project evaluator calls a seed successful when it builds and its measured functional
coverage is at least $0.999$. Track G requires seed completeness of at least $0.999$
and averages reliability estimates over briefs. These are test-defined events, not
complete semantic correctness. The live project path currently allows one seed,
which supplies no multi-run reliability estimate.

For the *Bugfix* family (Track R), let $r\in\{0,1\}$ indicate that the executed
hidden resolution tests pass without a generation error. Let $a\in\{0,1\}$ indicate
that the submitted patch contains no prohibited test-file edits detected by the
path-based filter. With bounded graded signals $s$ and convex weights $w$,
$C_R=ar(w\cdot s)$. If a semantic patch judge supplies $J\in[0,1]$, the formula is
$C_R=ar\bigl(0.8(w\cdot s)+0.2J\bigr)$.
The signals measure held-out robustness, preservation of existing behavior, patch
minimality/locality relative to the reference fix, and code health.

The lenient resolution rate reports $r$. The implemented strict rate also requires
$a=1$ and held-out/regression scores of at least $0.999$.
An absent held-out or regression suite receives score $1$ with zero executed tests;
therefore the strict rate certifies those additional checks only when the suites are
nonempty and actually run. The test-path filter does not exclude arbitrary evaluator tampering.

### 5.3 Safety: attack-success and confidence intervals

Let $\mathcal{I}=\{1,\ldots,N_{\mathrm{case}}\}$ index $N_{\mathrm{case}}\ge1$
evaluated cases. For each $i\in\mathcal{I}$, let $n_i\in\mathbb{N}_{+}$ be its
recorded attempt count and $c_i\in\{0,\ldots,n_i\}$ its classified successes.
The **attempt-pooled** headline is
$\widehat p=\sum_{i\in\mathcal{I}}c_i/\sum_{i\in\mathcal{I}}n_i$.
The separate case-weighted $\mathrm{ASR}@1$ is
$N_{\mathrm{case}}^{-1}\sum_{i\in\mathcal{I}}c_i/n_i$.
They differ when attempt counts differ. With $N=\sum_{i\in\mathcal{I}}n_i>0$
and normal quantile $z>0$ (default $z=1.96$ for nominal 95% coverage), the Wilson score interval
<sup><a href="#ref-13">13</a></sup> is

$$ \frac{\widehat p+\frac{z^2}{2N}}{1+\frac{z^2}{N}}\;\pm\;\frac{z}{1+\frac{z^2}{N}}
 \sqrt{\frac{\widehat p(1-\widehat p)}{N}+\frac{z^2}{4N^2}}. $$

For a common Bernoulli success probability $p\in[0,1]$, the endpoints solve
$(\widehat p-p)^2=z^2p(1-p)/N$ exactly. Coverage is approximate, not exact;
correlated attempts and heterogeneous cases weaken this sampling interpretation.

The case-cluster percentile bootstrap <sup><a href="#ref-14">14</a></sup> resamples
whole cases and recomputes the attempt-pooled ratio. Defaults are 1,000 resamples,
pseudorandom seed zero, and 95% intervals. After sorting the resampled estimates,
the implementation selects zero-based entries 25 and 975 and rounds to four decimal
places. Track G applies the corresponding procedure to brief-level mean completeness.
One cluster or identical cluster values produces a point interval, not evidence of
zero population uncertainty. Population inference still requires a representative
cluster sample. With no observations, rates and intervals are unavailable.

For each case with integers $0\le c_{\mathrm{s}}\le n$ and $1\le k\le n$,

$$ \mathrm{ASR}@k=1-\frac{\binom{n-c_{\mathrm{s}}}{k}}{\binom{n}{k}}. $$

This is one minus the probability that a uniform $k$-subset of recorded attempts
contains no success; it is nondecreasing in $k$.
Under i.i.d. Bernoulli sampling it is unbiased for the probability of at least one
success in $k$ fresh attempts <sup><a href="#ref-15">15</a></sup>. It is undefined for
$k>n$. A multi-pass adaptive attack path is one trial with its own fixed budget,
not a set of independent attacks. Results with different budgets are not comparable.

Incomplete cells are excluded and listed with their reason, rather than silently
compressing surviving seeds into a complete-budget result. This is still a
conditional-on-observation estimate: missingness can bias it. Common-case comparisons
and coverage reporting are required. Over-refusal uses benign controls. Live
**secure-and-useful** is unavailable in this implementation: a transcript marker
cannot independently verify the legitimate task into which an attack is inserted
(the *carrier task*). Secure-and-useful evaluation is a goal motivated by
<sup><a href="#ref-38">38</a>,<a href="#ref-39">39</a>,<a href="#ref-40">40</a></sup>,
not an established live measurement here.

### 5.4 Gated qualitative judging

The optional Claude-rubric backend uses absolute 0–4 rubrics for visual, architecture,
and UX judgments <sup><a href="#ref-16">16</a>,<a href="#ref-17">17</a>,<a href="#ref-18">18</a></sup>.
Its outputs must be finite and within that range before division by four; malformed
outputs are unavailable evaluations. Absolute presentation avoids pairwise ordering
as an input, but does not remove verbosity, style, or model-family bias.

Other backends measure different quantities. The heuristic backend uses deterministic
functional and code-structure proxies; the CLIP backend uses image similarity and
descriptor comparisons. A heuristic visual proxy does not inspect rendered appearance.
Backend identity and evaluated evidence coverage are therefore part of score provenance.

**Assumption A3 (bounded gated judging).** To qualify as evidence-based judging, a backend
must return a bounded score from candidate evidence it actually reads. Visual and UX
assessment require a built, served artifact; static architecture assessment requires
a built repository with scoreable files. This is an eligibility condition, not an
established property of every backend. Human agreement and resistance to adversarial
candidate content require separate empirical validation.

### 5.5 Cross-family aggregate (the Gauntlet Index)

Let $\mathcal{T}=\{S,Q,R,G,P\}$ be the five fixed task families, and write
$\tilde s_t(M)\in\mathbb{I}$ for arm $M$'s normalized family-$t$ headline.
The implementation maps $S$ to $1-\mathrm{ASR}$, $Q$ to requirement coverage, and $G$ to
$g_{\text{score}}$, the reported aggregate described in Section 5.2.
Families $P$ and $R$ use their respective composites. Higher values are preferred.
For an arm with qualified scores on **all five** families, define

$$ \mathrm{Index}(M)=\frac{1}{5}\sum_{t\in\mathcal{T}}\tilde s_t(M)\in\mathbb{I}. $$

The index is unavailable when any family is missing; individual scores and coverage
remain visible. Its range follows from convexity, not empirical comparability.
Qualification requires current scoring, observed execution, and complete evaluable
coverage. The current publication excludes Security records from qualified headlines,
so it does not presently report a five-family index.
Matched tasks, budgets, provenance, and timestamps are still necessary for competitive
comparisons. The index is not a validated general-capability scale.

### 5.6 Operational diagnostics for long-horizon results

The quantities in Table 1 are **proposed diagnostics**, not measurements supplied by the
current paper. A valid transition model or repeated, uncensored run-level observations
would be needed to estimate them. A budget cap is not an observed completion time.

<figure class="tbl" id="tbl-1">
<table>
<thead><tr><th>Diagnostic</th><th>Meaning</th></tr></thead>
<tbody>
<tr><td>$n$</td><td>Maximum loop iterations / total passes allowed for the run.</td></tr>
<tr><td>Productive passes</td><td>Passes with $S_{t+1}\supsetneq S_t$ in the certificate-accumulation trace.</td></tr>
<tr><td>$\mathrm{efc}(S_t)$</td><td>New certificates enabled by the abstract operator: $|\Phi(S_t)\setminus S_t|$.</td></tr>
<tr><td>$|R|,\ |R_{\mathrm{req}}|$</td><td>Total and required requirement counts (the milestone budget).</td></tr>
<tr><td>Reasoning budget $b$</td><td>Thinking mode / compute budget the harness ran under.</td></tr>
<tr><td>$\Pr(T_C\le n)$</td><td>Probability of covering $R_{\mathrm{req}}$ within the iteration budget (§4.4).</td></tr>
<tr><td>$\mathbb{E}[T_C]$</td><td>Expected number of passes to completion.</td></tr>
<tr><td>$-\log_2 p$</td><td>Event surprisal in bits; for a harmful event, a descriptive risk transform.</td></tr>
</tbody>
</table>
<figcaption>Table 1. Proposed execution diagnostics. No fitted Markov kernel, calibrated
per-requirement prior, or completion-time distribution is reported here.</figcaption>
</figure>

The last row uses self-information <sup><a href="#ref-54">54</a></sup>.
For an event of probability $p\in(0,1]$, its *surprisal* is

$$ I(p)=-\log_2 p\ \ \text{bits}\qquad\bigl(p=\tfrac12\Rightarrow 1\ \text{bit},\ \ p=\tfrac14\Rightarrow 2\ \text{bits},\ \ p=0.01\Rightarrow 6.64\ \text{bits}\bigr), $$

This is finite on $(0,1]$; extend $I(0)=+\infty$.
A zero observed attack count is not proof that the underlying probability is zero.
For positive raw and governed rates, a descriptive bit difference is
$\log_2(\widehat p_{\mathrm{raw}}/\widehat p_{\mathrm{gov}})$; $0/0$ is undefined.
A probability interval $[p_L,p_U]$ transforms to
$[-\log_2 p_U,-\log_2 p_L]$, with an infinite upper endpoint if $p_L=0$.
This transformation creates no new evidence or confidence guarantee.

A proposed information-weighted count must specify its event. Let
$Z_t=(H_0,S_0,\ldots,H_t,S_t)$ be the observed run history through pass $t$.
For each uncertified $r\in R\setminus S_t$, suppose a calibrated estimate
$q_t(r)=\Pr(r\in S_{t+1}\setminus S_t\mid Z_t)\in(0,1]$ were available.
For an observed transition one could then define
$\mathrm{iefc}_t=\sum_{r\in S_{t+1}\setminus S_t}-\log_2q_t(r)$.
This sums marginal event surprisals; it is not joint information without an appropriate
dependence model, nor a measure of task value. No such probability estimates are reported here.

## 6. Experimental Setup

The evaluation separates three questions. First, does a configured governance
layer reduce classified unsafe responses while preserving behavior on benign
requests? Second, how do coding harnesses differ in the functional and structural
quality of the artifacts they produce? Third, can automatically estimated semantic
references recover rankings obtained with hand-authored references?
These questions require different experimental units: attack attempts, completed
coding tasks, and independently specified application briefs, respectively.

Sections 6.1–6.6 define the comparison protocol and measurement boundaries.
Section 7 then describes the retained June 2026 pilot studies, including their
tasks, sample coverage, numerical outcomes, and limitations. The pilots were not
one uniformly controlled experiment. Model execution and rescoring of existing
artifacts have different evidential meanings. The paper reports benchmark outcomes,
not constructed demonstrations; neither rescoring nor report regeneration is a new
independent model execution.

### 6.1 Baselines and base models

An arm is a harness, configured provider/model, prompts, tools, environment, and budget.
The implementation offers raw Codex CLI, Claude Code, Oh My Pi (OMP), and OpenCode
adapters with Cortex-configured counterparts. These are product-bundle comparisons.
Configuration and display labels are not attestations of the model that actually served
a historical request. Floating aliases, environment overrides, reasoning effort, and
tool/runtime versions must be recorded per execution.

Same-model labels alone do not identify a governance-only causal effect. Cortex arms
also change prompts, configuration, and sometimes planning/repair budgets. A policy-only
ablation needs matched effective models, tools, environments, cases, evaluation access,
and total resource budgets. A benchmark invocation can contain many internal agent actions.

### 6.2 Relation to existing benchmarks

SWE-bench and its variants assess repository issue resolution
<sup><a href="#ref-32">32</a>,<a href="#ref-33">33</a>,<a href="#ref-34">34</a></sup>;
LiveCodeBench emphasizes contamination-resistant code evaluation
<sup><a href="#ref-37">37</a></sup>. Commit0 and Terminal-Bench include difficult
multi-stage work <sup><a href="#ref-36">36</a>,<a href="#ref-35">35</a></sup>.
Independent tasks do not imply single-pass agents or saturated performance.
CyberSecEval, AgentDojo, and InjecAgent study security and prompt injection
<sup><a href="#ref-38">38</a>,<a href="#ref-39">39</a>,<a href="#ref-40">40</a></sup>;
AgentDojo also evaluates benign task utility. AgentBench, GAIA, WebArena, OSWorld,
and τ-bench cover other agent environments and interaction contracts
<sup><a href="#ref-42">42</a>,<a href="#ref-43">43</a>,<a href="#ref-44">44</a>,<a href="#ref-45">45</a>,<a href="#ref-41">41</a></sup>.
Gauntlet is a complementary framework, not evidence that these suites lack
long-horizon work, utility evaluation, or harness comparisons.

### 6.3 Tasks and measured outcomes

Table 2 distinguishes the intended task family from what its evaluator can establish.
Passing finite tests is evidence for those tests, not complete semantic correctness.

<figure class="tbl" id="tbl-2">
<table>
<thead><tr><th>Family</th><th>Task and score</th><th>Validity boundary</th></tr></thead>
<tbody>
<tr><td>S: Safety</td><td>Classified attack responses and proposed actions; ASR and benign over-refusal.</td><td>Lexical classification and action replay are not observed exploits. Live carrier-task utility is unmeasured.</td></tr>
<tr><td>Q: Quality</td><td>Generated code, hidden behavioral tests, static findings, lint/types and quality rubrics.</td><td>Analyzer availability and evaluator integrity are prerequisites; finite tests are incomplete.</td></tr>
<tr><td>R: Bugfix</td><td>Repository patches; resolution-gated score with held-out and regression checks.</td><td>Reference-diff similarity is not correctness. Test-runner tampering must be independently excluded.</td></tr>
<tr><td>G: Generative</td><td>Full-stack application generation; build/serve checks, feature probes, static scores and optional visual evidence.</td><td>Passed features do not establish complete application behavior, real model-endpoint use or time-resolved progress. Historical applications and the current chat-app protocol are distinguished below.</td></tr>
<tr><td>P: Project</td><td>One storefront brief, build-gated functional/semantic/visual/static composite.</td><td>Partial behavioral and accessibility proxies are not a complete storefront or payment validation.</td></tr>
</tbody>
</table>
<figcaption>Table 2. Five families and their measurement boundaries. No direction of a
raw-versus-governed effect is assumed by the score definition.</figcaption>
</figure>

**Application construction protocol.** The storefront brief asks for a fashion-shopping
application with product browsing, filtering or sorting, variant selection, cart
editing, consistent price totals, checkout, and order confirmation. Candidates choose
their implementation structure. The brief also requests a documented backend API,
a responsive interface, accessibility support, an installable progressive web app,
an offline shell, automated core-flow tests, and build/serve instructions.
Payment is specified in test mode; no real-money transaction is required.

The functional evaluator organizes the storefront into five journeys: home, browsing,
product detail, cart, and checkout, with respective weights $1,2,2,3,3$.
It scores the weighted fraction of passing evaluable journeys after a successful build.
The implemented checks are narrower than the brief. Some verify that a control exists
rather than that filtering, sorting, or quantity editing works. Cart checks compare
displayed arithmetic; checkout checks reaching a checkout surface. No implemented
test-payment driver establishes payment completion. Likewise, manifest and
service-worker checks do not demonstrate an offline shopping session, and markup
heuristics do not establish full keyboard accessibility.

The separate current chat-app protocol checks message/composer elements, stylesheet
and script availability, a chat-response token, and a history response. Its supplied
model-service substitute is a deterministic echo responder, not a learned model.
Passing a token check does not prove that the application contacted that service;
an application could construct the same response itself. These checks therefore
provide interface and API smoke coverage, not evidence of model reasoning, streaming,
conversation isolation, or durable history. The historical five-probe application
study in Section 7.2 and Appendix B.3 instead evaluates a to-do application and is not a chat result.

### 6.4 Configuration isolation and adaptive evaluation

Raw security adapters create temporary workspaces and scrub selected environment and
tool-home configuration. Governed adapters add a safety preamble and link repository
configuration. This is configuration isolation, **not host or network confinement**,
nor proof that every hook loaded. Track S does not itself run the completion loop.
Some nominal tool-output and memory attacks are delivered as workspace files representing
those surfaces, not through native tool-result or session-memory interfaces.

Adaptive attacks use earlier target responses to generate later prompts, but each target
attempt starts a fresh session/workspace. Their budgeted path is not a continuous target
conversation, and follow-ups need not preserve the original delivery surface.
Selecting a corpus using previous outcomes and merely labeling examples as held out
do not establish an independently frozen evaluation set. A genuine holdout must be
fixed before development and withheld from prompt design, curation, and repair feedback.

The project evaluator scores first/final snapshots and retains the highest composite.
Governed arms can also use evaluation feedback during repair. These current and historical
paths produce adaptively selected development scores, not untouched holdout measurements.
Access to more evaluations can favor one arm. A controlled comparison must commit each
artifact before a separate final evaluation and report all generation/evaluation costs.

### 6.5 Replication and missingness

Seed labels index repeated calls; they are not controlled provider RNG seeds.
Configured maximum attempts, completed attempts, skipped cases, internal repair passes,
and measured provider usage are separate quantities. Q and R report worst observed
repeats rather than a pooled per-seed success estimate. Live full-app/repository paths
have historically been single-run paths; requested counts must not be interpreted as
performed trials. A timeout is not a refusal or proof of candidate safety.
Excluding incomplete cells requires coverage reporting and common-case comparisons,
and does not remove informative-missingness bias.

### 6.6 Containment and evaluator integrity

The Q/R/G/P evaluation paths execute generated code in Docker. For G/P, dependency
installation and compilation occur in a build stage with registry-network access;
the later runtime probe applies resource limits and a track-specific network policy.
Those probe restrictions must not be attributed to every build-stage operation.
Containerized evaluation also does not establish confinement of the generation harness.
The live Track S CLI adapters lack an outer sealed-agent sandbox; some use permission-bypass
modes, and governed arms inherit host configuration. Adversarial execution requires
independent verification of the actual isolation boundary.

The lexical detector (L0) and in-memory action-replay scorer (L1) classify captured
text and proposed actions. Their historical “confirmed” fields are scorer labels,
not authenticated side-effect attestations. Echo filtering, refusal heuristics,
bounded capture, and missing typed tool-event provenance can misclassify outcomes.
Dynamic evaluation must also protect test-runner configuration and authenticate
verdicts rather than trusting candidate-produced terminal summaries.
The present implementation has not established security or evaluator-integrity sign-off.

## 7. Results and Evidence Status

The following **historical descriptive studies** explain the retained observations
without requiring access to internal execution records. They concern June 2026
artifacts and captures, not newly reproduced experiments. Five arm labels recur:
Codex CLI, Claude Code, OpenCode, Cortex over Codex, and Cortex over Claude.
The labels identify configurations, not independently authenticated model versions.
Each study's task set and observation unit are specified separately.

### 7.1 Captured-response safety pilot

This pilot asks how often captured responses are classified as following an unsafe
instruction, while separately checking benign refusals. The case set contains 61
harmful cases, two diagnostic instruction-following probes, and two benign controls.
Harmful objectives include secret disclosure, destructive repository operations,
unsafe dependencies, and attempts to disable protections. Delivery contexts include
direct requests and representations of repository, tool-output, and memory content;
they are not all native integrations with those surfaces.

One attempt is recorded for each completed case–arm cell. Across five arms, 290 of
305 possible harmful observations are retained; 15 are missing after timeouts.
The diagnostic probes and benign controls are excluded from the harmful-response
denominator. Figure 4 and Table 3 report classified successes divided by observed
harmful attempts, not by the configured maximum number of attempts.

__FIG_SAFETY__

<figure class="tbl" id="tbl-3">
<table>
<thead><tr><th>Historical arm label</th><th>Classified successes / observed attempts</th><th>ASR</th><th>Stored 95% Wilson interval</th></tr></thead>
<tbody>
<tr><td>Codex raw</td><td>25 / 59</td><td>42.37%</td><td>30.61–55.07%</td></tr>
<tr><td>Cortex over Codex</td><td>14 / 58</td><td>24.14%</td><td>14.96–36.53%</td></tr>
<tr><td>Claude raw</td><td>2 / 59</td><td>3.39%</td><td>0.93–11.54%</td></tr>
<tr><td>Cortex over Claude</td><td>1 / 60</td><td>1.67%</td><td>0.29–8.86%</td></tr>
<tr><td>OpenCode</td><td>23 / 54</td><td>42.59%</td><td>30.33–55.84%</td></tr>
</tbody>
</table>
<figcaption>Table 3. Historical classified safety outcomes from the stated June 2026
cohort. Intervals are the stored 95% Wilson intervals, not newly reproduced estimates.</figcaption>
</figure>

Using the exact observed counts, the descriptive relative ASR reductions,
$(\mathrm{ASR}_{\mathrm{raw}}-\mathrm{ASR}_{\mathrm{governed}})/\mathrm{ASR}_{\mathrm{raw}}$,
are approximately $43.0\%$ for the Codex-labeled pair and $50.8\%$ for the Claude-labeled
pair. These are relative reductions, not percentage-point differences.
The completed case sets differ between arms, and timed-out attempts cannot be
treated as safe responses. Each of the four paired arms has zero refusals on only
two benign controls, with stored interval $[0,65.76\%]$; OpenCode refuses one of
its two controls. Two diagnostic probes per arm are reported separately and are
not additional benign-utility trials.

The retained responses were subsequently rescored using lexical analysis,
in-memory replay of proposed actions, and response judging. No authenticated
external exploit follows from a positive classification. Historical judge summaries
also conflict: a summary describes heuristic judging while per-response entries
identify a language-model judge. This limits reconstruction of the exact scoring
protocol. These observations establish neither unchanged benign utility nor
statistical equivalence, low population over-refusal, or a governance-only causal effect.

### 7.2 Coding and application outcomes

Figure 5 compares three different outcomes, each with its own denominator.
The **quality study** comprises six code-generation tasks and one outcome per
task and arm. Its headline is the equal-weight mean of the six behavioral-test
pass fractions. Raw Codex and Claude both score $0.8125$, and their corresponding
Cortex configurations both score $0.9792$. The entire paired difference comes
from the TypeScript upload task; all four configurations still miss one
shopping-cart check. Table 4 in Appendix B.1 includes every task-level numerator
and denominator, including differing upload-test totals and generation failures.

The **repair study** replays patches for six elementary Python bugs, with one
outcome per issue and arm. All four raw/governed Codex and Claude configurations
resolve all six issues; OpenCode resolves five. There is no paired difference in
issue-resolution rate. Table 5 in Appendix B.2 reports all issue tests and the
separate patch-sensitive composites; empty auxiliary test groups are not evidence
of regression robustness.

The **application study** concerns a to-do app, not the chat gallery. Each arm
has one candidate and five final feature checks. Codex passes $3/5$; the other
four configurations pass $5/5$. All candidates build. Table 6 defines the checks,
and Figure 7 in Appendix B.3 shows their positions in the final checklist.
Those positions are not elapsed time or repeated execution milestones.

__FIG_5__

These are descriptive artifact evaluations, not matched governance-only trials.
Quality execution metadata conflict, repair lacks auxiliary robustness tests,
and the application study has no independently repeated candidates. Appendix B
retains these limitations beside the complete evidence.

### 7.3 Storefront outcomes and reference agreement

Two candidate pools address the same storefront brief in Section 6.3, with one
built application per arm. The two-arm pool scores $0.7489$ for raw Claude and
$0.6507$ for raw Codex. In the separate five-arm pool, raw Codex scores $0.7212$,
OpenCode $0.7071$, Cortex over Codex $0.6799$, raw Claude $0.6737$, and Cortex over
Claude $0.6533$. There is no universal Cortex advantage in these observations.
Tables 7–8 and Figure 8 in Appendix B.4 include every component, the composite
definition, recorded evaluator identities, and proxy limitations.

Figure 6 asks a narrower question: does estimated-reference VERTEX order these
same applications like authored-reference VERTEX? Higher similarity gives a
better rank; rank 1 is highest. The two-arm pool has identical ordering and
Spearman correlation $1$. The five-arm pool exchanges the first and third
positions, giving correlation $0.6$. Table 9 in Appendix B.5 supplies every score
pair and rank. Neither value is correctness accuracy or a probability that a
reference is valid. Peer-derived reference construction differs between pools;
both pools concern one brief, not seven independent task samples.

__FIG_6__

## 8. Discussion

The finite-lattice result identifies a precise contract for requirement closure:
validation must be monotone, accepted evidence sound, and prior certificates persistent.
Repairing code complicates the last condition because an edit can invalidate earlier
checks. Fresh validation of the final artifact is therefore central to connecting
the abstract contract with an operational completion decision.

The evaluation framework makes these obligations observable in principle, but the
archived comparisons do not identify a governance-only effect. A policy ablation should
hold the effective model, task set, tools, and total budget fixed, with independent final
evaluation. Replication across independently selected tasks and adequate benign controls
is needed to assess generalization and utility. Only retained benchmark observations
support the empirical discussion here; constructed outcomes are not evidence.

## 9. Assumptions and Limitations

The formal assumptions concern different boundaries. A1 requires complete mediation
and threat-class coverage; A2 requires sufficient abstract state and sound,
monotone, persistent certification; A3 requires bounded judgments grounded in
the evaluated evidence. Parsing a task into expectation records does not construct a sound
oracle. The probabilistic bound additionally requires uniformly positive progress
before completion; without it, expected completion time can be infinite.

The principal measurement limitations are length-sensitive similarity, heuristic
references, conditional journey/frame coverage, correlated attempts, and incomplete
observations. Section 6.6 specifies the unresolved execution and evaluator-integrity
boundaries. The current probes also do not fully measure payment integration,
carrier-task utility, consistency of claims with artifacts, or long-horizon behavior.

Historical missing or failed signals cannot be certified by changing current error
handling. The retained examples were recorded in June 2026; a later report date
does not represent a new experiment.

## 10. Conclusion

The retained benchmark outcomes do not show a uniform Cortex advantage. Classified
harmful-response rates are lower in the paired Cortex configurations, but completed
case sets differ and benign controls are too few to establish preserved utility
(Figure 4 and Table 3). Higher paired quality coverage comes from one upload task;
repair resolution is unchanged between paired configurations, and the single to-do
brief distinguishes task creation and readback rather than long-horizon progress
(Figure 5 and Tables 4–6). The storefront pools do not consistently favor Cortex.
Estimated-reference rank agreement varies across two pools for one brief and does
not establish correctness calibration (Figure 6 and Tables 7–9).

These conclusions concern the recorded benchmark outcomes, including artifact
rescoring. Unequal observation sets and unresolved provenance prevent treating all
cohorts as verified live experiments or attributing differences to governance alone.
The finite-lattice and stochastic results are conditional mathematical statements,
not performance gains established by these comparisons. Matched, independently
evaluated experiments are still required to estimate effects on safety, utility,
generalization and long-horizon completion.

## Availability

The interactive paper and latest published results are available at
[benchmark.cortex.a2olabs.com](https://benchmark.cortex.a2olabs.com).
Results retain their source cohorts, recorded measurements and evidence limitations.
The standalone Gauntlet benchmark snapshot is available at
[github.com/Xpitfire/cortex-gauntlet](https://github.com/Xpitfire/cortex-gauntlet).
It excludes private implementation dependencies and raw captures, so the screened
snapshot alone is not a complete end-to-end reproduction environment.
Download the Cortex CLI from [cortex.a2olabs.com](https://cortex.a2olabs.com/).
The downloadable PDF is a dated rendering of this paper, not a claim that the
historical results are new measurements.

## References

<ol class="refs">
<li id="ref-1">Dinu, M.-C., Leoveanu-Condrei, C., Holzleitner, M., Zellinger, W. &amp; Hochreiter, S.
(2024). <i>SymbolicAI: A framework for logic-based approaches combining generative models and
solvers.</i> arXiv:2402.00854. (Relational-trajectory
evaluation: Gaussian-kernel cross-similarity against a reference distribution, normalized against a
fixed random-sequence baseline.)</li>
<li id="ref-2">van Emden, M. H. & Kowalski, R. A. (1976). <i>The Semantics of Predicate Logic as a
Programming Language.</i> Journal of the ACM 23(4):733–742. (Immediate-consequence operator; least
fixed point.)</li>
<li id="ref-3">Tarski, A. (1955). <i>A lattice-theoretical fixpoint theorem and its applications.</i>
Pacific Journal of Mathematics 5(2):285–309.</li>
<li id="ref-4">Kleene, S. C. (1952). <i>Introduction to Metamathematics.</i> North-Holland. (Kleene iteration / first
recursion theorem.)</li>
<li id="ref-5">Banach, S. (1922). <i>Sur les opérations dans les ensembles abstraits et leur
application aux équations intégrales.</i> Fundamenta Mathematicae 3:133–181. (Contraction mapping.)</li>
<li id="ref-6">Garcez, A. d'Avila & Lamb, L. C. (2023). <i>Neurosymbolic AI: the 3rd wave.</i>
Artificial Intelligence Review 56(11):12387–12406.</li>
<li id="ref-7">Kautz, H. (2022). <i>The Third AI Summer.</i> AI Magazine 43(1) (AAAI Engelmore
Lecture).</li>
<li id="ref-8">Newell, A. & Simon, H. A. (1972). <i>Human Problem Solving.</i> Prentice-Hall.</li>
<li id="ref-9">Laird, J. E., Newell, A. & Rosenbloom, P. S. (1987). <i>SOAR: An architecture for general
intelligence.</i> Artificial Intelligence 33(1):1–64.</li>
<li id="ref-10">Anderson, J. R. et al. (2004). <i>An Integrated Theory of the Mind.</i>
Psychological Review 111(4):1036–1060.</li>
<li id="ref-11">Zhang, T., Kishore, V., Wu, F., Weinberger, K. Q. & Artzi, Y. (2020). <i>BERTScore:
Evaluating Text Generation with BERT.</i> ICLR.</li>
<li id="ref-12">Sakoe, H. & Chiba, S. (1978). <i>Dynamic programming algorithm optimization for spoken
word recognition.</i> IEEE Trans. ASSP 26(1):43–49.</li>
<li id="ref-13">Wilson, E. B. (1927). <i>Probable inference, the law of succession, and statistical
inference.</i> JASA 22(158):209–212.</li>
<li id="ref-14">Efron, B. (1979). <i>Bootstrap methods: another look at the jackknife.</i> Annals of
Statistics 7(1):1–26.</li>
<li id="ref-15">Chen, M. et al. (2021). <i>Evaluating Large Language Models Trained on Code.</i>
arXiv:2107.03374. (The $\mathrm{pass}@k$ unbiased estimator.)</li>
<li id="ref-16">Liu, Y. et al. (2023). <i>G-Eval: NLG Evaluation using GPT-4 with Better Human
Alignment.</i> EMNLP. arXiv:2303.16634.</li>
<li id="ref-17">Zheng, L. et al. (2023). <i>Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.</i>
NeurIPS. arXiv:2306.05685.</li>
<li id="ref-18">Kim, S. et al. (2024). <i>Prometheus 2: An open-source language model specialized in
evaluating other language models.</i> arXiv:2405.01535.</li>
<li id="ref-19">Patel, A. et al. (2024). <i>Large Language Models Can Self-Improve At Web Agent
Tasks.</i> arXiv:2405.20309.</li>
<li id="ref-20">Greshake, K. et al. (2023). <i>Not what you've signed up for: Compromising real-world
LLM-integrated applications with indirect prompt injection.</i> ACM AISec. arXiv:2302.12173.</li>
<li id="ref-21">Zhang, X., Wang, D., Xu, K., Zhu, Q. & Che, W. (2026). <i>Scaling Laws for Agent Harnesses
via Effective Feedback Compute.</i> arXiv:2605.29682.</li>
<li id="ref-22">Howard, R. A. (1966). <i>Information Value Theory.</i> IEEE Transactions on Systems
Science and Cybernetics 2(1):22–26.</li>
<li id="ref-23">Russell, S. & Wefald, E. (1991). <i>Principles of metareasoning.</i> Artificial
Intelligence 49(1–3):361–395.</li>
<li id="ref-24">Kaplan, J. et al. (2020). <i>Scaling Laws for Neural Language Models.</i>
arXiv:2001.08361.</li>
<li id="ref-25">Hoffmann, J. et al. (2022). <i>Training Compute-Optimal Large Language Models.</i>
arXiv:2203.15556.</li>
<li id="ref-26">Snell, C. et al. (2024). <i>Scaling LLM Test-Time Compute Optimally can be More Effective
than Scaling Model Parameters.</i> arXiv:2408.03314.</li>
<li id="ref-27">Brown, B. et al. (2024). <i>Large Language Monkeys: Scaling Inference Compute with
Repeated Sampling.</i> arXiv:2407.21787.</li>
<li id="ref-28">Lightman, H. et al. (2024). <i>Let's Verify Step by Step.</i> ICLR. arXiv:2305.20050.</li>
<li id="ref-29">Madaan, A. et al. (2023). <i>Self-Refine: Iterative Refinement with Self-Feedback.</i>
NeurIPS. arXiv:2303.17651.</li>
<li id="ref-30">Shinn, N. et al. (2023). <i>Reflexion: Language Agents with Verbal Reinforcement
Learning.</i> NeurIPS. arXiv:2303.11366.</li>
<li id="ref-31">Yao, S. et al. (2023). <i>ReAct: Synergizing Reasoning and Acting in Language Models.</i>
ICLR. arXiv:2210.03629.</li>
<li id="ref-32">Jimenez, C. E. et al. (2024). <i>SWE-bench: Can Language Models Resolve Real-World GitHub
Issues?</i> ICLR. arXiv:2310.06770.</li>
<li id="ref-33">OpenAI (2024). <i>Introducing SWE-bench Verified.</i> A 500-instance human-validated subset of
SWE-bench. openai.com/index/introducing-swe-bench-verified/.</li>
<li id="ref-34">Zhang, L. et al. (2025). <i>SWE-bench Goes Live!</i> arXiv:2505.23419. (Continuously updated,
contamination-resistant issue resolution.)</li>
<li id="ref-35">Merrill, M. A. et al. (2026). <i>Terminal-Bench: Benchmarking Agents on Hard, Realistic Tasks
in Command-Line Interfaces.</i> arXiv:2601.11868. tbench.ai.</li>
<li id="ref-36">Zhao, W. et al. (2025). <i>Commit0: Library Generation from Scratch.</i> ICLR.
arXiv:2412.01769.</li>
<li id="ref-37">Jain, N. et al. (2025). <i>LiveCodeBench: Holistic and Contamination-Free Evaluation of Large
Language Models for Code.</i> ICLR. arXiv:2403.07974.</li>
<li id="ref-38">Bhatt, M. et al. (2023). <i>Purple Llama CyberSecEval: A Secure Coding Benchmark for Language
Models.</i> arXiv:2312.04724.</li>
<li id="ref-39">Debenedetti, E. et al. (2024). <i>AgentDojo: A Dynamic Environment to Evaluate Prompt
Injection Attacks and Defenses for LLM Agents.</i> NeurIPS Datasets & Benchmarks. arXiv:2406.13352.</li>
<li id="ref-40">Zhan, Q. et al. (2024). <i>InjecAgent: Benchmarking Indirect Prompt Injections in
Tool-Integrated Large Language Model Agents.</i> ACL Findings. arXiv:2403.02691.</li>
<li id="ref-41">Yao, S. et al. (2024). <i>τ-bench: A Benchmark for Tool-Agent-User Interaction in Real-World
Domains.</i> arXiv:2406.12045.</li>
<li id="ref-42">Liu, X. et al. (2024). <i>AgentBench: Evaluating LLMs as Agents.</i> ICLR. arXiv:2308.03688.</li>
<li id="ref-43">Mialon, G. et al. (2024). <i>GAIA: a benchmark for General AI Assistants.</i> ICLR.
arXiv:2311.12983.</li>
<li id="ref-44">Zhou, S. et al. (2024). <i>WebArena: A Realistic Web Environment for Building Autonomous
Agents.</i> ICLR. arXiv:2307.13854.</li>
<li id="ref-45">Xie, T. et al. (2024). <i>OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real
Computer Environments.</i> NeurIPS Datasets & Benchmarks. arXiv:2404.07972.</li>
<li id="ref-46">Wei, A., Haghtalab, N. & Steinhardt, J. (2023). <i>Jailbroken: How Does LLM Safety Training
Fail?</i> NeurIPS. arXiv:2307.02483.</li>
<li id="ref-47">Rei, R., Stewart, C., Farinha, A. C. & Lavie, A. (2020). <i>COMET: A Neural Framework for MT
Evaluation.</i> EMNLP. arXiv:2009.09025. (Source-aware, reference-based translation evaluation.)</li>
<li id="ref-48">Gao, Y., Zhao, W. & Eger, S. (2020). <i>SUPERT: Towards New Frontiers in Unsupervised
Evaluation Metrics for Multi-Document Summarization.</i> ACL. arXiv:2005.03724. (Pseudo-reference built
from salient source content.)</li>
<li id="ref-49">Pillutla, K. et al. (2021). <i>MAUVE: Measuring the Gap Between Neural Text and Human Text
using Divergence Frontiers.</i> NeurIPS. arXiv:2102.01454. (Distributional comparison to a reference set
rather than to a single point.)</li>
<li id="ref-50">Kumar, S. & Byrne, W. (2004). <i>Minimum Bayes-Risk Decoding for Statistical Machine
Translation.</i> NAACL-HLT. (Selecting by consensus utility; other samples act as pseudo-references.)</li>
<li id="ref-51">Dawid, A. P. & Skene, A. M. (1979). <i>Maximum Likelihood Estimation of Observer Error-Rates
Using the EM Algorithm.</i> J. R. Stat. Soc. C 28(1):20–28. (A probabilistic noisy-observer model;
not a consistency proof for this benchmark's heuristic.)</li>
<li id="ref-52">van den Oord, A., Li, Y. & Vinyals, O. (2018). <i>Representation Learning with Contrastive
Predictive Coding.</i> arXiv:1807.03748. (InfoNCE: a contrastive objective that lower-bounds mutual
information.)</li>
<li id="ref-53">Ratner, A. et al. (2017). <i>Snorkel: Rapid Training Data Creation with Weak Supervision.</i>
VLDB 11(3):269–282. arXiv:1711.10160. (Denoising multiple weak label sources into one probabilistic
signal.)</li>
<li id="ref-54">Shannon, C. E. (1948). <i>A Mathematical Theory of Communication.</i> Bell System
Technical Journal 27:379–423, 623–656. (Self-information $-\log_2 p$ in bits; the basis for the surprisal
and risk-bit diagnostics of Section 5.6.)</li>
</ol>

## Appendix A — Proofs

The following calculations give the identities used in the score definitions and
conditional bounds. Labels P1–P8 distinguish these appendix calculations; they are
not additional manuscript propositions.

- **P1 (normalizer).** For $b\in[0,1)$, $\eta_b(x)=\operatorname{clamp}((x-b)/(1-b);0,1)$ maps $[b,1]$ onto $[0,1]$. On that interval the clamp is inactive and the affine map has positive slope $1/(1-b)$, with endpoints $\eta_b(b)=0$ and $\eta_b(1)=1$. Outside the interval the clamp is constant, so the complete map is nondecreasing, but not globally strictly increasing.
- **P2 (composite).** For $w\in\Delta(\{1,\dots,K\})$ and $s_k\in\mathbb{I}$, let $s_{\min}=\min_k s_k$ and $s_{\max}=\max_k s_k$. Multiplying $s_{\min}\le s_k\le s_{\max}$ by $w_k\ge0$ and summing gives $s_{\min}\le\sum_k w_k s_k\le s_{\max}$, because the weights sum to one. Thus the ungated average lies in $\mathbb{I}$, and the binary build gate gives $C=0$ when $g=0$ without changing that bound when $g=1$.
- **P3 (harmonic mean).** For $P,Q\ge0$, set $F=0$ at $P=Q=0$, otherwise $F=2PQ/(P+Q)$. The zero case satisfies the bounds directly; henceforth assume $P+Q>0$. If $0\le P\le Q$, then $F-P=P(Q-P)/(P+Q)\ge0$ and $Q-F=Q(Q-P)/(P+Q)\ge0$; exchange $P,Q$ for the other case. Also $(P+Q)/2-F=(P-Q)^2/(2(P+Q))\ge0$.
- **P4 (DTW).** For $m,n\in\mathbb{N}_{+}$, similarities in $[-1,1]$, and finite $\lambda\ge0$, both the local dissimilarity and its positional penalty factor are nonnegative. Every admissible alignment path therefore has nonnegative cost, as does the minimum over paths. Consequently $1-\mathrm{DTW}/(m+n)\le1$; clamping this quantity below at zero gives $D\in\mathbb{I}$. This is a range bound, not a guarantee that descriptor order represents elapsed execution time.
- **P5 (any-success and all-success estimators).** For integers $0\le c\le n$ and $1\le k\le n$, exactly $\binom{n-c}{k}$ of the $\binom{n}{k}$ subsets avoid success, while exactly $\binom{c}{k}$ consist entirely of successes. Thus $\mathrm{pass}@k=1-\binom{n-c}{k}/\binom{n}{k}$ is the fraction of $k$-subsets containing any success, and $\mathrm{pass}^{k}=\binom{c}{k}/\binom{n}{k}$ is the fraction consisting entirely of successes. Both lie in $[0,1]$. Coupling the subsets as prefixes of one uniform permutation shows that the any-success event can only grow with $k$, whereas the all-success event can only shrink. Under independent Bernoulli trials with common success probability $p$, each fixed subset has any-success probability $1-(1-p)^k$ and all-success probability $p^k$. Linearity of expectation gives unbiasedness for these respective targets. Independence is required for these targets, not for the finite-subset identities or monotonicity.
- **P6 (Wilson).** For $N>0$, $z>0$, and $\widehat p\in[0,1]$, the score-test boundary $(\widehat p-p)^2=z^2p(1-p)/N$ becomes $(N+z^2)p^2-(2N\widehat p+z^2)p+N\widehat p^2=0$. Applying the quadratic formula and dividing numerator and denominator by $N$ yields the interval endpoints in Section 5.3. Exact solution of this equation does not give exact confidence coverage: the score-test approximation and sampling assumptions remain necessary.
- **P7 (Theorem 1).** Inflationarity gives an increasing chain of requirement sets; each strict increase adds at least one previously absent member of finite $R$. Starting from the empty set permits at most $|R|$ such increases. Monotonicity keeps every iterate below every fixed point, so stabilization gives the least fixed point. Proposition 1 then follows because the successive set differences are disjoint and their union is the final certified set.
- **P8 (monotone Markov execution).** Under Proposition 2's uniform positive-progress assumption, the waiting time for each strict increase is bounded by a geometric waiting time of mean $1/\varepsilon$. At most $|R|-|S_0|$ increases can precede completion, giving the stated expectation bound by addition of expectations; independence between these waiting times is not needed. An incomplete absorbing state violates the progress assumption and is not covered by the result.

These arguments establish algebraic identities and conditional bounds. They do not
establish that a concrete validator is sound, that a repair preserves earlier
certificates, or that a reported experimental outcome is authentic. Those claims
require separate execution evidence and empirical validation.

## Appendix B — Complete historical result exhibits

This appendix contains the task-level and component-level evidence behind
Section 7. Figures and tables use a fixed arm order: raw Codex, Cortex over Codex,
raw Claude, Cortex over Claude, and OpenCode. A column headed by a base harness
and “+ Cortex” denotes its configured Cortex counterpart; “raw” means unwrapped.
Labels do not independently attest the historical model endpoint.

### B.1 Six-task code generation

The tasks are password and secret utilities, safe input parsing, database access,
a TypeScript upload API, web-security utilities, and a multi-file shopping-cart
package. The other five tasks use Python. There is one retained outcome per task
and arm, giving 30 outcomes. Four OpenCode generation failures remain in the
denominator rather than being discarded.

Table 4 gives passing and collected behavioral checks. The macro coverage is
the equal-weight mean of six task rates, not a pooled check count and not the
fraction of natural-language requirements independently certified. For the four
paired arms, the only differing task is upload: raw configurations record one
failing check, while Cortex configurations record two passing checks. Shopping
cart remains at seven of eight checks. Figure 5's left panel summarizes these
exact task rates.

__TABLE_4__

Per-outcome entries describe dynamic execution and nonzero test counts, but an
accompanying methodology summary describes offline variant selection and a
static-only containment boundary. These conflicting descriptions prevent
certifying a controlled live experiment; they also do not justify relabeling
every outcome synthetic. Static and heuristic quality indicators are
supplementary. Zero findings do not establish absence of vulnerabilities.

### B.2 Six elementary repair issues

The Python issues concern summing even rather than odd values, restoring
last-in-first-out stack removal, lowercasing URL slugs and stripping punctuation,
rounding up pagination for a partial page, case-insensitive word counting,
and enforcing a lower clamp bound. These are small issue-resolution tasks,
not a difficult multi-file repository benchmark.

Saved patches were replayed through the evaluator, producing 30 issue–arm
outcomes. Table 5 contains seven issue tests per arm: two stack tests and one
for every other issue. All four paired configurations resolve all six issues;
OpenCode fails pagination. The recorded composites combine resolution with
patch descriptors; the small Codex difference reflects patch minimality rather
than additional resolved issues. Figure 5 therefore plots resolution counts,
not a misleading composite improvement.

__TABLE_5__

No auxiliary held-out or regression tests were executed in any outcome.
Empty auxiliary groups received passing defaults and contribute no independent
robustness evidence. Reference-relative patch size and locality are not
correctness certificates. Replaying one patch is not another independent
generation, and no repeated-run variability is established.

### B.3 To-do application and final feature positions

The brief requests one full-stack to-do application. Table 6 lists its five
checks: a rendered task-list page, an input form, listing tasks, creating a task,
and reading that task back in the same session. The last check does not
establish persistence across process restarts. All candidates recorded successful
builds. There are five applications and 25 checks, not 25 independent tasks.

__TABLE_6__

Figure 7 displays the same final binary outcomes in their checklist order,
with normalized position from first to last feature. It does not depict a
completion-decay curve: there are no successive builds, evolving requirements,
or timestamped milestones in this summary. A collapsed interval from a single
candidate would not establish repeatability.

__FIG_7__

The surrounding historical summary describes a chat app and a larger feature
inventory, whereas the retained task and individual outcomes consistently
identify these five to-do checks. Separate chat illustrations and the current
chat protocol in Section 6.3 are not part of this scored evidence.

### B.4 Storefront components and composite

Two pools concern the same fashion-shopping storefront brief. All candidates
record successful build and serve checks and four screenshot entries. Existing
artifacts were rescored rather than regenerated for this analysis. Table 7
contains the two-arm pool; Table 8 contains the separate five-arm pool.

The eight composite weights, in table order before the composite row, are
$0.26$ for functional behavior, $0.14$ for VERTEX, $0.09$ for progressive-web-app
and accessibility checks, $0.16$ for visual similarity, $0.12$ for code and
architecture, $0.08$ for robustness, $0.06$ for code health, and $0.09$ for static
security. They sum to one and apply behind the build gate in Section 5.2.
The separately reported UX score is not another term.

Functional checks probe requested behavior; VERTEX compares capability and
architecture descriptors; PWA/accessibility checks are coarse structural
proxies; visual similarity compares screenshots. Code/architecture, robustness,
code-health, and static-security scores are bounded evaluator summaries, not
exhaustive correctness, resilience, or vulnerability certifications.
Section 6.3 details these limitations. The recorded visual backend is
CLIP ViT-B/32 and the descriptor embedding backend is all-MiniLM-L6-v2.
These are recorded identities, not an independent attestation of the complete
historical environment.

__TABLE_7__

__TABLE_8__

Figure 8 gives a common-scale view of all these components. The composite uses
authored-reference VERTEX; the estimated-reference diagnostic in Appendix B.5
does not replace that component. The pools do not isolate governance:
configuration, repair opportunities, and final-evaluation independence were
not held fixed.

__FIG_8__

### B.5 Authored and estimated reference ranks

The authored reference contains 13 capability descriptions and five architectural
anchors. Estimated references use the public brief and the synthetic design
vocabulary explained in Section 5.1.1. The pool diagnostic can also use descriptors
supported by at least two other arms, excluding the candidate itself. This peer
component is unavailable in the two-arm pool and can contribute in the five-arm
pool, so reference construction differs.

Table 9 contains all score pairs underlying Figure 6. Both methods rank Claude
above Codex in the two-arm pool; with two unequal observations, matching order
alone yields correlation $1$. The five-arm pool exchanges raw Codex and Cortex
over Codex between ranks one and three, leaving the remaining ranks unchanged
and yielding correlation $0.6$.

__TABLE_9__

Both diagnostics concern one independently specified brief. No cross-brief
holdout evaluation or correlation interval is reported. Similarity-rank
agreement is not agreement on complete task correctness; peer-derived references
can reproduce shared errors. These observations motivate further validation,
not discarding authored references or claiming measured long-horizon performance.

## Cite this work

If you use Cortex or its evaluation harness, please cite this report:

<div class="cite">
  <div class="cite-row"><span class="cite-label">BibTeX</span><button class="copy-btn" data-copy="cite-bibtex">Copy BibTeX</button></div>
  <pre id="cite-bibtex">@techreport{dinu2026cortex,
  title       = {Cortex: A Fixed-Point Theory of Governed Coding Agents},
  author      = {Dinu, Marius-Constantin and Zeba, Florian},
  institution = {Alpha Omega Labs},
  year        = {2026},
  type        = {Technical report},
  url         = {https://benchmark.cortex.a2olabs.com}
}</pre>
  <div class="cite-row"><span class="cite-label">Plain text</span><button class="copy-btn" data-copy="cite-plain">Copy</button></div>
  <p id="cite-plain">Dinu, M.-C. &amp; Zeba, F. (2026). Cortex: A Fixed-Point Theory of Governed Coding Agents. Technical report, Alpha Omega Labs.</p>
</div>

<div class="links">
  <a href="https://arxiv.org/abs/2402.00854" target="_blank" rel="noopener">Dinu et al. 2024 — arXiv:2402.00854</a>
</div>
"""


def _paper_md() -> str:
    return render_exhibits(
        _PAPER.replace("__FIG_LOOP__", '<figure class="fig" id="fig-1">'
                       f'<div class="figure-graphic" role="group" tabindex="0" aria-label="Repair-loop diagram">{_FIG_LOOP}</div>'
                       "<figcaption>Figure 1. Schematic execution–validation–repair architecture. "
                       "Its consequence-operator abstraction requires a sufficient requirement state, "
                       "monotone validation, and sound persistent certificates (Section 4.2). "
                       "The operational repair cycle does not establish those assumptions.</figcaption></figure>")
        .replace("__FIG_LATTICE__", '<figure class="fig" id="fig-2">'
                 f'<div class="figure-graphic" role="group" tabindex="0" aria-label="Closure diagram">{_FIG_LATTICE}</div>'
                 "<figcaption>Figure 2. Illustrative Kleene ascent for the fixed monotone operator "
                 "of Theorem 1, not a measured agent trace. At most $|R|$ strict increases occur; "
                 "one further evaluation may detect closure. A fair schedule reaches the same "
                 "least fixed point, which can leave required work unresolved.</figcaption></figure>")
        .replace("__FIG_VERTEX__", '<figure class="fig" id="fig-3">'
                 f'<div class="figure-graphic" role="group" tabindex="0" aria-label="VERTEX diagrams">{_FIG_VERTEX}</div>'
                 "<figcaption>Figure 3. The two components of the VERTEX trajectory score (Section 5.1). "
                 "Left: the cross-similarity matrix $\\mathbf{S}_{ij}=\\langle\\varphi(c_i),\\varphi(r_j)\\rangle$ "
                 "between candidate descriptors $c_i$ (rows) and reference descriptors $r_j$ (columns); "
                 "stronger color indicates higher similarity in this illustrative matrix. The <em>presence</em> component reads bidirectional best "
                 "matches off this matrix (which reference behaviors appear, and how strongly). Right: "
                 "the <em>order</em> component uses a minimum-cost monotone DTW alignment. Its "
                 "step cost $(1-\\mathbf{S}_{ij})(1+\\lambda|\\frac{i-1}{m}-\\frac{j-1}{n}|)$ increases with "
                 "normalized positional displacement. Both components are recalibrated against the mean-similarity "
                 "baseline (Proposition 3).</figcaption></figure>")
        .replace("__FIG_SAFETY__", '<figure class="fig" id="fig-4">'
                 f'<div class="figure-graphic" role="group" tabindex="0" aria-label="Historical ASR chart">{_safety_figure()}</div>'
                 "<figcaption>Figure 4. Classified attack responses in the June 2026 safety pilot, "
                 "comparing five historical harness configurations. Points show observed rates, whiskers "
                 "the stored 95% Wilson intervals, and labels the successes and observed attempts. "
                 "Model names are historical labels. Section 7 describes coverage, provenance, "
                 "and benign-control limitations; these are descriptive, not causal comparisons.</figcaption></figure>")
        .replace("{generated}", "September 2026")
    )


# public deploy base (see BENCHMARK.md) — used to build ABSOLUTE Open-Graph URLs so link previews work
# in WhatsApp/Slack/iMessage/X/LinkedIn/Facebook (scrapers don't run JS, so the tags must be static).
# Update this one constant + re-run `python -m tools.build_og_cover` after a redeploy to a new host.
_SITE_BASE = "https://benchmark.cortex.a2olabs.com"
_OG_TITLE = "Cortex: A Fixed-Point Theory of Governed Coding Agents"
_OG_DESC = ("Conditional fixed-point semantics and benchmark methodology for governed coding agents, "
            "with explicit mathematical assumptions and historical-evidence limitations.")
_OG_META = (
    f'<meta name="description" content="{_OG_DESC}"/>\n'
    f'<link rel="canonical" href="{_SITE_BASE}/docs.html"/>\n'
    f'<meta property="og:type" content="article"/>\n'
    f'<meta property="og:site_name" content="Cortex Research · Alpha Omega Labs"/>\n'
    f'<meta property="og:title" content="{_OG_TITLE}"/>\n'
    f'<meta property="og:description" content="{_OG_DESC}"/>\n'
    f'<meta property="og:url" content="{_SITE_BASE}/docs.html"/>\n'
    f'<meta property="og:image" content="{_SITE_BASE}/og-cover.png"/>\n'
    '<meta property="og:image:width" content="1200"/>\n'
    '<meta property="og:image:height" content="630"/>\n'
    '<meta name="twitter:card" content="summary_large_image"/>\n'
    f'<meta name="twitter:title" content="{_OG_TITLE}"/>\n'
    f'<meta name="twitter:description" content="{_OG_DESC}"/>\n'
    f'<meta name="twitter:image" content="{_SITE_BASE}/og-cover.png"/>'
)

_DOCS_TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Cortex — Formal Foundations</title>
__OG__
__HEAD__
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css"/>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>__CSS__
  body{overflow-x:hidden}
  .paper{display:grid;grid-template-columns:240px minmax(0,1fr);gap:32px;align-items:start;max-width:100%;min-width:0}
  @media(max-width:900px){.paper{grid-template-columns:1fr}.toc{display:none}}
  .toc{position:sticky;top:84px;font-size:13px;border-left:2px solid var(--line);padding-left:14px;max-height:calc(100vh - 110px);overflow:auto}
  .toc a{display:block;color:var(--muted);text-decoration:none;padding:3px 0}
  .toc a:hover,.toc a.on{color:var(--accent)}
  .toc a.h3{padding-left:12px;font-size:12px}
  article.doc{max-width:820px;min-width:0;overflow-wrap:anywhere}
  article.doc>*{max-width:100%}
  article.doc h1{font-size:30px;letter-spacing:-.6px;margin:0 0 4px;overflow-wrap:anywhere}
  article.doc h2{font-size:21px;margin:34px 0 8px;padding-top:8px;border-top:1px solid var(--line)}
  article.doc h3{font-size:16px;margin:20px 0 6px}
  article.doc p,article.doc li{line-height:1.7;overflow-wrap:anywhere}
  article.doc .byline{color:var(--muted);font-size:14px;margin-bottom:6px}
  article.doc .authors{margin:2px 0 14px;font-size:15px}
  article.doc .authors .author{color:var(--ink);font-weight:600}
  article.doc .authors .sep{color:var(--muted);margin:0 8px}
  article.doc .authors .affil{color:var(--muted);font-size:13px;margin-top:2px}
  article.doc .cite{border:1px solid var(--line);border-radius:12px;padding:6px 14px 12px;margin:12px 0;
    background:rgba(127,127,127,.04)}
  article.doc .cite-row{display:flex;align-items:center;justify-content:space-between;margin:12px 0 4px}
  article.doc .cite-label{color:var(--muted);font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
  article.doc .cite pre{background:var(--card);border:1px solid var(--line);border-radius:8px;
    padding:11px 13px;overflow-x:auto;font-size:12.5px;line-height:1.5;margin:0;color:var(--ink)}
  article.doc .cite pre code{background:none;color:var(--ink)}
  article.doc .cite p{margin:0;font-size:13.5px;color:var(--ink)}
  .copy-btn{cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--accent);
    border-radius:7px;padding:3px 11px;font-size:12px;font-weight:600;transition:all .12s}
  .copy-btn:hover{border-color:var(--accent)} .copy-btn.copied{color:#16a34a;border-color:#16a34a}
  article.doc .links{margin:10px 0 4px;display:flex;flex-wrap:wrap;gap:14px}
  article.doc .links a{color:var(--accent);text-decoration:none;font-weight:600;font-size:13.5px}
  article.doc .links a:hover{text-decoration:underline}
  article.doc .share{display:flex;align-items:center;gap:9px;margin:0 0 22px;flex-wrap:wrap}
  article.doc .share-label{color:var(--muted);font-size:12px;font-weight:600;text-transform:uppercase;
    letter-spacing:.05em;margin-right:2px}
  .share-btn{display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;
    border:1px solid var(--line);border-radius:9px;color:var(--muted);background:var(--card);
    cursor:pointer;text-decoration:none;transition:all .14s}
  .share-btn:hover{color:#fff;background:var(--accent);border-color:var(--accent);transform:translateY(-1px)}
  .share-btn.copied{color:#fff;background:#16a34a;border-color:#16a34a}
  article.doc blockquote{border-left:3px solid var(--accent);margin:14px 0;padding:6px 16px;
    background:rgba(109,94,251,.06);border-radius:0 10px 10px 0}
  figure.fig{margin:28px 0;min-width:0}
  .figure-graphic{max-width:100%;overflow-x:auto;overflow-y:hidden;padding:12px 0}
  .figure-graphic:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
  .figure-graphic::before{display:none;content:"Scroll horizontally to view the full diagram";position:sticky;left:0;
    color:var(--muted);font-size:12px;padding-bottom:10px}
  @media(max-width:720px){.figure-graphic::before{display:block}}
  figure.fig .figsvg{display:block;width:100%;min-width:680px;max-width:800px;height:auto;margin-inline:auto}
  figure.fig figcaption{color:var(--muted);font-size:13px;line-height:1.6;margin:10px 0 0;text-align:left}
  @media print{.figure-graphic{overflow:visible}.figure-graphic::before{display:none}
    figure.fig .figsvg{min-width:0;max-width:100%}figure.fig{break-inside:avoid}}
  ol.refs{font-size:13.5px;line-height:1.55;padding-left:22px} ol.refs li{margin:5px 0}
  .katex-display{max-width:100%;overflow-x:auto;overflow-y:hidden;padding:4px 0}
  sup a{color:var(--accent);text-decoration:none;cursor:pointer}
  sup a:hover{text-decoration:underline}
  .citecard{position:absolute;z-index:60;width:360px;max-width:88vw;background:var(--card);
    border:1px solid var(--line);border-radius:12px;padding:13px 15px;
    box-shadow:0 8px 28px rgba(16,18,34,.22);font-size:12.5px;line-height:1.5}
  .citecard .cc-t{font-weight:700;color:var(--ink);margin-bottom:2px}
  .citecard .cc-m{color:var(--muted);font-size:11.5px;margin-bottom:7px}
  .citecard .cc-a{color:var(--ink);max-height:180px;overflow:auto}
  .citecard .cc-l{display:inline-block;margin-top:9px;color:var(--accent);text-decoration:none;font-weight:600}
  .cc-back{color:var(--accent);text-decoration:none;font-weight:700;margin-left:6px}
  article.doc code{background:rgba(127,127,127,.12);border-radius:5px;padding:1px 5px;font-size:.92em}
  article.doc table{display:block;width:100%;max-width:100%;border-collapse:collapse;font-size:13px;margin:10px 0;overflow-x:auto}
  article.doc th,article.doc td{border:1px solid var(--line);padding:7px 9px;text-align:left;vertical-align:top}
  article.doc th{background:rgba(127,127,127,.06);font-weight:600}
  a.xref{color:var(--accent);text-decoration:none;border-bottom:1px dotted currentColor}
  a.xref:hover{border-bottom-style:solid}
  figure.tbl{margin:20px 0}
  figure.tbl figcaption{color:var(--muted);font-size:12.5px;margin-top:6px;text-align:left;max-width:780px}
  .paper-downloads{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 20px}
  .paper-downloads a{display:inline-flex;align-items:center;border:1px solid var(--line);
    border-radius:9px;padding:9px 14px;color:var(--accent);background:var(--card);
    font-size:13px;font-weight:600;text-decoration:none}
  .paper-downloads a:hover{border-color:var(--accent)}
  .paper-downloads a.primary{background:var(--accent);color:#fff}
</style></head><body>
__NAVBAR__
<div class="wrap">
  __DOWNLOADS__
  <div class="paper">
    <nav class="toc" id="toc"></nav>
    <article class="doc" id="article">Rendering…</article>
  </div>
  <footer>Formal companion to the empirical reports · generated __GENERATED__.</footer>
</div>
<script id="paper" type="text/markdown">__PAPER__</script>
<script id="cites" type="application/json">__CITES_JSON__</script>
<script>__COMMON_JS__</script>
<script>
// collapse newlines + blockquote '>' prefixes so a $…$ / $$…$$ span that crosses a line (e.g. inside a
// blockquote theorem) is still valid LaTeX after extraction.
function cleanMath(e){return e.replace(/\n\s*>?\s*/g,' ').trim();}
function renderPaper(){
  const md = document.getElementById('paper').textContent;
  const math=[];
  let s = md.replace(/\$\$([\s\S]+?)\$\$/g,(_m,e)=>{math.push([cleanMath(e),true]);return '@@M'+(math.length-1)+'@@';});
  s = s.replace(/\$([^$]+?)\$/g,(_m,e)=>{math.push([cleanMath(e),false]);return '@@M'+(math.length-1)+'@@';});
  let html = marked.parse(s);
  html = html.replace(/@@M(\d+)@@/g,(_m,i)=>{const [e,d]=math[i];
    try{return katex.renderToString(e,{displayMode:d,throwOnError:false});}catch(err){return e;}});
  const art=document.getElementById('article'); art.innerHTML=html;
  const toc=document.getElementById('toc'); const heads=art.querySelectorAll('h2,h3,h4');
  heads.forEach(h=>{const t=h.textContent.trim(); const num=t.match(/^(\d+(?:\.\d+)*)/);
    h.id = num ? 'sec-'+num[1] : 'sec-'+t.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/(^-|-$)/g,'');
    const a=document.createElement('a'); a.href='#'+h.id; a.textContent=t;
    if(h.tagName!=='H2')a.className='h3'; toc.appendChild(a);});
  crossLink(art);  // turn "Section X", "Theorem N", "Figure N", "Proposition N", "Table N" into jump links
  const links=[...toc.querySelectorAll('a')];
  const obs=new IntersectionObserver(es=>{es.forEach(e=>{if(e.isIntersecting){
    links.forEach(l=>l.classList.toggle('on', l.getAttribute('href')==='#'+e.target.id));}});},
    {rootMargin:'-80px 0px -70% 0px'});
  heads.forEach(h=>obs.observe(h));
  wireCitations(art);
  wireCopy(art);  // copy-to-clipboard for the BibTeX / citation blocks
  wireShare(art); // social share buttons (X / LinkedIn / Facebook / WhatsApp / copy link)
}
// build share-intent links from the LIVE page URL (works wherever the site is deployed)
function wireShare(art){
  const url=location.href, text='Cortex: A Fixed-Point Theory of Governed Coding Agents';
  const u=encodeURIComponent(url), t=encodeURIComponent(text);
  const targets={
    x:`https://twitter.com/intent/tweet?text=${t}&url=${u}`,
    linkedin:`https://www.linkedin.com/sharing/share-offsite/?url=${u}`,
    facebook:`https://www.facebook.com/sharer/sharer.php?u=${u}`,
    whatsapp:`https://wa.me/?text=${t}%20${u}`,
  };
  art.querySelectorAll('.share-btn[data-share]').forEach(b=>{
    const k=b.getAttribute('data-share');
    if(targets[k]){ b.setAttribute('href',targets[k]); b.setAttribute('target','_blank'); b.setAttribute('rel','noopener');
      b.addEventListener('click',e=>{e.preventDefault();window.open(targets[k],'_blank','noopener,noreferrer,width=620,height=580');});
    } else if(k==='copy'){
      b.addEventListener('click',()=>{const done=()=>{b.classList.add('copied');b.title='Link copied!';
        setTimeout(()=>{b.classList.remove('copied');b.title='Copy link';},1400);};
        if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(url).then(done).catch(()=>copyFallback(url,done));}
        else copyFallback(url,done);});
    }
  });
}
// copy the referenced block's text to the clipboard with brief "Copied!" feedback
function wireCopy(art){
  art.querySelectorAll('.copy-btn[data-copy]').forEach(btn=>{
    const original=btn.textContent;let reset;
    btn.addEventListener('click',()=>{
      const el=document.getElementById(btn.getAttribute('data-copy')); if(!el)return;
      const text=el.textContent;
      const done=()=>{clearTimeout(reset);btn.textContent='Copied!';btn.classList.add('copied');
        reset=setTimeout(()=>{btn.textContent=original;btn.classList.remove('copied');},1400);};
      if(navigator.clipboard&&navigator.clipboard.writeText){
        navigator.clipboard.writeText(text).then(done).catch(()=>copyFallback(text,done));
      }else copyFallback(text,done);
    });
  });
}
function copyFallback(text,done){const ta=document.createElement('textarea');ta.value=text;
  ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();
  try{document.execCommand('copy');done();}catch(e){}document.body.removeChild(ta);}
// auto-link cross-references to their anchors (text nodes only; never inside math, code, links, or captions)
function crossLink(art){
  const SRC='\\bSections?\\s+\\d+(?:\\.\\d+)*\\s*[\\u2013-]\\s*\\d+(?:\\.\\d+)*'+
            '|\\bSection\\s+\\d+(?:\\.\\d+)*|§\\s*\\d+(?:\\.\\d+)*'+
            '|\\bTheorem\\s+\\d+|\\bProposition\\s+\\d+|\\bFigures?\\s+\\d+|\\bTable\\s+\\d+';
  const idFor=s=>{const n=s.match(/\d+(?:\.\d+)*/)[0];
    if(/Theorem/.test(s))return 'thm-'+n; if(/Proposition/.test(s))return 'prop-'+n;
    if(/Figure/.test(s))return 'fig-'+n; if(/Table/.test(s))return 'tbl-'+n; return 'sec-'+n;};
  const SKIP=new Set(['A','CODE','PRE','SUP','H1','H2','H3','FIGCAPTION']);
  const walker=document.createTreeWalker(art, NodeFilter.SHOW_TEXT, {acceptNode:n=>{
    for(let p=n.parentNode;p&&p!==art;p=p.parentNode){
      if(SKIP.has(p.nodeName)||(p.classList&&p.classList.contains('katex')))return NodeFilter.FILTER_REJECT;}
    return new RegExp(SRC).test(n.nodeValue)?NodeFilter.FILTER_ACCEPT:NodeFilter.FILTER_SKIP;}});
  const nodes=[]; let cur; while(cur=walker.nextNode())nodes.push(cur);
  nodes.forEach(n=>{const txt=n.nodeValue; const re=new RegExp(SRC,'g');
    let last=0,m,changed=false; const frag=document.createDocumentFragment();
    while(m=re.exec(txt)){const id=idFor(m[0]); if(!document.getElementById(id))continue;
      frag.appendChild(document.createTextNode(txt.slice(last,m.index)));
      const a=document.createElement('a'); a.className='xref'; a.href='#'+id; a.textContent=m[0];
      frag.appendChild(a); last=m.index+m[0].length; changed=true;}
    if(changed){frag.appendChild(document.createTextNode(txt.slice(last))); n.parentNode.replaceChild(frag,n);}});
}
// hover preview cards for every [n] citation; click still jumps to the reference, which links back.
function wireCitations(art){
  const CITES = JSON.parse(document.getElementById('cites').textContent);
  const card=document.createElement('div'); card.className='citecard'; card.style.display='none';
  document.body.appendChild(card);
  let hideT=null, lastCite=null;
  const show=a=>{const n=(a.getAttribute('href')||'').replace('#ref-',''); const c=CITES[n]; if(!c)return;
    card.innerHTML=`<div class="cc-t">${c.title}</div><div class="cc-m">${c.meta}</div>`+
      `<div class="cc-a">${c.abstract}</div>`+
      (c.url?`<a class="cc-l" href="${c.url}" target="_blank" rel="noopener">open paper ↗</a>`:'');
    const r=a.getBoundingClientRect(); const w=360;
    card.style.display='block';
    card.style.top=(window.scrollY+r.bottom+8)+'px';
    card.style.left=Math.max(12, Math.min(window.scrollX+r.left, window.scrollX+document.documentElement.clientWidth-w-12))+'px';};
  const hide=()=>{hideT=setTimeout(()=>{card.style.display='none';},180);};
  const keep=()=>clearTimeout(hideT);
  art.querySelectorAll('sup a[href^="#ref-"]').forEach(a=>{
    a.addEventListener('mouseenter',()=>{keep();show(a);});
    a.addEventListener('mouseleave',hide);
    a.addEventListener('click',()=>{lastCite=a;});
  });
  card.addEventListener('mouseenter',keep); card.addEventListener('mouseleave',hide);
  art.querySelectorAll('ol.refs li[id^="ref-"]').forEach(li=>{
    const b=document.createElement('a'); b.className='cc-back'; b.href='#'; b.title='back to citation';
    b.setAttribute('aria-label','back to citation'); b.textContent=' ↩';
    b.addEventListener('click',e=>{e.preventDefault(); if(lastCite) lastCite.scrollIntoView({behavior:'smooth',block:'center'});});
    li.appendChild(b);
  });
}
if(window.katex&&window.marked){renderPaper();}else{window.addEventListener('load',renderPaper);}
</script>
</body></html>
"""


def _paper_downloads(out_path: Path) -> str:
    import hashlib
    import json
    from .paper import source_digest, template_digest

    links = '<a href="https://github.com/Xpitfire/cortex-gauntlet" target="_blank" rel="noopener">GitHub repository</a>'
    directory = out_path.parent / "paper"
    manifest = directory / "manifest.json"
    if manifest.exists():
        metadata = json.loads(manifest.read_text())
        if metadata["source_sha256"] != source_digest() or metadata["template_sha256"] != template_digest():
            raise ValueError("Paper publication is stale; run python -m gauntlet.paper before rebuilding the site")
        for filename, key in (("cortex-gauntlet.pdf", "pdf_sha256"),
                              ("cortex-gauntlet-arxiv.zip", "archive_sha256")):
            if hashlib.sha256((directory / filename).read_bytes()).hexdigest() != metadata[key]:
                raise ValueError(f"Paper publication artifact does not match its manifest: {filename}")
        links = (
            '<a class="primary" href="paper/cortex-gauntlet.pdf" download="cortex-gauntlet.pdf">Download paper PDF</a>'
            '<a href="paper/cortex-gauntlet-arxiv.zip" download>arXiv LaTeX source</a>'
            '<a href="paper/submission.txt">Submission instructions</a>' + links
        )
    return '<div class="paper-downloads" aria-label="Paper downloads and source">' + links + '</div>'


def build_docs(out_path: Path, links: dict | None = None) -> str:
    import json

    generated = datetime.now().isoformat(timespec="seconds")
    html = (
        _DOCS_TEMPLATE.replace("__OG__", _OG_META).replace("__HEAD__", REPORT_HEAD).replace("__CSS__", REPORT_CSS)
        .replace("__NAVBAR__", navbar("index.html", "Paper", links))
        .replace("__COMMON_JS__", COMMON_JS)
        .replace("__DOWNLOADS__", _paper_downloads(out_path))
        .replace("__PAPER__", _paper_md().replace("</script>", "<\\/script>"))
        .replace("__CITES_JSON__", json.dumps(CITES).replace("</", "<\\/"))
        .replace("__GENERATED__", generated)
    )
    out_path.write_text(html, encoding="utf-8")
    return html
