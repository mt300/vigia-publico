"""Ingestao inicial (backfill): deputados atuais + historico de seus mandatos.

Escopo: os ~512 deputados EM EXERCICIO agora (endpoint `/deputados` sem filtro),
e para cada um deles, despesas/discursos/votos de TODAS as legislaturas em que
ja atuaram (nao de todo mundo que ja passou pela Camara - isso seria uma ordem
de grandeza maior e nao e o que foi pedido). As legislaturas de cada deputado
sao descobertas via `/deputados/{id}/historico`, que ja cobre a timeline
completa (todas as legislaturas), sem necessidade de cruzar listas.

Resumivel: cada unidade de trabalho (despesas de um deputado num ano, discursos
de um deputado num ano, votacoes de uma legislatura num ano) e registrada em
`ingest_state`; rodar de novo pula o que ja esta `concluido`.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3

import httpx

from senado_sentinel.camara_api import endpoints as ep
from senado_sentinel.camara_api.client import CamaraApiClient
from senado_sentinel.config import DB_PATH
from senado_sentinel.db import repository as repo
from senado_sentinel.db.connection import get_connection, run_migrations

logger = logging.getLogger(__name__)

# Legislatura 53 comecou em 2007-02-01, pouco antes da CEAP (cota parlamentar,
# vigente desde 2009) existir. Nao ha necessidade de ir mais para tras: e o
# limite pratico de dados financeiros comparaveis.
LEGISLATURA_MINIMA_ID = 53

ID_ORGAO_PLENARIO_VIRTUAL = 180


def _anos_da_legislatura(legislatura: dict) -> list[int]:
    """Recebe um dict de legislatura no formato bruto da API (dataInicio/dataFim)."""
    ano_inicio = int(legislatura["dataInicio"][:4])
    data_fim = legislatura.get("dataFim") or dt.date.today().isoformat()
    ano_fim = min(int(data_fim[:4]), dt.date.today().year)
    return list(range(ano_inicio, ano_fim + 1))


def ingest_despesas_ano(conn: sqlite3.Connection, client: CamaraApiClient, deputado_id: int, ano: int) -> None:
    chave = str(ano)
    if repo.ingest_deve_pular(conn, "despesas", deputado_id, chave):
        return
    try:
        itens = ep.despesas_deputado(client, deputado_id, ano)
        for item in itens:
            repo.upsert_despesa(conn, deputado_id, item)
        repo.mark_ingest_state(conn, "despesas", deputado_id, chave, "concluido")
    except Exception as exc:  # noqa: BLE001 - falha isolada, nao aborta o backfill inteiro
        logger.warning("Falha ao ingerir despesas deputado=%s ano=%s: %s", deputado_id, ano, exc)
        repo.mark_ingest_state(conn, "despesas", deputado_id, chave, "erro", str(exc))
    conn.commit()


def ingest_discursos_ano(conn: sqlite3.Connection, client: CamaraApiClient, deputado_id: int, ano: int) -> None:
    chave = str(ano)
    if repo.ingest_deve_pular(conn, "discursos", deputado_id, chave):
        return
    try:
        itens = ep.discursos_deputado(client, deputado_id, f"{ano}-01-01", f"{ano}-12-31")
        for item in itens:
            repo.upsert_discurso(conn, deputado_id, item)
        repo.mark_ingest_state(conn, "discursos", deputado_id, chave, "concluido")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao ingerir discursos deputado=%s ano=%s: %s", deputado_id, ano, exc)
        repo.mark_ingest_state(conn, "discursos", deputado_id, chave, "erro", str(exc))
    conn.commit()


# /votacoes rejeita com 400 intervalos de data acima de ~3 meses -> varre por trimestre.
_TRIMESTRES = [("01-01", "03-31"), ("04-01", "06-30"), ("07-01", "09-30"), ("10-01", "12-31")]


def ingest_votacoes_ano(
    conn: sqlite3.Connection,
    client: CamaraApiClient,
    legislatura_id: int,
    ano: int,
    deputados_alvo: set[int],
) -> None:
    """Ingere votacoes do Plenario Virtual num ano e os votos dos deputados_alvo.

    So registra o voto de quem esta em `deputados_alvo` (nossos deputados
    atuais) - quem nao aparece na lista de votos de uma votacao e considerado
    ausente por exclusao (a API nao expoe motivo de ausencia, ver docs/spike).
    """
    for i, (inicio, fim) in enumerate(_TRIMESTRES, start=1):
        chave = f"{legislatura_id}-{ano}-Q{i}"
        # A cobertura e rastreada POR DEPUTADO (nao um flag global do trimestre):
        # se o conjunto-alvo cresceu desde a ultima rodada (ex: teste com poucos
        # deputados -> backfill completo), os novos precisam ser cobertos mesmo
        # que o trimestre ja tenha sido buscado antes.
        pendentes = deputados_alvo - repo.ingest_state_cobertos(conn, "votacoes", chave)
        if not pendentes:
            continue
        try:
            votacoes = ep.listar_votacoes(
                client, f"{ano}-{inicio}", f"{ano}-{fim}", id_orgao=ID_ORGAO_PLENARIO_VIRTUAL
            )
            for votacao in votacoes:
                repo.upsert_votacao(conn, votacao)
                try:
                    votos = ep.votos_votacao(client, votacao["id"])
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        # Votacao simbolica/unanime: a API nao tem votos individuais
                        # para registrar (nao ha erro real, so nao ha o que listar).
                        continue
                    raise
                for voto in votos:
                    deputado = voto.get("deputado_") or {}
                    dep_id = deputado.get("id")
                    if dep_id in deputados_alvo:
                        repo.upsert_voto(conn, votacao["id"], dep_id, voto.get("tipoVoto"), None)
            # A busca cobre TODOS os deputados_alvo de uma vez (o custo de API
            # nao muda com o tamanho do conjunto-alvo) - marca o conjunto inteiro.
            for dep_id in deputados_alvo:
                repo.mark_ingest_state(conn, "votacoes", dep_id, chave, "concluido")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao ingerir votacoes legislatura=%s chave=%s: %s", legislatura_id, chave, exc)
            for dep_id in pendentes:
                repo.mark_ingest_state(conn, "votacoes", dep_id, chave, "erro", str(exc))
        conn.commit()


def ingest_perfil_e_historico(conn: sqlite3.Connection, client: CamaraApiClient, deputado_id: int) -> list[dict]:
    """Ingere perfil + timeline do deputado. Retorna as legislaturas (id) em que ele atuou."""
    perfil = ep.detalhe_deputado(client, deputado_id)
    repo.upsert_deputado(conn, perfil)
    repo.upsert_deputado_redes_sociais(conn, deputado_id, perfil.get("redeSocial"))
    conn.commit()

    historico = ep.historico_deputado(client, deputado_id)
    legislaturas_ids = set()
    for item in historico:
        legislatura_id = item.get("idLegislatura")
        legislaturas_ids.add(legislatura_id)
        repo.upsert_deputado_historico(conn, deputado_id, legislatura_id, item)
    conn.commit()
    return sorted(legislaturas_ids)


def run_backfill(db_path=DB_PATH, limite_deputados: int | None = None) -> None:
    """`limite_deputados` restringe a quantos deputados processar - util para
    validar o pipeline num subconjunto pequeno antes de rodar o backfill completo."""
    conn = get_connection(db_path)
    run_migrations(conn)

    with CamaraApiClient() as client:
        logger.info("Buscando legislaturas...")
        legislaturas = ep.listar_legislaturas(client)
        for legislatura in legislaturas:
            repo.upsert_legislatura(conn, legislatura)
        conn.commit()
        legislaturas_por_id = {leg["id"]: leg for leg in legislaturas}

        logger.info("Buscando deputados atuais...")
        deputados_atuais = ep.listar_deputados(client)
        if limite_deputados is not None:
            deputados_atuais = deputados_atuais[:limite_deputados]
        deputados_ids = {d["id"] for d in deputados_atuais}
        logger.info("%d deputados atuais encontrados", len(deputados_ids))

        for i, deputado_basico in enumerate(deputados_atuais, start=1):
            deputado_id = deputado_basico["id"]
            logger.info("[%d/%d] Deputado %s (%s)", i, len(deputados_ids), deputado_basico["nome"], deputado_id)

            try:
                legislaturas_ids = ingest_perfil_e_historico(conn, client, deputado_id)
            except Exception as exc:  # noqa: BLE001 - falha isolada, nao aborta o backfill inteiro
                logger.warning("Falha ao ingerir perfil/historico do deputado=%s: %s", deputado_id, exc)
                repo.mark_ingest_state(conn, "perfil", deputado_id, "perfil", "erro", str(exc))
                continue

            anos = sorted(
                {
                    ano
                    for leg_id in legislaturas_ids
                    if leg_id in legislaturas_por_id
                    for ano in _anos_da_legislatura(legislaturas_por_id[leg_id])
                }
            )
            for ano in anos:
                ingest_despesas_ano(conn, client, deputado_id, ano)
                ingest_discursos_ano(conn, client, deputado_id, ano)

        logger.info("Ingerindo votacoes/votos por legislatura...")
        legislaturas_relevantes = [leg for leg in legislaturas if leg["id"] >= LEGISLATURA_MINIMA_ID]
        for legislatura in legislaturas_relevantes:
            for ano in _anos_da_legislatura(legislatura):
                ingest_votacoes_ano(conn, client, legislatura["id"], ano, deputados_ids)

    conn.close()
    logger.info("Backfill concluido.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_backfill()
