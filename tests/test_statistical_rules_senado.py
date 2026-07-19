from vigia_publico.detection.statistical_senado import (
    detectar_concentracao_fornecedor_senado,
    detectar_fornecedor_pouco_comum_senado,
    detectar_outliers_gasto_senado,
    detectar_outliers_gasto_vs_pares_senado,
    detectar_valores_repetidos_senado,
)


def _add_senador(conn, sen_id, nome="Teste", partido=None, uf=None):
    conn.execute(
        "INSERT INTO senadores (id, nome_parlamentar, sigla_partido, sigla_uf) VALUES (?, ?, ?, ?)",
        (sen_id, nome, partido, uf),
    )


def _add_despesa_senador(conn, sen_id, ano, mes, tipo, valor, fornecedor="Fornecedor X", doc=None, data_documento=None, cnpj=None):
    uid = f"{sen_id}-{ano}-{mes}-{tipo}-{fornecedor}-{valor}"
    if doc is not None:
        uid += f"-{doc}"
    data_documento = data_documento or f"{ano:04d}-{mes:02d}-01"
    conn.execute(
        """
        INSERT INTO despesas_senadores (uid, senador_id, ano, mes, tipo_despesa, nome_fornecedor, valor_reembolsado, data_documento, cnpj_cpf_fornecedor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (uid, sen_id, ano, mes, tipo, fornecedor, valor, data_documento, cnpj),
    )


def test_detectar_outliers_gasto_senado_sinaliza_valor_muito_acima_da_media(conn):
    _add_senador(conn, 1)
    for mes in range(1, 7):
        _add_despesa_senador(conn, 1, 2024, mes, "COMBUSTIVEIS", 1000 + mes)
    _add_despesa_senador(conn, 1, 2024, 7, "COMBUSTIVEIS", 50000)
    conn.commit()

    findings = detectar_outliers_gasto_senado(conn, "2024-07")

    assert len(findings) == 1
    assert findings[0]["tipo"] == "GASTO_OUTLIER"
    assert findings[0]["senador_id"] == 1
    assert findings[0]["fonte_url"].endswith("/despesas_ceaps/2024")


def test_detectar_outliers_gasto_vs_pares_senado_sinaliza_acima_dos_colegas(conn):
    # Valores dos pares levemente diferentes entre si (nao identicos) -
    # desvio-padrao exatamente 0 faz a regra pular o grupo (protecao contra
    # divisao por zero), entao precisa de alguma variancia real nos pares.
    _add_senador(conn, 1, partido="PT", uf="SP")
    for outros, valor in zip(range(2, 6), (950, 1000, 1050, 1000)):
        _add_senador(conn, outros, partido="PT", uf="SP")
        _add_despesa_senador(conn, outros, 2024, 3, "PASSAGEM_AEREA", valor, fornecedor=f"Cia {outros}")
    _add_despesa_senador(conn, 1, 2024, 3, "PASSAGEM_AEREA", 50000)
    conn.commit()

    findings = detectar_outliers_gasto_vs_pares_senado(conn, "2024-03", min_pares=3)

    assert len(findings) >= 1
    assert findings[0]["senador_id"] == 1
    assert findings[0]["tipo"] == "GASTO_OUTLIER_VS_PARES"


def test_detectar_valores_repetidos_senado_sinaliza_fracionamento(conn):
    _add_senador(conn, 1)
    for i in range(3):
        _add_despesa_senador(conn, 1, 2024, 3, "MATERIAL_ESCRITORIO", 500.0, fornecedor="Papelaria X", doc=str(i), data_documento="2024-03-10")
    conn.commit()

    findings = detectar_valores_repetidos_senado(conn, "2024-03")

    assert len(findings) == 1
    assert findings[0]["tipo"] == "VALOR_REPETIDO_SUSPEITO"
    assert findings[0]["dados_suporte"]["repeticoes"] == 3


def test_detectar_valores_repetidos_senado_ignora_categoria_excluida(conn):
    """Mesma protecao que a Camara ja tem contra falso positivo de hotel
    emitindo notas identicas no checkout - so que com o vocabulario proprio
    do CEAPS (categoria bundla hospedagem com outras coisas)."""
    _add_senador(conn, 1)
    for i in range(3):
        _add_despesa_senador(
            conn, 1, 2024, 3, "Locomoção, hospedagem, alimentação, combustíveis e lubrificantes",
            500.0, fornecedor="Hotel X", doc=str(i), data_documento="2024-03-10",
        )
    conn.commit()

    findings = detectar_valores_repetidos_senado(conn, "2024-03")

    assert findings == []


def test_detectar_fornecedor_pouco_comum_senado_sinaliza(conn):
    _add_senador(conn, 1)
    _add_despesa_senador(conn, 1, 2024, 3, "CONSULTORIA", 20000.0, fornecedor="Empresa Nicho", cnpj="11.111.111/0001-11")
    conn.commit()

    findings = detectar_fornecedor_pouco_comum_senado(conn, "2024-03")

    assert len(findings) == 1
    assert findings[0]["tipo"] == "FORNECEDOR_POUCO_COMUM"


def test_detectar_concentracao_fornecedor_senado_sinaliza(conn):
    _add_senador(conn, 1)
    _add_despesa_senador(conn, 1, 2024, 3, "CONSULTORIA", 10000.0, fornecedor="Fornecedor Principal")
    _add_despesa_senador(conn, 1, 2024, 3, "MATERIAL", 100.0, fornecedor="Fornecedor B")
    _add_despesa_senador(conn, 1, 2024, 3, "PASSAGEM", 100.0, fornecedor="Fornecedor C")
    conn.commit()

    findings = detectar_concentracao_fornecedor_senado(conn, "2024-03")

    assert len(findings) == 1
    assert findings[0]["tipo"] == "FORNECEDOR_CONCENTRADO"
