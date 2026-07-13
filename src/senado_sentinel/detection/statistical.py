"""Regras estatisticas de deteccao: outliers de gasto, faltas, troca de partido.

Cada funcao retorna uma lista de dicts prontos para `repository.insert_finding`
(tipo, severidade, descricao, dados_suporte, fonte_url), para o deputado e mes
de referencia dados.
"""

from __future__ import annotations

import bisect
import sqlite3

import pandas as pd

from senado_sentinel.config import FALTA_INJUSTIFICADA_TAXA_LIMIAR, GASTO_ZSCORE_LIMIAR

SITUACAO_LICENCA = "Licença"


def _severidade_por_zscore(zscore: float) -> str:
    if abs(zscore) >= GASTO_ZSCORE_LIMIAR * 1.6:
        return "alta"
    if abs(zscore) >= GASTO_ZSCORE_LIMIAR:
        return "media"
    return "baixa"


def detectar_outliers_gasto(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    """Compara o gasto do deputado por categoria no mes com seu proprio historico
    (media/desvio dos ultimos 24 meses na mesma categoria). Sinaliza z-score alto.
    """
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    historico = pd.read_sql_query(
        """
        SELECT deputado_id, tipo_despesa, ano, mes, SUM(valor_liquido) AS total
        FROM despesas
        WHERE (ano * 100 + mes) <= ? AND (ano * 100 + mes) > ?
        GROUP BY deputado_id, tipo_despesa, ano, mes
        """,
        conn,
        params=(ano * 100 + mes, (ano - 2) * 100 + mes),
    )
    if historico.empty:
        return []

    mes_atual = historico[(historico["ano"] == ano) & (historico["mes"] == mes)]
    anteriores = historico[~((historico["ano"] == ano) & (historico["mes"] == mes))]

    findings = []
    for (deputado_id, tipo_despesa), grupo_atual in mes_atual.groupby(["deputado_id", "tipo_despesa"]):
        base = anteriores[(anteriores["deputado_id"] == deputado_id) & (anteriores["tipo_despesa"] == tipo_despesa)]
        if len(base) < 3:
            continue  # historico curto demais para um z-score confiavel
        media, desvio = base["total"].mean(), base["total"].std(ddof=0)
        if desvio == 0:
            continue
        valor_atual = grupo_atual["total"].iloc[0]
        zscore = (valor_atual - media) / desvio
        # So gasto ACIMA do normal e sinalizado - o objetivo e detectar possivel
        # superfaturamento/compra suspeita, nao quedas de gasto (que nao indicam
        # irregularidade contra o interesse publico).
        if zscore >= GASTO_ZSCORE_LIMIAR:
            findings.append(
                {
                    "deputado_id": int(deputado_id),
                    "tipo": "GASTO_OUTLIER",
                    "severidade": _severidade_por_zscore(zscore),
                    "descricao": (
                        f"Gasto em '{tipo_despesa}' de R$ {valor_atual:,.2f} no mes, "
                        f"{zscore:.1f} desvios-padrao acima da media "
                        f"historica do proprio deputado nessa categoria (R$ {media:,.2f})."
                    ),
                    "dados_suporte": {
                        "tipo_despesa": tipo_despesa,
                        "valor_mes": float(valor_atual),
                        "media_historica": float(media),
                        "desvio_historico": float(desvio),
                        "zscore": float(zscore),
                    },
                }
            )
    return findings


def detectar_concentracao_fornecedor(conn: sqlite3.Connection, mes_referencia: str, limiar_pct: float = 0.6) -> list[dict]:
    """Sinaliza quando um unico fornecedor concentra uma fracao grande do gasto do mes.

    So considera fornecedores com total POSITIVO (estornos/glosas nao entram na
    conta - um estorno grande em outro fornecedor nao pode fazer o "principal"
    parecer mais de 100% do gasto). Exige pelo menos 3 fornecedores distintos
    no mes - com 1 ou 2 fornecedores, "100% concentrado" e trivial (nao havia
    com quem comparar) e nao e um sinal informativo.
    """
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    df = pd.read_sql_query(
        """
        SELECT deputado_id, nome_fornecedor, SUM(valor_liquido) AS total
        FROM despesas WHERE ano = ? AND mes = ?
        GROUP BY deputado_id, nome_fornecedor
        HAVING total > 0
        """,
        conn,
        params=(ano, mes),
    )
    if df.empty:
        return []

    findings = []
    totais_deputado = df.groupby("deputado_id")["total"].sum()
    contagem_fornecedores = df.groupby("deputado_id").size()
    for deputado_id, grupo in df.groupby("deputado_id"):
        if contagem_fornecedores[deputado_id] < 3:
            continue
        total_deputado = totais_deputado[deputado_id]
        top = grupo.sort_values("total", ascending=False).iloc[0]
        fracao = top["total"] / total_deputado
        if fracao >= limiar_pct:
            findings.append(
                {
                    "deputado_id": int(deputado_id),
                    "tipo": "FORNECEDOR_CONCENTRADO",
                    "severidade": "media" if fracao < 0.85 else "alta",
                    "descricao": (
                        f"{fracao:.0%} do gasto do mes (R$ {total_deputado:,.2f}) concentrado "
                        f"num unico fornecedor: {top['nome_fornecedor']}."
                    ),
                    "dados_suporte": {
                        "fornecedor": top["nome_fornecedor"],
                        "valor_fornecedor": float(top["total"]),
                        "total_mes": float(total_deputado),
                        "fracao": float(fracao),
                    },
                }
            )
    return findings


def _mapa_situacao_por_data(conn: sqlite3.Connection) -> dict[int, tuple[list[str], list[str]]]:
    """Para cada deputado, a timeline de situacao (Exercicio/Licenca/etc) ordenada
    por data - usado para descobrir qual era a situacao dele numa data especifica
    (a ultima mudanca de status registrada ate aquela data, inclusive).

    Retorna {deputado_id: (datas_ordenadas, situacoes_correspondentes)}, pronto
    para busca binaria (bisect) por data.
    """
    df = pd.read_sql_query(
        """
        SELECT deputado_id, substr(data_hora, 1, 10) AS data, situacao
        FROM deputado_historico
        WHERE data_hora IS NOT NULL
        ORDER BY deputado_id, data_hora
        """,
        conn,
    )
    mapa: dict[int, tuple[list[str], list[str]]] = {}
    for deputado_id, grupo in df.groupby("deputado_id"):
        mapa[deputado_id] = (grupo["data"].tolist(), grupo["situacao"].tolist())
    return mapa


def _situacao_na_data(mapa: dict[int, tuple[list[str], list[str]]], deputado_id: int, data: str) -> str | None:
    entrada = mapa.get(deputado_id)
    if not entrada:
        return None
    datas, situacoes = entrada
    idx = bisect.bisect_right(datas, data) - 1
    return situacoes[idx] if idx >= 0 else None


def detectar_faltas(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    """Taxa de ausencia SEM JUSTIFICATIVA (votacoes nominais do Plenario sem voto
    registrado, com o deputado fora de licenca oficial naquela data) no mes.

    A API nao expoe um campo formal de "motivo de ausencia" por votacao, entao
    a ausencia e inferida por exclusao (deputado nao aparece entre os votos de
    uma votacao). Duas correcoes sobre essa inferencia bruta:

    - So conta votacoes NOMINAIS (com pelo menos um voto individual
      registrado) no denominador - a maioria das votacoes do Plenario e
      simbolica/por unanimidade e a API nao devolve voto individual de
      ninguem nesses casos, o que inflaria a ausencia de todo mundo por igual.
    - Falta durante um periodo de "Licenca" oficial (registrado no historico
      do deputado - afastamento medico, maternidade, missao etc) NAO conta
      como ausencia sem justificativa; e contabilizada separadamente em
      `dados_suporte.faltas_licenca` para transparencia, mas nao entra na
      taxa que dispara o alerta. "Obstrucao" (tatica de plenario) ja aparece
      como um voto registrado normal e nao e afetada por essa distincao.
    """
    votacoes_mes = pd.read_sql_query(
        """
        SELECT DISTINCT v.id, v.data FROM votacoes v
        JOIN votos vo ON vo.votacao_id = v.id
        WHERE strftime('%Y-%m', v.data) = ?
        """,
        conn,
        params=(mes_referencia,),
    )
    if votacoes_mes.empty:
        return []
    total_votacoes_mes = len(votacoes_mes)

    deputados = pd.read_sql_query("SELECT id FROM deputados", conn)["id"].tolist()
    mapa_situacao = _mapa_situacao_por_data(conn)

    votos_mes = pd.read_sql_query(
        """
        SELECT deputado_id, votacao_id FROM votos
        WHERE votacao_id IN (SELECT id FROM votacoes WHERE strftime('%Y-%m', data) = ?)
        """,
        conn,
        params=(mes_referencia,),
    )
    votadas_por_deputado = votos_mes.groupby("deputado_id")["votacao_id"].apply(set).to_dict()

    findings = []
    for deputado_id in deputados:
        votadas = votadas_por_deputado.get(deputado_id, set())
        faltas_licenca = 0
        faltas_sem_justificativa = 0
        for votacao in votacoes_mes.itertuples():
            if votacao.id in votadas:
                continue
            situacao = _situacao_na_data(mapa_situacao, deputado_id, votacao.data)
            if situacao == SITUACAO_LICENCA:
                faltas_licenca += 1
            else:
                faltas_sem_justificativa += 1

        taxa_sem_justificativa = faltas_sem_justificativa / total_votacoes_mes
        if taxa_sem_justificativa >= FALTA_INJUSTIFICADA_TAXA_LIMIAR:
            complemento = f" (mais {faltas_licenca} falta(s) durante licenca oficial, nao contabilizada(s) aqui)." if faltas_licenca else "."
            findings.append(
                {
                    "deputado_id": int(deputado_id),
                    "tipo": "TAXA_AUSENCIA_ALTA",
                    "severidade": "alta" if taxa_sem_justificativa >= 0.6 else "media",
                    "descricao": (
                        f"Ausente sem licenca registrada (sem voto registrado) em {taxa_sem_justificativa:.0%} "
                        f"das {total_votacoes_mes} votacoes nominais do Plenario no mes" + complemento +
                        " O motivo especifico da ausencia nao esta disponivel na API - requer verificacao manual."
                    ),
                    "dados_suporte": {
                        "votacoes_no_mes": int(total_votacoes_mes),
                        "faltas_sem_justificativa": int(faltas_sem_justificativa),
                        "faltas_licenca": int(faltas_licenca),
                        "taxa_ausencia_sem_justificativa": float(taxa_sem_justificativa),
                    },
                }
            )
    return findings


def detectar_troca_partido(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    """Detecta mudanca de sigla_partido em deputado_historico dentro do mes de referencia."""
    df = pd.read_sql_query(
        """
        SELECT deputado_id, data_hora, sigla_partido
        FROM deputado_historico
        WHERE strftime('%Y-%m', data_hora) = ?
        ORDER BY deputado_id, data_hora
        """,
        conn,
        params=(mes_referencia,),
    )
    if df.empty:
        return []

    findings = []
    for deputado_id, grupo in df.groupby("deputado_id"):
        partidos = grupo["sigla_partido"].dropna().unique().tolist()
        if len(partidos) >= 2:
            findings.append(
                {
                    "deputado_id": int(deputado_id),
                    "tipo": "TROCA_PARTIDO",
                    "severidade": "baixa",
                    "descricao": f"Mudanca de partido registrada no mes: {' -> '.join(partidos)}.",
                    "dados_suporte": {"partidos": partidos},
                }
            )
    return findings


def rodar_regras_estatisticas(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    findings: list[dict] = []
    findings += detectar_outliers_gasto(conn, mes_referencia)
    findings += detectar_concentracao_fornecedor(conn, mes_referencia)
    findings += detectar_faltas(conn, mes_referencia)
    findings += detectar_troca_partido(conn, mes_referencia)
    return findings
