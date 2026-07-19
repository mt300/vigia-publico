"""Testa `export_public_snapshot` - so o que mudou nesta sessao (extensao
pra Senado): `senadores.email` anonimizado, `despesas_senadores` sem `uid`
com dados preservados, achados de Senado sobrevivem ao filtro de
`TIPOS_PUBLICOS` (mesma coluna `tipo` compartilhada com a Camara)."""

from __future__ import annotations

import sqlite3

import pytest

from vigia_publico.db.connection import run_migrations
from vigia_publico.reporting.public_snapshot import export_public_snapshot


@pytest.fixture
def banco_origem(tmp_path):
    path = tmp_path / "origem.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    run_migrations(conn)

    conn.execute(
        "INSERT INTO senadores (id, nome_parlamentar, sigla_partido, sigla_uf, email) VALUES (1, 'Fulana', 'PT', 'SP', 'fulana@senado.leg.br')"
    )
    conn.execute(
        """
        INSERT INTO despesas_senadores (uid, senador_id, ano, mes, tipo_despesa, nome_fornecedor, valor_reembolsado, data_documento)
        VALUES ('uid-1', 1, 2024, 3, 'PASSAGEM_AEREA', 'Cia X', 500.0, '2024-03-01')
        """
    )
    conn.execute(
        """
        INSERT INTO findings (mes_referencia, casa, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url)
        VALUES ('2024-03', 'senado', 1, 'GASTO_OUTLIER', 'alta', 'desc interna', '{}', 'https://adm.senado.gov.br/x')
        """
    )
    conn.execute(
        """
        INSERT INTO findings (mes_referencia, casa, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url)
        VALUES ('2024-03', 'senado', 1, 'TIPO_NAO_PUBLICO_QUALQUER', 'alta', 'desc interna', '{}', NULL)
        """
    )
    conn.commit()
    conn.close()
    return path


def test_snapshot_anonimiza_email_e_preserva_dados_de_senador(banco_origem, tmp_path):
    destino = tmp_path / "public.db"
    export_public_snapshot(source_db_path=banco_origem, output_path=destino)

    conn = sqlite3.connect(destino)
    senador = conn.execute("SELECT nome_parlamentar, email FROM senadores WHERE id = 1").fetchone()
    assert senador == ("Fulana", None)

    despesa = conn.execute(
        "SELECT senador_id, tipo_despesa, valor_reembolsado FROM despesas_senadores WHERE senador_id = 1"
    ).fetchone()
    assert despesa == (1, "PASSAGEM_AEREA", 500.0)

    colunas = {row[1] for row in conn.execute("PRAGMA table_info(despesas_senadores)")}
    assert "uid" not in colunas  # mesmo tratamento de reducao de `despesas` (ver _reduzir_despesas)


def test_snapshot_filtra_findings_de_senado_por_tipos_publicos(banco_origem, tmp_path):
    destino = tmp_path / "public.db"
    export_public_snapshot(source_db_path=banco_origem, output_path=destino)

    conn = sqlite3.connect(destino)
    tipos = {row[0] for row in conn.execute("SELECT tipo FROM findings WHERE casa = 'senado'")}
    assert tipos == {"GASTO_OUTLIER"}  # TIPO_NAO_PUBLICO_QUALQUER filtrado, mesma logica da Camara
