"""Ingestao inicial (backfill) de senadores + despesas CEAPS.

Escopo: os ~81 senadores EM EXERCICIO agora (endpoint `/senador/lista/atual`),
e para cada um, despesas CEAPS desde o inicio pratico dos dados comparaveis
(`ANO_MINIMO`). Diferente da Camara (uma chamada por deputado por ano), o
CEAPS devolve TODOS os senadores de um ano numa chamada so (confirmado num
spike real) - o loop e por ano, nao por senador.

Resumivel: cada ano de despesas fica registrado em `ingest_state`
(entidade="despesas_senado", chave=str(ano), deputado_id=0 sentinel - a
unidade de trabalho nao e por senador, mesmo padrao ja usado em
`ingestion/backfill.py` pra votacoes).
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3

from vigia_publico.config import DB_PATH
from vigia_publico.db import repository as repo
from vigia_publico.db.connection import get_connection, run_migrations
from vigia_publico.senado_api import endpoints as ep
from vigia_publico.senado_api.client import SenadoApiClient

logger = logging.getLogger(__name__)

# CEAPS tem dado comparavel a partir de ~2009 (mesma epoca da CEAP da
# Camara, ver LEGISLATURA_MINIMA_ID em backfill.py) - o Senado nao tem o
# conceito de "legislatura minima" do jeito que a ingestao da Camara usa,
# entao aqui e um ano direto.
ANO_MINIMO = 2009


def ingest_despesas_ano_senado(
    conn: sqlite3.Connection,
    client: SenadoApiClient,
    ano: int,
    senadores_validos: set[int],
    *,
    persistir_estado: bool = True,
) -> None:
    """`persistir_estado=False` (usado por `limite_senadores`, ver abaixo)
    processa o ano sem ler nem gravar `ingest_state` - uma rodada limitada
    (`senadores_validos` e so um subconjunto) NAO pode marcar o ano como
    "concluido", senao uma rodada completa posterior pularia o ano inteiro
    pensando que ja foi feito, e a maioria dos senadores nunca teria suas
    despesas inseridas. Bug real, reproduzido: `backfill --casa senado
    --limite 5` seguido de `backfill --casa senado` (sem limite) - o segundo
    comando nao inseria nada, porque achava que todo ano ja estava
    `concluido` (do primeiro comando, que so viu 5 senadores validos)."""
    chave = str(ano)
    if persistir_estado and repo.ingest_deve_pular(conn, "despesas_senado", None, chave):
        return
    try:
        itens = ep.despesas_ceaps_ano(client, ano)
        ignorados = 0
        for item in itens:
            senador_id = item.get("codSenador")
            if senador_id not in senadores_validos:
                # codSenador de quem ja nao esta na lista atual (suplente
                # trocado, mandato encerrado etc) - mesmo criterio "so quem
                # esta em exercicio agora" que a Camara ja usa (ver README).
                ignorados += 1
                continue
            repo.upsert_despesa_senador(conn, senador_id, item)
        if ignorados:
            logger.info("Ano %s: %d despesas ignoradas (senador fora da lista atual)", ano, ignorados)
        if persistir_estado:
            repo.mark_ingest_state(conn, "despesas_senado", None, chave, "concluido")
    except Exception as exc:  # noqa: BLE001 - falha isolada, nao aborta o backfill inteiro
        logger.warning("Falha ao ingerir despesas do Senado ano=%s: %s", ano, exc)
        if persistir_estado:
            repo.mark_ingest_state(conn, "despesas_senado", None, chave, "erro", str(exc))
    conn.commit()


def run_backfill_senado(db_path=DB_PATH, limite_senadores: int | None = None) -> None:
    """`limite_senadores` restringe a quantos senadores processar - util pra
    validar o pipeline num subconjunto pequeno (mesmo espirito de
    `limite_deputados` em `ingestion/backfill.py`). Diferente da Camara (onde
    a unidade de trabalho de `ingest_state` ja e por-deputado, entao um limite
    naturalmente so afeta quem entra), a unidade de trabalho do Senado e
    por-ANO (todos os senadores vem numa chamada so - ver docstring do
    modulo) - por isso uma rodada limitada nunca persiste `ingest_state`
    (`persistir_estado=False` abaixo), pra nao "queimar" o ano como
    concluido baseado num universo parcial de senadores validos.
    """
    conn = get_connection(db_path)
    run_migrations(conn)

    with SenadoApiClient() as client:
        logger.info("Buscando senadores atuais...")
        senadores = ep.listar_senadores_atuais(client)
        if limite_senadores is not None:
            senadores = senadores[:limite_senadores]
        for identificacao in senadores:
            repo.upsert_senador(conn, identificacao)
        conn.commit()
        senadores_validos = {int(s["CodigoParlamentar"]) for s in senadores}
        logger.info("%d senadores atuais encontrados", len(senadores_validos))

        persistir_estado = limite_senadores is None
        ano_atual = dt.date.today().year
        for ano in range(ANO_MINIMO, ano_atual + 1):
            logger.info("Ingerindo despesas CEAPS do ano %s...", ano)
            ingest_despesas_ano_senado(conn, client, ano, senadores_validos, persistir_estado=persistir_estado)

    conn.close()
    logger.info("Backfill do Senado concluido.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backfill_senado()
