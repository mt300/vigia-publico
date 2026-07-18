"""Aba 'Presenca/Votos' do painel."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from vigia_publico.dashboard import data, export, theme
from vigia_publico.dashboard.filtros import Filtros, Mode


def render(mode: Mode, filtros: Filtros) -> None:
    presenca = data.get_presenca_mensal(filtros.mes_inicio, filtros.mes_fim, filtros.partidos, filtros.ufs, filtros.deputado_id)
    presenca = presenca.dropna(subset=["taxa_presenca"])
    if presenca.empty:
        st.info("Sem votacoes nominais no periodo/filtro selecionado.")
        return

    media = presenca["taxa_presenca"].mean()
    st.metric("Taxa media de presenca no periodo", f"{media:.0%}")
    fig = px.line(
        presenca, x="mes", y="taxa_presenca", markers=True, title="Taxa de presenca por mes",
        color_discrete_sequence=[theme.COR_PRIMARIA],
    )
    # Amber (cor de "atencao ao contexto"), nao vermelho/crimson - o
    # destaque e so um lembrete temporal (proximidade de eleicao), nao um
    # alarme, e vermelho contradiria o texto logo abaixo.
    fig.add_bar(
        x=presenca["mes"], y=presenca["taxa_presenca"],
        marker_color=[theme.COR_DESTAQUE_ELEICAO if p else "rgba(0,0,0,0)" for p in presenca["proximo_eleicao"]],
        showlegend=False, opacity=0.25, name="Proximo de eleicao",
    )
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Presenca bruta = votos registrados / votacoes NOMINAIS do Plenario no mes "
        "(votacoes simbolicas/por unanimidade nao entram na conta). Este grafico NAO "
        "desconta periodos de licenca oficial - para a taxa de ausencia SEM JUSTIFICATIVA "
        "(que ja exclui licenca e e a base dos alertas), veja a aba Achados. Faixas em "
        "destaque marcam ago/set/out de anos de eleicao geral (quando deputados "
        "federais concorrem a reeleicao) - e comum a presenca cair nesses meses por causa "
        "de campanha, isso NAO e por si so um sinal de irregularidade."
    )

    if presenca["proximo_eleicao"].any() and (~presenca["proximo_eleicao"]).any():
        col1, col2 = st.columns(2)
        col1.metric("Presenca media - proximo de eleicao", f"{presenca.loc[presenca['proximo_eleicao'], 'taxa_presenca'].mean():.0%}")
        col2.metric("Presenca media - resto do mandato", f"{presenca.loc[~presenca['proximo_eleicao'], 'taxa_presenca'].mean():.0%}")

    export.botoes_exportar(presenca, "vigia_publico_presenca", key_prefix="presenca")
