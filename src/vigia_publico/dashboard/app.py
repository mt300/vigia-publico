"""Dashboard local (Streamlit) para explorar dados e achados do vigia-publico.

Rodar com: uv run streamlit run src/vigia_publico/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from vigia_publico.dashboard import theme, views, views_senado

st.set_page_config(page_title="Vigia Público", page_icon="\U0001f3db️", layout="wide")
theme.injetar_css()

pagina = st.navigation(
    [
        st.Page(lambda: views.render(mode="local"), title="Painel Deputados", icon="📊", url_path="painel", default=True),
        st.Page(lambda: views_senado.render(mode="local"), title="Painel Senadores", icon="📊", url_path="painel-senado"),
    ]
)
pagina.run()
