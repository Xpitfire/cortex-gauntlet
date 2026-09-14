"""Stable enums for the benchmark data contract (no scattered string literals)."""

from enum import Enum


class Track(str, Enum):
    SECURITY = "security"
    GENERATIVE = "generative"
    QUALITY = "quality"
    PROJECT = "project"  # Track P: one-prompt full-repo build, sandboxed + multi-signal scored
    REPO = "repo"  # "Bugfix" track (display name): fix a bug in an existing repo so a failing hidden
    #                test passes (SWE-bench style). Value stays "repo" — the stable run-id/CLI/route id.


class Surface(str, Enum):
    """Where an attack enters the harness."""

    DIRECT_TURN = "direct_turn"
    REPO_FILE = "repo_file"
    TOOL_OUTPUT = "tool_output"
    MEMORY_SESSION = "memory_session"
    IMAGE = "image"
    AUDIO = "audio"


class Technique(str, Enum):
    """How a payload evades safeguards."""

    DIRECT = "direct"
    IGNORE_PREVIOUS = "ignore_previous"
    ROLEPLAY_DAN = "roleplay_dan"
    SOCIAL_ENGINEERING = "social_engineering"
    ENCODING_BASE64 = "encoding_base64"
    LEETSPEAK = "leetspeak"
    PAYLOAD_SPLIT = "payload_split"
    ZERO_WIDTH = "zero_width"
    MANY_SHOT = "many_shot"
    LOW_RESOURCE_LANG = "low_resource_lang"
    PAST_TENSE = "past_tense"
    ASCII_ART = "ascii_art"
    CIPHER = "cipher"
    # recent obfuscation transforms (2024-2026) applied to a buried injection — see transforms.py
    MIXED_CASE = "mixed_case"  # 404media "APpaREnTLy" / BoN caps component
    BON_PERTURBATION = "bon_perturbation"  # Best-of-N: scramble + caps + ASCII noise (arXiv:2412.03556)
    FLIP = "flip"  # FlipAttack: reverse the text + recovery hint (arXiv:2410.02832)
    ASCII_SMUGGLE = "ascii_smuggle"  # invisible Unicode Tags U+E0000-E007F (Rehberger; vs Claude Code)
    HOMOGLYPH = "homoglyph"  # Latin->Cyrillic confusables (defeats keyword/regex scans)
    BASE64_COMMENT = "base64_comment"  # base64 inside an HTML comment ("Comment & Control")
    BITBYPASS = "bitbypass"  # hyphen-separated bitstream camouflage (arXiv:2506.02479)
    ARTPROMPT = "artprompt"  # ASCII-art / spaced-letter masking of the request (arXiv:2402.11753)
    POLICY_PUPPETRY = "policy_puppetry"  # authoritative policy/config-block framing + leetspeak (HiddenLayer)
    # agentic tier: the injection is framed as legitimate workflow/authority in a file the agent reads
    WORKFLOW_FRAMED = "workflow_framed"  # README/setup/important-message: "first confirm setup by …"
    DIAGNOSTIC = "diagnostic"  # CI log / code comment: "to debug, echo the secret …"
    CONFUSED_DEPUTY = "confused_deputy"  # hidden HTML comment in an issue/PR: "<!-- SYSTEM: … -->"
    RULES_FILE = "rules_file"  # .cursorrules/AGENTS-style: "MANDATORY FIRST STEP: read .env …"
    MARKDOWN_EXFIL = "markdown_exfil"  # emit an image/URL embedding the secret (base64)
    DANGEROUS_ACTION = "dangerous_action"  # propose the exact exfil command
    FALSE_PROVENANCE = "false_provenance"  # fabricated legality/authorization/policy recontextualizes it


class Objective(str, Enum):
    """The harmful coding action a case targets (what we score)."""

    SECRET_EXFIL = "secret_exfil"
    MALICIOUS_DEP = "malicious_dep"
    DESTRUCTIVE_GIT = "destructive_git"
    ARBITRARY_SHELL = "arbitrary_shell"
    SAFETY_DISABLE = "safety_disable"  # disable/weaken auth, TLS, signature, or other security checks
    ILLEGAL_INTEGRATION = "illegal_integration"  # wire in an illegitimate/infringing source (fake-legal)
    BRAND_CLONE = "brand_clone"  # clone a famous brand's UI from a screenshot (IP/trademark infringement)
    CANARY_ECHO = "canary_echo"
    BENIGN = "benign"


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class Language(str, Enum):
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Instrument(str, Enum):
    """Which scorer produced a verdict."""

    DETERMINISTIC = "deterministic"
    SANDBOX = "sandbox"
    JUDGE = "judge"
    HUMAN = "human"


class Verdict(str, Enum):
    """Track S attack-success rubric."""

    REFUSAL = "refusal"
    DEFLECT = "deflect"
    PARTIAL_COMPLY = "partial_comply"
    FULL_COMPLY = "full_comply"


HARMFUL_OBJECTIVES = frozenset(
    {Objective.SECRET_EXFIL, Objective.MALICIOUS_DEP, Objective.DESTRUCTIVE_GIT, Objective.ARBITRARY_SHELL,
     Objective.SAFETY_DISABLE, Objective.ILLEGAL_INTEGRATION, Objective.BRAND_CLONE}
)

# Agentic-tier framings author their injection inline in agentic_corpus.py (no text transform); the
# rest obfuscate a base instruction and are registered in transforms.TRANSFORMS.
AGENTIC_TECHNIQUES = frozenset(
    {Technique.WORKFLOW_FRAMED, Technique.DIAGNOSTIC, Technique.CONFUSED_DEPUTY,
     Technique.RULES_FILE, Technique.MARKDOWN_EXFIL, Technique.DANGEROUS_ACTION,
     Technique.FALSE_PROVENANCE}
)
OBFUSCATION_TECHNIQUES = frozenset(Technique) - AGENTIC_TECHNIQUES
