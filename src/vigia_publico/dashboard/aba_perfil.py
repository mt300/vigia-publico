"""Aba 'Perfil do Deputado' do painel."""

from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from vigia_publico.dashboard import data, export, fonte_page, theme
from vigia_publico.dashboard.filtros import Filtros, Mode
from vigia_publico.detection import neutral_copy


def render(mode: Mode, filtros: Filtros) -> None:
    if filtros.deputado_id is None:
        st.info("Selecione um deputado especifico no filtro da barra lateral para ver o perfil.")
        return

    deputado_id_sel = filtros.deputado_id
    perfil = data.get_perfil_deputado(deputado_id_sel)
    col_foto, col_info = st.columns([1, 3])
    with col_foto:
        if perfil.get("url_foto"):
            st.image(perfil["url_foto"], width=150)
    with col_info:
        st.subheader(f"{perfil['nome_eleitoral']} ({perfil['sigla_partido']}/{perfil['sigla_uf']})")
        st.write(f"**Situacao:** {perfil.get('situacao') or '-'} | **Condicao eleitoral:** {perfil.get('condicao_eleitoral') or '-'}")
        if mode == "local":
            st.write(f"**Nome civil:** {perfil.get('nome_civil') or '-'}")
            st.write(f"**Email:** {perfil.get('email') or '-'}")
            st.write(f"**Gabinete:** predio {perfil.get('gabinete_predio') or '-'}, sala {perfil.get('gabinete_sala') or '-'}, tel {perfil.get('gabinete_telefone') or '-'}")

        redes = data.get_redes_sociais(deputado_id_sel)
        if not redes.empty:
            links = " | ".join(f"[{r.rede}]({r.url})" for r in redes.itertuples())
            st.markdown(f"**Redes sociais:** {links}")

    st.subheader("Historico de mandatos e trocas de partido")
    historico = data.get_historico_deputado(deputado_id_sel)
    st.dataframe(historico, use_container_width=True, hide_index=True)
    export.botoes_exportar(historico, f"vigia_publico_historico_{deputado_id_sel}", key_prefix="perfil_historico")

    st.subheader("Gasto mensal")
    despesas_dep = data.get_despesas_mensal(filtros.mes_inicio, filtros.mes_fim, deputado_id=deputado_id_sel)
    if not despesas_dep.empty:
        fig = px.bar(despesas_dep, x="mes", y="total", color_discrete_sequence=[theme.COR_PRIMARIA])
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("🔍 Ver despesas individuais (fornecedor, data, valor, nota)"):
        detalhado_dep = data.get_despesas_detalhado(filtros.mes_inicio, filtros.mes_fim, deputado_id=deputado_id_sel, limite=1000)
        if detalhado_dep.empty:
            st.info("Sem despesas individuais no periodo selecionado.")
        else:
            st.dataframe(
                detalhado_dep, use_container_width=True, hide_index=True,
                column_config={"url_documento": st.column_config.LinkColumn("Nota", display_text="Ver nota")},
            )
            export.botoes_exportar(detalhado_dep, f"vigia_publico_despesas_{deputado_id_sel}", key_prefix="perfil_despesas_detalhado")

    st.subheader("Achados deste deputado no periodo")
    findings_dep = data.get_findings(filtros.mes_inicio, filtros.mes_fim, deputado_id=deputado_id_sel)
    if findings_dep.empty:
        st.dataframe(findings_dep, use_container_width=True, hide_index=True)
    elif mode == "public":
        findings_dep = findings_dep.copy()
        findings_dep["categoria"] = findings_dep["tipo"].map(lambda t: neutral_copy.TIPO_LABEL_PUBLICO.get(t, t))
        findings_dep["resumo"] = [
            neutral_copy.render(row.tipo, json.loads(row.dados_suporte) if row.dados_suporte else {})
            for row in findings_dep.itertuples()
        ]
        findings_dep["fonte"] = findings_dep["fonte_url"].apply(lambda u: fonte_page.build_fonte_amigavel_url(u) if u else None)
        st.dataframe(
            findings_dep[["mes_referencia", "categoria", "resumo", "fonte"]], use_container_width=True, hide_index=True,
            column_config={"fonte": st.column_config.LinkColumn("Fonte", display_text="Ver fonte")},
        )
        findings_dep_cols = findings_dep[["mes_referencia", "categoria", "resumo", "fonte_url"]]
        export.botoes_exportar(findings_dep_cols, f"vigia_publico_achados_{deputado_id_sel}", key_prefix="perfil_achados")
    else:
        findings_dep_cols = findings_dep[["mes_referencia", "tipo", "severidade", "descricao", "fonte_url"]]
        st.dataframe(
            findings_dep_cols, use_container_width=True, hide_index=True,
            column_config={"fonte_url": st.column_config.LinkColumn("Fonte", display_text="Ver fonte (JSON)")},
        )
        export.botoes_exportar(findings_dep_cols, f"vigia_publico_achados_{deputado_id_sel}", key_prefix="perfil_achados")
