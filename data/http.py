"""HTTP 클라이언트 팩토리 — 회사 프록시 인증서 신뢰 + 타임아웃 필수."""

import ssl

import httpx
import truststore

import config

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
