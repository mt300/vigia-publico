"""Camada de acesso a dados do dashboard - consultas com cache do Streamlit.

Cada funcao abre sua propria conexao sqlite (leitura, barata) e devolve um
pandas.DataFrame ja filtrado, pronto pra tabela/grafico. `st.cache_data`
evita reconsultar o banco a cada interacao de filtro na mesma sessao.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from senado_sentinel.config import DB_PATH

CACHE_TTL_SEGUNDOS = 300


def _conn() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


def _query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with _conn() as conn:
        return pd.read_sql_query(sql, conn, params=params)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_partidos() -> list[str]:
    df = _query("SELECT DISTINCT sigla_partido FROM deputados WHERE sigla_partido IS NOT NULL ORDER BY sigla_partido")
    return df["sigla_partido"].tolist()


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_ufs() -> list[str]:
    df = _query("SELECT DISTINCT sigla_uf FROM deputados WHERE sigla_uf IS NOT NULL ORDER BY sigla_uf")
    return df["sigla_uf"].tolist()


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_deputados(partidos: tuple[str, ...] = (), ufs: tuple[str, ...] = ()) -> pd.DataFrame:
    sql = "SELECT id, nome_eleitoral, sigla_partido, sigla_uf, situacao, url_foto, email FROM deputados WHERE 1=1"
    params: list = []
    if partidos:
        sql += f" AND sigla_partido IN ({','.join('?' * len(partidos))})"
        params += list(partidos)
    if ufs:
        sql += f" AND sigla_uf IN ({','.join('?' * len(ufs))})"
        params += list(ufs)
    sql += " ORDER BY nome_eleitoral"
    return _query(sql, tuple(params))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_meses_disponiveis() -> list[str]:
    """Meses (YYYY-MM) com dado de despesa - usado pros filtros de periodo."""
    df = _query(
        "SELECT DISTINCT printf('%04d-%02d', ano, mes) AS m FROM despesas ORDER BY m"
    )
    return df["m"].tolist()


def _filtro_deputados(partidos: tuple[str, ...], ufs: tuple[str, ...], deputado_id: int | None) -> tuple[str, list]:
    clausulas, params = [], []
    if deputado_id:
        clausulas.append("d.id = ?")
        params.append(deputado_id)
    if partidos:
        clausulas.append(f"d.sigla_partido IN ({','.join('?' * len(partidos))})")
        params += list(partidos)
    if ufs:
        clausulas.append(f"d.sigla_uf IN ({','.join('?' * len(ufs))})")
        params += list(ufs)
    return (" AND " + " AND ".join(clausulas)) if clausulas else "", params


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
    filtro, params = _filtro_deputados(partidos, ufs, deputado_id)
    sql = f"""
        SELECT f.mes_referencia, d.nome_eleitoral, d.sigla_partido, d.sigla_uf,
               f.tipo, f.severidade, f.descricao, f.fonte_url, f.deputado_id
        FROM findings f
        JOIN deputados d ON d.id = f.deputado_id
        WHERE f.mes_referencia >= ? AND f.mes_referencia <= ? {filtro}
    """
    params = [mes_inicio, mes_fim] + params
    if tipos:
        sql += f" AND f.tipo IN ({','.join('?' * len(tipos))})"
        params += list(tipos)
    if severidades:
        sql += f" AND f.severidade IN ({','.join('?' * len(severidades))})"
        params += list(severidades)
    sql += " ORDER BY f.mes_referencia DESC, f.severidade"
    return _query(sql, tuple(params))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def listar_tipos_finding() -> list[str]:
    return _query("SELECT DISTINCT tipo FROM findings ORDER BY tipo")["tipo"].tolist()


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_despesas_mensal(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
) -> pd.DataFrame:
    """Total de despesa (valor_liquido) por mes, agregado no conjunto filtrado."""
    filtro, params = _filtro_deputados(partidos, ufs, deputado_id)
    sql = f"""
        SELECT printf('%04d-%02d', e.ano, e.mes) AS mes, SUM(e.valor_liquido) AS total
        FROM despesas e
        JOIN deputados d ON d.id = e.deputado_id
        WHERE printf('%04d-%02d', e.ano, e.mes) >= ? AND printf('%04d-%02d', e.ano, e.mes) <= ? {filtro}
        GROUP BY mes ORDER BY mes
    """
    return _query(sql, tuple([mes_inicio, mes_fim] + params))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_despesas_por_categoria(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
) -> pd.DataFrame:
    filtro, params = _filtro_deputados(partidos, ufs, deputado_id)
    sql = f"""
        SELECT e.tipo_despesa, SUM(e.valor_liquido) AS total
        FROM despesas e
        JOIN deputados d ON d.id = e.deputado_id
        WHERE printf('%04d-%02d', e.ano, e.mes) >= ? AND printf('%04d-%02d', e.ano, e.mes) <= ? {filtro}
        GROUP BY e.tipo_despesa ORDER BY total DESC
    """
    return _query(sql, tuple([mes_inicio, mes_fim] + params))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_ranking_gasto(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    limite: int = 20,
) -> pd.DataFrame:
    filtro, params = _filtro_deputados(partidos, ufs, None)
    sql = f"""
        SELECT d.id, d.nome_eleitoral, d.sigla_partido, d.sigla_uf, SUM(e.valor_liquido) AS total
        FROM despesas e
        JOIN deputados d ON d.id = e.deputado_id
        WHERE printf('%04d-%02d', e.ano, e.mes) >= ? AND printf('%04d-%02d', e.ano, e.mes) <= ? {filtro}
        GROUP BY d.id ORDER BY total DESC LIMIT ?
    """
    return _query(sql, tuple([mes_inicio, mes_fim] + params + [limite]))


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_presenca_mensal(
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
) -> pd.DataFrame:
    """Taxa de presenca por mes = votos registrados / votacoes NOMINAIS do mes,
    agregado no conjunto filtrado de deputados. So conta votacoes nominais
    (com pelo menos 1 voto individual) - ver detection/statistical.py para o
    motivo (votacoes simbolicas nao tem voto de ninguem e nao devem contar
    como "falta")."""
    filtro, params = _filtro_deputados(partidos, ufs, deputado_id)
    sql = f"""
        WITH nominais AS (
            SELECT DISTINCT v.id, strftime('%Y-%m', v.data) AS mes
            FROM votacoes v JOIN votos vo ON vo.votacao_id = v.id
        ),
        deputados_filtrados AS (
            SELECT d.id FROM deputados d WHERE 1=1 {filtro}
        )
        SELECT n.mes,
               COUNT(DISTINCT n.id) * (SELECT COUNT(*) FROM deputados_filtrados) AS total_esperado,
               COUNT(vo.votacao_id) AS total_votado
        FROM nominais n
        CROSS JOIN deputados_filtrados df
        LEFT JOIN votos vo ON vo.votacao_id = n.id AND vo.deputado_id = df.id
        WHERE n.mes >= ? AND n.mes <= ?
        GROUP BY n.mes ORDER BY n.mes
    """
    df = _query(sql, tuple(params + [mes_inicio, mes_fim]))
    df["taxa_presenca"] = df["total_votado"] / df["total_esperado"].replace(0, pd.NA)
    df["proximo_eleicao"] = df["mes"].apply(mes_proximo_de_eleicao_geral)
    return df


def mes_proximo_de_eleicao_geral(mes: str) -> bool:
    """True se `mes` (YYYY-MM) esta nos 3 meses (ago/set/out) que antecedem
    uma eleicao geral (presidente/governador/senador/deputados - onde
    deputados federais concorrem a reeleicao), que no Brasil acontece em
    outubro de anos com resto 2 na divisao por 4 (2018, 2022, 2026, 2030...).
    Nao cobre eleicoes municipais (prefeito/vereador, deputados federais nao
    sao candidatos nelas)."""
    ano, m = (int(p) for p in mes.split("-"))
    return ano % 4 == 2 and m in (8, 9, 10)


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_perfil_deputado(deputado_id: int) -> dict | None:
    df = _query("SELECT * FROM deputados WHERE id = ?", (deputado_id,))
    return df.iloc[0].to_dict() if not df.empty else None


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_historico_deputado(deputado_id: int) -> pd.DataFrame:
    return _query(
        """
        SELECT h.data_hora, h.situacao, h.condicao_eleitoral, h.sigla_partido,
               h.descricao_status, l.id AS legislatura_id
        FROM deputado_historico h
        JOIN legislaturas l ON l.id = h.legislatura_id
        WHERE h.deputado_id = ? ORDER BY h.data_hora
        """,
        (deputado_id,),
    )


@st.cache_data(ttl=CACHE_TTL_SEGUNDOS)
def get_redes_sociais(deputado_id: int) -> pd.DataFrame:
    return _query("SELECT rede, url FROM deputado_redes_sociais WHERE deputado_id = ?", (deputado_id,))
