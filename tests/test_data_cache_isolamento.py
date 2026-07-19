"""Regressao de dois bugs de cache achados/corrigidos juntos em
`dashboard/data.py`:

1. Cacheava sem levar em conta qual banco estava ativo (`use_db_path`) -
   trocar de banco no mesmo processo devolvia resultado cacheado do banco
   ANTERIOR pra qualquer chamada com os mesmos argumentos, ja que
   `st.cache_data` so olha os argumentos visiveis da funcao, nao a
   variavel de modulo `_db_path`.
2. Ao corrigir (1) com um decorator generico `_cached_query`, apareceu um
   SEGUNDO bug: duas queries DIFERENTES com a MESMA forma de argumentos
   (ex: `get_despesas_mensal` e `get_despesas_por_categoria`, ambas
   `(mes_inicio, mes_fim, partidos, ufs, deputado_id)`) chamadas com os
   MESMOS valores colidiam no cache - uma devolvia o resultado da outra.
   Causa: a funcao interna do decorator nasce com o mesmo `__qualname__`
   pra toda funcao decorada (mesma linha de origem), e o Streamlit usa
   esse identificador estatico como parte da chave de cache.

Nenhum dos dois morde em producao (cada processo so usa um banco, e cada
chamada usa argumentos tipicamente distintos o bastante na pratica) - mas
sao bugs reais, reproduziveis, e o tipo de coisa que morderia em silencio
(dado errado, sem crash) numa mudanca futura sem esses testes.
"""

from __future__ import annotations

import sqlite3

import pytest

from vigia_publico.dashboard import data
from vigia_publico.db.connection import run_migrations


def _criar_banco_com_partido(path, partido: str) -> None:
    conn = sqlite3.connect(path)
    run_migrations(conn)
    conn.execute(
        "INSERT INTO deputados (id, nome_eleitoral, sigla_partido, sigla_uf) VALUES (1, 'Fulano', ?, 'SP')",
        (partido,),
    )
    conn.commit()
    conn.close()


@pytest.fixture
def dois_bancos(tmp_path):
    banco_a = tmp_path / "a.db"
    banco_b = tmp_path / "b.db"
    _criar_banco_com_partido(banco_a, "PT")
    _criar_banco_com_partido(banco_b, "PSDB")
    return banco_a, banco_b


def test_trocar_de_banco_nao_reaproveita_cache_do_banco_anterior(dois_bancos):
    banco_a, banco_b = dois_bancos

    data.use_db_path(banco_a)
    assert data.listar_partidos() == ["PT"]

    data.use_db_path(banco_b)
    assert data.listar_partidos() == ["PSDB"]  # falhava antes do fix: devolvia ['PT']


def test_voltar_pro_banco_anterior_ainda_funciona(dois_bancos):
    banco_a, banco_b = dois_bancos

    data.use_db_path(banco_a)
    data.listar_partidos()

    data.use_db_path(banco_b)
    data.listar_partidos()

    data.use_db_path(banco_a)
    assert data.listar_partidos() == ["PT"]


@pytest.fixture
def banco_com_despesa(tmp_path):
    path = tmp_path / "despesas.db"
    conn = sqlite3.connect(path)
    run_migrations(conn)
    conn.execute("INSERT INTO deputados (id, nome_eleitoral, sigla_partido, sigla_uf) VALUES (1, 'Fulano', 'PT', 'SP')")
    conn.execute(
        """
        INSERT INTO despesas (uid, deputado_id, ano, mes, tipo_despesa, valor_liquido, data_documento)
        VALUES ('u1', 1, 2024, 3, 'COMBUSTIVEIS', 100.0, '2024-03-01')
        """
    )
    conn.commit()
    conn.close()
    return path


def test_queries_diferentes_com_mesma_forma_de_argumentos_nao_colidem(banco_com_despesa):
    """`get_despesas_mensal` e `get_despesas_por_categoria` tem a mesma
    assinatura (mes_inicio, mes_fim, partidos, ufs, deputado_id) - chamar
    as duas com os mesmos valores nao pode fazer uma devolver o resultado
    cacheado da outra."""
    data.use_db_path(banco_com_despesa)

    mensal = data.get_despesas_mensal("2024-03", "2024-03")
    assert list(mensal.columns) == ["mes", "total"]

    por_categoria = data.get_despesas_por_categoria("2024-03", "2024-03")
    assert list(por_categoria.columns) == ["tipo_despesa", "total"]  # falhava antes: vinha ['mes', 'total']


def test_query_senado_e_query_camara_com_mesma_forma_nao_colidem(banco_com_despesa):
    """`listar_partidos` (Camara) e `listar_partidos_senado` (Senado) tem a
    MESMA forma (zero argumentos) - garante que sao funcoes decoradas
    distintas (nomes qualificados diferentes), nao a mesma entrada de
    cache reaproveitada entre as duas casas."""
    conn = sqlite3.connect(banco_com_despesa)
    conn.execute("INSERT INTO senadores (id, nome_parlamentar, sigla_partido, sigla_uf) VALUES (1, 'Fulana', 'PSDB', 'RJ')")
    conn.commit()
    conn.close()

    data.use_db_path(banco_com_despesa)

    assert data.listar_partidos() == ["PT"]
    assert data.listar_partidos_senado() == ["PSDB"]
