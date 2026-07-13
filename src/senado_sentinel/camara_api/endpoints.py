"""Wrappers tipados por endpoint da API da Camara dos Deputados."""

from __future__ import annotations

from senado_sentinel.camara_api.client import CamaraApiClient


def listar_legislaturas(client: CamaraApiClient) -> list[dict]:
    return client.get_all_pages("/legislaturas", {"ordem": "asc", "ordenarPor": "id"})


def listar_deputados(client: CamaraApiClient, id_legislatura: int | None = None) -> list[dict]:
    params = {"idLegislatura": id_legislatura} if id_legislatura else {}
    return client.get_all_pages("/deputados", params)


def detalhe_deputado(client: CamaraApiClient, deputado_id: int) -> dict:
    return client.get(f"/deputados/{deputado_id}")["dados"]


def historico_deputado(client: CamaraApiClient, deputado_id: int) -> list[dict]:
    """Retorna a timeline completa de partido/situacao do deputado, cobrindo
    TODAS as legislaturas em que ele atuou (nao aceita filtro de legislatura)."""
    return client.get_all_pages(f"/deputados/{deputado_id}/historico", paginated=False)


def despesas_deputado(client: CamaraApiClient, deputado_id: int, ano: int, mes: int | None = None) -> list[dict]:
    params: dict = {"ano": ano}
    if mes is not None:
        params["mes"] = mes
    return client.get_all_pages(f"/deputados/{deputado_id}/despesas", params)


def discursos_deputado(client: CamaraApiClient, deputado_id: int, data_inicio: str, data_fim: str) -> list[dict]:
    return client.get_all_pages(
        f"/deputados/{deputado_id}/discursos",
        {"dataInicio": data_inicio, "dataFim": data_fim},
    )


def listar_votacoes(
    client: CamaraApiClient,
    data_inicio: str,
    data_fim: str,
    id_orgao: int | None = None,
) -> list[dict]:
    params = {"dataInicio": data_inicio, "dataFim": data_fim}
    if id_orgao is not None:
        params["idOrgao"] = id_orgao
    return client.get_all_pages("/votacoes", params)


def votos_votacao(client: CamaraApiClient, id_votacao: str) -> list[dict]:
    return client.get_all_pages(f"/votacoes/{id_votacao}/votos", paginated=False)


def listar_orgaos(client: CamaraApiClient) -> list[dict]:
    return client.get_all_pages("/orgaos")
