"""Cliente HTTP para as APIs de Dados Abertos do Senado Federal.

Duas APIs distintas (hosts diferentes): a administrativa (CEAPS - despesas)
e a legislativa (perfil/roster de senadores). Mesmo padrao de throttle/retry
de `camara_api/client.py`, mas SEM a paginacao HATEOAS (`links`/`dados`) de
la - confirmado num spike real (Fase 0) que o CEAPS devolve um array JSON
puro (todos os senadores do ano numa chamada so) e o roster devolve um
objeto JSON aninhado, nenhum dos dois pagina.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from vigia_publico.config import SENADO_ADM_API_BASE_URL, SENADO_API_REQUESTS_PER_SECOND, SENADO_LEGIS_API_BASE_URL

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


class SenadoApiClient:
    """Um client, dois hosts - a API administrativa (CEAPS) e a legislativa
    (perfil de senadores) sao servicos separados do Senado, cada um com sua
    propria base URL."""

    def __init__(
        self,
        adm_base_url: str = SENADO_ADM_API_BASE_URL,
        legis_base_url: str = SENADO_LEGIS_API_BASE_URL,
        requests_per_second: float = SENADO_API_REQUESTS_PER_SECOND,
        timeout: float = 30.0,
    ) -> None:
        self._adm = httpx.Client(base_url=adm_base_url, timeout=timeout, headers={"Accept": "application/json"})
        self._legis = httpx.Client(base_url=legis_base_url, timeout=timeout, headers={"Accept": "application/json"})
        self._throttle = _Throttle(requests_per_second)

    def close(self) -> None:
        self._adm.close()
        self._legis.close()

    def __enter__(self) -> "SenadoApiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get_adm(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """API administrativa (CEAPS) - devolve array/objeto JSON puro, sem paginacao."""
        self._throttle.wait()
        logger.debug("GET (adm) %s params=%s", path, params)
        response = self._adm.get(path, params=params)
        response.raise_for_status()
        return response.json()

    @retry(
        retry=retry_if_exception(_is_retryable),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def get_legis(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """API legislativa (perfil/roster) - o `path` precisa terminar em
        `.json` (a API devolve XML por padrao sem esse sufixo, confirmado
        no spike da Fase 0)."""
        self._throttle.wait()
        logger.debug("GET (legis) %s params=%s", path, params)
        response = self._legis.get(path, params=params)
        response.raise_for_status()
        return response.json()
