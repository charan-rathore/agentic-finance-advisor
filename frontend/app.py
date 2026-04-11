"""
Streamlit dashboard for the finance advisor platform.

Run: `streamlit run frontend/app.py`
"""

import os
from typing import Any

import httpx
import streamlit as st

st.set_page_config(
    page_title="Finance Advisor",
    layout="wide",
    initial_sidebar_state="expanded",
)

_default_base = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000").rstrip("/")
DEFAULT_API = f"{_default}/api/v1"


def _get_base_url() -> str:
    return st.sidebar.text_input("FastAPI base URL", value=DEFAULT_API).rstrip("/")


def _health(client: httpx.Client, base: str) -> dict[str, Any]:
    r = client.get(f"{base}/health", timeout=10.0)
    r.raise_for_status()
    return r.json()


def main() -> None:
    st.title("Multi-agent personal finance advisor")
    st.caption("Budgeting, expenses, savings, investments, fraud alerts, and explanations.")

    base = _get_base_url()
    st.sidebar.markdown("### API status")

    try:
        with httpx.Client() as client:
            status = _health(client, base)
            st.sidebar.success(status.get("message", "ok"))
            if st.sidebar.button("Run sample multi-agent pipeline"):
                user_id = st.sidebar.text_input("User id", value="demo-user")
                r = client.post(
                    f"{base}/transactions/analyze-sample",
                    data={"user_external_id": user_id},
                    timeout=60.0,
                )
                r.raise_for_status()
                st.info(r.json().get("message", r.text))
    except httpx.HTTPError as exc:
        st.sidebar.error(f"API unreachable: {exc}")
        st.info("Start the API: `uvicorn app.main:app --reload` (see README).")

    st.subheader("Roadmap in this repo")
    st.markdown(
        """
        - **CSV upload** → Kafka → worker ingests into PostgreSQL
        - **RAG** → Chroma + Gemini for grounded answers
        - **Agents** → specialized workers consuming `agent.events`
        """
    )


if __name__ == "__main__":
    main()
