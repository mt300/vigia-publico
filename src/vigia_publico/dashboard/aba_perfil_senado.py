"""Aba 'Perfil do Senador' do Painel Senado - espelha `aba_perfil.py`.

Sem secao de historico de mandatos/redes sociais (dados nao existem no
roster do Senado, so no CEAPS + lista atual - ver plano, MVP e so gastos).
"""

from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from vigia_publico.dashboard import data, export, fonte_page, theme
from vigia_publico.dashboard.filtros import Mode
from vigia_publico.dashboard.filtros_senado import FiltrosSenado
from vigia_publico.detection import neutral_copy


def render(mode: Mode, filtros: FiltrosSenado) -> None:
    if filtros.senador_id is None:
        st.info("Selecione um senador especifico no filtro da barra lateral para ver o perfil.")
        return

    senador_id_sel = filtros.senador_id
    perfil = data.get_perfil_senador(senador_id_sel)
    col_foto, col_info = st.columns([1, 3])
    with col_foto:
        if perfil.get("url_foto"):
            st.image(perfil["url_foto"], width=150)
    with col_info:
        st.subheader(f"{perfil['nome_parlamentar']} ({perfil['sigla_partido']}/{perfil['sigla_uf']})")
        st.write(f"**Situacao:** {perfil.get('situacao') or '-'}")
        if mode == "local":
            st.write(f"**Nome civil:** {perfil.get('nome_civil') or '-'}")
            st.write(f"**Email:** {perfil.get('email') or '-'}")

    st.subheader("Gasto mensal")
    despesas_sen = data.get_despesas_mensal_senado(filtros.mes_inicio, filtros.mes_fim, senador_id=senador_id_sel)
    if not despesas_sen.empty:
        fig = px.bar(despesas_sen, x="mes", y="total", color_discrete_sequence=[theme.COR_PRIMARIA])
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("🔍 Ver despesas individuais (fornecedor, data, valor)"):
        detalhado_sen = data.get_despesas_detalhado_senado(filtros.mes_inicio, filtros.mes_fim, senador_id=senador_id_sel, limite=1000)
        if detalhado_sen.empty:
            st.info("Sem despesas individuais no periodo selecionado.")
        else:
            st.dataframe(detalhado_sen, use_container_width=True, hide_index=True)
            export.botoes_exportar(detalhado_sen, f"vigia_publico_despesas_senado_{senador_id_sel}", key_prefix="perfil_despesas_detalhado_senado")

    st.subheader("Achados deste senador no periodo")
    findings_sen = data.get_findings_senado(filtros.mes_inicio, filtros.mes_fim, senador_id=senador_id_sel)
    if findings_sen.empty:
        st.dataframe(findings_sen, use_container_width=True, hide_index=True)
    elif mode == "public":
        findings_sen = findings_sen.copy()
        findings_sen["categoria"] = findings_sen["tipo"].map(lambda t: neutral_copy.TIPO_LABEL_PUBLICO.get(t, t))
        findings_sen["resumo"] = [
            neutral_copy.render(row.tipo, json.loads(row.dados_suporte) if row.dados_suporte else {})
            for row in findings_sen.itertuples()
        ]
        findings_sen["fonte"] = findings_sen["fonte_url"].apply(lambda u: fonte_page.build_fonte_amigavel_url(u) if u else None)
        st.dataframe(
            findings_sen[["mes_referencia", "categoria", "resumo", "fonte"]], use_container_width=True, hide_index=True,
            column_config={"fonte": st.column_config.LinkColumn("Fonte", display_text="Ver fonte")},
        )
        findings_sen_cols = findings_sen[["mes_referencia", "categoria", "resumo", "fonte_url"]]
        export.botoes_exportar(findings_sen_cols, f"vigia_publico_achados_senado_{senador_id_sel}", key_prefix="perfil_achados_senado")
    else:
        findings_sen_cols = findings_sen[["mes_referencia", "tipo", "severidade", "descricao", "fonte_url"]]
        st.dataframe(
            findings_sen_cols, use_container_width=True, hide_index=True,
            column_config={"fonte_url": st.column_config.LinkColumn("Fonte", display_text="Ver fonte (JSON)")},
        )
        export.botoes_exportar(findings_sen_cols, f"vigia_publico_achados_senado_{senador_id_sel}", key_prefix="perfil_achados_senado")
