from senado_sentinel.detection.statistical import (
    detectar_baixa_atividade_geral,
    detectar_concentracao_fornecedor,
    detectar_faltas,
    detectar_fornecedor_pouco_comum,
    detectar_mudanca_alinhamento_voto,
    detectar_mudanca_foco_tematico,
    detectar_outliers_gasto,
    detectar_outliers_gasto_vs_pares,
    detectar_silencio_subito_discursos,
    detectar_troca_partido,
    detectar_valores_repetidos,
)


def _add_deputado(conn, dep_id, nome="Teste", partido=None, uf=None):
    conn.execute(
        "INSERT INTO deputados (id, nome_eleitoral, sigla_partido, sigla_uf) VALUES (?, ?, ?, ?)",
        (dep_id, nome, partido, uf),
    )


def _add_despesa(conn, dep_id, ano, mes, tipo, valor, fornecedor="Fornecedor X", doc=None, data_documento=None, cnpj=None):
    uid = f"{dep_id}-{ano}-{mes}-{tipo}-{fornecedor}-{valor}"
    if doc is not None:
        uid += f"-{doc}"
    data_documento = data_documento or f"{ano:04d}-{mes:02d}-01"
    conn.execute(
        """
        INSERT INTO despesas (uid, deputado_id, ano, mes, tipo_despesa, nome_fornecedor, valor_liquido, data_documento, cnpj_cpf_fornecedor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (uid, dep_id, ano, mes, tipo, fornecedor, valor, data_documento, cnpj),
    )


def test_detectar_outliers_gasto_sinaliza_valor_muito_acima_da_media(conn):
    _add_deputado(conn, 1)
    # 6 meses de historico estavel em ~1000
    for mes in range(1, 7):
        _add_despesa(conn, 1, 2024, mes, "COMBUSTIVEIS", 1000 + mes)
    # mes de referencia com gasto muito acima do padrao
    _add_despesa(conn, 1, 2024, 7, "COMBUSTIVEIS", 50000)
    conn.commit()

    findings = detectar_outliers_gasto(conn, "2024-07")

    assert len(findings) == 1
    assert findings[0]["tipo"] == "GASTO_OUTLIER"
    assert findings[0]["deputado_id"] == 1
    assert findings[0]["severidade"] in {"media", "alta"}


def test_detectar_outliers_gasto_nao_sinaliza_gasto_muito_abaixo_da_media(conn):
    """So gasto ACIMA do normal e sinalizado - queda de gasto nao e uma compra
    suspeita, e a maioria dos achados de producao antes dessa mudanca eram
    justamente quedas (152 de 222), o que nao fazia sentido para o objetivo
    do relatorio (detectar possivel superfaturamento)."""
    _add_deputado(conn, 1)
    for mes in range(1, 7):
        _add_despesa(conn, 1, 2024, mes, "COMBUSTIVEIS", 10000)
    _add_despesa(conn, 1, 2024, 7, "COMBUSTIVEIS", 100)
    conn.commit()

    findings = detectar_outliers_gasto(conn, "2024-07")
    assert findings == []


def test_detectar_outliers_gasto_nao_sinaliza_gasto_estavel(conn):
    _add_deputado(conn, 1)
    for mes in range(1, 8):
        _add_despesa(conn, 1, 2024, mes, "COMBUSTIVEIS", 1000)
    conn.commit()

    findings = detectar_outliers_gasto(conn, "2024-07")
    assert findings == []


def test_detectar_outliers_gasto_vs_pares_sinaliza_muito_acima_do_partido(conn):
    """Deputado novo (sem historico proprio) que gasta muito mais que os
    colegas de partido na mesma categoria e no mesmo mes - nao pega no
    z-score individual (precisa de historico), mas pega na comparacao com
    pares, que e o ponto dessa regra."""
    for i in range(1, 6):
        _add_deputado(conn, i, partido="PXX", uf="SP")
        _add_despesa(conn, i, 2024, 7, "COMBUSTIVEIS", 1000 + i * 10)
    _add_deputado(conn, 99, partido="PXX", uf="RJ")
    _add_despesa(conn, 99, 2024, 7, "COMBUSTIVEIS", 20000)
    conn.commit()

    findings = detectar_outliers_gasto_vs_pares(conn, "2024-07", min_pares=5)

    ids_sinalizados = {f["deputado_id"] for f in findings}
    assert 99 in ids_sinalizados
    assert not ({1, 2, 3, 4, 5} & ids_sinalizados)
    finding = next(f for f in findings if f["deputado_id"] == 99)
    assert finding["tipo"] == "GASTO_OUTLIER_VS_PARES"
    assert finding["dados_suporte"]["n_pares"] == 5


def test_detectar_outliers_gasto_vs_pares_ignora_grupo_pequeno_demais(conn):
    """Com menos colegas que min_pares, a comparacao nao e confiavel - nao
    deveria sinalizar nada."""
    for i in range(1, 3):
        _add_deputado(conn, i, partido="PXX", uf="SP")
        _add_despesa(conn, i, 2024, 7, "COMBUSTIVEIS", 1000)
    _add_deputado(conn, 99, partido="PXX", uf="RJ")
    _add_despesa(conn, 99, 2024, 7, "COMBUSTIVEIS", 20000)
    conn.commit()

    findings = detectar_outliers_gasto_vs_pares(conn, "2024-07", min_pares=5)
    assert findings == []


def test_detectar_valores_repetidos_sinaliza_fracionamento(conn):
    _add_deputado(conn, 1)
    for i in range(4):
        _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 999.90, fornecedor="Fornecedor Suspeito", doc=i)
    conn.commit()

    findings = detectar_valores_repetidos(conn, "2024-03", min_repeticoes=3)

    assert len(findings) == 1
    assert findings[0]["tipo"] == "VALOR_REPETIDO_SUSPEITO"
    assert findings[0]["dados_suporte"]["repeticoes"] == 4
    assert findings[0]["dados_suporte"]["total"] == 999.90 * 4


def test_detectar_valores_repetidos_ignora_hospedagem(conn):
    """Regressao: descoberto com dados reais de producao - hoteis costumam
    emitir uma nota por diaria, todas processadas/datadas no checkout, entao
    uma estadia legitima de varias noites aparece como 'N notas identicas no
    mesmo dia'. Confirmado com numeros de documento sequenciais nos dados
    reais (nao e fracionamento, e cobranca normal de hospedagem)."""
    _add_deputado(conn, 1)
    for i in range(3):
        _add_despesa(
            conn, 1, 2024, 3, "HOSPEDAGEM ,EXCETO DO PARLAMENTAR NO DISTRITO FEDERAL.",
            538.0, fornecedor="Hotel Exemplo", doc=i,
        )
    conn.commit()

    findings = detectar_valores_repetidos(conn, "2024-03", min_repeticoes=3)
    assert findings == []


def test_detectar_valores_repetidos_ignora_poucas_repeticoes(conn):
    _add_deputado(conn, 1)
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 999.90, fornecedor="Fornecedor Normal", doc=1)
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 999.90, fornecedor="Fornecedor Normal", doc=2)
    conn.commit()

    findings = detectar_valores_repetidos(conn, "2024-03", min_repeticoes=3)
    assert findings == []


def test_detectar_valores_repetidos_ignora_valores_pequenos(conn):
    _add_deputado(conn, 1)
    for i in range(5):
        _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 10.0, fornecedor="Fornecedor Barato", doc=i)
    conn.commit()

    findings = detectar_valores_repetidos(conn, "2024-03", min_repeticoes=3, valor_minimo=100.0)
    assert findings == []


def test_detectar_valores_repetidos_ignora_repeticoes_em_dias_diferentes(conn):
    """Regressao: descoberto com dados reais de producao - abastecimento
    semanal de combustivel no mesmo posto pelo mesmo valor exato (ex: sempre
    R$150) em datas DIFERENTES nao e fracionamento, e so um valor recorrente
    legitimo. So repeticao no MESMO DIA e um sinal especifico o suficiente."""
    _add_deputado(conn, 1)
    for dia in (11, 15, 27):
        _add_despesa(
            conn, 1, 2024, 3, "COMBUSTIVEIS", 150.0, fornecedor="Posto Exemplo",
            doc=dia, data_documento=f"2024-03-{dia:02d}",
        )
    conn.commit()

    findings = detectar_valores_repetidos(conn, "2024-03", min_repeticoes=3, valor_minimo=100.0)
    assert findings == []


def test_detectar_concentracao_fornecedor(conn):
    _add_deputado(conn, 1)
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 8000, fornecedor="Unico Fornecedor Ltda")
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 1000, fornecedor="Outro Fornecedor")
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 1000, fornecedor="Terceiro Fornecedor")
    conn.commit()

    findings = detectar_concentracao_fornecedor(conn, "2024-03", limiar_pct=0.6)

    assert len(findings) == 1
    assert findings[0]["tipo"] == "FORNECEDOR_CONCENTRADO"
    assert findings[0]["dados_suporte"]["fornecedor"] == "Unico Fornecedor Ltda"


def test_detectar_concentracao_fornecedor_ignora_menos_de_tres_fornecedores(conn):
    """Com so 1-2 fornecedores no mes, '100% concentrado' e trivial (nao havia
    com quem comparar) - nao deveria ser sinalizado como um padrao suspeito."""
    _add_deputado(conn, 1)
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 5000, fornecedor="Unico Fornecedor Ltda")
    conn.commit()

    findings = detectar_concentracao_fornecedor(conn, "2024-03", limiar_pct=0.6)
    assert findings == []


def test_detectar_concentracao_fornecedor_ignora_estornos_negativos(conn):
    """Regressao: um estorno grande (valor negativo) em outro fornecedor nao
    pode fazer o fornecedor principal parecer >100% do gasto do mes."""
    _add_deputado(conn, 1)
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 5000, fornecedor="Fornecedor A")
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 1000, fornecedor="Fornecedor B")
    _add_despesa(conn, 1, 2024, 3, "MANUTENCAO", 1000, fornecedor="Fornecedor C")
    _add_despesa(conn, 1, 2024, 3, "PASSAGEM AEREA", -2000, fornecedor="Fornecedor D (estorno)")
    conn.commit()

    findings = detectar_concentracao_fornecedor(conn, "2024-03", limiar_pct=0.6)
    assert len(findings) == 1
    assert findings[0]["dados_suporte"]["fracao"] <= 1.0


def test_detectar_troca_partido(conn):
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    _add_deputado(conn, 1)
    conn.commit()
    conn.execute(
        "INSERT INTO deputado_historico (deputado_id, legislatura_id, data_hora, sigla_partido) VALUES (1, 57, '2024-03-01T00:00', 'PXX')"
    )
    conn.execute(
        "INSERT INTO deputado_historico (deputado_id, legislatura_id, data_hora, sigla_partido) VALUES (1, 57, '2024-03-15T00:00', 'PYY')"
    )
    conn.commit()

    findings = detectar_troca_partido(conn, "2024-03")

    assert len(findings) == 1
    assert findings[0]["tipo"] == "TROCA_PARTIDO"
    assert findings[0]["dados_suporte"]["partidos"] == ["PXX", "PYY"]


def _add_votacao(conn, votacao_id, data):
    conn.execute("INSERT INTO votacoes (id, data) VALUES (?, ?)", (votacao_id, data))


def _add_voto(conn, votacao_id, dep_id, voto="Sim"):
    conn.execute(
        "INSERT INTO votos (votacao_id, deputado_id, voto) VALUES (?, ?, ?)",
        (votacao_id, dep_id, voto),
    )


def test_detectar_faltas_ignora_votacoes_simbolicas_sem_voto_individual(conn):
    """Regressao: uma votacao simbolica/unanime nao tem NENHUM voto individual
    registrado pela API (nem para quem esteve presente). Contar essas votacoes
    no denominador da taxa de ausencia inflava a "ausencia" de TODO MUNDO por
    igual - descoberto porque um teste real com dados de producao sinalizou
    512 de 512 deputados como "alta ausencia" no mesmo mes, o que era
    obviamente um falso positivo sistemico, nao um achado real."""
    _add_deputado(conn, 1)
    _add_deputado(conn, 2)
    conn.commit()

    # 2 votacoes simbolicas no mes (ninguem tem voto individual registrado)
    _add_votacao(conn, "sym-1", "2026-06-05")
    _add_votacao(conn, "sym-2", "2026-06-10")
    # 1 votacao nominal, onde so o deputado 1 votou (deputado 2 realmente ausente)
    _add_votacao(conn, "nom-1", "2026-06-15")
    _add_voto(conn, "nom-1", 1)
    conn.commit()

    findings = detectar_faltas(conn, "2026-06")

    # deputado 1 votou na unica votacao nominal -> 0% de ausencia, nao deveria aparecer
    ids_com_finding = {f["deputado_id"] for f in findings}
    assert 1 not in ids_com_finding
    # deputado 2 nao votou na unica votacao nominal -> 100% de ausencia (de 1 votacao, nao 3)
    assert 2 in ids_com_finding
    finding_dep2 = next(f for f in findings if f["deputado_id"] == 2)
    assert finding_dep2["dados_suporte"]["votacoes_no_mes"] == 1


def _add_historico(conn, dep_id, legislatura_id, data_hora, situacao):
    conn.execute(
        "INSERT INTO deputado_historico (deputado_id, legislatura_id, data_hora, situacao) VALUES (?, ?, ?, ?)",
        (dep_id, legislatura_id, data_hora, situacao),
    )


def test_detectar_faltas_nao_conta_ausencia_durante_licenca(conn):
    """Falta durante um periodo de Licenca oficial (afastamento medico,
    maternidade, missao etc) nao e uma ausencia suspeita - nao deve entrar na
    taxa que dispara o alerta, mas deve ficar registrada separadamente em
    dados_suporte para transparencia."""
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    _add_deputado(conn, 1)
    _add_deputado(conn, 999)
    conn.commit()
    # entra de licenca em 1/jun, sem data de retorno registrada ainda
    _add_historico(conn, 1, 57, "2023-02-01T00:00", "Exercício")
    _add_historico(conn, 1, 57, "2026-06-01T00:00", "Licença")
    conn.commit()

    # 5 votacoes nominais no mes, o deputado nao vota em nenhuma (esta de licenca)
    for i in range(5):
        votacao_id = f"nom-{i}"
        _add_votacao(conn, votacao_id, f"2026-06-{10+i:02d}")
        _add_voto(conn, votacao_id, 999)  # outro deputado qualquer vota, torna a votacao "nominal"
    conn.commit()

    findings = detectar_faltas(conn, "2026-06")

    # em licenca o mes inteiro -> nao deve gerar alerta de ausencia sem justificativa
    assert not any(f["deputado_id"] == 1 for f in findings)


def test_detectar_faltas_diferencia_licenca_de_sem_justificativa(conn):
    """Deputado que falta PARTE do mes em licenca e parte SEM licenca - so a
    parte sem licenca conta pra taxa que dispara o alerta."""
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    _add_deputado(conn, 1)
    _add_deputado(conn, 999)
    conn.commit()
    _add_historico(conn, 1, 57, "2023-02-01T00:00", "Exercício")
    _add_historico(conn, 1, 57, "2026-06-01T00:00", "Licença")
    _add_historico(conn, 1, 57, "2026-06-15T00:00", "Exercício")  # volta da licenca no meio do mes
    conn.commit()

    # 2 votacoes durante a licenca (dias 5, 10) + 3 depois que voltou (dias 20, 21, 22), todas perdidas
    for dia, votacao_id in [(5, "v1"), (10, "v2"), (20, "v3"), (21, "v4"), (22, "v5")]:
        _add_votacao(conn, votacao_id, f"2026-06-{dia:02d}")
        _add_voto(conn, votacao_id, 999)
    conn.commit()

    findings = detectar_faltas(conn, "2026-06")

    finding = next(f for f in findings if f["deputado_id"] == 1)
    assert finding["dados_suporte"]["faltas_licenca"] == 2
    assert finding["dados_suporte"]["faltas_sem_justificativa"] == 3
    assert finding["dados_suporte"]["taxa_ausencia_sem_justificativa"] == 3 / 5


def _add_discurso(conn, dep_id, data_hora_inicio, doc=None, keywords=None):
    uid = f"discurso-{dep_id}-{data_hora_inicio}"
    if doc is not None:
        uid += f"-{doc}"
    conn.execute(
        "INSERT INTO discursos (uid, deputado_id, data_hora_inicio, keywords) VALUES (?, ?, ?, ?)",
        (uid, dep_id, data_hora_inicio, keywords),
    )


def test_detectar_silencio_subito_discursos_sinaliza_queda_apos_padrao_regular(conn):
    _add_deputado(conn, 1)
    conn.commit()
    # 6 meses anteriores com media de 2 discursos/mes
    for mes in range(1, 7):
        for i in range(2):
            _add_discurso(conn, 1, f"2024-{mes:02d}-10T10:00", doc=i)
    conn.commit()

    findings = detectar_silencio_subito_discursos(conn, "2024-07", meses_historico=6, media_minima_historica=1.0)

    assert len(findings) == 1
    assert findings[0]["deputado_id"] == 1
    assert findings[0]["tipo"] == "DISCURSOS_SILENCIO_SUBITO"
    assert findings[0]["dados_suporte"]["media_mensal_historica"] == 2.0


def test_detectar_silencio_subito_discursos_ignora_deputado_ja_naturalmente_quieto(conn):
    """Deputado que so discursou 1 vez em 6 meses (media 0.17/mes) nunca teve
    um padrao regular estabelecido - silencio no mes seguinte e normal pra
    ele, nao e uma queda digna de alerta."""
    _add_deputado(conn, 1)
    conn.commit()
    _add_discurso(conn, 1, "2024-02-10T10:00")
    conn.commit()

    findings = detectar_silencio_subito_discursos(conn, "2024-07", meses_historico=6, media_minima_historica=1.0)
    assert findings == []


def test_detectar_silencio_subito_discursos_nao_sinaliza_quem_continua_ativo(conn):
    _add_deputado(conn, 1)
    conn.commit()
    for mes in range(1, 7):
        _add_discurso(conn, 1, f"2024-{mes:02d}-10T10:00")
    _add_discurso(conn, 1, "2024-07-05T10:00")  # continuou discursando no mes de referencia
    conn.commit()

    findings = detectar_silencio_subito_discursos(conn, "2024-07", meses_historico=6, media_minima_historica=1.0)
    assert findings == []


def test_detectar_fornecedor_pouco_comum_sinaliza_fornecedor_de_nicho(conn):
    _add_deputado(conn, 1)
    conn.commit()
    # fornecedor "raro" usado so pelo deputado 1, em 2 meses diferentes (2 deputados nao, e o mesmo 1)
    _add_despesa(conn, 1, 2024, 2, "CONSULTORIA", 500, fornecedor="Nicho Consultoria ME", cnpj="11111111000111")
    _add_despesa(conn, 1, 2024, 3, "CONSULTORIA", 5000, fornecedor="Nicho Consultoria ME", cnpj="11111111000111")
    conn.commit()

    findings = detectar_fornecedor_pouco_comum(conn, "2024-03", max_deputados_historico=3, valor_minimo=1000.0)

    assert len(findings) == 1
    assert findings[0]["deputado_id"] == 1
    assert findings[0]["tipo"] == "FORNECEDOR_POUCO_COMUM"
    assert findings[0]["dados_suporte"]["n_deputados_historico"] == 1
    assert findings[0]["severidade"] == "alta"


def test_detectar_fornecedor_pouco_comum_ignora_fornecedor_grande_nacional(conn):
    """Fornecedor usado por muitos deputados (posto de gasolina de rede,
    companhia aerea etc) nao e de nicho, mesmo com valor alto num mes."""
    for i in range(1, 6):
        _add_deputado(conn, i)
        _add_despesa(conn, i, 2024, 3, "PASSAGEM AEREA", 3000, fornecedor="Companhia Aerea Nacional", cnpj="99999999000199")
    conn.commit()

    findings = detectar_fornecedor_pouco_comum(conn, "2024-03", max_deputados_historico=3, valor_minimo=1000.0)
    assert findings == []


def test_detectar_fornecedor_pouco_comum_ignora_valor_pequeno(conn):
    _add_deputado(conn, 1)
    conn.commit()
    _add_despesa(conn, 1, 2024, 3, "CONSULTORIA", 200, fornecedor="Nicho Consultoria ME", cnpj="11111111000111")
    conn.commit()

    findings = detectar_fornecedor_pouco_comum(conn, "2024-03", max_deputados_historico=3, valor_minimo=1000.0)
    assert findings == []


def test_detectar_mudanca_foco_tematico_sinaliza_temas_sem_relacao_com_historico(conn):
    _add_deputado(conn, 1)
    conn.commit()
    # 6 meses falando sempre de agropecuaria
    for mes in range(1, 7):
        _add_discurso(conn, 1, f"2024-{mes:02d}-10T10:00", keywords="AGROPECUARIA, SOJA, EXPORTACAO, FAZENDA, PECUARIA.")
    # mes de referencia: temas completamente diferentes
    _add_discurso(conn, 1, "2024-07-05T10:00", keywords="CRIPTOMOEDA, BLOCKCHAIN, MINERACAO DIGITAL.")
    conn.commit()

    findings = detectar_mudanca_foco_tematico(conn, "2024-07", meses_historico=6, min_keywords_historico=5)

    assert len(findings) == 1
    assert findings[0]["deputado_id"] == 1
    assert findings[0]["tipo"] == "DISCURSOS_MUDANCA_FOCO_TEMATICO"
    assert findings[0]["dados_suporte"]["jaccard"] == 0.0


def test_detectar_mudanca_foco_tematico_nao_sinaliza_temas_consistentes(conn):
    _add_deputado(conn, 1)
    conn.commit()
    for mes in range(1, 7):
        _add_discurso(conn, 1, f"2024-{mes:02d}-10T10:00", keywords="AGROPECUARIA, SOJA, EXPORTACAO, FAZENDA, PECUARIA.")
    _add_discurso(conn, 1, "2024-07-05T10:00", keywords="AGROPECUARIA, SOJA, NOVA SAFRA.")
    conn.commit()

    findings = detectar_mudanca_foco_tematico(conn, "2024-07", meses_historico=6, min_keywords_historico=5)
    assert findings == []


def test_detectar_mudanca_foco_tematico_ignora_perfil_historico_pequeno_demais(conn):
    """Sem um perfil tematico historico minimamente estabelecido, nao ha
    'padrao usual' pra comparar - nao deveria sinalizar nada."""
    _add_deputado(conn, 1)
    conn.commit()
    _add_discurso(conn, 1, "2024-02-10T10:00", keywords="TEMA UNICO.")
    _add_discurso(conn, 1, "2024-07-05T10:00", keywords="OUTRO TEMA TOTALMENTE DIFERENTE.")
    conn.commit()

    findings = detectar_mudanca_foco_tematico(conn, "2024-07", meses_historico=6, min_keywords_historico=5)
    assert findings == []


def test_detectar_baixa_atividade_geral_sinaliza_mandato_inativo(conn):
    _add_deputado(conn, 1)
    _add_deputado(conn, 999)  # outro deputado, so pra existir uma votacao nominal
    conn.commit()
    _add_votacao(conn, "v1", "2024-03-10")
    _add_voto(conn, "v1", 999)
    conn.commit()
    # deputado 1: nao vota, nao discursa, nao tem despesa - inativo no mes

    findings = detectar_baixa_atividade_geral(conn, "2024-03")

    ids = {f["deputado_id"] for f in findings}
    assert 1 in ids
    assert 999 not in ids  # votou, entao nao e "inativo"
    assert findings[0]["tipo"] == "BAIXA_ATIVIDADE_GERAL"


def test_detectar_baixa_atividade_geral_nao_sinaliza_se_teve_discurso(conn):
    """So conta se os TRES sinais (presenca, discurso, gasto) baterem ao
    mesmo tempo - ter discursado ja tira do combinado, mesmo sem votar/gastar."""
    _add_deputado(conn, 1)
    _add_deputado(conn, 999)
    conn.commit()
    _add_votacao(conn, "v1", "2024-03-10")
    _add_voto(conn, "v1", 999)
    _add_discurso(conn, 1, "2024-03-05T10:00")
    conn.commit()

    findings = detectar_baixa_atividade_geral(conn, "2024-03")
    assert not any(f["deputado_id"] == 1 for f in findings)


def test_detectar_baixa_atividade_geral_nao_sinaliza_licenca(conn):
    """Ausencia inteira do mes justificada por licenca nao conta pro sinal
    combinado - mesma logica de detectar_faltas."""
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    _add_deputado(conn, 1)
    _add_deputado(conn, 999)
    conn.commit()
    _add_historico(conn, 1, 57, "2023-02-01T00:00", "Exercício")
    _add_historico(conn, 1, 57, "2024-03-01T00:00", "Licença")
    _add_votacao(conn, "v1", "2024-03-10")
    _add_voto(conn, "v1", 999)
    conn.commit()

    findings = detectar_baixa_atividade_geral(conn, "2024-03")
    assert not any(f["deputado_id"] == 1 for f in findings)


def test_detectar_mudanca_alinhamento_voto_reporta_concordancia_antes_e_depois(conn):
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    _add_deputado(conn, 1, partido="NOVO")  # partido atual, pos-troca
    _add_deputado(conn, 998, partido="NOVO")  # colega do partido novo
    _add_deputado(conn, 999, partido="ANTIGO")  # colega do partido antigo
    conn.commit()
    conn.execute(
        "INSERT INTO deputado_historico (deputado_id, legislatura_id, data_hora, sigla_partido) VALUES (1, 57, '2024-03-01T00:00', 'ANTIGO')"
    )
    conn.execute(
        "INSERT INTO deputado_historico (deputado_id, legislatura_id, data_hora, sigla_partido) VALUES (1, 57, '2024-03-15T00:00', 'NOVO')"
    )
    conn.commit()

    # antes da troca (jan-fev): deputado 1 e colega do ANTIGO sempre votam Sim juntos
    for i, dia in enumerate(["2024-01-10", "2024-01-20", "2024-02-10"]):
        vid = f"antes-{i}"
        _add_votacao(conn, vid, dia)
        _add_voto(conn, vid, 1, voto="Sim")
        _add_voto(conn, vid, 999, voto="Sim")

    # depois da troca (15/mar em diante): deputado 1 e colega do NOVO sempre votam Nao juntos
    for i, dia in enumerate(["2024-03-16", "2024-03-20", "2024-03-25"]):
        vid = f"depois-{i}"
        _add_votacao(conn, vid, dia)
        _add_voto(conn, vid, 1, voto="Não")
        _add_voto(conn, vid, 998, voto="Não")
    conn.commit()

    findings = detectar_mudanca_alinhamento_voto(conn, "2024-03", meses_janela=6)

    assert len(findings) == 1
    f = findings[0]
    assert f["deputado_id"] == 1
    assert f["tipo"] == "MUDANCA_ALINHAMENTO_VOTO"
    assert f["dados_suporte"]["concordancia_partido_antigo"] == 1.0
    assert f["dados_suporte"]["concordancia_partido_novo"] == 1.0


def test_detectar_mudanca_alinhamento_voto_ignora_sem_troca_no_mes(conn):
    _add_deputado(conn, 1, partido="X")
    conn.commit()
    findings = detectar_mudanca_alinhamento_voto(conn, "2024-03")
    assert findings == []
