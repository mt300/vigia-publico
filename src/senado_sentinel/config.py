"""Configuracao central do projeto: paths, thresholds e parametros de LLM."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "db" / "migrations"

DB_PATH = DATA_DIR / "senado_sentinel.db"

CAMARA_API_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
CAMARA_API_REQUESTS_PER_SECOND = 4

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
LLM_MONTHLY_BUDGET_USD = float(os.environ.get("LLM_MONTHLY_BUDGET_USD", "10"))

LLM_MODEL_TIER1_SUMMARY = "claude-haiku-4-5"
LLM_MODEL_TIER2_ANALYSIS = "claude-sonnet-5"
LLM_PROMPT_VERSION = "v1"

# Regras estatisticas: limiares padrao (podem ser ajustados sem mudar codigo)
GASTO_ZSCORE_LIMIAR = 2.5
FALTA_INJUSTIFICADA_TAXA_LIMIAR = 0.3

# Depois de tantas falhas seguidas numa unidade de trabalho (ex: despesas de um
# deputado num ano), para de retentar automaticamente a cada rodada - alguns
# registros da API publica falham de forma persistente (nao transitoria), e
# sem esse limite o backfill gastaria minutos retentando o mesmo item toda vez
# que fosse resumido, indefinidamente.
INGEST_MAX_TENTATIVAS = 3

for _dir in (DATA_DIR, LOGS_DIR, REPORTS_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
