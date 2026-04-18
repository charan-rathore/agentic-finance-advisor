"""
core/trust.py

Lightweight Trust Layer — source provenance, validation, and knowledge versioning.

Purely additive infrastructure. Nothing in this module modifies existing agent
logic. It is the back-end for two questions the rest of the system cannot
currently answer:

    1. *Where did this data come from, and is the source trusted + reachable?*
    2. *What changed in this wiki page, when, and which sources drove it?*

PR 2 of the Trust Layer roadmap. Wired into ``core/wiki.py`` in PR 3 and
``core/fetchers.py`` in PR 4. Tests live in ``tests/test_trust.py`` and use
``httpx.MockTransport`` so the suite never touches the live network.

Design notes worth keeping in mind when extending this module:

- ``validate_source`` is **async** because every real caller in this project
  is an ``async def`` fetcher. A sync wrapper is intentionally not provided —
  if a sync caller appears, ``asyncio.run(validate_source(url))`` is fine.
- ``extract_domain`` uses ``str.removeprefix("www.")`` rather than
  ``lstrip("www.")``. The ``lstrip`` form (in the original spec) is a
  character-set strip and would mangle e.g. ``wsj.com`` → ``sj.com``.
- ``register_source`` and ``record_wiki_version`` open their own short-lived
  ``Session(engine)`` so callers don't have to thread a session through.
  This matches the pattern in ``core/fetch_state.py``.
- The trusted-domain whitelist is the *only* allowlist in the project; keep
  it in this module so security review has a single file to read.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from core.models import KnowledgeVersion, SourceRegistry

# ── Trusted domain whitelist ─────────────────────────────────────────────────
# Sources outside these domains are recorded with ``is_trusted=False`` so the
# UI / fetcher gates can decide what to do (today: warn-and-skip in PR 4).
# Add new entries here when a new data source is integrated — this is the
# single source of truth for "do we trust this host?".

TRUSTED_DOMAINS: set[str] = {
    # Market data
    "finance.yahoo.com",
    "query1.finance.yahoo.com",
    "query2.finance.yahoo.com",
    # SEC / Government
    "sec.gov",
    "data.sec.gov",
    "efts.sec.gov",
    # Federal Reserve
    "fred.stlouisfed.org",
    "api.stlouisfed.org",
    # Vendor APIs
    "www.alphavantage.co",
    "alphavantage.co",
    "finnhub.io",
    # News
    "reuters.com",
    "bloomberg.com",
    "wsj.com",
    "ft.com",
    "cnbc.com",
    "marketwatch.com",
    "news.google.com",
    # Reddit
    "reddit.com",
    "oauth.reddit.com",
    # CNN (Fear & Greed)
    "production.dataviz.cnn.io",
    "cnn.com",
}


# ── Source Validation ────────────────────────────────────────────────────────


def extract_domain(url: str) -> str:
    """Return the lowercase host for ``url`` with a leading ``www.`` stripped.

    Returns an empty string for unparseable input. Uses ``removeprefix``
    instead of ``lstrip`` because ``lstrip("www.")`` strips any leading
    character in the set ``{"w", "."}`` and would corrupt domains like
    ``wsj.com`` → ``sj.com``.
    """
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return ""
    return netloc.removeprefix("www.")


def is_trusted_domain(url: str) -> bool:
    """``True`` when ``url``'s domain is in :data:`TRUSTED_DOMAINS` or is a
    sub-domain of a trusted parent (e.g. ``api.fred.stlouisfed.org``)."""
    domain = extract_domain(url)
    if not domain:
        return False
    if domain in TRUSTED_DOMAINS:
        return True
    return any(domain.endswith("." + trusted) for trusted in TRUSTED_DOMAINS)


def _build_validation_result(
    url: str, *, is_reachable: bool, http_status: int | None
) -> dict[str, Any]:
    return {
        "url": url,
        "domain": extract_domain(url),
        "is_trusted": is_trusted_domain(url),
        "is_reachable": is_reachable,
        "http_status": http_status,
    }


async def validate_source(
    url: str,
    *,
    timeout: float = 5.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Validate a source URL: domain trust + HTTP reachability.

    Tries a HEAD first (cheap), falls back to a 1-byte ranged GET if the
    server rejects HEAD or anything else goes wrong. Never raises — any
    error becomes ``is_reachable=False`` so the fetcher pipeline can never
    be stalled by a wedged validation call.

    Returns::

        {
            "url":          original URL,
            "domain":       extracted host (no leading "www."),
            "is_trusted":   bool — passes the domain whitelist,
            "is_reachable": bool — HEAD/GET returned a non-error status,
            "http_status":  int | None — last status code observed,
        }

    The ``transport`` argument exists for tests; production callers should
    leave it ``None`` and let httpx pick the default transport.
    """
    status: int | None = None
    reachable = False

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        ) as client:
            try:
                r = await client.head(url)
                status = r.status_code
                reachable = r.status_code < 400
                # Some servers return 405 / 403 to HEAD but happily serve GET.
                if not reachable and r.status_code in (403, 405, 501):
                    raise RuntimeError("HEAD rejected — try GET")
            except Exception:
                r = await client.get(url, headers={"Range": "bytes=0-0"})
                status = r.status_code
                reachable = r.status_code < 400
    except Exception as e:
        logger.debug(f"[Trust] Reachability check failed for {url}: {e}")

    return _build_validation_result(url, is_reachable=reachable, http_status=status)


# ── Source Registry ──────────────────────────────────────────────────────────


def register_source(
    engine: object,
    url: str,
    source_name: str,
    source_type: str,
    validation_result: dict[str, Any] | None = None,
) -> None:
    """Upsert ``url`` into the ``source_registry`` table.

    On first sight, inserts a full row. On subsequent calls, increments
    ``fetch_count``, refreshes ``last_fetched_at``, and updates the trust /
    reachability fields with the latest observation.

    ``validation_result`` is the dict returned by :func:`validate_source`.
    When ``None``, we synthesise a minimal "trusted-and-reachable" result
    from the URL itself — useful for callers that have already proven
    reachability by completing the actual data fetch (the cheaper path
    PR 4 will prefer over an extra HEAD probe).
    """
    if validation_result is None:
        validation_result = _build_validation_result(url, is_reachable=True, http_status=200)

    now = datetime.now(UTC)

    with Session(engine) as session:  # type: ignore[arg-type]
        existing = session.query(SourceRegistry).filter_by(url=url).first()

        if existing is not None:
            existing.last_fetched_at = now
            existing.fetch_count = (existing.fetch_count or 0) + 1
            existing.is_reachable = validation_result.get("is_reachable", True)
            existing.http_status = validation_result.get("http_status")
            existing.is_trusted = validation_result.get("is_trusted", False)
            # ``domain`` / ``source_name`` / ``source_type`` are deliberately
            # NOT overwritten on update — they are properties of the URL
            # itself, not of any single fetch.
        else:
            session.add(
                SourceRegistry(
                    url=url,
                    domain=validation_result.get("domain", extract_domain(url)),
                    source_name=source_name,
                    source_type=source_type,
                    is_trusted=validation_result.get("is_trusted", False),
                    is_reachable=validation_result.get("is_reachable", True),
                    http_status=validation_result.get("http_status"),
                    first_fetched_at=now,
                    last_fetched_at=now,
                    fetch_count=1,
                )
            )

        session.commit()
        logger.debug(
            f"[Trust] Registered source: {url} " f"(trusted={validation_result.get('is_trusted')})"
        )


# ── Knowledge Versioning ─────────────────────────────────────────────────────


def record_wiki_version(
    engine: object,
    page_name: str,
    new_content: str,
    old_content: str,
    change_summary: str,
    source_urls: list[str],
    source_types: list[str],
    triggered_by: str = "ingest",
) -> int:
    """Record a new ``KnowledgeVersion`` row for a wiki page write.

    Computes the next version number as ``max(existing) + 1`` per page (so
    versions are dense and human-readable: 1, 2, 3, ...). Stores word counts
    before/after so the UI can chart how the knowledge base grows over time.

    Returns the new version number — useful for callers that want to embed
    a ``[[page-vN]]`` reference in subsequent prose.
    """
    with Session(engine) as session:  # type: ignore[arg-type]
        last = (
            session.query(KnowledgeVersion)
            .filter_by(page_name=page_name)
            .order_by(KnowledgeVersion.version.desc())
            .first()
        )
        next_version = (last.version + 1) if last is not None else 1

        session.add(
            KnowledgeVersion(
                page_name=page_name,
                version=next_version,
                changed_at=datetime.now(UTC),
                change_summary=change_summary,
                source_urls=json.dumps(source_urls),
                source_types=json.dumps(source_types),
                word_count_before=len(old_content.split()) if old_content else 0,
                word_count_after=len(new_content.split()),
                triggered_by=triggered_by,
            )
        )
        session.commit()
        logger.debug(f"[Trust] Versioned {page_name} → v{next_version} ({triggered_by})")
        return next_version


# ── Read helpers (used by the Streamlit "Sources & History" page in PR 5) ────


def get_page_version_history(engine: object, page_name: str) -> list[dict[str, Any]]:
    """Return all versions of ``page_name``, newest first, as plain dicts.

    Plain dicts (rather than ORM rows) keep the UI layer free of SQLAlchemy
    knowledge — Streamlit components only need to know about Python types.
    """
    with Session(engine) as session:  # type: ignore[arg-type]
        rows = (
            session.query(KnowledgeVersion)
            .filter_by(page_name=page_name)
            .order_by(KnowledgeVersion.version.desc())
            .all()
        )
        return [
            {
                "page": r.page_name,
                "version": r.version,
                "changed_at": r.changed_at,
                "change_summary": r.change_summary,
                "source_urls": json.loads(r.source_urls or "[]"),
                "source_types": json.loads(r.source_types or "[]"),
                "word_count_before": r.word_count_before,
                "word_count_after": r.word_count_after,
                "triggered_by": r.triggered_by,
            }
            for r in rows
        ]


def get_all_sources(engine: object) -> list[dict[str, Any]]:
    """Return every registered source, most-recent fetch first."""
    with Session(engine) as session:  # type: ignore[arg-type]
        rows = session.query(SourceRegistry).order_by(SourceRegistry.last_fetched_at.desc()).all()
        return [
            {
                "url": r.url,
                "domain": r.domain,
                "source_name": r.source_name,
                "source_type": r.source_type,
                "is_trusted": r.is_trusted,
                "is_reachable": r.is_reachable,
                "http_status": r.http_status,
                "first_fetched_at": r.first_fetched_at,
                "last_fetched_at": r.last_fetched_at,
                "fetch_count": r.fetch_count,
            }
            for r in rows
        ]
