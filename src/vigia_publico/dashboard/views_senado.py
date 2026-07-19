"""Corpo do Painel Senado - espelha `views.py`, pagina separada do Painel
Camara (nao mexe nele). So MVP de gastos (CEAPS) - ver plano, sem aba de
Presenca/Votos (formato de dado do Senado pra isso ainda nao verificado).
"""

from __future__ import annotations

import datetime as dt

import streamlit as st

from vigia_publico.dashboard import aba_achados_senado, aba_gastos_senado, aba_perfil_senado, data
from vigia_publico.dashboard.filtros import Mode
from vigia_publico.dashboard.filtros_senado import render_sidebar_senado


def render(mode: Mode = "local") -> None:
    """Renderiza o Painel Senado (abas Achados/Gastos/Perfil).

    Nao chama `st.set_page_config` - mesma responsabilidade de quem entra
    primeiro no script (ver `views.py`).
    """
    st.title("Vigia Público - Monitor de Senadores")
    if mode == "public":
        st.caption(
            "Dados publicos da API de Dados Abertos do Senado Federal (CEAPS - Cota para Exercicio da "
            "Atividade Parlamentar). Os indicadores abaixo sao comparacoes estatisticas simples (gasto vs. "
            "media propria ou de pares) - nao constituem acusacao nem conclusao sobre irregularidade. "
            "Termos como 'desvio-padrao' explicados na pagina **Como funciona** (menu lateral)."
        )

    meses_disponiveis = data.listar_meses_disponiveis_senado()
    if not meses_disponiveis:
        st.warning("Banco de dados ainda sem despesas de senadores. Rode o backfill/update --casa senado antes de usar o painel.")
        st.stop()

    filtros = render_sidebar_senado(mode, meses_disponiveis)

    aba_achados_tab, aba_gastos_tab, aba_perfil_tab = st.tabs(["Achados", "Gastos", "Perfil do Senador"])
    with aba_achados_tab:
        aba_achados_senado.render(mode, filtros)
    with aba_gastos_tab:
        aba_gastos_senado.render(mode, filtros)
    with aba_perfil_tab:
        aba_perfil_senado.render(mode, filtros)

    st.caption(f"Dados atualizados ate {meses_disponiveis[-1]}. Gerado em {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}.")
    st.caption("Desenvolvido por [MWebS](https://www.mwebs.com.br).")
