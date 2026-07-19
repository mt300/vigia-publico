import json
from pathlib import Path

from vigia_publico.db import repository as repo

FIXTURES = Path(__file__).parent / "fixtures" / "sample_api_responses"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _contagem(conn, tabela: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0]


def test_upsert_deputado_e_idempotente(conn):
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    conn.commit()
    perfil = _load("deputado_perfil.json")

    repo.upsert_deputado(conn, perfil)
    repo.upsert_deputado_redes_sociais(conn, perfil["id"], perfil["redeSocial"])
    conn.commit()
    repo.upsert_deputado(conn, perfil)
    repo.upsert_deputado_redes_sociais(conn, perfil["id"], perfil["redeSocial"])
    conn.commit()

    assert _contagem(conn, "deputados") == 1
    assert _contagem(conn, "deputado_redes_sociais") == 2

    row = conn.execute("SELECT email, sigla_partido FROM deputados WHERE id = ?", (perfil["id"],)).fetchone()
    assert row["email"] == "dep.acaciofavacho@camara.leg.br"
    assert row["sigla_partido"] == "MDB"


def test_upsert_despesa_e_idempotente(conn):
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    conn.execute("INSERT INTO deputados (id, nome_eleitoral) VALUES (204379, 'Teste')")
    conn.commit()
    despesa = _load("despesa.json")

    repo.upsert_despesa(conn, 204379, despesa)
    repo.upsert_despesa(conn, 204379, despesa)
    conn.commit()

    assert _contagem(conn, "despesas") == 1


def test_upsert_discurso_e_idempotente(conn):
    conn.execute("INSERT INTO legislaturas (id, data_inicio, data_fim) VALUES (57, '2023-02-01', '2027-01-31')")
    conn.execute("INSERT INTO deputados (id, nome_eleitoral) VALUES (204379, 'Teste')")
    conn.commit()
    discurso = _load("discurso.json")

    uid1 = repo.upsert_discurso(conn, 204379, discurso)
    uid2 = repo.upsert_discurso(conn, 204379, discurso)
    conn.commit()

    assert uid1 == uid2
    assert _contagem(conn, "discursos") == 1
    row = conn.execute("SELECT transcricao FROM discursos WHERE uid = ?", (uid1,)).fetchone()
    assert "teste do discurso" in row["transcricao"]


def test_ingest_state_sem_deputado_e_idempotente(conn):
    """Regressao: deputado_id=None usava NULL na PRIMARY KEY composta, e o SQLite
    trata NULLs como sempre distintos, entao o ON CONFLICT nunca casava e cada
    rodada inseria uma linha nova. Corrigido com um sentinel (0) em vez de NULL."""
    repo.mark_ingest_state(conn, "votacoes", None, "57-2024-Q1", "concluido")
    repo.mark_ingest_state(conn, "votacoes", None, "57-2024-Q1", "concluido")
    conn.commit()

    assert _contagem(conn, "ingest_state") == 1
    assert repo.ingest_status(conn, "votacoes", None, "57-2024-Q1") == "concluido"


def test_upsert_senador_e_idempotente(conn):
    identificacao = {
        "CodigoParlamentar": "5672",
        "NomeCompletoParlamentar": "Alan Rick Miranda",
        "NomeParlamentar": "Alan Rick",
        "SexoParlamentar": "Masculino",
        "EmailParlamentar": "sen.alanrick@senado.leg.br",
        "UrlFotoParlamentar": "http://www.senado.leg.br/senadores/img/fotos-oficiais/senador5672.jpg",
        "SiglaPartidoParlamentar": "REPUBLICANOS",
        "UfParlamentar": "AC",
    }

    repo.upsert_senador(conn, identificacao)
    repo.upsert_senador(conn, identificacao)
    conn.commit()

    assert _contagem(conn, "senadores") == 1
    row = conn.execute("SELECT nome_parlamentar, sigla_partido, sigla_uf FROM senadores WHERE id = 5672").fetchone()
    assert row["nome_parlamentar"] == "Alan Rick"
    assert row["sigla_partido"] == "REPUBLICANOS"
    assert row["sigla_uf"] == "AC"


def test_upsert_despesa_senador_e_idempotente(conn):
    identificacao = {"CodigoParlamentar": "5672", "NomeParlamentar": "Alan Rick", "SiglaPartidoParlamentar": "REPUBLICANOS", "UfParlamentar": "AC"}
    repo.upsert_senador(conn, identificacao)
    conn.commit()

    despesa = {
        "id": 2241097,
        "tipoDocumento": "Fatura",
        "ano": 2024,
        "mes": 9,
        "tipoDespesa": "Contratação de consultorias, assessorias, pesquisas, trabalhos técnicos",
        "cpfCnpj": "05.120.923/0001-09",
        "fornecedor": "AEROTUR SERVIÇOS",
        "documento": "0005018906",
        "data": "2024-09-20",
        "detalhamento": None,
        "valorReembolsado": 698.85,
    }

    repo.upsert_despesa_senador(conn, 5672, despesa)
    repo.upsert_despesa_senador(conn, 5672, despesa)
    conn.commit()

    assert _contagem(conn, "despesas_senadores") == 1
    row = conn.execute("SELECT nome_fornecedor, valor_reembolsado FROM despesas_senadores WHERE senador_id = 5672").fetchone()
    assert row["nome_fornecedor"] == "AEROTUR SERVIÇOS"
    assert row["valor_reembolsado"] == 698.85


def test_findings_reprocessamento_substitui_mes(conn):
    conn.execute("INSERT INTO deputados (id, nome_eleitoral) VALUES (1, 'Teste')")
    conn.commit()

    repo.insert_finding(conn, "2024-03", 1, "GASTO_OUTLIER", "alta", "descricao 1")
    repo.insert_finding(conn, "2024-03", 1, "GASTO_OUTLIER", "alta", "descricao 2")
    conn.commit()
    assert _contagem(conn, "findings") == 2

    repo.clear_findings_for_month(conn, "2024-03")
    repo.insert_finding(conn, "2024-03", 1, "GASTO_OUTLIER", "media", "descricao unica apos reprocessar")
    conn.commit()

    rows = conn.execute("SELECT descricao, severidade FROM findings WHERE mes_referencia = '2024-03'").fetchall()
    assert len(rows) == 1
    assert rows[0]["descricao"] == "descricao unica apos reprocessar"


def test_findings_camara_e_senado_coexistem_sem_interferir(conn):
    """Regressao: findings.deputado_id guarda deputado_id OU senador_id
    (sem FK, ver db/migrations/0002_senadores.sql) - limpar/inserir achados
    de uma casa nao pode afetar achados da outra casa no mesmo mes, mesmo
    quando o ID numerico colide (namespaces independentes)."""
    conn.execute("INSERT INTO deputados (id, nome_eleitoral) VALUES (1, 'Deputado Teste')")
    conn.execute(
        "INSERT INTO senadores (id, nome_parlamentar) VALUES (1, 'Senador Teste')"
    )  # mesmo id 1, casas diferentes - de proposito
    conn.commit()

    repo.insert_finding(conn, "2024-03", 1, "GASTO_OUTLIER", "alta", "achado da camara", casa="camara")
    repo.insert_finding(conn, "2024-03", 1, "GASTO_OUTLIER", "alta", "achado do senado", casa="senado")
    conn.commit()

    assert _contagem(conn, "findings") == 2
    por_casa = {row["casa"]: row["descricao"] for row in conn.execute("SELECT casa, descricao FROM findings")}
    assert por_casa == {"camara": "achado da camara", "senado": "achado do senado"}

    repo.clear_findings_for_month(conn, "2024-03", casa="senado")
    conn.commit()

    restantes = conn.execute("SELECT casa, descricao FROM findings").fetchall()
    assert len(restantes) == 1
    assert restantes[0]["casa"] == "camara"
