"""Testa a interacao dos filtros do Painel Senado via AppTest - espelha
`test_dashboard_filters.py` (mesmo bug de referencia: widget sem `key` fixo
perde selecao a cada rerun)."""

from __future__ import annotations

import sqlite3

import pytest
from streamlit.testing.v1 import AppTest

from vigia_publico.db.connection import run_migrations


@pytest.fixture
def db_path(tmp_path):
    """Banco de teste em ARQUIVO (nao :memory:) - `dashboard/data.py` abre a
    conexao via `file:{path}?mode=ro`, que exige um arquivo real."""
    path = tmp_path / "vigia_publico_test.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    senadores = [
        (1, "Fulana da Silva", "PT", "BA"),
        (2, "Cicrana Souza", "PT", "SP"),
        (3, "Beltrana Lima", "AVANTE", "SP"),
    ]
    for sen_id, nome, partido, uf in senadores:
        conn.execute(
            "INSERT INTO senadores (id, nome_parlamentar, sigla_partido, sigla_uf) VALUES (?, ?, ?, ?)",
            (sen_id, nome, partido, uf),
        )
        conn.execute(
            """
            INSERT INTO despesas_senadores (uid, senador_id, ano, mes, tipo_despesa, nome_fornecedor, valor_reembolsado, data_documento)
            VALUES (?, ?, 2024, 3, 'PASSAGEM_AEREA', 'Cia X', 100.0, '2024-03-01')
            """,
            (f"uid-{sen_id}", sen_id),
        )
    conn.commit()
    conn.close()
    return path


def _render_painel_senado_publico(db_path):
    from vigia_publico.dashboard import data, views_senado

    data.use_db_path(db_path)
    views_senado.render(mode="public")


def test_selecionar_dois_partidos_mantem_ambos(db_path):
    at = AppTest.from_function(_render_painel_senado_publico, kwargs={"db_path": db_path})
    at.run()
    assert not at.exception

    partido_ms = at.sidebar.multiselect[0]
    assert partido_ms.label == "Partido"
    partido_ms.select("PT")
    at.run()
    assert at.sidebar.multiselect[0].value == ["PT"]

    at.sidebar.multiselect[0].select("AVANTE")
    at.run()
    assert set(at.sidebar.multiselect[0].value) == {"PT", "AVANTE"}
    assert not at.exception


def test_selecionar_partido_e_uf_nao_interferem_entre_si(db_path):
    at = AppTest.from_function(_render_painel_senado_publico, kwargs={"db_path": db_path})
    at.run()

    at.sidebar.multiselect[0].select("PT")  # Partido
    at.run()
    at.sidebar.multiselect[1].select("SP")  # Estado (UF)
    at.run()

    assert at.sidebar.multiselect[0].value == ["PT"]
    assert at.sidebar.multiselect[1].value == ["SP"]
    assert not at.exception


def test_senador_selecionado_reseta_sem_crash_quando_sai_do_filtro(db_path):
    at = AppTest.from_function(_render_painel_senado_publico, kwargs={"db_path": db_path})
    at.run()

    at.sidebar.multiselect[0].select("PT")
    at.run()
    sen_select = at.sidebar.selectbox[-1]
    alvo = next(o for o in sen_select.options if "/BA)" in o)
    sen_select.select(alvo)
    at.run()
    assert at.sidebar.selectbox[-1].value == alvo

    at.sidebar.multiselect[1].select("SP")  # exclui a senadora da BA da lista
    at.run()

    assert not at.exception
    assert at.sidebar.selectbox[-1].value == "(todos)"
