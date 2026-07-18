"""Helpers de exportacao (CSV/Excel/Markdown), reusados pelas abas do
dashboard - CSV/Excel pra quem quer analisar por conta propria (pesquisa,
jornalismo), Markdown pra um resumo legivel (relatorio).
"""

from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import streamlit as st

from vigia_publico.config import PUBLIC_BASE_URL
from vigia_publico.dashboard.fonte_page import build_fonte_amigavel_url


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    # utf-8-sig (BOM) pra o Excel abrir acento certo sem o usuario ter que
    # escolher encoding manualmente na importacao.
    return df.to_csv(index=False).encode("utf-8-sig")


def to_excel_bytes(df: pd.DataFrame, sheet_name: str = "dados") -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name[:31])  # limite do Excel pro nome da aba
    return buffer.getvalue()


def botoes_exportar(df: pd.DataFrame, nome_base: str, key_prefix: str) -> None:
    """CSV + Excel lado a lado pra um dataframe - usado em toda aba que tem
    uma tabela central. `key_prefix` evita colisao de key entre abas que
    chamam isso mais de uma vez na mesma pagina."""
    if df.empty:
        return
    col1, col2 = st.columns(2)
    col1.download_button(
        "⬇️ CSV", to_csv_bytes(df), file_name=f"{nome_base}.csv", mime="text/csv",
        key=f"{key_prefix}_csv", use_container_width=True,
    )
    col2.download_button(
        "⬇️ Excel", to_excel_bytes(df, sheet_name=nome_base[:31]), file_name=f"{nome_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_excel", use_container_width=True,
    )


def build_markdown_summary(findings: pd.DataFrame, filtros: dict[str, str]) -> str:
    """Resumo em Markdown dos achados filtrados, pronto pra baixar/colar num
    relatorio. Usa as colunas 'categoria'/'resumo' (linguagem neutra) se
    presentes (modo publico) - senao 'tipo'/'severidade'/'descricao' (modo
    local, ja preservando o texto interno original)."""
    linhas = ["# Vigia Público — Relatório de achados", ""]
    linhas.append(f"Gerado em {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}.")
    linhas.append("")

    filtros_ativos = {k: v for k, v in filtros.items() if v}
    if filtros_ativos:
        linhas.append("## Filtros aplicados")
        for chave, valor in filtros_ativos.items():
            linhas.append(f"- **{chave}:** {valor}")
        linhas.append("")

    linhas.append(f"Total de achados: **{len(findings)}**")
    linhas.append("")

    if findings.empty:
        linhas.append("Nenhum achado no filtro selecionado.")
        return "\n".join(linhas)

    usa_categoria = "categoria" in findings.columns
    coluna_tipo = "categoria" if usa_categoria else "tipo"
    coluna_texto = "resumo" if usa_categoria else "descricao"

    for (nome, partido, uf), grupo in findings.groupby(["nome_eleitoral", "sigla_partido", "sigla_uf"]):
        linhas.append(f"## {nome} ({partido}/{uf})")
        linhas.append("")
        for row in grupo.itertuples():
            texto = getattr(row, coluna_texto) or ""
            tipo = getattr(row, coluna_tipo)
            linhas.append(f"- **{tipo}** ({row.mes_referencia}): {texto}")
            fonte_url = getattr(row, "fonte_url", None)
            if fonte_url:
                # Link amigavel (nao o XML cru da API) no modo publico - ver
                # fonte_page.py. Modo local mantem a URL crua (uso interno).
                # Aqui (diferente da coluna da tela) precisa do dominio
                # completo: o .md sai do app e e lido em outro lugar
                # (editor de texto, outro site), sem "pagina atual" pra um
                # link relativo se ancorar.
                link = f"{PUBLIC_BASE_URL}{build_fonte_amigavel_url(fonte_url)}" if usa_categoria else fonte_url
                linhas.append(f"  [Ver fonte]({link})")
        linhas.append("")

    linhas.append("---")
    linhas.append(
        "Achados são sinais estatísticos automáticos (comparação com o histórico próprio ou com "
        "colegas de partido/estado) - não constituem acusação nem conclusão sobre irregularidade, "
        "e sempre requerem verificação humana."
    )
    linhas.append("")
    linhas.append("Fonte: Vigia Público — https://github.com/mt300/vigia-publico")
    return "\n".join(linhas)
