"""Cliente HTTP para a API de Dados Abertos da Camara dos Deputados.

API publica, sem autenticacao. Nao ha limite documentado, mas o cliente
aplica um throttle simples e retry/backoff para ser um bom cidadao.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from vigia_publico.config import CAMARA_API_BASE_URL, CAMARA_API_REQUESTS_PER_SECOND

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class _Throttle:
    """Espaca as chamadas para no maximo N por segundo, thread-safe."""

    def __init__(self, requests_per_second: float) -> None:
        self._min_interval = 1.0 / requests_per_second
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            remaining = self._min_interval - elapsed
            if remaining > 0:
                time.sleep(remaining)
            self._last_call = time.monotonic()


class CamaraApiClient:
    def __init__(
        self,
        base_url: str = CAMARA_API_BASE_URL,
        requests_per_second: float = CAMARA_API_REQUESTS_PER_SECOND,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._throttle = _Throttle(requests_per_second)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CamaraApiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        self._throttle.wait()
        logger.debug("GET %s params=%s", path, params)
        response = self._client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _get_full_url(self, url: str) -> dict:
        self._throttle.wait()
        logger.debug("GET %s", url)
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def get_all_pages(
        self, path: str, params: dict[str, Any] | None = None, itens: int = 100, paginated: bool = True
    ) -> list[dict]:
        """Segue a paginacao via `links` (rel=next) ate esgotar.

        Alguns sub-recursos (ex: /historico, /votacoes/{id}/votos) rejeitam os
        parametros de paginacao com 400 Bad Request e sempre devolvem tudo numa
        pagina so - para esses, use `paginated=False`.
        """
        page_params = dict(params or {})
        if paginated:
            page_params.setdefault("itens", itens)
            page_params.setdefault("pagina", 1)

        results: list[dict] = []
        next_url: str | None = None
        while True:
            payload = self._get_full_url(next_url) if next_url else self.get(path, page_params)

            results.extend(payload.get("dados", []))

            next_url = None
            for link in payload.get("links", []):
                if link.get("rel") == "next":
                    next_url = link["href"]
                    break
            if not next_url:
                break

        return results
