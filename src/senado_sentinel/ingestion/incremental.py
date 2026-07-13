"""Atualizacao mensal incremental: so o mes de referencia, para deputados em exercicio.

Detecta deputados novos/afastados (comparando o roster atual com o que ja
esta no banco) e busca despesas/discursos/votacoes apenas do mes de referencia
(por padrao, o mes anterior ao atual - o mes corrente ainda tem dados
incompletos na API).
"""

from __future__ import annotations

import calendar
import datetime as dt
import logging
import sqlite3

import httpx

from senado_sentinel.camara_api import endpoints as ep
from senado_sentinel.camara_api.client import CamaraApiClient
from senado_sentinel.config import DB_PATH
from senado_sentinel.db import repository as repo
from senado_sentinel.db.connection import get_connection, run_migrations
from senado_sentinel.ingestion.backfill import ID_ORGAO_PLENARIO_VIRTUAL, ingest_perfil_e_historico

logger = logging.getLogger(__name__)


def mes_referencia_padrao(hoje: dt.date | None = None) -> tuple[int, int]:
    """O mes anterior ao atual - o mes corrente ainda tem dados incompletos na API."""
    hoje = hoje or dt.date.today()
    primeiro_dia_mes_atual = hoje.replace(day=1)
    ultimo_dia_mes_anterior = primeiro_dia_mes_atual - dt.timedelta(days=1)
    return ultimo_dia_mes_anterior.year, ultimo_dia_mes_anterior.month


def sincronizar_roster(conn: sqlite3.Connection, client: CamaraApiClient) -> set[int]:
    """Atualiza perfil/historico de todos os deputados em exercicio (novos e existentes).

    Retorna o conjunto de ids em exercicio agora.
    """
    deputados_atuais = ep.listar_deputados(client)
    ids_atuais = {d["id"] for d in deputados_atuais}

    ids_conhecidos = {row["id"] for row in conn.execute("SELECT id FROM deputados")}
    novos = ids_atuais - ids_conhecidos
    afastados = ids_conhecidos - ids_atuais
    if novos:
        logger.info("Deputados novos detectados: %s", sorted(novos))
    if afastados:
        logger.info("Deputados que deixaram de constar como em exercicio: %s", sorted(afastados))

    for deputado_id in ids_atuais:
        try:
            ingest_perfil_e_historico(conn, client, deputado_id)
        except Exception as exc:  # noqa: BLE001 - falha isolada, nao aborta a atualizacao inteira
            logger.warning("Falha ao ingerir perfil/historico do deputado=%s: %s", deputado_id, exc)
            repo.mark_ingest_state(conn, "perfil", deputado_id, "perfil", "erro", str(exc))

    return ids_atuais


def ingest_despesas_mes(conn: sqlite3.Connection, client: CamaraApiClient, deputado_id: int, ano: int, mes: int) -> None:
    chave = f"{ano}-{mes:02d}"
    if repo.ingest_deve_pular(conn, "despesas_mensal", deputado_id, chave):
        return
    try:
        itens = ep.despesas_deputado(client, deputado_id, ano, mes)
        for item in itens:
            repo.upsert_despesa(conn, deputado_id, item)
        repo.mark_ingest_state(conn, "despesas_mensal", deputado_id, chave, "concluido")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao atualizar despesas deputado=%s mes=%s: %s", deputado_id, chave, exc)
        repo.mark_ingest_state(conn, "despesas_mensal", deputado_id, chave, "erro", str(exc))
    conn.commit()


def ingest_discursos_mes(conn: sqlite3.Connection, client: CamaraApiClient, deputado_id: int, ano: int, mes: int) -> None:
    chave = f"{ano}-{mes:02d}"
    if repo.ingest_deve_pular(conn, "discursos_mensal", deputado_id, chave):
        return
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    try:
        itens = ep.discursos_deputado(client, deputado_id, f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-{ultimo_dia}")
        for item in itens:
            repo.upsert_discurso(conn, deputado_id, item)
        repo.mark_ingest_state(conn, "discursos_mensal", deputado_id, chave, "concluido")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao atualizar discursos deputado=%s mes=%s: %s", deputado_id, chave, exc)
        repo.mark_ingest_state(conn, "discursos_mensal", deputado_id, chave, "erro", str(exc))
    conn.commit()


def ingest_votacoes_mes(
    conn: sqlite3.Connection, client: CamaraApiClient, ano: int, mes: int, deputados_alvo: set[int]
) -> None:
    chave = f"{ano}-{mes:02d}"
    # Cobertura por deputado (nao um flag global do mes) - mesma razao do backfill:
    # se o conjunto-alvo mudou (ex: deputado novo por substituicao), ele precisa
    # ser coberto mesmo que o mes ja tenha sido buscado antes para os demais.
    pendentes = deputados_alvo - repo.ingest_state_cobertos(conn, "votacoes_mensal", chave)
    if not pendentes:
        return
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    try:
        votacoes = ep.listar_votacoes(
            client, f"{ano}-{mes:02d}-01", f"{ano}-{mes:02d}-{ultimo_dia}", id_orgao=ID_ORGAO_PLENARIO_VIRTUAL
        )
        for votacao in votacoes:
            repo.upsert_votacao(conn, votacao)
            try:
                votos = ep.votos_votacao(client, votacao["id"])
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    continue
                raise
            for voto in votos:
                deputado = voto.get("deputado_") or {}
                dep_id = deputado.get("id")
                if dep_id in deputados_alvo:
                    repo.upsert_voto(conn, votacao["id"], dep_id, voto.get("tipoVoto"), None)
        for dep_id in deputados_alvo:
            repo.mark_ingest_state(conn, "votacoes_mensal", dep_id, chave, "concluido")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao atualizar votacoes mes=%s: %s", chave, exc)
        for dep_id in pendentes:
            repo.mark_ingest_state(conn, "votacoes_mensal", dep_id, chave, "erro", str(exc))
    conn.commit()


def run_incremental(ano: int | None = None, mes: int | None = None, db_path=DB_PATH) -> tuple[int, int]:
    """Roda a atualizacao incremental para o mes de referencia (padrao: mes anterior)."""
    if ano is None or mes is None:
        ano, mes = mes_referencia_padrao()
    logger.info("Atualizacao incremental para %04d-%02d", ano, mes)

    conn = get_connection(db_path)
    run_migrations(conn)

    with CamaraApiClient() as client:
        for legislatura in ep.listar_legislaturas(client):
            repo.upsert_legislatura(conn, legislatura)
        conn.commit()

        ids_atuais = sincronizar_roster(conn, client)

        for i, deputado_id in enumerate(sorted(ids_atuais), start=1):
            logger.info("[%d/%d] deputado %s: despesas/discursos de %04d-%02d", i, len(ids_atuais), deputado_id, ano, mes)
            ingest_despesas_mes(conn, client, deputado_id, ano, mes)
            ingest_discursos_mes(conn, client, deputado_id, ano, mes)

        ingest_votacoes_mes(conn, client, ano, mes, ids_atuais)

    conn.close()
    logger.info("Atualizacao incremental de %04d-%02d concluida.", ano, mes)
    return ano, mes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_incremental()
