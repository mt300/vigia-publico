import sqlite3

import pytest

from vigia_publico.db.connection import run_migrations


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    run_migrations(connection)
    yield connection
    connection.close()
