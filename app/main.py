"""
FastAPI legacy stub.

v2 runs agents via `python main.py` and the dashboard via `streamlit run ui/app.py`.
Optional: `uvicorn app.main:app` exposes /api/v1/health for simple checks.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI


def create_app() -> FastAPI:
    """Minimal ASGI app so older smoke tests and tooling keep a stable entrypoint."""
    application = FastAPI(
        title="Finance Advisor",
        version="0.2.0",
        description="Legacy HTTP stub; v2 multi-agent stack uses root main.py.",
    )
    api = APIRouter(prefix="/api/v1")

    @api.get("/health")
    def health() -> dict[str, str]:
        return {"message": "ok"}

    @api.get("/ready")
    def ready() -> dict[str, str]:
        return {"message": "ready"}

    application.include_router(api)
    return application


app = create_app()
