"""Regras estatisticas de deteccao pro Senado - espelham as 5 regras
baseadas em despesa de `detection/statistical.py` (funcoes explicitas
separadas, mesmo padrao do projeto - nao um motor de regra generico),
reescritas contra `despesas_senadores`/`senadores`.

Cada funcao devolve dicts prontos pra `db.repository.insert_finding(...,
casa="senado")`, usando a chave `"senador_id"` (nao `"deputado_id"` - quem
monta a chamada de insert_finding e que faz a traducao, ver
`orchestrator.py`). Usam deliberadamente os MESMOS strings de `tipo` e as
MESMAS chaves de `dados_suporte` que as regras da Camara, pra
`detection/neutral_copy.py` funcionar sem nenhuma mudanca - a coluna `casa`
em `findings` ja distingue de onde veio.
"""

from __future__ import annotations

import sqlite3

import pandas as pd

from vigia_publico.config import GASTO_ZSCORE_LIMIAR, SENADO_ADM_API_BASE_URL


def _severidade_por_zscore(zscore: float) -> str:
    if abs(zscore) >= GASTO_ZSCORE_LIMIAR * 1.6:
        return "alta"
    if abs(zscore) >= GASTO_ZSCORE_LIMIAR:
        return "media"
    return "baixa"


def _fonte_despesas_senado(ano: int) -> str:
    """Diferente de `_fonte_despesas` da Camara (por deputado): o CEAPS
    devolve TODOS os senadores de um ano numa chamada so (confirmado no
    spike), entao o link e o mesmo pra qualquer senador daquele ano - nao
    da pra apontar so pro registro de um senador especifico na URL."""
    return f"{SENADO_ADM_API_BASE_URL}/senadores/despesas_ceaps/{ano}"


def detectar_outliers_gasto_senado(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    """Compara o gasto do senador por categoria no mes com seu proprio
    historico (media/desvio dos ultimos 24 meses na mesma categoria).
    Espelha `detection.statistical.detectar_outliers_gasto`."""
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    historico = pd.read_sql_query(
        """
        SELECT senador_id, tipo_despesa, ano, mes, SUM(valor_reembolsado) AS total
        FROM despesas_senadores
        WHERE (ano * 100 + mes) <= ? AND (ano * 100 + mes) > ?
        GROUP BY senador_id, tipo_despesa, ano, mes
        """,
        conn,
        params=(ano * 100 + mes, (ano - 2) * 100 + mes),
    )
    if historico.empty:
        return []

    mes_atual = historico[(historico["ano"] == ano) & (historico["mes"] == mes)]
    anteriores = historico[~((historico["ano"] == ano) & (historico["mes"] == mes))]

    findings = []
    for (senador_id, tipo_despesa), grupo_atual in mes_atual.groupby(["senador_id", "tipo_despesa"]):
        base = anteriores[(anteriores["senador_id"] == senador_id) & (anteriores["tipo_despesa"] == tipo_despesa)]
        if len(base) < 3:
            continue
        media, desvio = base["total"].mean(), base["total"].std(ddof=0)
        if desvio == 0:
            continue
        valor_atual = grupo_atual["total"].iloc[0]
        zscore = (valor_atual - media) / desvio
        if zscore >= GASTO_ZSCORE_LIMIAR:
            findings.append(
                {
                    "senador_id": int(senador_id),
                    "tipo": "GASTO_OUTLIER",
                    "severidade": _severidade_por_zscore(zscore),
                    "descricao": (
                        f"Gasto em '{tipo_despesa}' de R$ {valor_atual:,.2f} no mes, "
                        f"{zscore:.1f} desvios-padrao acima da media "
                        f"historica do proprio senador nessa categoria (R$ {media:,.2f})."
                    ),
                    "dados_suporte": {
                        "tipo_despesa": tipo_despesa,
                        "valor_mes": float(valor_atual),
                        "media_historica": float(media),
                        "desvio_historico": float(desvio),
                        "zscore": float(zscore),
                    },
                    "fonte_url": _fonte_despesas_senado(ano),
                }
            )
    return findings


def detectar_outliers_gasto_vs_pares_senado(conn: sqlite3.Connection, mes_referencia: str, min_pares: int = 3) -> list[dict]:
    """Compara o gasto do senador por categoria no mes com a distribuicao
    de gasto de OUTROS senadores do mesmo partido/UF. `min_pares=3` (menor
    que o default de 5 da Camara) porque o Senado tem so 81 membros -
    grupos por partido ficam bem menores. Espelha
    `detection.statistical.detectar_outliers_gasto_vs_pares`."""
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    df = pd.read_sql_query(
        """
        SELECT e.senador_id, s.sigla_partido, s.sigla_uf, e.tipo_despesa, SUM(e.valor_reembolsado) AS total
        FROM despesas_senadores e JOIN senadores s ON s.id = e.senador_id
        WHERE e.ano = ? AND e.mes = ?
        GROUP BY e.senador_id, e.tipo_despesa
        """,
        conn,
        params=(ano, mes),
    )
    if df.empty:
        return []

    findings = []
    ja_sinalizado = set()
    for grupo_tipo, coluna_grupo in (("partido", "sigla_partido"), ("estado", "sigla_uf")):
        for (grupo_valor, tipo_despesa), grupo_df in df.groupby([coluna_grupo, "tipo_despesa"]):
            if len(grupo_df) < min_pares + 1:
                continue
            for row in grupo_df.itertuples():
                chave = (row.senador_id, tipo_despesa)
                if chave in ja_sinalizado:
                    continue
                pares = grupo_df.loc[grupo_df["senador_id"] != row.senador_id, "total"]
                if len(pares) < min_pares:
                    continue
                media, desvio = pares.mean(), pares.std(ddof=0)
                if desvio == 0:
                    continue
                zscore = (row.total - media) / desvio
                if zscore >= GASTO_ZSCORE_LIMIAR:
                    ja_sinalizado.add(chave)
                    findings.append(
                        {
                            "senador_id": int(row.senador_id),
                            "tipo": "GASTO_OUTLIER_VS_PARES",
                            "severidade": _severidade_por_zscore(zscore),
                            "descricao": (
                                f"Gasto em '{tipo_despesa}' de R$ {row.total:,.2f} no mes, "
                                f"{zscore:.1f} desvios-padrao acima da media de {len(pares)} colegas "
                                f"de {grupo_tipo} ({grupo_valor}) na mesma categoria (R$ {media:,.2f})."
                            ),
                            "dados_suporte": {
                                "tipo_despesa": tipo_despesa,
                                "valor_mes": float(row.total),
                                "grupo_comparado": grupo_tipo,
                                "grupo_valor": grupo_valor,
                                "n_pares": int(len(pares)),
                                "media_pares": float(media),
                                "desvio_pares": float(desvio),
                                "zscore": float(zscore),
                            },
                            "fonte_url": _fonte_despesas_senado(ano),
                        }
                    )
    return findings


# CEAPS bundla "hospedagem" dentro de uma categoria maior
# ("Locomocao, hospedagem, alimentacao, combustiveis e lubrificantes") -
# mesmo risco de falso positivo que a Camara ja teve com estadias de varias
# noites emitindo notas identicas no checkout (ver
# CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO em detection/statistical.py). Nao e a
# mesma string da Camara (vocabulario proprio do CEAPS), por isso uma lista
# separada.
CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO_SENADO = (
    "Locomoção, hospedagem, alimentação, combustíveis e lubrificantes",
)


def detectar_valores_repetidos_senado(
    conn: sqlite3.Connection, mes_referencia: str, min_repeticoes: int = 3, valor_minimo: float = 100.0
) -> list[dict]:
    """Espelha `detection.statistical.detectar_valores_repetidos`."""
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    placeholders = ",".join("?" * len(CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO_SENADO))
    df = pd.read_sql_query(
        f"""
        SELECT senador_id, nome_fornecedor, tipo_despesa, valor_reembolsado,
               substr(data_documento, 1, 10) AS data, COUNT(*) AS repeticoes
        FROM despesas_senadores
        WHERE ano = ? AND mes = ? AND valor_reembolsado >= ? AND data_documento IS NOT NULL
          AND tipo_despesa NOT IN ({placeholders})
        GROUP BY senador_id, nome_fornecedor, valor_reembolsado, data
        HAVING repeticoes >= ?
        """,
        conn,
        params=(ano, mes, valor_minimo, *CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO_SENADO, min_repeticoes),
    )
    if df.empty:
        return []

    findings = []
    for row in df.itertuples():
        total = row.valor_reembolsado * row.repeticoes
        findings.append(
            {
                "senador_id": int(row.senador_id),
                "tipo": "VALOR_REPETIDO_SUSPEITO",
                "severidade": "alta" if row.repeticoes >= 4 else "media",
                "descricao": (
                    f"Mesmo valor de R$ {row.valor_reembolsado:,.2f} repetido {row.repeticoes}x no mesmo dia "
                    f"({row.data}) com o fornecedor '{row.nome_fornecedor}' em '{row.tipo_despesa}' "
                    f"(total R$ {total:,.2f}) - possivel fracionamento de compra."
                ),
                "dados_suporte": {
                    "fornecedor": row.nome_fornecedor,
                    "tipo_despesa": row.tipo_despesa,
                    "data": row.data,
                    "valor_unitario": float(row.valor_reembolsado),
                    "repeticoes": int(row.repeticoes),
                    "total": float(total),
                },
                "fonte_url": _fonte_despesas_senado(ano),
            }
        )
    return findings


def detectar_fornecedor_pouco_comum_senado(
    conn: sqlite3.Connection, mes_referencia: str, max_senadores_historico: int = 1, valor_minimo: float = 15000.0
) -> list[dict]:
    """Espelha `detection.statistical.detectar_fornecedor_pouco_comum`."""
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    gasto_mes = pd.read_sql_query(
        """
        WITH popularidade AS (
            SELECT cnpj_cpf_fornecedor, COUNT(DISTINCT senador_id) AS n_senadores
            FROM despesas_senadores
            WHERE cnpj_cpf_fornecedor IS NOT NULL AND cnpj_cpf_fornecedor != ''
            GROUP BY cnpj_cpf_fornecedor
            HAVING n_senadores <= ?
        )
        SELECT e.senador_id, e.cnpj_cpf_fornecedor, e.nome_fornecedor,
               GROUP_CONCAT(DISTINCT e.tipo_despesa) AS tipos_despesa,
               SUM(e.valor_reembolsado) AS total, p.n_senadores
        FROM despesas_senadores e
        JOIN popularidade p ON p.cnpj_cpf_fornecedor = e.cnpj_cpf_fornecedor
        WHERE e.ano = ? AND e.mes = ?
        GROUP BY e.senador_id, e.cnpj_cpf_fornecedor
        HAVING total >= ?
        """,
        conn,
        params=(max_senadores_historico, ano, mes, valor_minimo),
    )
    if gasto_mes.empty:
        return []

    findings = []
    for row in gasto_mes.itertuples():
        findings.append(
            {
                "senador_id": int(row.senador_id),
                "tipo": "FORNECEDOR_POUCO_COMUM",
                "severidade": "alta" if row.n_senadores == 1 else "media",
                "descricao": (
                    f"Gasto de R$ {row.total:,.2f} em '{row.tipos_despesa}' com '{row.nome_fornecedor}', "
                    f"um fornecedor usado por apenas {row.n_senadores} senador(es) em todo o historico "
                    f"registrado."
                ),
                "dados_suporte": {
                    "fornecedor": row.nome_fornecedor,
                    "cnpj_cpf_fornecedor": row.cnpj_cpf_fornecedor,
                    "tipos_despesa": row.tipos_despesa,
                    "valor_mes": float(row.total),
                    "n_deputados_historico": int(row.n_senadores),
                },
                "fonte_url": _fonte_despesas_senado(ano),
            }
        )
    return findings


def detectar_concentracao_fornecedor_senado(conn: sqlite3.Connection, mes_referencia: str, limiar_pct: float = 0.6) -> list[dict]:
    """Espelha `detection.statistical.detectar_concentracao_fornecedor`."""
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    df = pd.read_sql_query(
        """
        SELECT senador_id, nome_fornecedor, SUM(valor_reembolsado) AS total
        FROM despesas_senadores WHERE ano = ? AND mes = ?
        GROUP BY senador_id, nome_fornecedor
        HAVING total > 0
        """,
        conn,
        params=(ano, mes),
    )
    if df.empty:
        return []

    findings = []
    totais_senador = df.groupby("senador_id")["total"].sum()
    contagem_fornecedores = df.groupby("senador_id").size()
    for senador_id, grupo in df.groupby("senador_id"):
        if contagem_fornecedores[senador_id] < 3:
            continue
        total_senador = totais_senador[senador_id]
        top = grupo.sort_values("total", ascending=False).iloc[0]
        fracao = top["total"] / total_senador
        if fracao >= limiar_pct:
            findings.append(
                {
                    "senador_id": int(senador_id),
                    "tipo": "FORNECEDOR_CONCENTRADO",
                    "severidade": "media" if fracao < 0.85 else "alta",
                    "descricao": (
                        f"{fracao:.0%} do gasto do mes (R$ {total_senador:,.2f}) concentrado "
                        f"num unico fornecedor: {top['nome_fornecedor']}."
                    ),
                    "dados_suporte": {
                        "fornecedor": top["nome_fornecedor"],
                        "valor_fornecedor": float(top["total"]),
                        "total_mes": float(total_senador),
                        "fracao": float(fracao),
                    },
                    "fonte_url": _fonte_despesas_senado(ano),
                }
            )
    return findings


def rodar_regras_estatisticas_senado(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    findings: list[dict] = []
    findings += detectar_outliers_gasto_senado(conn, mes_referencia)
    findings += detectar_outliers_gasto_vs_pares_senado(conn, mes_referencia)
    findings += detectar_valores_repetidos_senado(conn, mes_referencia)
    findings += detectar_fornecedor_pouco_comum_senado(conn, mes_referencia)
    findings += detectar_concentracao_fornecedor_senado(conn, mes_referencia)
    return findings
