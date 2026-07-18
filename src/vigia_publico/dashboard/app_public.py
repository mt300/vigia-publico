"""Dashboard publico (Streamlit Community Cloud).

Entrypoint separado do dashboard local (`app.py`): aponta pro snapshot
publico read-only (`public_data/vigia_publico_public.db`, gerado por
`vigia-publico export-public-snapshot` - ver `reporting/public_snapshot.py`)
e renderiza em `mode="public"` (sem severidade/descricao interpretativa, sem
contato pessoal do deputado - ver `dashboard/views.py`).

Sem nenhuma secret: nao importa `anthropic`/`httpx` (nao estao no
`requirements.txt` deste deploy) nem le `ANTHROPIC_API_KEY` - fisicamente
incapaz de disparar ingestao ou custo de LLM.
"""

from __future__ import annotations

from vigia_publico.dashboard import data, views
from vigia_publico.reporting.public_snapshot import ensure_decompressed

data.use_db_path(ensure_decompressed())
views.render(mode="public")
