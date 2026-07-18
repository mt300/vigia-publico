"""Dashboard local (Streamlit) para explorar dados e achados do vigia-publico.

Rodar com: uv run streamlit run src/vigia_publico/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from vigia_publico.dashboard import views

st.set_page_config(page_title="Vigia Público", page_icon="\U0001f3db️", layout="wide")
views.render(mode="local")
