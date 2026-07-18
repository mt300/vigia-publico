"""Consultas de leitura sobre o banco - sem dependencia de Streamlit.

Compartilhado pelo dashboard local, pelo dashboard publico (dashboard/views.py)
e pela geracao de conteudo social (fase futura). Cada funcao recebe uma
`sqlite3.Connection` explicita e devolve um `pandas.DataFrame` (ou list/dict
simples), sem cache e sem UI - cache e responsabilidade de quem chama (ver
`dashboard/data.py`).
"""

from __future__ import annotations

import sqlite3

import pandas as pd


def _query(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> pd.DataFrame:
    return pd.read_sql_query(sql, conn, params=params)


def listar_partidos(conn: sqlite3.Connection) -> list[str]:
    df = _query(conn, "SELECT DISTINCT sigla_partido FROM deputados WHERE sigla_partido IS NOT NULL ORDER BY sigla_partido")
    return df["sigla_partido"].tolist()


def listar_ufs(conn: sqlite3.Connection) -> list[str]:
    df = _query(conn, "SELECT DISTINCT sigla_uf FROM deputados WHERE sigla_uf IS NOT NULL ORDER BY sigla_uf")
    return df["sigla_uf"].tolist()


def listar_deputados(conn: sqlite3.Connection, partidos: tuple[str, ...] = (), ufs: tuple[str, ...] = ()) -> pd.DataFrame:
    sql = "SELECT id, nome_eleitoral, sigla_partido, sigla_uf, situacao, url_foto, email FROM deputados WHERE 1=1"
    params: list = []
    if partidos:
        sql += f" AND sigla_partido IN ({','.join('?' * len(partidos))})"
        params += list(partidos)
    if ufs:
        sql += f" AND sigla_uf IN ({','.join('?' * len(ufs))})"
        params += list(ufs)
    sql += " ORDER BY nome_eleitoral"
    return _query(conn, sql, tuple(params))


def listar_meses_disponiveis(conn: sqlite3.Connection) -> list[str]:
    """Meses (YYYY-MM) com dado de despesa - usado pros filtros de periodo."""
    df = _query(conn, "SELECT DISTINCT printf('%04d-%02d', ano, mes) AS m FROM despesas ORDER BY m")
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


def get_findings(
    conn: sqlite3.Connection,
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
               f.tipo, f.severidade, f.descricao, f.dados_suporte, f.fonte_url, f.deputado_id
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
    return _query(conn, sql, tuple(params))


def listar_tipos_finding(conn: sqlite3.Connection) -> list[str]:
    return _query(conn, "SELECT DISTINCT tipo FROM findings ORDER BY tipo")["tipo"].tolist()


def get_despesas_mensal(
    conn: sqlite3.Connection,
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
    return _query(conn, sql, tuple([mes_inicio, mes_fim] + params))


def get_despesas_por_categoria(
    conn: sqlite3.Connection,
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
    return _query(conn, sql, tuple([mes_inicio, mes_fim] + params))


def get_despesas_detalhado(
    conn: sqlite3.Connection,
    mes_inicio: str,
    mes_fim: str,
    partidos: tuple[str, ...] = (),
    ufs: tuple[str, ...] = (),
    deputado_id: int | None = None,
    limite: int = 300,
) -> pd.DataFrame:
    """Despesas individuais (uma linha por nota/documento), nao agregadas -
    pra quem quer ver o detalhe por tras dos totais (fornecedor, data, valor,
    link pro documento). Ordenado pelas maiores primeiro e limitado
    (`limite`) porque sem filtro de deputado o resultado pode ter centenas
    de milhares de linhas - ver `views.py` pro aviso de que a lista pode
    estar truncada."""
    filtro, params = _filtro_deputados(partidos, ufs, deputado_id)
    sql = f"""
        SELECT d.nome_eleitoral, d.sigla_partido, d.sigla_uf, e.data_documento,
               e.tipo_despesa, e.nome_fornecedor, e.valor_liquido, e.url_documento
        FROM despesas e
        JOIN deputados d ON d.id = e.deputado_id
        WHERE printf('%04d-%02d', e.ano, e.mes) >= ? AND printf('%04d-%02d', e.ano, e.mes) <= ? {filtro}
        ORDER BY e.valor_liquido DESC
        LIMIT ?
    """
    return _query(conn, sql, tuple([mes_inicio, mes_fim] + params + [limite]))


def get_ranking_gasto(
    conn: sqlite3.Connection,
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
    return _query(conn, sql, tuple([mes_inicio, mes_fim] + params + [limite]))


def mes_proximo_de_eleicao_geral(mes: str) -> bool:
    """True se `mes` (YYYY-MM) esta nos 3 meses (ago/set/out) que antecedem
    uma eleicao geral (presidente/governador/senador/deputados - onde
    deputados federais concorrem a reeleicao), que no Brasil acontece em
    outubro de anos com resto 2 na divisao por 4 (2018, 2022, 2026, 2030...).
    Nao cobre eleicoes municipais (prefeito/vereador, deputados federais nao
    sao candidatos nelas)."""
    ano, m = (int(p) for p in mes.split("-"))
    return ano % 4 == 2 and m in (8, 9, 10)


def get_presenca_mensal(
    conn: sqlite3.Connection,
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
    df = _query(conn, sql, tuple(params + [mes_inicio, mes_fim]))
    df["taxa_presenca"] = df["total_votado"] / df["total_esperado"].replace(0, pd.NA)
    df["proximo_eleicao"] = df["mes"].apply(mes_proximo_de_eleicao_geral)
    return df


def get_perfil_deputado(conn: sqlite3.Connection, deputado_id: int) -> dict | None:
    df = _query(conn, "SELECT * FROM deputados WHERE id = ?", (deputado_id,))
    return df.iloc[0].to_dict() if not df.empty else None


def get_historico_deputado(conn: sqlite3.Connection, deputado_id: int) -> pd.DataFrame:
    return _query(
        conn,
        """
        SELECT h.data_hora, h.situacao, h.condicao_eleitoral, h.sigla_partido,
               h.descricao_status, l.id AS legislatura_id
        FROM deputado_historico h
        JOIN legislaturas l ON l.id = h.legislatura_id
        WHERE h.deputado_id = ? ORDER BY h.data_hora
        """,
        (deputado_id,),
    )


def get_redes_sociais(conn: sqlite3.Connection, deputado_id: int) -> pd.DataFrame:
    return _query(conn, "SELECT rede, url FROM deputado_redes_sociais WHERE deputado_id = ?", (deputado_id,))
