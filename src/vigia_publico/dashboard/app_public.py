"""Dashboard publico (Streamlit Community Cloud / self-hosted).

Entrypoint separado do dashboard local (`app.py`): aponta pro snapshot
publico read-only (`public_data/vigia_publico_public.db`, gerado por
`vigia-publico export-public-snapshot` - ver `reporting/public_snapshot.py`)
e renderiza em `mode="public"` (sem severidade/descricao interpretativa, sem
contato pessoal do deputado - ver `dashboard/views.py`). Multipagina: Inicio
(landing), Painel (o dashboard em si) e Como funciona (tutorial) - ver
`dashboard/public_pages.py`.

Sem nenhuma secret: nao importa `anthropic`/`httpx` (nao estao no
`requirements.txt` deste deploy) nem le `ANTHROPIC_API_KEY` - fisicamente
incapaz de disparar ingestao ou custo de LLM.

Nao depende de `vigia_publico` estar pip-instalado (nem editable) - so
adiciona `src/` ao sys.path. Testado via build Docker real: instalar o
pacote com `pip install -e .` traz TODO `[project.dependencies]` do
pyproject.toml (anthropic/httpx inclusive), o que anularia o ponto inteiro
do requirements.txt curado. sys.path evita isso por completo.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st  # noqa: E402

from vigia_publico.dashboard import data, public_pages, views  # noqa: E402
from vigia_publico.reporting.public_snapshot import ensure_decompressed  # noqa: E402

st.set_page_config(page_title="Vigia Público", page_icon="\U0001f3db️", layout="wide")
data.use_db_path(ensure_decompressed())

pagina = st.navigation(
    [
        st.Page(public_pages.render_home, title="Início", icon="🏛️", default=True),
        st.Page(lambda: views.render(mode="public"), title="Painel", icon="📊"),
        st.Page(public_pages.render_tutorial, title="Como funciona", icon="📖"),
    ]
)
pagina.run()
