"""CLI do vigia-publico: backfill | update | detect | report | run-all."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from vigia_publico.config import LOGS_DIR
from vigia_publico.db.connection import get_connection, run_migrations
from vigia_publico.ingestion.backfill import run_backfill
from vigia_publico.ingestion.backfill_senado import run_backfill_senado
from vigia_publico.ingestion.incremental import run_incremental
from vigia_publico.ingestion.incremental_senado import run_incremental_senado
from vigia_publico.orchestrator import run_all, run_detection, run_detection_senado
from vigia_publico.reporting.public_snapshot import export_public_snapshot
from vigia_publico.reporting.report_builder import build_report


def _configurar_logging() -> None:
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(LOGS_DIR / "vigia_publico.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    _configurar_logging()
    parser = argparse.ArgumentParser(prog="vigia-publico")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_backfill = subparsers.add_parser("backfill", help="Ingestao inicial: deputados atuais + historico completo de seus mandatos.")
    p_backfill.add_argument("--limite", type=int, default=None, help="Limita a N deputados/senadores (para testes).")
    p_backfill.add_argument("--casa", choices=["camara", "senado"], default="camara")

    p_update = subparsers.add_parser("update", help="Atualizacao incremental do mes de referencia.")
    p_update.add_argument("--ano", type=int, default=None)
    p_update.add_argument("--mes", type=int, default=None)
    p_update.add_argument("--casa", choices=["camara", "senado"], default="camara")

    p_detect = subparsers.add_parser("detect", help="Roda a deteccao de padroes suspeitos do mes de referencia.")
    p_detect.add_argument("--ano", type=int, default=None)
    p_detect.add_argument("--mes", type=int, default=None)
    p_detect.add_argument("--casa", choices=["camara", "senado"], default="camara")

    p_report = subparsers.add_parser("report", help="Gera o relatorio Markdown do mes de referencia.")
    p_report.add_argument("--mes-referencia", required=True, help="Formato YYYY-MM")

    subparsers.add_parser("run-all", help="update -> detect -> report, para o mes de referencia (padrao: mes anterior).")

    subparsers.add_parser(
        "export-public-snapshot",
        help="Gera public_data/vigia_publico_public.db (sem dados pessoais/achados interpretativos) para o dashboard publico.",
    )

    args = parser.parse_args()

    if args.comando == "backfill":
        if args.casa == "senado":
            run_backfill_senado(limite_senadores=args.limite)
        else:
            run_backfill(limite_deputados=args.limite)
    elif args.comando == "update":
        if args.casa == "senado":
            run_incremental_senado(args.ano)
        else:
            run_incremental(args.ano, args.mes)
    elif args.comando == "detect":
        if args.casa == "senado":
            run_detection_senado(ano=args.ano, mes=args.mes)
        else:
            run_detection(ano=args.ano, mes=args.mes)
    elif args.comando == "report":
        conn = get_connection()
        run_migrations(conn)
        caminho = build_report(conn, args.mes_referencia)
        conn.close()
        print(caminho)
    elif args.comando == "run-all":
        try:
            caminho = run_all()
            print(caminho)
        except Exception:
            logging.getLogger(__name__).exception("Pipeline mensal falhou.")
            sys.exit(1)
    elif args.comando == "export-public-snapshot":
        caminho = export_public_snapshot()
        print(caminho)


if __name__ == "__main__":
    main()
