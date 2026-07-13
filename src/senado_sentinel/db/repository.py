"""Camada de acesso a dados: upserts idempotentes por entidade.

Dados brutos da API (despesas, discursos, votos, historico) usam uma chave
natural ou um `uid` sintetico (hash dos campos estaveis) com
`INSERT ... ON CONFLICT DO UPDATE`, entao rodar a ingestao de novo nunca duplica.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from typing import Any

from senado_sentinel.config import INGEST_MAX_TENTATIVAS


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _hash(*parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- legislaturas -----------------------------------------------------------


def upsert_legislatura(conn: sqlite3.Connection, dado: dict) -> None:
    conn.execute(
        """
        INSERT INTO legislaturas (id, data_inicio, data_fim)
        VALUES (:id, :dataInicio, :dataFim)
        ON CONFLICT (id) DO UPDATE SET
            data_inicio = excluded.data_inicio,
            data_fim = excluded.data_fim
        """,
        dado,
    )


# --- deputados ---------------------------------------------------------------


def upsert_deputado(conn: sqlite3.Connection, perfil: dict) -> None:
    ultimo_status = perfil.get("ultimoStatus", {})
    gabinete = ultimo_status.get("gabinete", {}) or {}

    conn.execute(
        """
        INSERT INTO deputados (
            id, nome_civil, nome_eleitoral, cpf, data_nascimento,
            uf_naturalidade, municipio_naturalidade, sexo, escolaridade, url_foto,
            sigla_partido, sigla_uf, situacao, condicao_eleitoral, email,
            gabinete_sala, gabinete_predio, gabinete_andar, gabinete_telefone,
            legislatura_atual_id, atualizado_em
        ) VALUES (
            :id, :nome_civil, :nome_eleitoral, :cpf, :data_nascimento,
            :uf_naturalidade, :municipio_naturalidade, :sexo, :escolaridade, :url_foto,
            :sigla_partido, :sigla_uf, :situacao, :condicao_eleitoral, :email,
            :gabinete_sala, :gabinete_predio, :gabinete_andar, :gabinete_telefone,
            :legislatura_atual_id, :atualizado_em
        )
        ON CONFLICT (id) DO UPDATE SET
            nome_civil = excluded.nome_civil,
            nome_eleitoral = excluded.nome_eleitoral,
            cpf = excluded.cpf,
            data_nascimento = excluded.data_nascimento,
            uf_naturalidade = excluded.uf_naturalidade,
            municipio_naturalidade = excluded.municipio_naturalidade,
            sexo = excluded.sexo,
            escolaridade = excluded.escolaridade,
            url_foto = excluded.url_foto,
            sigla_partido = excluded.sigla_partido,
            sigla_uf = excluded.sigla_uf,
            situacao = excluded.situacao,
            condicao_eleitoral = excluded.condicao_eleitoral,
            email = excluded.email,
            gabinete_sala = excluded.gabinete_sala,
            gabinete_predio = excluded.gabinete_predio,
            gabinete_andar = excluded.gabinete_andar,
            gabinete_telefone = excluded.gabinete_telefone,
            legislatura_atual_id = excluded.legislatura_atual_id,
            atualizado_em = excluded.atualizado_em
        """,
        {
            "id": perfil["id"],
            "nome_civil": perfil.get("nomeCivil") or perfil.get("nome"),
            "nome_eleitoral": perfil.get("ultimoStatus", {}).get("nomeEleitoral") or perfil.get("nome"),
            "cpf": perfil.get("cpf"),
            "data_nascimento": perfil.get("dataNascimento"),
            "uf_naturalidade": perfil.get("ufNascimento"),
            "municipio_naturalidade": perfil.get("municipioNascimento"),
            "sexo": perfil.get("sexo"),
            "escolaridade": perfil.get("escolaridade"),
            "url_foto": ultimo_status.get("urlFoto") or perfil.get("urlFoto"),
            "sigla_partido": ultimo_status.get("siglaPartido"),
            "sigla_uf": ultimo_status.get("siglaUf"),
            "situacao": ultimo_status.get("situacao"),
            "condicao_eleitoral": ultimo_status.get("condicaoEleitoral"),
            "email": gabinete.get("email") or ultimo_status.get("email"),
            "gabinete_sala": gabinete.get("sala"),
            "gabinete_predio": gabinete.get("predio"),
            "gabinete_andar": gabinete.get("andar"),
            "gabinete_telefone": gabinete.get("telefone"),
            "legislatura_atual_id": ultimo_status.get("idLegislatura"),
            "atualizado_em": _now(),
        },
    )


def upsert_deputado_redes_sociais(conn: sqlite3.Connection, deputado_id: int, redes: list[str]) -> None:
    for url in redes or []:
        rede = _identificar_rede(url)
        conn.execute(
            """
            INSERT INTO deputado_redes_sociais (deputado_id, rede, url)
            VALUES (?, ?, ?)
            ON CONFLICT (deputado_id, url) DO UPDATE SET rede = excluded.rede
            """,
            (deputado_id, rede, url),
        )


def _identificar_rede(url: str) -> str:
    url_lower = url.lower()
    for rede in ("twitter", "x.com", "facebook", "instagram", "youtube", "tiktok"):
        if rede in url_lower:
            return "twitter" if rede == "x.com" else rede
    return "outro"


def upsert_deputado_historico(conn: sqlite3.Connection, deputado_id: int, legislatura_id: int, item: dict) -> None:
    conn.execute(
        """
        INSERT INTO deputado_historico (
            deputado_id, legislatura_id, data_hora, situacao,
            condicao_eleitoral, sigla_partido, descricao_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (deputado_id, legislatura_id, data_hora, sigla_partido) DO UPDATE SET
            situacao = excluded.situacao,
            condicao_eleitoral = excluded.condicao_eleitoral,
            descricao_status = excluded.descricao_status
        """,
        (
            deputado_id,
            legislatura_id,
            item.get("dataHora"),
            item.get("situacao"),
            item.get("condicaoEleitoral"),
            item.get("siglaPartido"),
            item.get("descricaoStatus"),
        ),
    )


# --- despesas ------------------------------------------------------------


def despesa_uid(deputado_id: int, item: dict) -> str:
    return _hash(
        deputado_id,
        item.get("ano"),
        item.get("mes"),
        item.get("codDocumento"),
        item.get("numDocumento"),
        item.get("dataDocumento"),
        item.get("valorDocumento"),
    )


def upsert_despesa(conn: sqlite3.Connection, deputado_id: int, item: dict) -> None:
    uid = despesa_uid(deputado_id, item)
    conn.execute(
        """
        INSERT INTO despesas (
            uid, deputado_id, ano, mes, tipo_despesa, data_documento,
            nome_fornecedor, cnpj_cpf_fornecedor, tipo_documento, num_documento,
            cod_documento, valor_documento, valor_liquido, valor_glosa,
            num_ressarcimento, cod_lote, parcela, url_documento
        ) VALUES (
            :uid, :deputado_id, :ano, :mes, :tipo_despesa, :data_documento,
            :nome_fornecedor, :cnpj_cpf_fornecedor, :tipo_documento, :num_documento,
            :cod_documento, :valor_documento, :valor_liquido, :valor_glosa,
            :num_ressarcimento, :cod_lote, :parcela, :url_documento
        )
        ON CONFLICT (uid) DO UPDATE SET
            valor_documento = excluded.valor_documento,
            valor_liquido = excluded.valor_liquido,
            valor_glosa = excluded.valor_glosa,
            url_documento = excluded.url_documento
        """,
        {
            "uid": uid,
            "deputado_id": deputado_id,
            "ano": item.get("ano"),
            "mes": item.get("mes"),
            "tipo_despesa": item.get("tipoDespesa"),
            "data_documento": item.get("dataDocumento"),
            "nome_fornecedor": item.get("nomeFornecedor"),
            "cnpj_cpf_fornecedor": item.get("cnpjCpfFornecedor"),
            "tipo_documento": item.get("tipoDocumento"),
            "num_documento": item.get("numDocumento"),
            "cod_documento": item.get("codDocumento"),
            "valor_documento": item.get("valorDocumento"),
            "valor_liquido": item.get("valorLiquido"),
            "valor_glosa": item.get("valorGlosa"),
            "num_ressarcimento": item.get("numRessarcimento"),
            "cod_lote": item.get("codLote"),
            "parcela": item.get("parcela"),
            "url_documento": item.get("urlDocumento"),
        },
    )


# --- discursos -----------------------------------------------------------


def discurso_uid(deputado_id: int, item: dict) -> str:
    return _hash(deputado_id, item.get("dataHoraInicio"), item.get("dataHoraFim"), item.get("urlTexto") or item.get("sumario"))


def upsert_discurso(conn: sqlite3.Connection, deputado_id: int, item: dict) -> str:
    uid = discurso_uid(deputado_id, item)
    keywords = item.get("keywords") or item.get("indexacao")
    if isinstance(keywords, list):
        keywords = ", ".join(keywords)
    conn.execute(
        """
        INSERT INTO discursos (
            uid, deputado_id, data_hora_inicio, data_hora_fim, tipo_discurso,
            sumario, url_texto, keywords, fase_evento, transcricao
        ) VALUES (
            :uid, :deputado_id, :data_hora_inicio, :data_hora_fim, :tipo_discurso,
            :sumario, :url_texto, :keywords, :fase_evento, :transcricao
        )
        ON CONFLICT (uid) DO UPDATE SET
            sumario = excluded.sumario,
            url_texto = excluded.url_texto,
            keywords = excluded.keywords,
            transcricao = excluded.transcricao
        """,
        {
            "uid": uid,
            "deputado_id": deputado_id,
            "data_hora_inicio": item.get("dataHoraInicio"),
            "data_hora_fim": item.get("dataHoraFim"),
            "tipo_discurso": item.get("tipoDiscurso"),
            "sumario": item.get("sumario"),
            "url_texto": item.get("urlTexto"),
            "keywords": keywords,
            "fase_evento": item.get("faseEvento", {}).get("titulo") if isinstance(item.get("faseEvento"), dict) else item.get("faseEvento"),
            "transcricao": item.get("transcricao"),
        },
    )
    return uid


# --- votacoes / votos --------------------------------------------------------


def upsert_votacao(conn: sqlite3.Connection, item: dict) -> None:
    conn.execute(
        """
        INSERT INTO votacoes (id, data, sigla_orgao, id_orgao, descricao, aprovacao)
        VALUES (:id, :data, :sigla_orgao, :id_orgao, :descricao, :aprovacao)
        ON CONFLICT (id) DO UPDATE SET
            descricao = excluded.descricao,
            aprovacao = excluded.aprovacao
        """,
        {
            "id": item.get("id"),
            "data": item.get("data"),
            "sigla_orgao": item.get("siglaOrgao"),
            "id_orgao": item.get("idOrgao"),
            "descricao": item.get("descricao"),
            "aprovacao": item.get("aprovacao"),
        },
    )


def upsert_voto(conn: sqlite3.Connection, votacao_id: str, deputado_id: int, voto: str | None, motivo_ausencia: str | None) -> None:
    conn.execute(
        """
        INSERT INTO votos (votacao_id, deputado_id, voto, motivo_ausencia)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (votacao_id, deputado_id) DO UPDATE SET
            voto = excluded.voto,
            motivo_ausencia = excluded.motivo_ausencia
        """,
        (votacao_id, deputado_id, voto, motivo_ausencia),
    )


# --- ingest_state (controle de backfill/incremental resumivel) --------------


def ingest_status(conn: sqlite3.Connection, entidade: str, deputado_id: int | None, chave: str) -> str | None:
    row = conn.execute(
        "SELECT status FROM ingest_state WHERE entidade = ? AND deputado_id = ? AND chave = ?",
        (entidade, deputado_id or 0, chave),
    ).fetchone()
    return row["status"] if row else None


def ingest_deve_pular(
    conn: sqlite3.Connection,
    entidade: str,
    deputado_id: int | None,
    chave: str,
    max_tentativas: int = INGEST_MAX_TENTATIVAS,
) -> bool:
    """True se ja concluido, OU se ja falhou tantas vezes que nao vale mais
    a pena retentar automaticamente (registro provavelmente quebrado de forma
    persistente do lado da API, nao um problema transitorio)."""
    row = conn.execute(
        "SELECT status, tentativas FROM ingest_state WHERE entidade = ? AND deputado_id = ? AND chave = ?",
        (entidade, deputado_id or 0, chave),
    ).fetchone()
    if row is None:
        return False
    if row["status"] == "concluido":
        return True
    return row["status"] == "erro" and row["tentativas"] >= max_tentativas


def ingest_state_cobertos(conn: sqlite3.Connection, entidade: str, chave: str, max_tentativas: int = INGEST_MAX_TENTATIVAS) -> set[int]:
    """IDs de deputado ja cobertos (concluido, OU com tentativas esgotadas) para (entidade, chave).

    Usado quando uma unidade de trabalho e compartilhada entre varios
    deputados (ex: votacoes de um trimestre) para saber se algum deputado do
    conjunto-alvo atual ainda precisa ser coberto - por exemplo quando o
    conjunto-alvo cresce entre uma rodada de teste (poucos deputados) e o
    backfill completo (todos), sem isso o trimestre seria pulado por inteiro
    e os deputados novos ficariam sem voto algum registrado.
    """
    rows = conn.execute(
        """
        SELECT deputado_id FROM ingest_state
        WHERE entidade = ? AND chave = ?
          AND (status = 'concluido' OR (status = 'erro' AND tentativas >= ?))
        """,
        (entidade, chave, max_tentativas),
    ).fetchall()
    return {row["deputado_id"] for row in rows}


def mark_ingest_state(
    conn: sqlite3.Connection,
    entidade: str,
    deputado_id: int | None,
    chave: str,
    status: str,
    erro_msg: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO ingest_state (entidade, deputado_id, chave, status, tentativas, erro_msg, atualizado_em)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT (entidade, deputado_id, chave) DO UPDATE SET
            status = excluded.status,
            tentativas = ingest_state.tentativas + 1,
            erro_msg = excluded.erro_msg,
            atualizado_em = excluded.atualizado_em
        """,
        (entidade, deputado_id or 0, chave, status, erro_msg, _now()),
    )


# --- cache de analise LLM ---------------------------------------------------


def get_llm_cache(conn: sqlite3.Connection, discurso_uid: str, prompt_version: str) -> dict | None:
    row = conn.execute(
        "SELECT resultado_json FROM llm_discurso_cache WHERE discurso_uid = ? AND prompt_version = ?",
        (discurso_uid, prompt_version),
    ).fetchone()
    return json.loads(row["resultado_json"]) if row else None


def set_llm_cache(conn: sqlite3.Connection, discurso_uid: str, prompt_version: str, resultado: dict, modelo: str) -> None:
    conn.execute(
        """
        INSERT INTO llm_discurso_cache (discurso_uid, prompt_version, resultado_json, modelo, processado_em)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (discurso_uid, prompt_version) DO UPDATE SET
            resultado_json = excluded.resultado_json,
            modelo = excluded.modelo,
            processado_em = excluded.processado_em
        """,
        (discurso_uid, prompt_version, json.dumps(resultado, ensure_ascii=False), modelo, _now()),
    )


# --- findings ---------------------------------------------------------------


def clear_findings_for_month(conn: sqlite3.Connection, mes_referencia: str) -> None:
    conn.execute("DELETE FROM findings WHERE mes_referencia = ?", (mes_referencia,))


def insert_finding(
    conn: sqlite3.Connection,
    mes_referencia: str,
    deputado_id: int,
    tipo: str,
    severidade: str,
    descricao: str,
    dados_suporte: dict | None = None,
    fonte_url: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO findings (mes_referencia, deputado_id, tipo, severidade, descricao, dados_suporte, fonte_url, criado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            mes_referencia,
            deputado_id,
            tipo,
            severidade,
            descricao,
            json.dumps(dados_suporte, ensure_ascii=False) if dados_suporte is not None else None,
            fonte_url,
            _now(),
        ),
    )
