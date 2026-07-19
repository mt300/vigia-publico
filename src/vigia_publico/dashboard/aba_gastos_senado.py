"""Aba 'Gastos' do Painel Senado - espelha `aba_gastos.py`."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from vigia_publico.dashboard import data, export, theme
from vigia_publico.dashboard.filtros import Mode
from vigia_publico.dashboard.filtros_senado import FiltrosSenado


def render(mode: Mode, filtros: FiltrosSenado) -> None:
    despesas_mes = data.get_despesas_mensal_senado(filtros.mes_inicio, filtros.mes_fim, filtros.partidos, filtros.ufs, filtros.senador_id)
    if despesas_mes.empty:
        st.info("Sem dados de despesas no periodo/filtro selecionado.")
        return

    st.metric("Total gasto no periodo", f"R$ {despesas_mes['total'].sum():,.2f}")
    fig = px.line(
        despesas_mes, x="mes", y="total", markers=True, title="Gasto total por mes",
        color_discrete_sequence=[theme.COR_PRIMARIA],
    )
    st.plotly_chart(fig, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        categorias = data.get_despesas_por_categoria_senado(filtros.mes_inicio, filtros.mes_fim, filtros.partidos, filtros.ufs, filtros.senador_id)
        fig = px.bar(
            categorias.head(15), x="total", y="tipo_despesa", orientation="h", title="Gasto por categoria",
            color_discrete_sequence=[theme.COR_PRIMARIA],
        )
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, use_container_width=True)
        export.botoes_exportar(categorias, "vigia_publico_gastos_por_categoria_senado", key_prefix="gastos_categoria_senado")
    with col2:
        if filtros.senador_id is None:
            ranking_gasto = data.get_ranking_gasto_senado(filtros.mes_inicio, filtros.mes_fim, filtros.partidos, filtros.ufs)
            st.subheader("Top 20 senadores por gasto total")
            ranking_gasto_cols = ranking_gasto[["nome_parlamentar", "sigla_partido", "sigla_uf", "total"]]
            st.dataframe(ranking_gasto_cols, use_container_width=True, hide_index=True)
            export.botoes_exportar(ranking_gasto_cols, "vigia_publico_ranking_gasto_senado", key_prefix="ranking_gasto_senado")
        else:
            st.dataframe(categorias, use_container_width=True, hide_index=True)

    with st.expander("🔍 Ver despesas individuais (fornecedor, data, valor)"):
        detalhado = data.get_despesas_detalhado_senado(filtros.mes_inicio, filtros.mes_fim, filtros.partidos, filtros.ufs, filtros.senador_id)
        if detalhado.empty:
            st.info("Sem despesas individuais no periodo/filtro selecionado.")
        else:
            if len(detalhado) >= 300:
                st.caption("Mostrando as 300 maiores despesas do filtro atual - refine o filtro (ex: escolha um senador) pra ver tudo.")
            st.dataframe(detalhado, use_container_width=True, hide_index=True)
            export.botoes_exportar(detalhado, "vigia_publico_despesas_detalhado_senado", key_prefix="despesas_detalhado_senado")
