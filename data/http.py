"""HTTP 클라이언트 팩토리 — 회사 프록시 인증서 신뢰 + 타임아웃 필수."""

import logging
import ssl
import time

import httpx
import truststore

import config

_log = logging.getLogger(__name__)

# Windows 시스템 인증서 저장소 사용 (회사 프록시 인증서 자동 신뢰). verify=False 금지.
_ssl_ctx = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

DEFAULT_HEADERS = {
    "User-Agent": config.USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9",
}


def make_client(
    *, ajax: bool = False, referer: str | None = None
) -> httpx.Client:
    """동기 httpx 클라이언트. ajax=True면 XHR 헤더 추가."""
    headers = dict(DEFAULT_HEADERS)
    if ajax:
        headers["X-Requested-With"] = "XMLHttpRequest"
    if referer:
        headers["Referer"] = referer
    return httpx.Client(
        verify=_ssl_ctx,
        timeout=config.HTTP_TIMEOUT,
        follow_redirects=True,
        headers=headers,
    )


def request_with_retry(client: httpx.Client, method: str, url: str,
                       *, retries: int = 3, backoff: float = 1.5, **kwargs) -> httpx.Response:
    """일시적 연결 끊김/5xx에 재시도. (GitHub 등 외부 IP에서 서버가 간헐적으로 끊는 경우 대비)"""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client.request(method, url, **kwargs)
            if resp.status_code >= 500:
                resp.raise_for_status()
            return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
                _log.warning("재시도 %d/%d (%s): %s", attempt + 1, retries, url, e)
    raise last  # type: ignore[misc]
