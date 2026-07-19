"""Atualizacao incremental de senadores + despesas CEAPS.

O CEAPS nao parece filtrar por mes, so por ano (confirmado no spike da Fase
0) - "incremental" aqui significa re-buscar o ano CORRENTE inteiro, nao um
delta por mes. Seguro: o upsert e idempotente por `uid`, so um pouco
redundante em banda (o ano inteiro tem ~20 mil registros, não é pesado).
"""

from __future__ import annotations

import datetime as dt
import logging

from vigia_publico.config import DB_PATH
from vigia_publico.db import repository as repo
from vigia_publico.db.connection import get_connection, run_migrations
from vigia_publico.ingestion.backfill_senado import ingest_despesas_ano_senado
from vigia_publico.senado_api import endpoints as ep
from vigia_publico.senado_api.client import SenadoApiClient

logger = logging.getLogger(__name__)


def run_incremental_senado(ano: int | None = None, db_path=DB_PATH) -> int:
    ano = ano or dt.date.today().year

    conn = get_connection(db_path)
    run_migrations(conn)

    with SenadoApiClient() as client:
        senadores = ep.listar_senadores_atuais(client)
        for identificacao in senadores:
            repo.upsert_senador(conn, identificacao)
        conn.commit()
        senadores_validos = {int(s["CodigoParlamentar"]) for s in senadores}

        # Limpa o estado desse ano antes de rechamar - senao
        # `ingest_deve_pular` pularia por já estar "concluido" do backfill
        # (ou de uma rodada incremental anterior), e a atualizacao nunca
        # pegaria despesa nova lancada depois da ultima rodada.
        conn.execute("DELETE FROM ingest_state WHERE entidade = 'despesas_senado' AND chave = ?", (str(ano),))
        conn.commit()
        ingest_despesas_ano_senado(conn, client, ano, senadores_validos)

    conn.close()
    logger.info("Atualizacao incremental do Senado (ano %s) concluida.", ano)
    return ano


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_incremental_senado()
