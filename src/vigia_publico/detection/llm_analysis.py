"""Analise de discursos via API da Anthropic, em duas camadas para controlar custo.

Tier 1 (Haiku): todo discurso novo do mes -> resumo, topicos, teor.
Tier 2 (Sonnet): so quando ha discurso no mes -> compara com o historico de
votos do proprio deputado, sinaliza incoerencia e conteudo suspeito.

Controles de custo: cache por (discurso_uid, prompt_version) evita reprocessar
o que ja foi analisado com a versao atual do prompt; prompt caching no system
prompt (identico em todas as chamadas do mes); saida estruturada via JSON
Schema; estimativa de custo antes de rodar o lote, com teto configuravel.
"""

from __future__ import annotations

import json
import logging
import sqlite3

import anthropic

from vigia_publico.config import (
    ANTHROPIC_API_KEY,
    LLM_MODEL_TIER1_SUMMARY,
    LLM_MODEL_TIER2_ANALYSIS,
    LLM_MONTHLY_BUDGET_USD,
    LLM_PROMPT_VERSION,
)
from vigia_publico.db import repository as repo
from vigia_publico.detection.prompts import (
    TIER1_OUTPUT_SCHEMA,
    TIER1_SYSTEM_PROMPT,
    TIER2_OUTPUT_SCHEMA,
    TIER2_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

# Precos aproximados (USD por milhao de tokens) - conferir o preco vigente
# antes de rodar em producao, a Anthropic pode atualiza-los.
PRECO_POR_MTOK = {
    LLM_MODEL_TIER1_SUMMARY: {"input": 1.0, "output": 5.0},
    LLM_MODEL_TIER2_ANALYSIS: {"input": 3.0, "output": 15.0},
}

TIER1_PROMPT_VERSION = f"{LLM_PROMPT_VERSION}-tier1"
TIER2_PROMPT_VERSION = f"{LLM_PROMPT_VERSION}-tier2"

MAX_VOTOS_CONTEXTO = 30


def get_client() -> anthropic.Anthropic:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY nao configurada (veja .env.example)")
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def _cached_system(prompt: str) -> list[dict]:
    return [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]


def resumir_discurso(client: anthropic.Anthropic, texto: str) -> dict:
    response = client.messages.create(
        model=LLM_MODEL_TIER1_SUMMARY,
        max_tokens=1024,
        system=_cached_system(TIER1_SYSTEM_PROMPT),
        messages=[{"role": "user", "content": texto}],
        output_config={"format": {"type": "json_schema", "schema": TIER1_OUTPUT_SCHEMA}},
    )
    return _parse_json_response(response)


def _parse_json_response(response) -> dict:
    """Com `output_config.format=json_schema`, o bloco de texto final ja vem valido no schema."""
    texto = next(bloco.text for bloco in response.content if bloco.type == "text")
    return json.loads(texto)


def montar_contexto_votos(conn: sqlite3.Connection, deputado_id: int, ate_data: str, limite: int = MAX_VOTOS_CONTEXTO) -> str:
    linhas = conn.execute(
        """
        SELECT vt.data, vt.descricao, vo.voto
        FROM votos vo
        JOIN votacoes vt ON vt.id = vo.votacao_id
        WHERE vo.deputado_id = ? AND vt.data <= ?
        ORDER BY vt.data DESC
        LIMIT ?
        """,
        (deputado_id, ate_data, limite),
    ).fetchall()
    if not linhas:
        return "(sem votos registrados para este deputado ate a data do discurso)"
    return "\n".join(f"{row['data']} | {row['descricao']} | voto: {row['voto']}" for row in linhas)


def analisar_incoerencia(client: anthropic.Anthropic, texto: str, contexto_votos: str) -> dict:
    user_content = (
        f"TRANSCRICAO DO DISCURSO:\n{texto}\n\n"
        f"HISTORICO DE VOTOS RECENTES DO MESMO DEPUTADO (data | proposicao | voto):\n{contexto_votos}"
    )
    response = client.messages.create(
        model=LLM_MODEL_TIER2_ANALYSIS,
        max_tokens=2048,
        system=_cached_system(TIER2_SYSTEM_PROMPT),
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": TIER2_OUTPUT_SCHEMA}},
    )
    return _parse_json_response(response)


def estimar_tokens_lote(client: anthropic.Anthropic, discursos: list[sqlite3.Row]) -> int:
    total = 0
    for discurso in discursos:
        texto = discurso["transcricao"] or discurso["sumario"] or ""
        total += client.messages.count_tokens(
            model=LLM_MODEL_TIER1_SUMMARY,
            system=TIER1_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": texto}],
        ).input_tokens
    return total


def processar_discursos_mes(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    """Roda tier1+tier2 nos discursos do mes ainda nao cacheados. Retorna findings."""
    discursos = conn.execute(
        """
        SELECT uid, deputado_id, data_hora_inicio, sumario, transcricao, url_texto
        FROM discursos
        WHERE strftime('%Y-%m', data_hora_inicio) = ? AND transcricao IS NOT NULL AND transcricao != ''
        """,
        (mes_referencia,),
    ).fetchall()

    if not discursos:
        logger.info("Nenhum discurso com transcricao em %s.", mes_referencia)
        return []

    client = get_client()

    tokens_estimados = estimar_tokens_lote(client, discursos)
    custo_estimado = tokens_estimados / 1_000_000 * PRECO_POR_MTOK[LLM_MODEL_TIER1_SUMMARY]["input"]
    logger.info("Lote de %d discursos, ~%d tokens de entrada (tier1), custo estimado ~US$ %.2f", len(discursos), tokens_estimados, custo_estimado)
    if custo_estimado > LLM_MONTHLY_BUDGET_USD:
        logger.warning(
            "Estimativa de custo (US$ %.2f) excede o teto mensal configurado (US$ %.2f) - abortando analise de discursos.",
            custo_estimado,
            LLM_MONTHLY_BUDGET_USD,
        )
        return []

    findings = []
    for discurso in discursos:
        texto = discurso["transcricao"]

        tier1 = repo.get_llm_cache(conn, discurso["uid"], TIER1_PROMPT_VERSION)
        if tier1 is None:
            tier1 = resumir_discurso(client, texto)
            repo.set_llm_cache(conn, discurso["uid"], TIER1_PROMPT_VERSION, tier1, LLM_MODEL_TIER1_SUMMARY)
            conn.commit()

        tier2 = repo.get_llm_cache(conn, discurso["uid"], TIER2_PROMPT_VERSION)
        if tier2 is None:
            contexto_votos = montar_contexto_votos(conn, discurso["deputado_id"], discurso["data_hora_inicio"])
            tier2 = analisar_incoerencia(client, texto, contexto_votos)
            repo.set_llm_cache(conn, discurso["uid"], TIER2_PROMPT_VERSION, tier2, LLM_MODEL_TIER2_ANALYSIS)
            conn.commit()

        dados_suporte_base = {"resumo": tier1.get("resumo"), "topicos": tier1.get("topicos"), "teor": tier1.get("teor")}

        if tier2.get("incoerencia_flag"):
            findings.append(
                {
                    "deputado_id": discurso["deputado_id"],
                    "tipo": "DISCURSO_INCOERENTE",
                    "severidade": "media",
                    "descricao": tier2.get("incoerencia_explicacao") or "Possivel incoerencia entre discurso e voto (revisao humana necessaria).",
                    "dados_suporte": {**dados_suporte_base, "citacoes": tier2.get("incoerencia_citacoes")},
                    "fonte_url": discurso["url_texto"],
                }
            )
        if tier2.get("conteudo_suspeito_flag"):
            findings.append(
                {
                    "deputado_id": discurso["deputado_id"],
                    "tipo": "DISCURSO_CONTEUDO_SUSPEITO",
                    "severidade": "media",
                    "descricao": tier2.get("conteudo_suspeito_explicacao") or "Possivel conteudo contra interesse publico (revisao humana necessaria).",
                    "dados_suporte": {**dados_suporte_base, "citacoes": tier2.get("conteudo_suspeito_citacoes")},
                    "fonte_url": discurso["url_texto"],
                }
            )

    return findings
