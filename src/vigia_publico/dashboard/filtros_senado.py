"""Sidebar de filtros do Painel Senado - espelha `filtros.py` (mesma logica
de `key=` fixo + sincronizacao de URL), trocando deputado por senador.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urlencode

import streamlit as st

from vigia_publico.config import PUBLIC_BASE_URL
from vigia_publico.dashboard import data
from vigia_publico.dashboard.filtros import Mode


@dataclass(frozen=True)
class FiltrosSenado:
    mes_inicio: str
    mes_fim: str
    partidos: tuple[str, ...]
    ufs: tuple[str, ...]
    senador_id: int | None
    senador_label: str  # "(todos)" ou "Nome (Partido/UF)" - usado no export/relatorio


def render_sidebar_senado(mode: Mode, meses_disponiveis: list[str]) -> FiltrosSenado:
    """Mesma logica de `filtros.py::render_sidebar` - ver docstring la pro
    porque do `key=` fixo (licao ja paga cara nesse projeto: sem isso o
    multiselect perde a selecao a cada rerun)."""
    primeira_carga = mode == "public" and "_filtros_senado_url_aplicados" not in st.session_state
    qp = st.query_params if mode == "public" else {}

    if primeira_carga:
        if qp.get("de") in meses_disponiveis:
            st.session_state["filtro_senado_mes_inicio"] = qp["de"]
        if qp.get("ate") in meses_disponiveis:
            st.session_state["filtro_senado_mes_fim"] = qp["ate"]
        partidos_url = [p for p in qp.get_all("partido") if p in data.listar_partidos_senado()]
        if partidos_url:
            st.session_state["filtro_senado_partidos"] = partidos_url
        ufs_url = [u for u in qp.get_all("uf") if u in data.listar_ufs_senado()]
        if ufs_url:
            st.session_state["filtro_senado_ufs"] = ufs_url

    with st.sidebar:
        st.header("Filtros")

        idx_padrao_inicio = max(0, len(meses_disponiveis) - 12)  # ultimos 12 meses por padrao
        mes_inicio = st.selectbox("De (mes)", meses_disponiveis, index=idx_padrao_inicio, key="filtro_senado_mes_inicio")
        mes_fim = st.selectbox("Ate (mes)", meses_disponiveis, index=len(meses_disponiveis) - 1, key="filtro_senado_mes_fim")
        if mes_inicio > mes_fim:
            st.error("'De' precisa ser antes de 'Ate'.")
            st.stop()

        partidos_sel = tuple(st.multiselect("Partido", data.listar_partidos_senado(), key="filtro_senado_partidos"))
        ufs_sel = tuple(st.multiselect("Estado (UF)", data.listar_ufs_senado(), key="filtro_senado_ufs"))

        senadores_df = data.listar_senadores(partidos_sel, ufs_sel)
        opcoes_senador = ["(todos)"] + [
            f"{row.nome_parlamentar} ({row.sigla_partido}/{row.sigla_uf})" for row in senadores_df.itertuples()
        ]

        if primeira_carga and qp.get("senador"):
            for row in senadores_df.itertuples():
                if str(row.id) == qp["senador"]:
                    st.session_state["filtro_senado_label"] = f"{row.nome_parlamentar} ({row.sigla_partido}/{row.sigla_uf})"
                    break

        # Senador escolhido pode ter saido da lista (usuario mudou
        # partido/UF depois de escolher um senador especifico) - sem essa
        # checagem o selectbox quebra (valor em session_state fora de
        # `options`). Volta pra "(todos)", que e o comportamento esperado.
        if st.session_state.get("filtro_senado_label") not in opcoes_senador:
            st.session_state["filtro_senado_label"] = "(todos)"

        senador_escolhido = st.selectbox("Senador", opcoes_senador, key="filtro_senado_label")
        senador_id_sel = None
        if senador_escolhido != "(todos)":
            idx = opcoes_senador.index(senador_escolhido) - 1
            senador_id_sel = int(senadores_df.iloc[idx]["id"])

        if primeira_carga:
            st.session_state["_filtros_senado_url_aplicados"] = True

        st.caption(f"{len(senadores_df)} senador(es) no filtro atual de partido/UF.")
        if mode == "local" and st.button("Recarregar dados", key="filtro_senado_recarregar"):
            st.cache_data.clear()
            st.rerun()

        if mode == "public":
            _sincronizar_url(mes_inicio, mes_fim, partidos_sel, ufs_sel, senador_id_sel)
            _secao_compartilhar()

    return FiltrosSenado(
        mes_inicio=mes_inicio,
        mes_fim=mes_fim,
        partidos=partidos_sel,
        ufs=ufs_sel,
        senador_id=senador_id_sel,
        senador_label=senador_escolhido,
    )


def _sincronizar_url(
    mes_inicio: str, mes_fim: str, partidos_sel: tuple[str, ...], ufs_sel: tuple[str, ...], senador_id_sel: int | None
) -> None:
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
    if senador_id_sel:
        st.query_params["senador"] = str(senador_id_sel)
    elif "senador" in st.query_params:
        del st.query_params["senador"]


def _secao_compartilhar() -> None:
    st.divider()
    st.subheader("🔗 Compartilhar esta visão")
    querystring = urlencode(dict(st.query_params), doseq=True)
    url_compartilhavel = f"{PUBLIC_BASE_URL}/painel-senado" + (f"?{querystring}" if querystring else "")
    st.code(url_compartilhavel, language=None)
    texto_share = quote("Vigia Público — monitor de senadores com dados abertos do Senado Federal")
    url_share = quote(url_compartilhavel, safe="")
    st.link_button("Compartilhar no WhatsApp", f"https://api.whatsapp.com/send?text={texto_share}%20{url_share}", use_container_width=True)
    st.link_button("Compartilhar no X", f"https://twitter.com/intent/tweet?text={texto_share}&url={url_share}", use_container_width=True)
    st.link_button("Compartilhar no Telegram", f"https://t.me/share/url?url={url_share}&text={texto_share}", use_container_width=True)
