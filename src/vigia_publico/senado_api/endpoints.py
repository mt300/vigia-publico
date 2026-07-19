"""Wrappers tipados por endpoint das APIs de Dados Abertos do Senado."""

from __future__ import annotations

from vigia_publico.senado_api.client import SenadoApiClient


def listar_senadores_atuais(client: SenadoApiClient) -> list[dict]:
    """Lista dos senadores em exercicio agora. Devolve so os campos de
    `IdentificacaoParlamentar` (nome, partido, UF, foto, email etc) - o
    resto do payload bruto (`Mandato`, suplentes etc) nao e usado neste
    escopo (so gastos - ver plano)."""
    payload = client.get_legis("/senador/lista/atual.json")
    parlamentares = payload["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
    if isinstance(parlamentares, dict):
        # Gotcha comum de API que serializa XML->JSON: com 1 item so, vira
        # um objeto solto em vez de lista de 1 - nao bate no caso real hoje
        # (81 senadores), mas e barato de proteger.
        parlamentares = [parlamentares]
    return [p["IdentificacaoParlamentar"] for p in parlamentares]


def despesas_ceaps_ano(client: SenadoApiClient, ano: int) -> list[dict]:
    """Despesas CEAPS de TODOS os senadores num ano - uma chamada so, sem
    filtro por senador na API (diferente da Camara, que e uma chamada por
    deputado)."""
    return client.get_adm(f"/senadores/despesas_ceaps/{ano}")
