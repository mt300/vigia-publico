"""Conexao com o SQLite e runner de migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from vigia_publico.config import DB_PATH, MIGRATIONS_DIR


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica em ordem os arquivos .sql de migrations_dir ainda nao registrados.

    Idempotente: rodar de novo so aplica o que falta.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()

    applied = {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}
    pending = sorted(p for p in migrations_dir.glob("*.sql") if p.name not in applied)

    newly_applied = []
    for path in pending:
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
        conn.commit()
        newly_applied.append(path.name)

    return newly_applied
