"""Aba 'Achados' do Painel Senado - espelha `aba_achados.py`."""

from __future__ import annotations

import json

import plotly.express as px
import streamlit as st

from vigia_publico.dashboard import data, export, fonte_page, theme
from vigia_publico.dashboard.filtros import Mode
from vigia_publico.dashboard.filtros_senado import FiltrosSenado
from vigia_publico.detection import neutral_copy


def render(mode: Mode, filtros: FiltrosSenado) -> None:
    col1, col2 = st.columns(2)
    tipos_disponiveis = data.listar_tipos_finding_senado()
    if mode == "public":
        opcoes_tipo = {neutral_copy.TIPO_LABEL_PUBLICO.get(t, t): t for t in tipos_disponiveis}
        labels_sel = col1.multiselect("Categoria de achado", sorted(opcoes_tipo.keys()))
        tipos_sel = tuple(opcoes_tipo[label] for label in labels_sel)
    else:
        tipos_sel = tuple(col1.multiselect("Tipo de achado", tipos_disponiveis))
    severidades_sel = ()
    if mode == "local":
        severidades_sel = tuple(col2.multiselect("Severidade", ["baixa", "media", "alta"]))

    findings = data.get_findings_senado(
        filtros.mes_inicio, filtros.mes_fim, filtros.partidos, filtros.ufs, filtros.senador_id, tipos_sel, severidades_sel
    )

    st.metric("Total de achados no periodo/filtro", len(findings))

    if findings.empty:
        st.info("Nenhum achado no periodo/filtro selecionado.")
        return

    findings = findings.copy()
    if mode == "public":
        findings["categoria"] = findings["tipo"].map(lambda t: neutral_copy.TIPO_LABEL_PUBLICO.get(t, t))

    c1, c2 = st.columns(2)
    with c1:
        if mode == "public":
            fig = px.bar(
                findings["categoria"].value_counts().reset_index(),
                x="categoria", y="count", title="Achados por categoria",
                color="categoria", color_discrete_map=theme.COR_POR_CATEGORIA_LABEL,
            )
        else:
            fig = px.bar(
                findings["tipo"].value_counts().reset_index(),
                x="tipo", y="count", title="Achados por tipo",
                color="tipo", color_discrete_map=theme.COR_POR_TIPO_ACHADO,
            )
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    if mode == "local":
        with c2:
            fig = px.pie(
                findings, names="severidade", title="Achados por severidade",
                color="severidade", color_discrete_map=theme.COR_POR_SEVERIDADE,
            )
            st.plotly_chart(fig, use_container_width=True)

    ranking = findings.groupby(["nome_parlamentar", "sigla_partido", "sigla_uf"]).size().reset_index(name="alertas")
    ranking = ranking.sort_values("alertas", ascending=False).head(20)
    st.subheader("Top 20 senadores por numero de alertas")
    st.dataframe(ranking, use_container_width=True, hide_index=True)

    st.subheader("Detalhamento")
    if mode == "public":
        findings["resumo"] = [
            neutral_copy.render(row.tipo, json.loads(row.dados_suporte) if row.dados_suporte else {})
            for row in findings.itertuples()
        ]
        findings["fonte"] = findings["fonte_url"].apply(lambda u: fonte_page.build_fonte_amigavel_url(u) if u else None)
        colunas_tela = ["mes_referencia", "nome_parlamentar", "sigla_partido", "sigla_uf", "categoria", "resumo", "fonte"]
        colunas_export = ["mes_referencia", "nome_parlamentar", "sigla_partido", "sigla_uf", "categoria", "resumo", "fonte_url"]
        st.dataframe(
            findings[colunas_tela], use_container_width=True, hide_index=True,
            column_config={"fonte": st.column_config.LinkColumn("Fonte", display_text="Ver fonte")},
        )
        st.caption("Nao entendeu uma categoria ou termo? Veja a pagina **Como funciona** no menu lateral.")
    else:
        colunas_export = ["mes_referencia", "nome_parlamentar", "sigla_partido", "sigla_uf", "tipo", "severidade", "descricao", "fonte_url"]
        st.dataframe(
            findings[colunas_export], use_container_width=True, hide_index=True,
            column_config={"fonte_url": st.column_config.LinkColumn("Fonte", display_text="Ver fonte (JSON)")},
        )

    st.markdown("**Exportar achados filtrados:**")
    export.botoes_exportar(findings[colunas_export], "vigia_publico_achados_senado", key_prefix="achados_senado")
    filtros_atuais = {
        "Periodo": f"{filtros.mes_inicio} a {filtros.mes_fim}",
        "Partido": ", ".join(filtros.partidos) or None,
        "Estado (UF)": ", ".join(filtros.ufs) or None,
        "Senador": filtros.senador_label if filtros.senador_id else None,
    }
    st.download_button(
        "📄 Baixar relatório (Markdown)",
        export.build_markdown_summary(findings, filtros_atuais),
        file_name="vigia_publico_relatorio_senado.md",
        mime="text/markdown",
        key="achados_senado_markdown",
    )
