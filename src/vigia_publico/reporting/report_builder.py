"""Gera o relatorio mensal (Markdown) a partir dos findings gravados no banco."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from vigia_publico.config import REPORTS_DIR

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _carregar_findings_por_deputado(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT f.*, d.nome_eleitoral, d.sigla_partido, d.sigla_uf
        FROM findings f
        JOIN deputados d ON d.id = f.deputado_id
        WHERE f.casa = 'camara' AND f.mes_referencia = ?
        ORDER BY d.nome_eleitoral, f.severidade DESC
        """,
        (mes_referencia,),
    ).fetchall()

    por_deputado: dict[int, dict] = {}
    for row in rows:
        dep_id = row["deputado_id"]
        if dep_id not in por_deputado:
            por_deputado[dep_id] = {
                "nome_eleitoral": row["nome_eleitoral"],
                "sigla_partido": row["sigla_partido"],
                "sigla_uf": row["sigla_uf"],
                "findings": [],
            }
        por_deputado[dep_id]["findings"].append(
            {
                "tipo": row["tipo"],
                "severidade": row["severidade"],
                "descricao": row["descricao"],
                "dados_suporte": json.loads(row["dados_suporte"]) if row["dados_suporte"] else None,
                "fonte_url": row["fonte_url"],
            }
        )
    return list(por_deputado.values())


def _carregar_findings_por_senador(conn: sqlite3.Connection, mes_referencia: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT f.*, s.nome_parlamentar, s.sigla_partido, s.sigla_uf
        FROM findings f
        JOIN senadores s ON s.id = f.deputado_id
        WHERE f.casa = 'senado' AND f.mes_referencia = ?
        ORDER BY s.nome_parlamentar, f.severidade DESC
        """,
        (mes_referencia,),
    ).fetchall()

    por_senador: dict[int, dict] = {}
    for row in rows:
        sen_id = row["deputado_id"]
        if sen_id not in por_senador:
            por_senador[sen_id] = {
                "nome_parlamentar": row["nome_parlamentar"],
                "sigla_partido": row["sigla_partido"],
                "sigla_uf": row["sigla_uf"],
                "findings": [],
            }
        por_senador[sen_id]["findings"].append(
            {
                "tipo": row["tipo"],
                "severidade": row["severidade"],
                "descricao": row["descricao"],
                "dados_suporte": json.loads(row["dados_suporte"]) if row["dados_suporte"] else None,
                "fonte_url": row["fonte_url"],
            }
        )
    return list(por_senador.values())


def _ranking_por_total(itens: list[dict], chave_nome: str) -> list[dict]:
    return sorted(
        (
            {"nome": item[chave_nome], "sigla_partido": item["sigla_partido"], "sigla_uf": item["sigla_uf"], "total": len(item["findings"])}
            for item in itens
        ),
        key=lambda item: item["total"],
        reverse=True,
    )


def build_report(conn: sqlite3.Connection, mes_referencia: str, output_dir: Path = REPORTS_DIR) -> Path:
    deputados_com_achados = _carregar_findings_por_deputado(conn, mes_referencia)
    senadores_com_achados = _carregar_findings_por_senador(conn, mes_referencia)

    contagem_por_tipo: dict[str, int] = {}
    for dep in deputados_com_achados + senadores_com_achados:
        for finding in dep["findings"]:
            contagem_por_tipo[finding["tipo"]] = contagem_por_tipo.get(finding["tipo"], 0) + 1

    ranking = _ranking_por_total(deputados_com_achados, "nome_eleitoral")
    ranking_senadores = _ranking_por_total(senadores_com_achados, "nome_parlamentar")

    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=select_autoescape(enabled_extensions=()))
    template = env.get_template("monthly_report.md.jinja")
    conteudo = template.render(
        mes_referencia=mes_referencia,
        gerado_em=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_findings=sum(contagem_por_tipo.values()),
        contagem_por_tipo=contagem_por_tipo,
        ranking=ranking,
        deputados_com_achados=deputados_com_achados,
        ranking_senadores=ranking_senadores,
        senadores_com_achados=senadores_com_achados,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{mes_referencia}.md"
    output_path.write_text(conteudo, encoding="utf-8")
    return output_path
