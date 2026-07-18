"""Pagina 'Fonte de um achado': busca ao vivo o dado bruto da API de Dados
Abertos da Camara por tras de um achado e mostra de um jeito legivel.

Por que existir: os links salvos em `findings.fonte_url` (ver
`detection/statistical.py`) apontam pra API real da Camara - mas um clique
direto nesse link, vindo de um navegador comum, cai no formato XML da API
(a API so devolve JSON quando o cliente manda `Accept: application/json`,
como o proprio pipeline de ingestao faz - ver `camara_api/client.py`). Quase
ninguem le XML cru. Essa pagina busca o mesmo endpoint com o header certo e
renderiza uma tabela/JSON legivel, com um link pro endpoint bruto embaixo
pra quem realmente quiser ir la.

Seguranca: so busca URLs do proprio host da API da Camara (HOST_PERMITIDO) -
sem essa checagem, aceitar `?url=` livremente seria um SSRF (visitante
poderia tentar fazer o servidor buscar qualquer URL, inclusive interna).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd
import streamlit as st

HOST_PERMITIDO = "dadosabertos.camara.leg.br"


def build_fonte_amigavel_url(raw_url: str) -> str:
    """Envolve uma URL da API da Camara num link RELATIVO pra essa pagina -
    usado na tela do dashboard (coluna 'Ver fonte'). Deliberadamente sem
    dominio (PUBLIC_BASE_URL): esse link e clicado dentro do proprio app, e
    precisa funcionar em qualquer origem onde o app estiver rodando (local
    em dev, VPS em producao) sem apontar sempre pro dominio de producao -
    isso causava 404 ao testar local (o link levava pro dominio de
    producao, nao pro localhost onde o app realmente estava rodando).

    Pro relatorio Markdown (que sai do app, e lido em outro lugar), use
    `PUBLIC_BASE_URL + build_fonte_amigavel_url(...)` explicitamente - ver
    `export.py`."""
    return f"/fonte?url={urllib.parse.quote(raw_url, safe='')}"


def _url_permitida(url: str) -> bool:
    p = urllib.parse.urlparse(url)
    return p.scheme == "https" and p.hostname == HOST_PERMITIDO


def _buscar_json(url: str) -> dict | list:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "vigia-publico"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - host ja validado em _url_permitida
        return json.loads(resp.read().decode("utf-8"))


def render_fonte() -> None:
    st.title("🔎 Fonte de um achado")
    st.caption(
        "Busca ao vivo, na API pública de Dados Abertos da Câmara dos Deputados, o dado bruto "
        "por trás de um achado - a mesma fonte que o Vigia Público usa - num formato mais fácil "
        "de ler do que o XML/JSON cru da API."
    )

    url = st.query_params.get("url")
    if not url or not _url_permitida(url):
        st.warning(
            "Nenhuma fonte válida foi indicada nessa página. Volte pro **Painel** e clique em "
            "'Ver fonte' na tabela de achados."
        )
        return

    try:
        payload = _buscar_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        st.error(f"Não foi possível buscar o dado agora ({exc}). Tente o link direto abaixo.")
        st.link_button("Ver o dado bruto direto na API da Câmara", url)
        return

    dados = payload.get("dados", payload) if isinstance(payload, dict) else payload

    if isinstance(dados, list) and dados:
        st.dataframe(pd.json_normalize(dados), use_container_width=True, hide_index=True)
    elif isinstance(dados, dict) and dados:
        st.json(dados)
    else:
        st.info("A consulta não retornou dados.")

    st.divider()
    st.link_button("Ver o dado bruto (JSON) direto na API da Câmara", url)
