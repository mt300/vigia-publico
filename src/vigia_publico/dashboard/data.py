"""Camada de cache do Streamlit sobre `analytics.queries`.

So orquestra conexao + `st.cache_data` - a logica de consulta em si vive em
`analytics/queries.py` (sem Streamlit), reaproveitada pelo dashboard local e
pelo publico. `use_db_path` deixa o entrypoint escolher o banco (local
gravavel vs snapshot publico read-only) sem tocar em secrets/env.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from vigia_publico.analytics import queries
from vigia_publico.config import DB_PATH

CACHE_TTL_SEGUNDOS = 300

_db_path: Path = DB_PATH


def use_db_path(path: Path) -> None:
    global _db_path
    _db_path = path


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{_db_path}?mode=ro", uri=True)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_partidos() -> list[str]:
    with _conn() as conn:
        return queries.listar_partidos(conn)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_ufs() -> list[str]:
    with _conn() as conn:
        return queries.listar_ufs(conn)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_deputados(partidos: tuple[str, ...] = (), ufs: tuple[str, ...] = ()) -> pd.DataFrame:
    with _conn() as conn:
        return queries.listar_deputados(conn, partidos, ufs)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_meses_disponiveis() -> list[str]:
    with _conn() as conn:
        return queries.listar_meses_disponiveis(conn)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_findings(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
    tipos: tuple[str, ...] = (),
    severidades: tuple[str, ...] = (),
) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_findings(conn, mes_inicio, mes_fim, partidos, ufs, deputado_id, tipos, severidades)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_tipos_finding() -> list[str]:
    with _conn() as conn:
        return queries.listar_tipos_finding(conn)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_despesas_mensal(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_despesas_mensal(conn, mes_inicio, mes_fim, partidos, ufs, deputado_id)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_despesas_por_categoria(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_despesas_por_categoria(conn, mes_inicio, mes_fim, partidos, ufs, deputado_id)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_ranking_gasto(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    limite: int = 20,
) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_ranking_gasto(conn, mes_inicio, mes_fim, partidos, ufs, limite)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_presenca_mensal(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_presenca_mensal(conn, mes_inicio, mes_fim, partidos, ufs, deputado_id)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_perfil_deputado(deputado_id: int) -> dict | None:
    with _conn() as conn:
        return queries.get_perfil_deputado(conn, deputado_id)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_historico_deputado(deputado_id: int) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_historico_deputado(conn, deputado_id)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_redes_sociais(deputado_id: int) -> pd.DataFrame:
    with _conn() as conn:
        return queries.get_redes_sociais(conn, deputado_id)
