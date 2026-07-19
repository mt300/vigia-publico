"""Gera um snapshot publico do banco (`public_data/vigia_publico_public.db`),
pronto pra ser commitado/versionado e servir o dashboard publico (Streamlit
Community Cloud). Diferente de `data/vigia_publico.db` (gitignorado), este
arquivo E git-tracked - so entra aqui o que e seguro publicar:

- Remove tabelas irrelevantes pro dashboard publico e mais pesadas
  (transcricao completa de discursos, cache de LLM, bookkeeping de ingestao).
- Anonimiza campos de contato/pessoais do deputado que nao servem ao
  proposito de transparencia de gasto/presenca (minimizacao - ver
  discussao no README sobre escopo de dado publico vs pessoal).
- Filtra `findings` para so os tipos puramente estatisticos elegiveis pra
  superficie publica (`detection.neutral_copy.TIPOS_PUBLICOS`) - achados
  derivados de LLM ou de natureza mais interpretativa ficam de fora.

`despesas`/`votos`/`deputado_historico` permanecem intactos: e o dado
central de interesse publico, e ja e publico via API da Camara.
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
from pathlib import Path

from vigia_publico.config import DB_PATH, PROJECT_ROOT
from vigia_publico.detection.neutral_copy import TIPOS_PUBLICOS

PUBLIC_DATA_DIR = PROJECT_ROOT / "public_data"
# .db (descompactado) e gitignorado - so serve pra teste local do app_public.py.
# .db.gz e o artefato de fato git-tracked/publicado: mesmo depois de tirar
# colunas de bookkeeping (ver _reduzir_despesas), o snapshot descompactado
# passa de 200 MB (649 mil linhas de despesas), acima do limite de arquivo do
# GitHub (100 MB) - o texto repetitivo (tipo_despesa, nome_fornecedor,
# url_documento) comprime ~5.5x, entao o .gz fica bem abaixo do limite.
PUBLIC_DB_PATH = PUBLIC_DATA_DIR / "vigia_publico_public.db"
PUBLIC_DB_GZ_PATH = PUBLIC_DATA_DIR / "vigia_publico_public.db.gz"

TABELAS_REMOVIDAS = ("discursos", "llm_discurso_cache", "ingest_state")


def _reduzir_despesas(dest: sqlite3.Connection) -> None:
    """Reconstroi `despesas` sem o `uid` (chave de dedupe da ingestao, sem
    valor publico) nem colunas de bookkeeping de documento fiscal (nao usadas
    por nenhuma consulta do dashboard/carrossel). `uid` sozinho e um PRIMARY
    KEY TEXT (nao inteiro), entao SQLite mantem um indice B-tree separado do
    tamanho da tabela pra ele - removendo a coluna (via rebuild, ja que
    `ALTER TABLE DROP COLUMN` nao permite dropar coluna de PRIMARY KEY)
    elimina esse indice inteiro. Isso e o que faz o snapshot caber no limite
    de tamanho de arquivo do GitHub (100 MB) - sem isso `despesas` sozinha
    passa de 250 MB (649 mil linhas) so de indice+bookkeeping irrelevante.
    """
    dest.execute(
        """
        CREATE TABLE despesas_public (
            deputado_id INTEGER NOT NULL,
            ano INTEGER,
            mes INTEGER,
            tipo_despesa TEXT,
            data_documento TEXT,
            nome_fornecedor TEXT,
            cnpj_cpf_fornecedor TEXT,
            valor_documento REAL,
            valor_liquido REAL,
            valor_glosa REAL,
            url_documento TEXT
        )
        """
    )
    dest.execute(
        """
        INSERT INTO despesas_public (
            deputado_id, ano, mes, tipo_despesa, data_documento,
            nome_fornecedor, cnpj_cpf_fornecedor, valor_documento, valor_liquido, valor_glosa, url_documento
        )
        SELECT deputado_id, ano, mes, tipo_despesa, data_documento,
               nome_fornecedor, cnpj_cpf_fornecedor, valor_documento, valor_liquido, valor_glosa, url_documento
        FROM despesas
        """
    )
    dest.execute("DROP TABLE despesas")
    dest.execute("ALTER TABLE despesas_public RENAME TO despesas")
    dest.execute("CREATE INDEX idx_despesas_dep_periodo ON despesas(deputado_id, ano, mes)")


def _reduzir_despesas_senadores(dest: sqlite3.Connection) -> None:
    """Mesmo tratamento de `_reduzir_despesas` (rebuild sem `uid`, elimina o
    indice B-tree do PRIMARY KEY TEXT), aplicado a `despesas_senadores`."""
    dest.execute(
        """
        CREATE TABLE despesas_senadores_public (
            senador_id INTEGER NOT NULL,
            ano INTEGER,
            mes INTEGER,
            tipo_despesa TEXT,
            data_documento TEXT,
            nome_fornecedor TEXT,
            cnpj_cpf_fornecedor TEXT,
            tipo_documento TEXT,
            num_documento TEXT,
            detalhamento TEXT,
            valor_reembolsado REAL
        )
        """
    )
    dest.execute(
        """
        INSERT INTO despesas_senadores_public (
            senador_id, ano, mes, tipo_despesa, data_documento,
            nome_fornecedor, cnpj_cpf_fornecedor, tipo_documento, num_documento, detalhamento, valor_reembolsado
        )
        SELECT senador_id, ano, mes, tipo_despesa, data_documento,
               nome_fornecedor, cnpj_cpf_fornecedor, tipo_documento, num_documento, detalhamento, valor_reembolsado
        FROM despesas_senadores
        """
    )
    dest.execute("DROP TABLE despesas_senadores")
    dest.execute("ALTER TABLE despesas_senadores_public RENAME TO despesas_senadores")
    dest.execute("CREATE INDEX idx_despesas_sen_periodo ON despesas_senadores(senador_id, ano, mes)")


def export_public_snapshot(source_db_path: Path = DB_PATH, output_path: Path = PUBLIC_DB_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)

    source = sqlite3.connect(f"file:{source_db_path}?mode=ro", uri=True)
    dest = sqlite3.connect(output_path)
    try:
        source.backup(dest)
    finally:
        source.close()

    dest.execute("PRAGMA foreign_keys = OFF")
    for tabela in TABELAS_REMOVIDAS:
        dest.execute(f"DROP TABLE IF EXISTS {tabela}")

    dest.execute(
        """
        UPDATE deputados SET
            cpf = NULL, email = NULL, data_nascimento = NULL,
            municipio_naturalidade = NULL, gabinete_sala = NULL,
            gabinete_predio = NULL, gabinete_andar = NULL, gabinete_telefone = NULL
        """
    )

    dest.execute("UPDATE senadores SET email = NULL")

    placeholders = ",".join("?" * len(TIPOS_PUBLICOS))
    dest.execute(f"DELETE FROM findings WHERE tipo NOT IN ({placeholders})", tuple(TIPOS_PUBLICOS))

    _reduzir_despesas(dest)
    _reduzir_despesas_senadores(dest)

    dest.commit()
    dest.execute("VACUUM")
    dest.commit()
    dest.close()

    gz_path = output_path.with_name(output_path.name + ".gz")
    with open(output_path, "rb") as f_in, gzip.open(gz_path, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

    return output_path


def ensure_decompressed(gz_path: Path = PUBLIC_DB_GZ_PATH, output_path: Path = PUBLIC_DB_PATH) -> Path:
    """Descompacta `gz_path` para `output_path` se ainda nao existir ou se o
    `.gz` for mais novo (redeploy com dado atualizado). Usado por
    `app_public.py` no boot do Streamlit Community Cloud, onde so o `.gz` e
    git-tracked."""
    if not output_path.exists() or gz_path.stat().st_mtime > output_path.stat().st_mtime:
        with gzip.open(gz_path, "rb") as f_in, open(output_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    return output_path
