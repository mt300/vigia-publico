"""CLI do senado-sentinel: backfill | update | detect | report | run-all."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from senado_sentinel.config import LOGS_DIR
from senado_sentinel.db.connection import get_connection, run_migrations
from senado_sentinel.ingestion.backfill import run_backfill
from senado_sentinel.ingestion.incremental import run_incremental
from senado_sentinel.orchestrator import run_all, run_detection
from senado_sentinel.reporting.report_builder import build_report


def _configurar_logging() -> None:
    handlers = [
        logging.StreamHandler(),
        RotatingFileHandler(LOGS_DIR / "senado_sentinel.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"),
    ]
    logging.basicConfig(level=logging.INFO, handlers=handlers, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    _configurar_logging()
    parser = argparse.ArgumentParser(prog="senado-sentinel")
    subparsers = parser.add_subparsers(dest="comando", required=True)

    p_backfill = subparsers.add_parser("backfill", help="Ingestao inicial: deputados atuais + historico completo de seus mandatos.")
    p_backfill.add_argument("--limite", type=int, default=None, help="Limita a N deputados (para testes).")

    p_update = subparsers.add_parser("update", help="Atualizacao incremental do mes de referencia.")
    p_update.add_argument("--ano", type=int, default=None)
    p_update.add_argument("--mes", type=int, default=None)

    p_detect = subparsers.add_parser("detect", help="Roda a deteccao de padroes suspeitos do mes de referencia.")
    p_detect.add_argument("--ano", type=int, default=None)
    p_detect.add_argument("--mes", type=int, default=None)

    p_report = subparsers.add_parser("report", help="Gera o relatorio Markdown do mes de referencia.")
    p_report.add_argument("--mes-referencia", required=True, help="Formato YYYY-MM")

    subparsers.add_parser("run-all", help="update -> detect -> report, para o mes de referencia (padrao: mes anterior).")

    args = parser.parse_args()

    if args.comando == "backfill":
        run_backfill(limite_deputados=args.limite)
    elif args.comando == "update":
        run_incremental(args.ano, args.mes)
    elif args.comando == "detect":
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


if __name__ == "__main__":
    main()
