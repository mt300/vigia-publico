"""Dashboard local (Streamlit) para explorar dados e achados do senado-sentinel.

Rodar com: uv run streamlit run src/senado_sentinel/dashboard/app.py
"""

from __future__ import annotations

import datetime as dt

import plotly.express as px
import streamlit as st

from senado_sentinel.dashboard import data

st.set_page_config(page_title="Senado Sentinel", page_icon="\U0001f3db️", layout="wide")

st.title("Senado Sentinel - Monitor de Deputados Federais")

# --- filtros globais (sidebar) ----------------------------------------------

meses_disponiveis = data.listar_meses_disponiveis()
if not meses_disponiveis:
    st.warning("Banco de dados ainda sem despesas. Rode o backfill/update antes de usar o dashboard.")
    st.stop()

with st.sidebar:
    st.header("Filtros")

    mes_min, mes_max = meses_disponiveis[0], meses_disponiveis[-1]
    idx_padrao_inicio = max(0, len(meses_disponiveis) - 12)  # ultimos 12 meses por padrao
    mes_inicio = st.selectbox("De (mes)", meses_disponiveis, index=idx_padrao_inicio)
    mes_fim = st.selectbox("Ate (mes)", meses_disponiveis, index=len(meses_disponiveis) - 1)
    if mes_inicio > mes_fim:
        st.error("'De' precisa ser antes de 'Ate'.")
        st.stop()

    partidos_sel = tuple(st.multiselect("Partido", data.listar_partidos()))
    ufs_sel = tuple(st.multiselect("Estado (UF)", data.listar_ufs()))

    deputados_df = data.listar_deputados(partidos_sel, ufs_sel)
    opcoes_deputado = ["(todos)"] + [
        f"{row.nome_eleitoral} ({row.sigla_partido}/{row.sigla_uf})" for row in deputados_df.itertuples()
    ]
    deputado_escolhido = st.selectbox("Deputado", opcoes_deputado)
    deputado_id_sel = None
    if deputado_escolhido != "(todos)":
        idx = opcoes_deputado.index(deputado_escolhido) - 1
        deputado_id_sel = int(deputados_df.iloc[idx]["id"])

    st.caption(f"{len(deputados_df)} deputado(s) no filtro atual de partido/UF.")
    if st.button("Recarregar dados"):
        st.cache_data.clear()
        st.rerun()

aba_achados, aba_gastos, aba_presenca, aba_perfil = st.tabs(
    ["Achados", "Gastos", "Presenca/Votos", "Perfil do Deputado"]
)

# --- aba: achados ------------------------------------------------------------

with aba_achados:
    col1, col2 = st.columns(2)
    tipos_sel = tuple(col1.multiselect("Tipo de achado", data.listar_tipos_finding()))
    severidades_sel = tuple(col2.multiselect("Severidade", ["baixa", "media", "alta"]))

    findings = data.get_findings(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel, tipos_sel, severidades_sel)

    st.metric("Total de achados no periodo/filtro", len(findings))

    if not findings.empty:
        c1, c2 = st.columns(2)
        with c1:
            fig = px.bar(
                findings["tipo"].value_counts().reset_index(),
                x="tipo", y="count", title="Achados por tipo",
            )
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.pie(findings, names="severidade", title="Achados por severidade")
            st.plotly_chart(fig, use_container_width=True)

        ranking = findings.groupby(["nome_eleitoral", "sigla_partido", "sigla_uf"]).size().reset_index(name="alertas")
        ranking = ranking.sort_values("alertas", ascending=False).head(20)
        st.subheader("Top 20 deputados por numero de alertas")
        st.dataframe(ranking, use_container_width=True, hide_index=True)

        st.subheader("Detalhamento")
        st.dataframe(
            findings[["mes_referencia", "nome_eleitoral", "sigla_partido", "sigla_uf", "tipo", "severidade", "descricao", "fonte_url"]],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Nenhum achado no periodo/filtro selecionado.")

# --- aba: gastos --------------------------------------------------------------

with aba_gastos:
    despesas_mes = data.get_despesas_mensal(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
    if despesas_mes.empty:
        st.info("Sem dados de despesas no periodo/filtro selecionado.")
    else:
        st.metric("Total gasto no periodo", f"R$ {despesas_mes['total'].sum():,.2f}")
        fig = px.line(despesas_mes, x="mes", y="total", markers=True, title="Gasto total por mes")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            categorias = data.get_despesas_por_categoria(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
            fig = px.bar(categorias.head(15), x="total", y="tipo_despesa", orientation="h", title="Gasto por categoria")
            fig.update_layout(yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            if deputado_id_sel is None:
                ranking_gasto = data.get_ranking_gasto(mes_inicio, mes_fim, partidos_sel, ufs_sel)
                st.subheader("Top 20 deputados por gasto total")
                st.dataframe(
                    ranking_gasto[["nome_eleitoral", "sigla_partido", "sigla_uf", "total"]],
                    use_container_width=True, hide_index=True,
                )
            else:
                st.dataframe(categorias, use_container_width=True, hide_index=True)

# --- aba: presenca/votos ------------------------------------------------------

with aba_presenca:
    presenca = data.get_presenca_mensal(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
    presenca = presenca.dropna(subset=["taxa_presenca"])
    if presenca.empty:
        st.info("Sem votacoes nominais no periodo/filtro selecionado.")
    else:
        media = presenca["taxa_presenca"].mean()
        st.metric("Taxa media de presenca no periodo", f"{media:.0%}")
        cores = presenca["proximo_eleicao"].map({True: "Proximo de eleicao geral (ago-out)", False: "Resto do mandato"})
        fig = px.line(presenca, x="mes", y="taxa_presenca", markers=True, title="Taxa de presenca por mes")
        fig.add_bar(
            x=presenca["mes"], y=presenca["taxa_presenca"],
            marker_color=["crimson" if p else "rgba(0,0,0,0)" for p in presenca["proximo_eleicao"]],
            showlegend=False, opacity=0.25, name="Proximo de eleicao",
        )
        fig.update_yaxes(tickformat=".0%", range=[0, 1])
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Presenca bruta = votos registrados / votacoes NOMINAIS do Plenario no mes "
            "(votacoes simbolicas/por unanimidade nao entram na conta). Este grafico NAO "
            "desconta periodos de licenca oficial - para a taxa de ausencia SEM JUSTIFICATIVA "
            "(que ja exclui licenca e e a base dos alertas), veja a aba Achados. Barras "
            "vermelhas destacam ago/set/out de anos de eleicao geral (quando deputados "
            "federais concorrem a reeleicao) - e comum a presenca cair nesses meses por causa "
            "de campanha, isso NAO e por si so um sinal de irregularidade."
        )

        if presenca["proximo_eleicao"].any() and (~presenca["proximo_eleicao"]).any():
            col1, col2 = st.columns(2)
            col1.metric("Presenca media - proximo de eleicao", f"{presenca.loc[presenca['proximo_eleicao'], 'taxa_presenca'].mean():.0%}")
            col2.metric("Presenca media - resto do mandato", f"{presenca.loc[~presenca['proximo_eleicao'], 'taxa_presenca'].mean():.0%}")

# --- aba: perfil do deputado ---------------------------------------------------

with aba_perfil:
    if deputado_id_sel is None:
        st.info("Selecione um deputado especifico no filtro da barra lateral para ver o perfil.")
    else:
        perfil = data.get_perfil_deputado(deputado_id_sel)
        col_foto, col_info = st.columns([1, 3])
        with col_foto:
            if perfil.get("url_foto"):
                st.image(perfil["url_foto"], width=150)
        with col_info:
            st.subheader(f"{perfil['nome_eleitoral']} ({perfil['sigla_partido']}/{perfil['sigla_uf']})")
            st.write(f"**Nome civil:** {perfil.get('nome_civil') or '-'}")
            st.write(f"**Situacao:** {perfil.get('situacao') or '-'} | **Condicao eleitoral:** {perfil.get('condicao_eleitoral') or '-'}")
            st.write(f"**Email:** {perfil.get('email') or '-'}")
            st.write(f"**Gabinete:** predio {perfil.get('gabinete_predio') or '-'}, sala {perfil.get('gabinete_sala') or '-'}, tel {perfil.get('gabinete_telefone') or '-'}")

            redes = data.get_redes_sociais(deputado_id_sel)
            if not redes.empty:
                links = " | ".join(f"[{r.rede}]({r.url})" for r in redes.itertuples())
                st.markdown(f"**Redes sociais:** {links}")

        st.subheader("Historico de mandatos e trocas de partido")
        historico = data.get_historico_deputado(deputado_id_sel)
        st.dataframe(historico, use_container_width=True, hide_index=True)

        st.subheader("Gasto mensal")
        despesas_dep = data.get_despesas_mensal(mes_inicio, mes_fim, deputado_id=deputado_id_sel)
        if not despesas_dep.empty:
            st.plotly_chart(px.bar(despesas_dep, x="mes", y="total"), use_container_width=True)

        st.subheader("Achados deste deputado no periodo")
        findings_dep = data.get_findings(mes_inicio, mes_fim, deputado_id=deputado_id_sel)
        st.dataframe(
            findings_dep[["mes_referencia", "tipo", "severidade", "descricao"]] if not findings_dep.empty else findings_dep,
            use_container_width=True, hide_index=True,
        )

st.caption(f"Dados atualizados ate {mes_max}. Gerado em {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}.")
