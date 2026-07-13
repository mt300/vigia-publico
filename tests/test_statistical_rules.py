from senado_sentinel.detection.statistical import (
    detectar_concentracao_fornecedor,
    detectar_faltas,
    detectar_outliers_gasto,
    detectar_troca_partido,
)


def _add_deputado(conn, dep_id, nome="Teste"):
    conn.execute("INSERT INTO deputados (id, nome_eleitoral) VALUES (?, ?)", (dep_id, nome))


def _add_despesa(conn, dep_id, ano, mes, tipo, valor, fornecedor="Fornecedor X"):
    conn.execute(
        """
        INSERT INTO despesas (uid, deputado_id, ano, mes, tipo_despesa, nome_fornecedor, valor_liquido)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (f"{dep_id}-{ano}-{mes}-{tipo}-{fornecedor}-{valor}", dep_id, ano, mes, tipo, fornecedor, valor),
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
