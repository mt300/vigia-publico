"""Testa o parsing da saida estruturada e o cache de LLM, sem bater na API real
(a API Anthropic e mockada)."""

import json
from types import SimpleNamespace

import pytest

from senado_sentinel.detection import llm_analysis as llm


class _FakeMessages:
    def __init__(self, payload: dict):
        self._payload = payload
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        texto_json = json.dumps(self._payload, ensure_ascii=False)
        bloco = SimpleNamespace(type="text", text=texto_json)
        return SimpleNamespace(content=[bloco])


class _FakeClient:
    def __init__(self, payload: dict):
        self.messages = _FakeMessages(payload)


def test_parse_json_response_extrai_bloco_de_texto():
    payload = {"resumo": "teste", "topicos": ["a", "b"], "teor": "neutro"}
    fake_client = _FakeClient(payload)
    resultado = llm.resumir_discurso(fake_client, "texto qualquer do discurso")

    assert resultado == payload
    assert fake_client.messages.calls == 1


def test_analisar_incoerencia_retorna_schema_esperado():
    payload = {
        "incoerencia_flag": True,
        "incoerencia_explicacao": "Disse X, votou Y",
        "incoerencia_citacoes": ["trecho literal"],
        "conteudo_suspeito_flag": False,
        "conteudo_suspeito_explicacao": "",
        "conteudo_suspeito_citacoes": [],
    }
    fake_client = _FakeClient(payload)
    resultado = llm.analisar_incoerencia(fake_client, "texto do discurso", "contexto de votos")

    assert resultado["incoerencia_flag"] is True
    assert resultado["incoerencia_citacoes"] == ["trecho literal"]


def test_processar_discursos_mes_usa_cache_e_nao_chama_llm_de_novo(conn, monkeypatch):
    conn.execute("INSERT INTO deputados (id, nome_eleitoral) VALUES (1, 'Teste')")
    conn.execute(
        """
        INSERT INTO discursos (uid, deputado_id, data_hora_inicio, sumario, transcricao, url_texto)
        VALUES ('uid-1', 1, '2024-03-15T10:00', 'sumario', 'transcricao de teste', 'https://example.com/1')
        """
    )
    conn.commit()

    tier1_payload = {"resumo": "r", "topicos": ["t"], "teor": "neutro"}
    tier2_payload = {
        "incoerencia_flag": False,
        "incoerencia_explicacao": "",
        "incoerencia_citacoes": [],
        "conteudo_suspeito_flag": True,
        "conteudo_suspeito_explicacao": "linguagem contra fiscalizacao",
        "conteudo_suspeito_citacoes": ["trecho x"],
    }

    chamadas = {"tier1": 0, "tier2": 0}

    def fake_resumir(client, texto):
        chamadas["tier1"] += 1
        return tier1_payload

    def fake_analisar(client, texto, contexto):
        chamadas["tier2"] += 1
        return tier2_payload

    monkeypatch.setattr(llm, "get_client", lambda: object())
    monkeypatch.setattr(llm, "resumir_discurso", fake_resumir)
    monkeypatch.setattr(llm, "analisar_incoerencia", fake_analisar)
    monkeypatch.setattr(llm, "estimar_tokens_lote", lambda client, discursos: 100)

    findings1 = llm.processar_discursos_mes(conn, "2024-03")
    findings2 = llm.processar_discursos_mes(conn, "2024-03")

    assert chamadas == {"tier1": 1, "tier2": 1}  # segunda rodada usou o cache
    assert len(findings1) == 1
    assert findings1[0]["tipo"] == "DISCURSO_CONTEUDO_SUSPEITO"
    assert findings1 == findings2
