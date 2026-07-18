def test_migrations_aplicam_em_banco_vazio(conn):
    tabelas = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    esperadas = {
        "legislaturas",
        "deputados",
        "deputado_redes_sociais",
        "deputado_historico",
        "despesas",
        "discursos",
        "votacoes",
        "votos",
        "ingest_state",
        "llm_discurso_cache",
        "findings",
    }
    assert esperadas <= tabelas


def test_migrations_sao_idempotentes(conn):
    from vigia_publico.db.connection import run_migrations

    aplicadas_de_novo = run_migrations(conn)
    assert aplicadas_de_novo == []
