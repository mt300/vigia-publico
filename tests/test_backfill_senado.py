"""Testa `ingest_despesas_ano_senado` - cobre um bug real reproduzido nesta
sessao: `backfill --casa senado --limite N` seguido de `backfill --casa
senado` (sem limite) nao inseria nada pra ninguem alem dos N primeiros,
porque a unidade de trabalho de `ingest_state` do Senado e por-ANO (nao
por-senador, diferente da Camara - o CEAPS devolve todos os senadores numa
chamada so) - a rodada limitada marcava o ano como "concluido" com base num
universo parcial de `senadores_validos`, e a rodada completa posterior
pulava o ano inteiro achando que ja estava feito.
"""

from __future__ import annotations

from unittest.mock import patch

from vigia_publico.ingestion.backfill_senado import ingest_despesas_ano_senado


def _add_senador(conn, sen_id, nome="Teste"):
    conn.execute(
        "INSERT INTO senadores (id, nome_parlamentar, sigla_partido, sigla_uf) VALUES (?, ?, 'PT', 'SP')",
        (sen_id, nome),
    )


CEAPS_ANO = [
    {"codSenador": 1, "ano": 2024, "mes": 3, "tipoDespesa": "PASSAGEM_AEREA", "valorReembolsado": 100.0, "data": "2024-03-01", "fornecedor": "Cia X"},
    {"codSenador": 2, "ano": 2024, "mes": 3, "tipoDespesa": "PASSAGEM_AEREA", "valorReembolsado": 200.0, "data": "2024-03-01", "fornecedor": "Cia Y"},
]


def test_rodada_limitada_nao_impede_rodada_completa_de_inserir_o_restante(conn):
    """Regressao do bug: `persistir_estado=False` (rodada limitada) nao pode
    gravar `ingest_state`, senao a rodada completa seguinte pula o ano."""
    _add_senador(conn, 1)
    _add_senador(conn, 2)
    conn.commit()

    with patch("vigia_publico.ingestion.backfill_senado.ep.despesas_ceaps_ano", return_value=CEAPS_ANO):
        # Rodada "limitada" (limite_senadores=1 na pratica): so o senador 1
        # e valido, senador 2 e ignorado - e NAO deve persistir ingest_state.
        ingest_despesas_ano_senado(conn, client=None, ano=2024, senadores_validos={1}, persistir_estado=False)

        despesas = conn.execute("SELECT senador_id FROM despesas_senadores").fetchall()
        assert [d[0] for d in despesas] == [1]  # so o senador 1 foi inserido ate aqui

        # Rodada completa seguinte, sem limite - TEM que processar o ano de
        # novo (nao pode achar que ja esta "concluido") e inserir o senador 2.
        ingest_despesas_ano_senado(conn, client=None, ano=2024, senadores_validos={1, 2}, persistir_estado=True)

    despesas = {d[0] for d in conn.execute("SELECT senador_id FROM despesas_senadores").fetchall()}
    assert despesas == {1, 2}  # falhava antes do fix: {1} (senador 2 nunca era inserido)


def test_rodada_completa_persiste_estado_e_pula_se_rechamada(conn):
    _add_senador(conn, 1)
    conn.commit()

    with patch("vigia_publico.ingestion.backfill_senado.ep.despesas_ceaps_ano", return_value=CEAPS_ANO[:1]) as mock_fetch:
        ingest_despesas_ano_senado(conn, client=None, ano=2024, senadores_validos={1}, persistir_estado=True)
        ingest_despesas_ano_senado(conn, client=None, ano=2024, senadores_validos={1}, persistir_estado=True)

    assert mock_fetch.call_count == 1  # segunda chamada pulou (ingest_state ja "concluido")
