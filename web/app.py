"""FastAPI 앱 — 대시보드 + 카드 이미지 안전 서빙."""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

import config
from web.routers import dashboard

_log = logging.getLogger(__name__)

app = FastAPI(title="카드사 신규 상품 모니터링")
app.include_router(dashboard.router)


@app.get("/images/{company}/{filename}")
def serve_card_image(company: str, filename: str) -> FileResponse:
    """로컬 캐시 이미지 서빙. IMAGE_DIR 하위로만 제한(경로 트래버설 방지)."""
    root = Path(config.IMAGE_DIR).resolve()
    target = (root / company / filename).resolve()
    if not str(target).startswith(str(root)) or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    media = _IMAGE_MEDIA.get(target.suffix.lower())
    return FileResponse(target, media_type=media)


_IMAGE_MEDIA = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp",
}
