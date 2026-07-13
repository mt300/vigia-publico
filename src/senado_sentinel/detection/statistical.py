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


def detectar_outliers_gasto_vs_pares(conn: sqlite3.Connection, mes_referencia: str, min_pares: int = 5) -> list[dict]:
    """Compara o gasto do deputado por categoria no mes com a distribuicao de
    gasto de OUTROS deputados do mesmo partido e do mesmo estado (UF) na mesma
    categoria no mesmo mes - diferente de `detectar_outliers_gasto`, que
    compara com o proprio historico. Mais forte para deputados novos, que nao
    tem historico proprio longo o suficiente pro z-score individual.

    So compara contra grupos com pelo menos `min_pares` colegas com gasto na
    categoria naquele mes, pra evitar comparacao contra grupo pequeno demais
    (numero instavel com poucos pontos).
    """
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    df = pd.read_sql_query(
        """
        SELECT e.deputado_id, d.sigla_partido, d.sigla_uf, e.tipo_despesa, SUM(e.valor_liquido) AS total
        FROM despesas e JOIN deputados d ON d.id = e.deputado_id
        WHERE e.ano = ? AND e.mes = ?
        GROUP BY e.deputado_id, e.tipo_despesa
        """,
        conn,
        params=(ano, mes),
    )
    if df.empty:
        return []

    findings = []
    ja_sinalizado = set()  # (deputado_id, tipo_despesa) - evita duplicar se bater no limiar via partido E uf
    for grupo_tipo, coluna_grupo in (("partido", "sigla_partido"), ("estado", "sigla_uf")):
        for (grupo_valor, tipo_despesa), grupo_df in df.groupby([coluna_grupo, "tipo_despesa"]):
            if len(grupo_df) < min_pares + 1:
                continue
            for row in grupo_df.itertuples():
                chave = (row.deputado_id, tipo_despesa)
                if chave in ja_sinalizado:
                    continue
                pares = grupo_df.loc[grupo_df["deputado_id"] != row.deputado_id, "total"]
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
                            "deputado_id": int(row.deputado_id),
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
                        }
                    )
    return findings


CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO = (
    # Hospedagem gera falso positivo sistematico: hoteis costumam emitir uma
    # nota por diaria e processar/datar todas no checkout, entao uma estadia
    # de 3 noites legitima aparece como "3 notas identicas no mesmo dia" -
    # confirmado com dados reais (48 dos 52 achados antes desse ajuste eram
    # estadias de hotel com numeros de documento sequenciais, nao fracionamento).
    "HOSPEDAGEM ,EXCETO DO PARLAMENTAR NO DISTRITO FEDERAL.",
)


def detectar_valores_repetidos(conn: sqlite3.Connection, mes_referencia: str, min_repeticoes: int = 3, valor_minimo: float = 100.0) -> list[dict]:
    """Sinaliza quando o MESMO valor exato se repete varias vezes NO MESMO DIA
    para o mesmo deputado+fornecedor - padrao de fracionamento (dividir uma
    compra maior em varias notas menores no mesmo dia pra ficar abaixo de
    algum limite de auditoria/aprovacao).

    Exigir o MESMO DIA (nao so o mesmo mes) e essencial: despesas legitimas e
    rotineiras (abastecimento semanal, mensalidade de servico) naturalmente
    repetem o mesmo valor exato varias vezes no mes em DIAS diferentes - isso
    nao e fracionamento, e so um valor fixo recorrente.

    Hospedagem e excluida (ver `CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO`) por
    gerar falso positivo sistematico com estadias de varias noites.

    `valor_minimo` evita ruido de pequenas cobrancas (ex: taxas de poucos reais).
    """
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    placeholders = ",".join("?" * len(CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO))
    df = pd.read_sql_query(
        f"""
        SELECT deputado_id, nome_fornecedor, tipo_despesa, valor_liquido,
               substr(data_documento, 1, 10) AS data, COUNT(*) AS repeticoes
        FROM despesas
        WHERE ano = ? AND mes = ? AND valor_liquido >= ? AND data_documento IS NOT NULL
          AND tipo_despesa NOT IN ({placeholders})
        GROUP BY deputado_id, nome_fornecedor, valor_liquido, data
        HAVING repeticoes >= ?
        """,
        conn,
        params=(ano, mes, valor_minimo, *CATEGORIAS_EXCLUIDAS_VALOR_REPETIDO, min_repeticoes),
    )
    if df.empty:
        return []

    findings = []
    for row in df.itertuples():
        total = row.valor_liquido * row.repeticoes
        findings.append(
            {
                "deputado_id": int(row.deputado_id),
                "tipo": "VALOR_REPETIDO_SUSPEITO",
                "severidade": "alta" if row.repeticoes >= 4 else "media",
                "descricao": (
                    f"Mesmo valor de R$ {row.valor_liquido:,.2f} repetido {row.repeticoes}x no mesmo dia "
                    f"({row.data}) com o fornecedor '{row.nome_fornecedor}' em '{row.tipo_despesa}' "
                    f"(total R$ {total:,.2f}) - possivel fracionamento de compra."
                ),
                "dados_suporte": {
                    "fornecedor": row.nome_fornecedor,
                    "tipo_despesa": row.tipo_despesa,
                    "data": row.data,
                    "valor_unitario": float(row.valor_liquido),
                    "repeticoes": int(row.repeticoes),
                    "total": float(total),
                },
            }
        )
    return findings


def detectar_fornecedor_pouco_comum(
    conn: sqlite3.Connection, mes_referencia: str, max_deputados_historico: int = 1, valor_minimo: float = 15000.0
) -> list[dict]:
    """Fornecedor usado por POUQUISSIMOS deputados no historico completo (nao
    so nesse mes) e com valor ALTO nesse mes - diferente de
    `detectar_concentracao_fornecedor`, que so olha a fracao do gasto de UM
    deputado, sem considerar se o fornecedor e um grande prestador nacional
    ou um fornecedor de nicho.

    Limitacao importante, validada contra dados reais: a MAIORIA dos
    fornecedores da CEAP e naturalmente regional (posto de combustivel,
    imobiliaria/aluguel de escritorio, locadora de veiculos, grafica local -
    cada deputado usa fornecedores da propria base eleitoral), entao "usado
    por poucos deputados" e o normal, nao uma excecao. Isolar de verdade uma
    empresa "de fachada" exigiria dado externo (idade da empresa, quadro
    societario via Receita Federal - ver README). Sem isso, o limiar de
    valor default e propositalmente ALTO (`valor_minimo`) pra reduzir ruido
    de relacoes legitimas com fornecedores locais pequenos, focando em gasto
    concentrado e substancial com um fornecedor que praticamente mais
    ninguem usa.

    Usa CNPJ/CPF do fornecedor (nao o nome) como identidade, pra nao
    depender de variacoes de grafia do nome. A comparacao de popularidade e
    feita via JOIN em SQL (nao uma clausula IN com milhares de valores) para
    nao esbarrar no limite de variaveis do SQLite.
    """
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    gasto_mes = pd.read_sql_query(
        """
        WITH popularidade AS (
            SELECT cnpj_cpf_fornecedor, COUNT(DISTINCT deputado_id) AS n_deputados
            FROM despesas
            WHERE cnpj_cpf_fornecedor IS NOT NULL AND cnpj_cpf_fornecedor != ''
            GROUP BY cnpj_cpf_fornecedor
            HAVING n_deputados <= ?
        )
        SELECT e.deputado_id, e.cnpj_cpf_fornecedor, e.nome_fornecedor,
               GROUP_CONCAT(DISTINCT e.tipo_despesa) AS tipos_despesa,
               SUM(e.valor_liquido) AS total, p.n_deputados
        FROM despesas e
        JOIN popularidade p ON p.cnpj_cpf_fornecedor = e.cnpj_cpf_fornecedor
        WHERE e.ano = ? AND e.mes = ?
        GROUP BY e.deputado_id, e.cnpj_cpf_fornecedor
        HAVING total >= ?
        """,
        conn,
        params=(max_deputados_historico, ano, mes, valor_minimo),
    )
    if gasto_mes.empty:
        return []

    findings = []
    for row in gasto_mes.itertuples():
        findings.append(
            {
                "deputado_id": int(row.deputado_id),
                "tipo": "FORNECEDOR_POUCO_COMUM",
                "severidade": "alta" if row.n_deputados == 1 else "media",
                "descricao": (
                    f"Gasto de R$ {row.total:,.2f} em '{row.tipos_despesa}' com '{row.nome_fornecedor}', "
                    f"um fornecedor usado por apenas {row.n_deputados} deputado(s) em todo o historico "
                    f"registrado."
                ),
                "dados_suporte": {
                    "fornecedor": row.nome_fornecedor,
                    "cnpj_cpf_fornecedor": row.cnpj_cpf_fornecedor,
                    "tipos_despesa": row.tipos_despesa,
                    "valor_mes": float(row.total),
                    "n_deputados_historico": int(row.n_deputados),
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


def _meses_atras(mes_referencia: str, n: int) -> str:
    ano, mes = (int(p) for p in mes_referencia.split("-"))
    total = (ano * 12 + (mes - 1)) - n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def detectar_silencio_subito_discursos(
    conn: sqlite3.Connection, mes_referencia: str, meses_historico: int = 6, media_minima_historica: float = 1.0
) -> list[dict]:
    """Deputado que tinha um padrao REGULAR de discursos (media historica
    minima de `media_minima_historica`/mes nos ultimos `meses_historico`
    meses) e fica em silencio total (zero discursos) no mes de referencia.

    Nao sinaliza deputados que simplesmente nunca discursam muito - isso e
    normal pra boa parte do mandato e nao e, por si so, um sinal (ver
    escopo/limitacoes no README). O sinal e a QUEDA em relacao ao proprio
    padrao estabelecido, nao o silencio absoluto.
    """
    inicio_janela = _meses_atras(mes_referencia, meses_historico)
    historico = pd.read_sql_query(
        """
        SELECT deputado_id, COUNT(*) AS n
        FROM discursos
        WHERE strftime('%Y-%m', data_hora_inicio) >= ? AND strftime('%Y-%m', data_hora_inicio) < ?
        GROUP BY deputado_id
        """,
        conn,
        params=(inicio_janela, mes_referencia),
    )
    if historico.empty:
        return []
    historico["media_mensal"] = historico["n"] / meses_historico

    contagem_mes = pd.read_sql_query(
        "SELECT deputado_id, COUNT(*) AS n FROM discursos WHERE strftime('%Y-%m', data_hora_inicio) = ? GROUP BY deputado_id",
        conn,
        params=(mes_referencia,),
    ).set_index("deputado_id")["n"]

    findings = []
    for row in historico.itertuples():
        if row.media_mensal < media_minima_historica:
            continue
        atual = contagem_mes.get(row.deputado_id, 0)
        if atual == 0:
            findings.append(
                {
                    "deputado_id": int(row.deputado_id),
                    "tipo": "DISCURSOS_SILENCIO_SUBITO",
                    "severidade": "alta" if row.media_mensal >= 3 else "media",
                    "descricao": (
                        f"Nenhum discurso registrado no mes, apesar de uma media de "
                        f"{row.media_mensal:.1f} discursos/mes nos {meses_historico} meses anteriores "
                        f"({int(row.n)} no total)."
                    ),
                    "dados_suporte": {
                        "media_mensal_historica": float(row.media_mensal),
                        "total_periodo_anterior": int(row.n),
                        "meses_historico": meses_historico,
                    },
                }
            )
    return findings


def rodar_regras_estatisticas(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    findings: list[dict] = []
    findings += detectar_outliers_gasto(conn, mes_referencia)
    findings += detectar_outliers_gasto_vs_pares(conn, mes_referencia)
    findings += detectar_valores_repetidos(conn, mes_referencia)
    findings += detectar_fornecedor_pouco_comum(conn, mes_referencia)
    findings += detectar_concentracao_fornecedor(conn, mes_referencia)
    findings += detectar_faltas(conn, mes_referencia)
    findings += detectar_troca_partido(conn, mes_referencia)
    findings += detectar_silencio_subito_discursos(conn, mes_referencia)
    return findings
