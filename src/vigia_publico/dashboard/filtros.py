"""Sidebar de filtros (periodo/partido/UF/deputado) do painel - fonte unica
dos filtros usados por todas as abas (`aba_achados.py`, `aba_gastos.py`,
`aba_presenca.py`, `aba_perfil.py`). No modo publico, tambem sincroniza com
a URL (link compartilhavel) e mostra os botoes de compartilhar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlencode

import streamlit as st

from vigia_publico.config import PUBLIC_BASE_URL
from vigia_publico.dashboard import data

Mode = Literal["local", "public"]


@dataclass(frozen=True)
class Filtros:
    mes_inicio: str
    mes_fim: str
    partidos: tuple[str, ...]
    ufs: tuple[str, ...]
    deputado_id: int | None
    deputado_label: str  # "(todos)" ou "Nome (Partido/UF)" - usado no export/relatorio


def render_sidebar(mode: Mode, meses_disponiveis: list[str]) -> Filtros:
    """Desenha a sidebar de filtros e devolve a selecao atual.

    Cada widget usa `key=` fixo (nunca muda entre reruns) - e o Streamlit
    quem mantem o valor em st.session_state[key] sozinho a partir dai. NAO
    passar `default`/`index` recalculado a cada rerun (o jeito antigo):
    isso muda a identidade implicita do widget toda vez que o valor
    computado difere do da rodada anterior, e o Streamlit trata como um
    widget NOVO - na pratica, o multiselect fecha/perde a selecao a cada
    clique. `key` fixo evita isso completamente.

    No modo publico, a URL preenche esses `session_state[key]` uma unica
    vez por sessao (`primeira_carga`), antes dos widgets serem criados -
    depois disso quem manda e so a interacao do usuario.
    """
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
            _sincronizar_url(mes_inicio, mes_fim, partidos_sel, ufs_sel, deputado_id_sel)
            _secao_compartilhar()

    return Filtros(
        mes_inicio=mes_inicio,
        mes_fim=mes_fim,
        partidos=partidos_sel,
        ufs=ufs_sel,
        deputado_id=deputado_id_sel,
        deputado_label=deputado_escolhido,
    )


def _sincronizar_url(
    mes_inicio: str, mes_fim: str, partidos_sel: tuple[str, ...], ufs_sel: tuple[str, ...], deputado_id_sel: int | None
) -> None:
    """Mantem a URL sempre sincronizada com o filtro atual - e o que torna
    a URL do Painel diretamente compartilhavel/copiavel."""
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


def _secao_compartilhar() -> None:
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
