"""설정 — .env 기반. 환경변수 → 기본값 순으로 해석."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
STORAGE_DIR = BASE_DIR / "storage"
DB_PATH = Path(os.environ.get("CARD_DB_PATH", STORAGE_DIR / "cards.db"))
IMAGE_DIR = Path(os.environ.get("CARD_IMAGE_DIR", STORAGE_DIR / "card_images"))


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# 수집 설정
HTTP_TIMEOUT = float(os.environ.get("CARD_HTTP_TIMEOUT", "25"))
REQUEST_DELAY = float(os.environ.get("CARD_REQUEST_DELAY", "0.5"))  # 요청 간 지연(초), 저속 수집
NEW_DAYS = _int("CARD_NEW_DAYS", 30)  # first_seen 이후 N일 이내 = 신규 배지
USER_AGENT = os.environ.get(
    "CARD_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
)

# 신규등록(모니터링) 배지 기준: first_seen 이후 N일 이내
NEW_REGISTERED_DAYS = _int("CARD_NEW_REGISTERED_DAYS", 14)

# Teams 알림 (Incoming Webhook 또는 Power Automate URL). 비우면 알림 끔.
TEAMS_WEBHOOK_URL = os.environ.get("CARD_TEAMS_WEBHOOK_URL", "").strip()

# 서버 설정
SERVE_HOST = os.environ.get("CARD_SERVE_HOST", "0.0.0.0")
SERVE_PORT = _int("CARD_SERVE_PORT", 8001)

# 어떤 회사를 수집할지 (쉼표구분, 비우면 전체 등록 회사)
ENABLED_COMPANIES = [
    c.strip() for c in os.environ.get("CARD_COMPANIES", "").split(",") if c.strip()
]
