"""Testa `build_report` - cobre a extensao desta sessao (relatorio unico
com secoes de Camara e Senado, ja que `findings` e uma tabela compartilhada
com discriminador `casa`)."""

from __future__ import annotations

import sqlite3

import pytest

from vigia_publico.db.connection import run_migrations
from vigia_publico.reporting.report_builder import build_report


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "db.sqlite"
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    run_migrations(c)
    yield c
    c.close()


def test_relatorio_inclui_secoes_de_camara_e_senado(conn, tmp_path):
    conn.execute("INSERT INTO deputados (id, nome_eleitoral, sigla_partido, sigla_uf) VALUES (1, 'Fulano', 'PT', 'SP')")
    conn.execute("INSERT INTO senadores (id, nome_parlamentar, sigla_partido, sigla_uf) VALUES (1, 'Fulana', 'PSDB', 'RJ')")
    conn.execute(
        """
        INSERT INTO findings (mes_referencia, casa, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url)
        VALUES ('2024-03', 'camara', 1, 'GASTO_OUTLIER', 'alta', 'gasto camara', '{}', 'https://dadosabertos.camara.leg.br/x')
        """
    )
    conn.execute(
        """
        INSERT INTO findings (mes_referencia, casa, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url)
        VALUES ('2024-03', 'senado', 1, 'GASTO_OUTLIER', 'alta', 'gasto senado', '{}', 'https://adm.senado.gov.br/x')
        """
    )
    conn.commit()

    caminho = build_report(conn, "2024-03", output_dir=tmp_path)
    conteudo = caminho.read_text(encoding="utf-8")

    assert "Fulano" in conteudo
    assert "gasto camara" in conteudo
    assert "Fulana" in conteudo
    assert "gasto senado" in conteudo
    assert "Ranking de senadores" in conteudo
    assert "Total de achados no mes: **2**" in conteudo


def test_relatorio_sem_achado_de_senado_nao_mostra_secao_vazia(conn, tmp_path):
    conn.execute("INSERT INTO deputados (id, nome_eleitoral, sigla_partido, sigla_uf) VALUES (1, 'Fulano', 'PT', 'SP')")
    conn.execute(
        """
        INSERT INTO findings (mes_referencia, casa, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url)
        VALUES ('2024-03', 'camara', 1, 'GASTO_OUTLIER', 'alta', 'gasto camara', '{}', NULL)
        """
    )
    conn.commit()

    caminho = build_report(conn, "2024-03", output_dir=tmp_path)
    conteudo = caminho.read_text(encoding="utf-8")

    assert "Ranking de senadores" not in conteudo
