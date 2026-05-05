"""
core/faq.py

Deterministic FAQ matcher. Pre-computed answers covering the highest-frequency
beginner questions, served with zero LLM calls and zero latency.

Why a FAQ layer:
* Beginner traffic concentrates on roughly 20 patterns: "what is SIP", "ELSS vs
  PPF", "how much to invest", "emergency fund kya hai", etc. A pre-computed
  answer gives instant gratification, never hallucinates, and cuts Gemini load.
* The Gemini free tier is rate-limited. Cache hits at this layer extend our
  effective query budget materially.

Storage:
    data/wiki_india/faq/<slug>.md
    Each file has YAML frontmatter with a `question_patterns` list.

Public API:
    faq_match(question: str) -> FAQHit | None
    list_faq_pages() -> list[FAQEntry]
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from core.settings import settings

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class FAQHit:
    """The result of matching a user question against the FAQ pages."""

    slug: str
    title: str
    answer: str
    sources: list[str]
    matched_pattern: str


@dataclass(frozen=True)
class FAQEntry:
    """A loaded FAQ page (used for indexing or admin views)."""

    slug: str
    title: str
    patterns: list[str]
    sources: list[str]
    body: str


def _faq_dir() -> Path:
    return Path(settings.INDIA_WIKI_DIR) / "faq"


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation other than rupee symbols and digits."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s₹]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_faq_file(path: Path) -> FAQEntry | None:
    """Parse a single FAQ markdown file. Returns None if frontmatter is missing."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        return None

    parts = raw.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter_text = parts[1]
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError:
        return None

    title = meta.get("title", path.stem.replace("_", " ").title())
    patterns = meta.get("question_patterns", []) or []
    sources = meta.get("data_sources", []) or []

    if not isinstance(patterns, list):
        patterns = [str(patterns)]

    return FAQEntry(
        slug=path.stem,
        title=title,
        patterns=[_normalise(p) for p in patterns if isinstance(p, str)],
        sources=[str(s) for s in sources],
        body=body,
    )


def list_faq_pages() -> list[FAQEntry]:
    """Return every parseable FAQ page in data/wiki_india/faq/."""
    root = _faq_dir()
    if not root.exists():
        return []
    entries: list[FAQEntry] = []
    for p in sorted(root.glob("*.md")):
        entry = _parse_faq_file(p)
        if entry is not None:
            entries.append(entry)
    return entries


def faq_match(question: str) -> FAQHit | None:
    """
    Match a user question against the FAQ pages.

    Strategy:
    1. Normalise both sides (lowercase, strip punctuation).
    2. For each FAQ page, scan its question_patterns for a substring hit.
    3. Tie-break by longest matching pattern (more specific wins).

    Returns ``None`` if no FAQ matches (caller should fall back to Gemini).
    """
    if not question or not question.strip():
        return None

    norm_q = _normalise(question)
    best: tuple[int, FAQEntry, str] | None = None

    for entry in list_faq_pages():
        for pattern in entry.patterns:
            if pattern and pattern in norm_q:
                score = len(pattern)
                if best is None or score > best[0]:
                    best = (score, entry, pattern)

    if best is None:
        return None

    _, entry, pattern = best
    return FAQHit(
        slug=entry.slug,
        title=entry.title,
        answer=entry.body,
        sources=entry.sources,
        matched_pattern=pattern,
    )
