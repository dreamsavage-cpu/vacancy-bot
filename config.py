import os
from dotenv import load_dotenv

load_dotenv()


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ================= HH.RU =================
HH_SEARCH_TEXT = os.environ.get(
    "HH_SEARCH_TEXT",
    '"AI video" OR "AI creator" OR Higgsfield OR Runway OR Veo OR Kling OR Seedance OR '
    '"генеративное видео" OR нейросет OR LLM OR GPT OR OpenAI OR Claude OR RAG OR '
    '"AI agent" OR "AI automation" OR автоматизация OR "Telegram bot" OR "чат-бот" OR '
    'парсер OR parser OR scraping OR Blender OR FreeCAD OR "3D"'
)

# 113 = Russia. Can be overridden with any HH area id.
HH_AREA = os.environ.get("HH_AREA", "113")
HH_SEARCH_FIELDS = _csv("HH_SEARCH_FIELDS", "name,description")
HH_POLL_INTERVAL = int(os.environ.get("HH_POLL_INTERVAL", "1800"))
HH_REQUEST_DELAY = float(os.environ.get("HH_REQUEST_DELAY", "0.25"))
HH_INITIAL_LOOKBACK_HOURS = int(os.environ.get("HH_INITIAL_LOOKBACK_HOURS", "24"))
HH_MIN_SCORE = int(os.environ.get("HH_MIN_SCORE", "45"))

HH_PROFESSIONAL_ROLES = _csv("HH_PROFESSIONAL_ROLES")
HH_EXPERIENCE = _csv("HH_EXPERIENCE")

# Optional hard API filters. By default we do NOT force them: remote/project
# vacancies get a score bonus so permanent remote work is not accidentally lost.
HH_REMOTE_ONLY = _bool("HH_REMOTE_ONLY", False)
HH_PROJECT_ONLY = _bool("HH_PROJECT_ONLY", False)
HH_WORK_FORMAT = _csv("HH_WORK_FORMAT")
HH_EMPLOYMENT_FORM = _csv("HH_EMPLOYMENT_FORM")

# HH application auth. Preferred after approval: copy the current app token from
# dev.hh.ru/admin to HH_ACCESS_TOKEN. If it is omitted, CLIENT_ID/SECRET can be
# used once to generate and cache an application token locally.
HH_ACCESS_TOKEN = os.environ.get("HH_ACCESS_TOKEN", "").strip()
HH_CLIENT_ID = os.environ.get("HH_CLIENT_ID", "").strip()
HH_CLIENT_SECRET = os.environ.get("HH_CLIENT_SECRET", "").strip()

# ================= TELEGRAM OUTPUT =================
# HH notifications use Bot API, not a personal Telegram session.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# ================= OPTIONAL TELEGRAM SOURCE LISTENER =================
# Kept from the upstream project as an optional feature. It still uses Telethon
# to READ channels, but is not used by hh_bot.py.
_api_id_raw = os.environ.get("API_ID", "").strip()
API_ID = int(_api_id_raw) if _api_id_raw else None
API_HASH = os.environ.get("API_HASH", "").strip()
PHONE = os.environ.get("PHONE", "").strip()
TARGET_CHANNEL = os.environ.get("TARGET_CHANNEL", "").strip()
SOURCE_CHANNELS = _csv("SOURCE_CHANNELS")
