"""Pipeline mensal: atualizacao incremental -> deteccao -> relatorio."""

from __future__ import annotations

import logging
from pathlib import Path

from vigia_publico.config import ANTHROPIC_API_KEY, DB_PATH
from vigia_publico.db import repository as repo
from vigia_publico.db.connection import get_connection, run_migrations
from vigia_publico.detection.llm_analysis import processar_discursos_mes
from vigia_publico.detection.statistical import rodar_regras_estatisticas
from vigia_publico.detection.statistical_senado import rodar_regras_estatisticas_senado
from vigia_publico.ingestion.incremental import mes_referencia_padrao, run_incremental
from vigia_publico.reporting.report_builder import build_report

logger = logging.getLogger(__name__)


def run_detection(db_path=DB_PATH, ano: int | None = None, mes: int | None = None) -> str:
    """Roda regras estatisticas + analise de discursos e grava os findings do mes.

    Reprocessamento: apaga os findings existentes do mes antes de reinserir -
    rodar de novo no mesmo mes regenera do zero, sem duplicar.
    """
    if ano is None or mes is None:
        ano, mes = mes_referencia_padrao()
    mes_referencia = f"{ano:04d}-{mes:02d}"

    conn = get_connection(db_path)
    run_migrations(conn)

    findings = rodar_regras_estatisticas(conn, mes_referencia)

    if ANTHROPIC_API_KEY:
        findings += processar_discursos_mes(conn, mes_referencia)
    else:
        logger.warning("ANTHROPIC_API_KEY nao configurada - pulando analise de discursos via LLM.")

    repo.clear_findings_for_month(conn, mes_referencia)
    for finding in findings:
        repo.insert_finding(
            conn,
            mes_referencia,
            finding["deputado_id"],
            finding["tipo"],
            finding.get("severidade", "media"),
            finding["descricao"],
            finding.get("dados_suporte"),
            finding.get("fonte_url"),
        )
    conn.commit()
    conn.close()

    logger.info("Deteccao de %s concluida: %d findings.", mes_referencia, len(findings))
    return mes_referencia


def run_detection_senado(db_path=DB_PATH, ano: int | None = None, mes: int | None = None) -> str:
    """Espelha `run_detection`, so que pras 5 regras de gasto do Senado
    (`statistical_senado.py`) - sem analise de discurso (fora de escopo do
    MVP, ver plano). `finding["senador_id"]` vira o `deputado_id` posicional
    de `insert_finding` (mesma coluna, sem FK, ver
    db/migrations/0002_senadores.sql) com `casa="senado"`."""
    if ano is None or mes is None:
        ano, mes = mes_referencia_padrao()
    mes_referencia = f"{ano:04d}-{mes:02d}"

    conn = get_connection(db_path)
    run_migrations(conn)

    findings = rodar_regras_estatisticas_senado(conn, mes_referencia)

    repo.clear_findings_for_month(conn, mes_referencia, casa="senado")
    for finding in findings:
        repo.insert_finding(
            conn,
            mes_referencia,
            finding["senador_id"],
            finding["tipo"],
            finding.get("severidade", "media"),
            finding["descricao"],
            finding.get("dados_suporte"),
            finding.get("fonte_url"),
            casa="senado",
        )
    conn.commit()
    conn.close()

    logger.info("Deteccao do Senado (%s) concluida: %d findings.", mes_referencia, len(findings))
    return mes_referencia


def run_all(db_path=DB_PATH, ano: int | None = None, mes: int | None = None) -> Path:
    ano, mes = run_incremental(ano, mes, db_path)
    mes_referencia = run_detection(db_path, ano, mes)

    conn = get_connection(db_path)
    caminho_relatorio = build_report(conn, mes_referencia)
    conn.close()

    logger.info("Pipeline mensal concluido. Relatorio em %s", caminho_relatorio)
    return caminho_relatorio
