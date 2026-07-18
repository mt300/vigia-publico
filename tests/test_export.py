"""Testa os helpers de exportacao (CSV/Excel/Markdown) - funcoes puras, sem
precisar de contexto de execucao do Streamlit."""

from __future__ import annotations

import io

import pandas as pd
import pytest

from vigia_publico.dashboard.export import build_markdown_summary, to_csv_bytes, to_excel_bytes


def test_to_csv_bytes_preserva_acentos():
    df = pd.DataFrame({"categoria": ["Manutenção de Escritório"], "total": [123.45]})
    csv = to_csv_bytes(df).decode("utf-8-sig")
    assert "Manutenção de Escritório" in csv
    assert "123.45" in csv


def test_to_excel_bytes_gera_arquivo_valido():
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    excel_bytes = to_excel_bytes(df, sheet_name="teste")
    lido = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="teste")
    assert list(lido["a"]) == [1, 2]
    assert list(lido["b"]) == ["x", "y"]


def test_to_excel_bytes_trunca_nome_de_aba_maior_que_31_chars():
    df = pd.DataFrame({"a": [1]})
    nome_longo = "a" * 50
    # Nao deve levantar excecao (limite do Excel pra nome de aba e 31 chars)
    to_excel_bytes(df, sheet_name=nome_longo)


@pytest.fixture
def findings_publico():
    return pd.DataFrame(
        [
            {
                "mes_referencia": "2024-03",
                "nome_eleitoral": "Fulano",
                "sigla_partido": "PT",
                "sigla_uf": "BA",
                "categoria": "Gasto acima do proprio historico",
                "resumo": "Gastou R$ 1.000,00 acima do normal.",
                "fonte_url": "https://dadosabertos.camara.leg.br/api/v2/deputados/1/despesas?ano=2024&mes=3",
            }
        ]
    )


def test_build_markdown_summary_modo_publico_usa_link_amigavel(findings_publico):
    fonte_crua = findings_publico.iloc[0]["fonte_url"]
    md = build_markdown_summary(findings_publico, {"Periodo": "2024-03 a 2024-03"})
    assert "Fulano (PT/BA)" in md
    assert "Gastou R$ 1.000,00 acima do normal." in md
    assert "/fonte?url=" in md  # link amigavel, nao a URL crua da API
    assert fonte_crua not in md  # a URL crua so aparece percent-encoded dentro do link, nunca clicavel direto


def test_build_markdown_summary_modo_local_mantem_url_crua():
    findings_local = pd.DataFrame(
        [
            {
                "mes_referencia": "2024-03",
                "nome_eleitoral": "Fulano",
                "sigla_partido": "PT",
                "sigla_uf": "BA",
                "tipo": "GASTO_OUTLIER",
                "severidade": "alta",
                "descricao": "Gasto muito acima da media.",
                "fonte_url": "https://dadosabertos.camara.leg.br/api/v2/deputados/1/despesas?ano=2024&mes=3",
            }
        ]
    )
    md = build_markdown_summary(findings_local, {})
    assert "dadosabertos.camara.leg.br" in md
    assert "/fonte?url=" not in md


def test_build_markdown_summary_sem_achados():
    md = build_markdown_summary(pd.DataFrame(), {})
    assert "Nenhum achado" in md
