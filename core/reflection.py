"""
core/reflection.py

Reflection critic — the hallucination guardrail that runs after every
synthesis call.

Pipeline shape (per PROJECT_TODO_MASTER.md §1.6):

    candidate_answer (from synthesis)
      → reflect(question, profile, source_pages, candidate_answer)
      → ReflectionResult{ verdict, checks, regenerate_guidance, raw }
      → if verdict == "REGENERATE":
            answer = await call_gemini(synthesis_prompt + critique)
        else:
            answer = candidate_answer

The critic uses the same Gemini model as synthesis (Gemini-only stack), but
with a structured-output prompt that forces a 6-check rubric. Output is parsed
defensively: if Gemini doesn't produce a verdict line we default to ACCEPT
(better to ship a possibly-imperfect answer than to never ship one).

The critic's response is also saved into the insight page YAML frontmatter as
``reflection: {grounded: PASS, ...}`` — this becomes a Trust Layer asset and a
visible UI badge ("🛡️ Fact-checked" vs "🟡 Refined after self-review").

This module is Gemini-only by policy (PROJECT_TODO_MASTER.md §17 lock).
"""

from __future__ import annotations

import re
from typing import Literal, TypedDict

from loguru import logger

from core.wiki import call_gemini

# ── Public types ─────────────────────────────────────────────────────────────


CheckName = Literal[
    "grounded",
    "scoped",
    "disclaimed",
    "tone",
    "consistent",
    "profile_fit",
]
CheckVerdict = Literal["PASS", "WARN", "FAIL"]
OverallVerdict = Literal["ACCEPT", "REGENERATE"]


class ReflectionResult(TypedDict, total=False):
    verdict: OverallVerdict
    checks: dict[str, str]  # CheckName -> CheckVerdict (loose typing for serialisation)
    reasons: list[str]
    regenerate_guidance: str
    raw: str
    error: str  # set only when the critic call itself failed


_CHECK_NAMES: tuple[CheckName, ...] = (
    "grounded",
    "scoped",
    "disclaimed",
    "tone",
    "consistent",
    "profile_fit",
)


# ── Prompt ───────────────────────────────────────────────────────────────────


_CRITIC_RUBRIC = """\
You are a strict fact-checker for an Indian investing advisor. Review the
ANSWER below against the SOURCE_PAGES and the user's PROFILE.

Score each check exactly as PASS, WARN, or FAIL on its own line.
After all six checks, output a single VERDICT line and (if not ACCEPT) a
REGENERATE_GUIDANCE paragraph telling the writer how to fix the answer.

Checks (in order, output them all):
  1. GROUNDED — every numeric claim, fund name, scheme code, and rate appears
     in SOURCE_PAGES (not invented). FAIL if any concrete claim is unsupported.
  2. SCOPED — answer stays educational. FAIL if it says "buy now",
     "I recommend stock X", or any direct individual-equity recommendation
     to a beginner.
  3. DISCLAIMED — ends with the SEBI educational disclaimer (or its Hindi
     equivalent). FAIL if missing entirely.
  4. TONE — matches the user's apparent level (beginner / intermediate /
     advanced). WARN if too jargon-heavy for a beginner; PASS otherwise.
  5. CONSISTENT — no internal contradictions; nothing that conflicts with
     SOURCE_PAGES. FAIL if a claim contradicts a cited page.
  6. PROFILE_FIT — uses the user's profile (income, goal, horizon, SIP budget)
     where given. PASS if profile is empty (no fit possible). WARN if profile
     was given but ignored.

Output format — strict, machine-parseable:

GROUNDED: <PASS|WARN|FAIL> — <one short reason>
SCOPED: <PASS|WARN|FAIL> — <one short reason>
DISCLAIMED: <PASS|WARN|FAIL> — <one short reason>
TONE: <PASS|WARN|FAIL> — <one short reason>
CONSISTENT: <PASS|WARN|FAIL> — <one short reason>
PROFILE_FIT: <PASS|WARN|FAIL> — <one short reason>
VERDICT: <ACCEPT|REGENERATE>
REGENERATE_GUIDANCE: <one paragraph or empty>

Rules for VERDICT:
- Any FAIL on GROUNDED, SCOPED, DISCLAIMED, or CONSISTENT  → REGENERATE.
- Two or more WARNs across all checks                       → REGENERATE.
- Otherwise                                                 → ACCEPT.
"""


def _format_pages(source_pages: dict[str, str]) -> str:
    if not source_pages:
        return "(no source pages were loaded for this answer)"
    parts: list[str] = []
    for name, content in source_pages.items():
        snippet = (content or "")[:1500]
        parts.append(f"### {name}\n{snippet}")
    return "\n\n".join(parts)


def _format_profile(profile: dict | None) -> str:
    if not profile:
        return "(no profile provided)"
    keys = (
        "name",
        "monthly_income",
        "monthly_sip_budget",
        "risk_tolerance",
        "tax_bracket_pct",
        "primary_goal",
        "horizon_pref",
    )
    lines = []
    for k in keys:
        if k in profile and profile[k] not in (None, ""):
            lines.append(f"  {k}: {profile[k]}")
    return "\n".join(lines) or "(profile present but empty)"


def _build_critic_prompt(
    question: str,
    profile: dict | None,
    source_pages: dict[str, str],
    candidate_answer: str,
) -> str:
    return (
        f"{_CRITIC_RUBRIC}\n\n"
        f"USER QUESTION:\n{question}\n\n"
        f"USER PROFILE:\n{_format_profile(profile)}\n\n"
        f"SOURCE_PAGES:\n{_format_pages(source_pages)}\n\n"
        f"ANSWER (under review):\n{candidate_answer}\n"
    )


# ── Parser ───────────────────────────────────────────────────────────────────


_CHECK_LINE = re.compile(
    r"^\s*(GROUNDED|SCOPED|DISCLAIMED|TONE|CONSISTENT|PROFILE_FIT)\s*:\s*"
    r"(PASS|WARN|FAIL)\s*(?:[—\-:]\s*(.*))?$",
    re.IGNORECASE | re.MULTILINE,
)
_VERDICT_LINE = re.compile(r"^\s*VERDICT\s*:\s*(ACCEPT|REGENERATE)\s*$", re.IGNORECASE | re.MULTILINE)
_GUIDANCE_LINE = re.compile(
    r"^\s*REGENERATE_GUIDANCE\s*:\s*(.+?)(?:\Z|\n[A-Z_]+\s*:)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def _parse_critic_output(raw: str) -> ReflectionResult:
    """Parse Gemini's structured critique. Defensive: missing fields default
    to PASS / ACCEPT so a critic that can't parse never blocks the user from
    receiving an answer.
    """
    checks: dict[str, str] = {}
    reasons: list[str] = []

    for m in _CHECK_LINE.finditer(raw):
        name = m.group(1).lower()
        verdict = m.group(2).upper()
        reason = (m.group(3) or "").strip()
        checks[name] = verdict
        if verdict != "PASS" and reason:
            reasons.append(f"{name}: {reason}")

    # Fill in any missing checks as PASS (no signal = no objection)
    for name in _CHECK_NAMES:
        checks.setdefault(name, "PASS")

    # Parse the VERDICT line; if absent, derive from check counts
    verdict_match = _VERDICT_LINE.search(raw)
    if verdict_match:
        overall: OverallVerdict = verdict_match.group(1).upper()  # type: ignore[assignment]
    else:
        overall = _derive_verdict(checks)

    guidance_match = _GUIDANCE_LINE.search(raw)
    guidance = (guidance_match.group(1).strip() if guidance_match else "")
    # Strip the trailing "REGENERATE_GUIDANCE:" of a follow-up section if regex over-grabbed
    guidance = guidance.split("\n\n")[0].strip() if guidance else ""

    return ReflectionResult(
        verdict=overall,
        checks=checks,
        reasons=reasons,
        regenerate_guidance=guidance,
        raw=raw,
    )


def _derive_verdict(checks: dict[str, str]) -> OverallVerdict:
    """Apply the deterministic rule from the critic prompt when Gemini omits
    the explicit VERDICT line.

    - Any FAIL on GROUNDED, SCOPED, DISCLAIMED, or CONSISTENT → REGENERATE
    - >= 2 WARN across all 6 checks → REGENERATE
    - Otherwise → ACCEPT
    """
    blocking = ("grounded", "scoped", "disclaimed", "consistent")
    if any(checks.get(k) == "FAIL" for k in blocking):
        return "REGENERATE"
    warn_count = sum(1 for v in checks.values() if v == "WARN")
    if warn_count >= 2:
        return "REGENERATE"
    return "ACCEPT"


# ── Public entry point ───────────────────────────────────────────────────────


async def reflect(
    question: str,
    profile: dict | None,
    source_pages: dict[str, str],
    candidate_answer: str,
    *,
    mode: Literal["india", "us"] = "india",
) -> ReflectionResult:
    """Run the reflection critic on a candidate Gemini answer.

    Returns a ReflectionResult dict — never raises. If the critic call itself
    fails (Gemini outage, rate limit), we default to ACCEPT with an ``error``
    field set so downstream callers can choose to surface a "self-check
    unavailable" badge in the UI.

    Args:
        question:         the user's original question
        profile:          UserProfile dict, or None
        source_pages:     {filename: content} of the wiki pages used
        candidate_answer: the synthesis output to review
        mode:             "india" or "us" — selects the disclaimer expectation
    """
    # An empty candidate is a non-answer; nothing to fact-check.
    if not (candidate_answer or "").strip():
        return ReflectionResult(
            verdict="REGENERATE",
            checks={k: "FAIL" for k in _CHECK_NAMES},
            reasons=["empty candidate answer"],
            regenerate_guidance="The previous attempt produced no answer. Try again.",
            raw="",
        )

    prompt = _build_critic_prompt(question, profile, source_pages, candidate_answer)

    try:
        raw = await call_gemini(prompt)
    except Exception as exc:
        logger.warning(f"[Reflection] critic call failed: {exc}")
        return ReflectionResult(
            verdict="ACCEPT",  # never block the user on infra failure
            checks={k: "PASS" for k in _CHECK_NAMES},
            reasons=[],
            regenerate_guidance="",
            raw="",
            error=f"{type(exc).__name__}: {exc}",
        )

    result = _parse_critic_output(raw)
    logger.debug(
        f"[Reflection] mode={mode} verdict={result['verdict']} "
        f"checks={result['checks']}"
    )
    return result


# ── UI-facing helper: badge mapping ──────────────────────────────────────────


def badge_for(result: ReflectionResult) -> str:
    """Return a one-glyph badge string for the UI based on the result.

    Use cases (per PROJECT_TODO_MASTER.md §1.6, §10):
      - 🛡️ Fact-checked        — verdict ACCEPT, no WARNs
      - 🟡 Refined              — verdict ACCEPT after a regen
      - ⚠️ Use with care        — verdict ACCEPT but with WARNs left
      - ❌ Self-check failed    — when the critic itself errored
    """
    if result.get("error"):
        return "❌ Self-check unavailable"
    checks = result.get("checks", {})
    if result.get("verdict") == "ACCEPT" and all(v == "PASS" for v in checks.values()):
        return "🛡️ Fact-checked"
    if result.get("verdict") == "ACCEPT":
        return "⚠️ Use with care"
    return "🟡 Refined after self-review"
