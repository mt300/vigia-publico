"""Testa a interacao dos filtros do dashboard (partido/UF/deputado) via
AppTest - cobre o bug corrigido onde widgets sem `key` fixo perdiam a
selecao a cada clique (o `default`/`index` recalculado a cada rerun mudava
a identidade implicita do widget e o Streamlit tratava como um novo).
"""

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

    deputados = [
        (1, "Fulano da Silva", "PT", "BA"),
        (2, "Ciclano Souza", "PT", "SP"),
        (3, "Beltrano Lima", "AVANTE", "SP"),
    ]
    for dep_id, nome, partido, uf in deputados:
        conn.execute(
            "INSERT INTO deputados (id, nome_eleitoral, sigla_partido, sigla_uf) VALUES (?, ?, ?, ?)",
            (dep_id, nome, partido, uf),
        )
        conn.execute(
            """
            INSERT INTO despesas (uid, deputado_id, ano, mes, tipo_despesa, nome_fornecedor, valor_liquido, data_documento)
            VALUES (?, ?, 2024, 3, 'COMBUSTIVEIS', 'Posto X', 100.0, '2024-03-01')
            """,
            (f"uid-{dep_id}", dep_id),
        )
    conn.commit()
    conn.close()
    return path


def _render_painel_publico(db_path):
    from vigia_publico.dashboard import data, views

    data.use_db_path(db_path)
    views.render(mode="public")


def test_selecionar_dois_partidos_mantem_ambos(db_path):
    """Regressao do bug: adicionar um segundo partido ao mesmo multiselect
    nao pode derrubar o primeiro."""
    at = AppTest.from_function(_render_painel_publico, kwargs={"db_path": db_path})
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
    at = AppTest.from_function(_render_painel_publico, kwargs={"db_path": db_path})
    at.run()

    at.sidebar.multiselect[0].select("PT")  # Partido
    at.run()
    at.sidebar.multiselect[1].select("SP")  # Estado (UF)
    at.run()

    assert at.sidebar.multiselect[0].value == ["PT"]
    assert at.sidebar.multiselect[1].value == ["SP"]
    assert not at.exception


def test_deputado_selecionado_reseta_sem_crash_quando_sai_do_filtro(db_path):
    """Deputado da BA escolhido, depois filtro UF=SP exclui ele da lista -
    nao pode quebrar (session_state com valor fora de `options`), tem que
    voltar pra '(todos)'."""
    at = AppTest.from_function(_render_painel_publico, kwargs={"db_path": db_path})
    at.run()

    at.sidebar.multiselect[0].select("PT")
    at.run()
    dep_select = at.sidebar.selectbox[-1]
    alvo = next(o for o in dep_select.options if "/BA)" in o)
    dep_select.select(alvo)
    at.run()
    assert at.sidebar.selectbox[-1].value == alvo

    at.sidebar.multiselect[1].select("SP")  # exclui o deputado da BA da lista
    at.run()

    assert not at.exception
    assert at.sidebar.selectbox[-1].value == "(todos)"
