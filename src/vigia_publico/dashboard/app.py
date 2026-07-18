"""Dashboard local (Streamlit) para explorar dados e achados do vigia-publico.

Rodar com: uv run streamlit run src/vigia_publico/dashboard/app.py
"""

from __future__ import annotations

from vigia_publico.dashboard import views

views.render(mode="local")
