"""Camada de cache do Streamlit sobre `analytics.queries`.

So orquestra conexao + `st.cache_data` - a logica de consulta em si vive em
`analytics/queries.py` (sem Streamlit), reaproveitada pelo dashboard local e
pelo publico. `use_db_path` deixa o entrypoint escolher o banco (local
gravavel vs snapshot publico read-only) sem tocar em secrets/env.
"""

from __future__ import annotations

import functools
import sqlite3
from pathlib import Path
from typing import Callable

import streamlit as st

from vigia_publico.analytics import queries
from vigia_publico.config import DB_PATH

CACHE_TTL_SEGUNDOS = 300

_db_path: Path = DB_PATH


def use_db_path(path: Path) -> None:
    global _db_path
    _db_path = path


def _cached_query(query_fn: Callable) -> Callable:
    """Decorator pra funcoes de `analytics/queries.py` (recebem `conn` como
    1o argumento). Abre a conexao com o banco ATUAL (`_db_path`) e - o
    ponto principal - inclui o CAMINHO do banco na chave de cache do
    Streamlit.

    Sem isso, `st.cache_data` cacheia so pelos argumentos visiveis da
    funcao (nunca ve `_db_path`, que e uma variavel de modulo por fora da
    assinatura) - trocar de banco no mesmo processo via `use_db_path()`
    devolve resultado cacheado do banco ANTERIOR pra qualquer chamada com
    os mesmos argumentos. Bug real, reproduzido: banco A com um partido,
    troca pra banco B com outro partido, `listar_partidos()` continua
    devolvendo o do banco A. So morde quando dois bancos coexistem no
    mesmo processo (nao acontece em producao - cada processo, local ou
    publico, so chama `use_db_path()` uma vez - mas acontece em testes que
    usam bancos temporarios diferentes por teste). Ver
    `tests/test_data_cache_isolamento.py`.

    Tambem inclui o NOME da query na chave - a funcao interna `_cached` e
    redefinida a cada chamada de `_cached_query` (uma vez por funcao
    decorada aqui embaixo), mas todas nascem no mesmo `__qualname__`
    (`_cached_query.<locals>._cached`, mesma linha de origem) porque sao
    definidas dentro do MESMO decorator. O Streamlit usa esse identificador
    estatico (nao a identidade do objeto em memoria) como parte da chave de
    cache - sem o nome da query, duas funcoes DIFERENTES com a MESMA forma
    de argumentos (ex: `get_despesas_mensal` e `get_despesas_por_categoria`,
    ambas `(mes_inicio, mes_fim, partidos, ufs, deputado_id)`) chamadas com
    os MESMOS valores colidem e uma devolve o resultado cacheado da outra.
    Bug reproduzido e coberto em `tests/test_data_cache_isolamento.py`.
    """

    @st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
    def _cached(query_name: str, db_path_str: str, *args, **kwargs):
        with sqlite3.connect(f"file:{db_path_str}?mode=ro", uri=True) as conn:
            return query_fn(conn, *args, **kwargs)

    @functools.wraps(query_fn)
    def wrapper(*args, **kwargs):
        return _cached(query_fn.__qualname__, str(_db_path), *args, **kwargs)

    return wrapper


listar_partidos = _cached_query(queries.listar_partidos)
listar_ufs = _cached_query(queries.listar_ufs)
listar_deputados = _cached_query(queries.listar_deputados)
listar_meses_disponiveis = _cached_query(queries.listar_meses_disponiveis)
get_findings = _cached_query(queries.get_findings)
listar_tipos_finding = _cached_query(queries.listar_tipos_finding)
get_despesas_mensal = _cached_query(queries.get_despesas_mensal)
get_despesas_por_categoria = _cached_query(queries.get_despesas_por_categoria)
get_despesas_detalhado = _cached_query(queries.get_despesas_detalhado)
get_ranking_gasto = _cached_query(queries.get_ranking_gasto)
get_presenca_mensal = _cached_query(queries.get_presenca_mensal)
get_perfil_deputado = _cached_query(queries.get_perfil_deputado)
get_historico_deputado = _cached_query(queries.get_historico_deputado)
get_redes_sociais = _cached_query(queries.get_redes_sociais)

# --- Senado --------------------------------------------------------------
# Mesmo decorator `_cached_query` - obrigatorio, nao opcional (ver docstring
# acima: e o mecanismo que ja teve 2 bugs de colisao de cache corrigidos).

listar_partidos_senado = _cached_query(queries.listar_partidos_senado)
listar_ufs_senado = _cached_query(queries.listar_ufs_senado)
listar_senadores = _cached_query(queries.listar_senadores)
listar_meses_disponiveis_senado = _cached_query(queries.listar_meses_disponiveis_senado)
get_findings_senado = _cached_query(queries.get_findings_senado)
listar_tipos_finding_senado = _cached_query(queries.listar_tipos_finding_senado)
get_despesas_mensal_senado = _cached_query(queries.get_despesas_mensal_senado)
get_despesas_por_categoria_senado = _cached_query(queries.get_despesas_por_categoria_senado)
get_despesas_detalhado_senado = _cached_query(queries.get_despesas_detalhado_senado)
get_ranking_gasto_senado = _cached_query(queries.get_ranking_gasto_senado)
get_perfil_senador = _cached_query(queries.get_perfil_senador)
