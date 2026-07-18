"""Corpo do dashboard Streamlit, compartilhado pelo entrypoint local
(`app.py`) e pelo publico (`app_public.py`).

So monta a pagina (titulo, sidebar de filtros, abas) e delega o conteudo de
cada aba pro modulo correspondente - `aba_achados.py`, `aba_gastos.py`,
`aba_presenca.py`, `aba_perfil.py`. `mode="public"` esconde o que so faz
sentido pra uso pessoal/interno (severidade, texto interno de `descricao`,
contato do deputado) - ver cada modulo de aba pro detalhe exato.
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from vigia_publico.dashboard import aba_achados, aba_gastos, aba_perfil, aba_presenca, data
from vigia_publico.dashboard import filtros as filtros_mod

Mode = filtros_mod.Mode


def render(mode: Mode = "local") -> None:
    """Renderiza o painel (abas Achados/Gastos/Presenca/Perfil).

    Nao chama `st.set_page_config` - isso e responsabilidade de quem entra
    primeiro no script (`app.py` pro local, `app_public.py` pro publico, que
    tem varias paginas e so pode chamar set_page_config uma vez no total).
    """
    st.title("Vigia Público - Monitor de Deputados Federais")
    if mode == "public":
        st.caption(
            "Dados publicos da API de Dados Abertos da Camara dos Deputados. Os indicadores abaixo sao "
            "comparacoes estatisticas simples (gasto/presenca vs. media propria ou de pares) - nao "
            "constituem acusacao nem conclusao sobre irregularidade. Termos como 'desvio-padrao' "
            "explicados na pagina **Como funciona** (menu lateral)."
        )

    meses_disponiveis = data.listar_meses_disponiveis()
    if not meses_disponiveis:
        st.warning("Banco de dados ainda sem despesas. Rode o backfill/update antes de usar o dashboard.")
        st.stop()

    filtros = filtros_mod.render_sidebar(mode, meses_disponiveis)

    aba_achados_tab, aba_gastos_tab, aba_presenca_tab, aba_perfil_tab = st.tabs(
        ["Achados", "Gastos", "Presenca/Votos", "Perfil do Deputado"]
    )
    with aba_achados_tab:
        aba_achados.render(mode, filtros)
    with aba_gastos_tab:
        aba_gastos.render(mode, filtros)
    with aba_presenca_tab:
        aba_presenca.render(mode, filtros)
    with aba_perfil_tab:
        aba_perfil.render(mode, filtros)

    st.caption(f"Dados atualizados ate {meses_disponiveis[-1]}. Gerado em {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}.")
    st.caption("Desenvolvido por [MWebS](https://www.mwebs.com.br).")
