"""Corpo do dashboard Streamlit, compartilhado pelo entrypoint local
(`app.py`) e pelo publico (`app_public.py`).

`mode="public"` esconde o que so faz sentido pra uso pessoal/interno:
severidade (rotulo interpretativo), o texto de `descricao` (reescrito via
`detection.neutral_copy` a partir de `dados_suporte`) e os campos de
contato do deputado no perfil. `mode="local"` preserva o comportamento
original, sem nenhuma perda de informacao.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Literal
from urllib.parse import quote, urlencode

import plotly.express as px
import streamlit as st

from vigia_publico.config import PUBLIC_BASE_URL
from vigia_publico.dashboard import data, export, fonte_page, theme
from vigia_publico.detection import neutral_copy

Mode = Literal["local", "public"]


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

    # --- filtros globais (sidebar) -------------------------------------------

    meses_disponiveis = data.listar_meses_disponiveis()
    if not meses_disponiveis:
        st.warning("Banco de dados ainda sem despesas. Rode o backfill/update antes de usar o dashboard.")
        st.stop()

    # Cada widget de filtro usa `key=` fixo (nunca muda entre reruns) - e
    # Streamlit quem mantem o valor em st.session_state[key] sozinho a
    # partir dai. NAO passar `default`/`index` recalculado a cada rerun (o
    # jeito antigo): isso muda a identidade implicita do widget toda vez
    # que o valor computado difere do da rodada anterior, e o Streamlit
    # trata como um widget NOVO - na pratica, o multiselect fecha/perde a
    # selecao a cada clique. `key` fixo evita isso completamente.
    #
    # No modo publico, a URL preenche esses `session_state[key]` uma unica
    # vez por sessao (`primeira_carga`), antes dos widgets serem criados -
    # depois disso quem manda e so a interacao do usuario.
    primeira_carga = mode == "public" and "_filtros_url_aplicados" not in st.session_state
    qp = st.query_params if mode == "public" else {}

    if primeira_carga:
        if qp.get("de") in meses_disponiveis:
            st.session_state["filtro_mes_inicio"] = qp["de"]
        if qp.get("ate") in meses_disponiveis:
            st.session_state["filtro_mes_fim"] = qp["ate"]
        partidos_url = [p for p in qp.get_all("partido") if p in data.listar_partidos()]
        if partidos_url:
            st.session_state["filtro_partidos"] = partidos_url
        ufs_url = [u for u in qp.get_all("uf") if u in data.listar_ufs()]
        if ufs_url:
            st.session_state["filtro_ufs"] = ufs_url

    with st.sidebar:
        st.header("Filtros")

        mes_min, mes_max = meses_disponiveis[0], meses_disponiveis[-1]
        idx_padrao_inicio = max(0, len(meses_disponiveis) - 12)  # ultimos 12 meses por padrao
        mes_inicio = st.selectbox("De (mes)", meses_disponiveis, index=idx_padrao_inicio, key="filtro_mes_inicio")
        mes_fim = st.selectbox("Ate (mes)", meses_disponiveis, index=len(meses_disponiveis) - 1, key="filtro_mes_fim")
        if mes_inicio > mes_fim:
            st.error("'De' precisa ser antes de 'Ate'.")
            st.stop()

        partidos_sel = tuple(st.multiselect("Partido", data.listar_partidos(), key="filtro_partidos"))
        ufs_sel = tuple(st.multiselect("Estado (UF)", data.listar_ufs(), key="filtro_ufs"))

        deputados_df = data.listar_deputados(partidos_sel, ufs_sel)
        opcoes_deputado = ["(todos)"] + [
            f"{row.nome_eleitoral} ({row.sigla_partido}/{row.sigla_uf})" for row in deputados_df.itertuples()
        ]

        if primeira_carga and qp.get("deputado"):
            for row in deputados_df.itertuples():
                if str(row.id) == qp["deputado"]:
                    st.session_state["filtro_deputado_label"] = f"{row.nome_eleitoral} ({row.sigla_partido}/{row.sigla_uf})"
                    break

        # Deputado escolhido pode ter saido da lista (usuario mudou
        # partido/UF depois de escolher um deputado especifico) - sem essa
        # checagem o selectbox quebra (valor em session_state fora de
        # `options`). Volta pra "(todos)", que e o comportamento esperado.
        if st.session_state.get("filtro_deputado_label") not in opcoes_deputado:
            st.session_state["filtro_deputado_label"] = "(todos)"

        deputado_escolhido = st.selectbox("Deputado", opcoes_deputado, key="filtro_deputado_label")
        deputado_id_sel = None
        if deputado_escolhido != "(todos)":
            idx = opcoes_deputado.index(deputado_escolhido) - 1
            deputado_id_sel = int(deputados_df.iloc[idx]["id"])

        if primeira_carga:
            st.session_state["_filtros_url_aplicados"] = True

        st.caption(f"{len(deputados_df)} deputado(s) no filtro atual de partido/UF.")
        if mode == "local" and st.button("Recarregar dados"):
            st.cache_data.clear()
            st.rerun()

        if mode == "public":
            # Mantem a URL sempre sincronizada com o filtro atual - e o que
            # torna a URL da aba diretamente compartilhavel/copiavel.
            st.query_params["de"] = mes_inicio
            st.query_params["ate"] = mes_fim
            if partidos_sel:
                st.query_params["partido"] = list(partidos_sel)
            elif "partido" in st.query_params:
                del st.query_params["partido"]
            if ufs_sel:
                st.query_params["uf"] = list(ufs_sel)
            elif "uf" in st.query_params:
                del st.query_params["uf"]
            if deputado_id_sel:
                st.query_params["deputado"] = str(deputado_id_sel)
            elif "deputado" in st.query_params:
                del st.query_params["deputado"]

            st.divider()
            st.subheader("🔗 Compartilhar esta visão")
            querystring = urlencode(dict(st.query_params), doseq=True)
            url_compartilhavel = f"{PUBLIC_BASE_URL}/painel" + (f"?{querystring}" if querystring else "")
            st.code(url_compartilhavel, language=None)
            texto_share = quote("Vigia Público — monitor de deputados federais com dados abertos da Câmara")
            url_share = quote(url_compartilhavel, safe="")
            st.link_button("Compartilhar no WhatsApp", f"https://api.whatsapp.com/send?text={texto_share}%20{url_share}", use_container_width=True)
            st.link_button("Compartilhar no X", f"https://twitter.com/intent/tweet?text={texto_share}&url={url_share}", use_container_width=True)
            st.link_button("Compartilhar no Telegram", f"https://t.me/share/url?url={url_share}&text={texto_share}", use_container_width=True)

    aba_achados, aba_gastos, aba_presenca, aba_perfil = st.tabs(
        ["Achados", "Gastos", "Presenca/Votos", "Perfil do Deputado"]
    )

    # --- aba: achados ---------------------------------------------------------

    with aba_achados:
        col1, col2 = st.columns(2)
        tipos_disponiveis = data.listar_tipos_finding()
        if mode == "public":
            # Mostra rotulo amigavel no filtro (nao o codigo cru tipo
            # "GASTO_OUTLIER_VS_PARES"), mas resolve de volta pro codigo
            # antes de consultar - ver detection/neutral_copy.py.
            opcoes_tipo = {neutral_copy.TIPO_LABEL_PUBLICO.get(t, t): t for t in tipos_disponiveis}
            labels_sel = col1.multiselect("Categoria de achado", sorted(opcoes_tipo.keys()))
            tipos_sel = tuple(opcoes_tipo[label] for label in labels_sel)
        else:
            tipos_sel = tuple(col1.multiselect("Tipo de achado", tipos_disponiveis))
        severidades_sel = ()
        if mode == "local":
            severidades_sel = tuple(col2.multiselect("Severidade", ["baixa", "media", "alta"]))

        findings = data.get_findings(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel, tipos_sel, severidades_sel)

        st.metric("Total de achados no periodo/filtro", len(findings))

        if not findings.empty:
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

            ranking = findings.groupby(["nome_eleitoral", "sigla_partido", "sigla_uf"]).size().reset_index(name="alertas")
            ranking = ranking.sort_values("alertas", ascending=False).head(20)
            st.subheader("Top 20 deputados por numero de alertas")
            st.dataframe(ranking, use_container_width=True, hide_index=True)

            st.subheader("Detalhamento")
            # "fonte" (tela) e "fonte_url" (export) sao intencionalmente
            # diferentes no modo publico: a tela usa o link amigavel (evita
            # o visitante cair no XML cru da API - ver fonte_page.py), o
            # export CSV/Excel/Markdown mantem a URL crua (mais direta pra
            # quem vai processar o dado por conta propria).
            if mode == "public":
                findings["resumo"] = [
                    neutral_copy.render(row.tipo, json.loads(row.dados_suporte) if row.dados_suporte else {})
                    for row in findings.itertuples()
                ]
                findings["fonte"] = findings["fonte_url"].apply(lambda u: fonte_page.build_fonte_amigavel_url(u) if u else None)
                colunas_tela = ["mes_referencia", "nome_eleitoral", "sigla_partido", "sigla_uf", "categoria", "resumo", "fonte"]
                colunas_export = ["mes_referencia", "nome_eleitoral", "sigla_partido", "sigla_uf", "categoria", "resumo", "fonte_url"]
                st.dataframe(
                    findings[colunas_tela], use_container_width=True, hide_index=True,
                    column_config={"fonte": st.column_config.LinkColumn("Fonte", display_text="Ver fonte")},
                )
                st.caption("Nao entendeu uma categoria ou termo? Veja a pagina **Como funciona** no menu lateral.")
            else:
                colunas_export = ["mes_referencia", "nome_eleitoral", "sigla_partido", "sigla_uf", "tipo", "severidade", "descricao", "fonte_url"]
                st.dataframe(
                    findings[colunas_export], use_container_width=True, hide_index=True,
                    column_config={"fonte_url": st.column_config.LinkColumn("Fonte", display_text="Ver fonte (JSON)")},
                )

            st.markdown("**Exportar achados filtrados:**")
            export.botoes_exportar(findings[colunas_export], "vigia_publico_achados", key_prefix="achados")
            filtros_atuais = {
                "Periodo": f"{mes_inicio} a {mes_fim}",
                "Partido": ", ".join(partidos_sel) or None,
                "Estado (UF)": ", ".join(ufs_sel) or None,
                "Deputado": deputado_escolhido if deputado_id_sel else None,
            }
            st.download_button(
                "📄 Baixar relatório (Markdown)",
                export.build_markdown_summary(findings, filtros_atuais),
                file_name="vigia_publico_relatorio.md",
                mime="text/markdown",
                key="achados_markdown",
            )
        else:
            st.info("Nenhum achado no periodo/filtro selecionado.")

    # --- aba: gastos ------------------------------------------------------------

    with aba_gastos:
        despesas_mes = data.get_despesas_mensal(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
        if despesas_mes.empty:
            st.info("Sem dados de despesas no periodo/filtro selecionado.")
        else:
            st.metric("Total gasto no periodo", f"R$ {despesas_mes['total'].sum():,.2f}")
            fig = px.line(
                despesas_mes, x="mes", y="total", markers=True, title="Gasto total por mes",
                color_discrete_sequence=[theme.COR_PRIMARIA],
            )
            st.plotly_chart(fig, use_container_width=True)

            col1, col2 = st.columns(2)
            with col1:
                categorias = data.get_despesas_por_categoria(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
                fig = px.bar(
                    categorias.head(15), x="total", y="tipo_despesa", orientation="h", title="Gasto por categoria",
                    color_discrete_sequence=[theme.COR_PRIMARIA],
                )
                fig.update_layout(yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig, use_container_width=True)
                export.botoes_exportar(categorias, "vigia_publico_gastos_por_categoria", key_prefix="gastos_categoria")
            with col2:
                if deputado_id_sel is None:
                    ranking_gasto = data.get_ranking_gasto(mes_inicio, mes_fim, partidos_sel, ufs_sel)
                    st.subheader("Top 20 deputados por gasto total")
                    ranking_gasto_cols = ranking_gasto[["nome_eleitoral", "sigla_partido", "sigla_uf", "total"]]
                    st.dataframe(ranking_gasto_cols, use_container_width=True, hide_index=True)
                    export.botoes_exportar(ranking_gasto_cols, "vigia_publico_ranking_gasto", key_prefix="ranking_gasto")
                else:
                    st.dataframe(categorias, use_container_width=True, hide_index=True)

            with st.expander("🔍 Ver despesas individuais (fornecedor, data, valor, nota)"):
                detalhado = data.get_despesas_detalhado(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
                if detalhado.empty:
                    st.info("Sem despesas individuais no periodo/filtro selecionado.")
                else:
                    if len(detalhado) >= 300:
                        st.caption("Mostrando as 300 maiores despesas do filtro atual - refine o filtro (ex: escolha um deputado) pra ver tudo.")
                    st.dataframe(
                        detalhado, use_container_width=True, hide_index=True,
                        column_config={"url_documento": st.column_config.LinkColumn("Nota", display_text="Ver nota")},
                    )
                    export.botoes_exportar(detalhado, "vigia_publico_despesas_detalhado", key_prefix="despesas_detalhado")

    # --- aba: presenca/votos ------------------------------------------------------

    with aba_presenca:
        presenca = data.get_presenca_mensal(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
        presenca = presenca.dropna(subset=["taxa_presenca"])
        if presenca.empty:
            st.info("Sem votacoes nominais no periodo/filtro selecionado.")
        else:
            media = presenca["taxa_presenca"].mean()
            st.metric("Taxa media de presenca no periodo", f"{media:.0%}")
            fig = px.line(
                presenca, x="mes", y="taxa_presenca", markers=True, title="Taxa de presenca por mes",
                color_discrete_sequence=[theme.COR_PRIMARIA],
            )
            # Amber (cor de "atencao ao contexto"), nao vermelho/crimson - o
            # destaque e so um lembrete temporal (proximidade de eleicao),
            # nao um alarme, e vermelho contradiria o texto logo abaixo.
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
            despesas_dep = data.get_despesas_mensal(mes_inicio, mes_fim, deputado_id=deputado_id_sel)
            if not despesas_dep.empty:
                fig = px.bar(despesas_dep, x="mes", y="total", color_discrete_sequence=[theme.COR_PRIMARIA])
                st.plotly_chart(fig, use_container_width=True)

            with st.expander("🔍 Ver despesas individuais (fornecedor, data, valor, nota)"):
                detalhado_dep = data.get_despesas_detalhado(mes_inicio, mes_fim, deputado_id=deputado_id_sel, limite=1000)
                if detalhado_dep.empty:
                    st.info("Sem despesas individuais no periodo selecionado.")
                else:
                    st.dataframe(
                        detalhado_dep, use_container_width=True, hide_index=True,
                        column_config={"url_documento": st.column_config.LinkColumn("Nota", display_text="Ver nota")},
                    )
                    export.botoes_exportar(detalhado_dep, f"vigia_publico_despesas_{deputado_id_sel}", key_prefix="perfil_despesas_detalhado")

            st.subheader("Achados deste deputado no periodo")
            findings_dep = data.get_findings(mes_inicio, mes_fim, deputado_id=deputado_id_sel)
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

    st.caption(f"Dados atualizados ate {mes_max}. Gerado em {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}.")
    st.caption("Desenvolvido por [MWebS](https://www.mwebs.com.br).")
