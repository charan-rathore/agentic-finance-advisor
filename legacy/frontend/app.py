"""
DEPRECATED in v2 — the dashboard was moved to ui/app.py.

Run: streamlit run ui/app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Moved", layout="centered")
st.warning("This path is deprecated. From the project root run: **streamlit run ui/app.py**")
