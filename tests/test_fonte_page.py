"""Testa o guard de SSRF e a montagem de link da pagina 'Fonte de um achado'
- funcoes puras, sem precisar buscar nada na rede de verdade."""

from __future__ import annotations

import pytest

from vigia_publico.dashboard.fonte_page import _url_permitida, build_fonte_amigavel_url


@pytest.mark.parametrize(
    "url",
    [
        "https://dadosabertos.camara.leg.br/api/v2/deputados/62881/despesas?ano=2026&mes=4",
        "https://dadosabertos.camara.leg.br/api/v2/deputados/1",
        "https://dadosabertos.camara.leg.br/api/v2/deputados/1/historico",
    ],
)
def test_url_permitida_aceita_api_real_da_camara(url):
    assert _url_permitida(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/2024",
        "https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/2020",
    ],
)
def test_url_permitida_aceita_api_real_do_senado(url):
    assert _url_permitida(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.com/steal-data",
        "http://169.254.169.254/latest/meta-data/",  # SSRF classico contra metadata de cloud
        "http://dadosabertos.camara.leg.br/api/v2/deputados/1",  # http, nao https
        "https://dadosabertos.camara.leg.br.evil.com/api/v2/deputados/1",  # host parecido, subdominio falso
        "http://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/2024",  # http, nao https
        "https://adm.senado.gov.br.evil.com/adm-dadosabertos/api/v1/senadores/despesas_ceaps/2024",  # host parecido, falso
        # legis.senado.leg.br deliberadamente NAO liberado neste plano (nenhum
        # fonte_url do MVP aponta pra la - so o CEAPS, host administrativo).
        "https://legis.senado.leg.br/dadosabertos/senador/lista/atual",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "",
        None,
    ],
)
def test_url_permitida_rejeita_qualquer_coisa_fora_do_host_da_api(url):
    if url is None:
        pytest.skip("None e tratado antes de chegar em _url_permitida (ver render_fonte)")
    assert _url_permitida(url) is False


def test_build_fonte_amigavel_url_e_relativa():
    """Link relativo (sem dominio) de proposito - precisa funcionar em
    qualquer origem onde o app estiver rodando (local em dev, producao na
    VPS), nao so no dominio de producao. Ver bug corrigido em views.py."""
    raw = "https://dadosabertos.camara.leg.br/api/v2/deputados/1/despesas?ano=2024&mes=3"
    link = build_fonte_amigavel_url(raw)
    assert link.startswith("/fonte?url=")
    assert "https://" not in link.split("?url=")[0]  # so a parte antes do param, nao o valor codificado


def test_build_fonte_amigavel_url_preserva_a_url_original_via_roundtrip():
    from urllib.parse import parse_qs, urlparse

    raw = "https://dadosabertos.camara.leg.br/api/v2/deputados/1/despesas?ano=2024&mes=3"
    link = build_fonte_amigavel_url(raw)
    query = parse_qs(urlparse(link).query)
    assert query["url"] == [raw]
