"""
Read-only HH.ru AI Job Radar.

- searches public vacancies through the official HH API;
- scores only against local deterministic rules;
- stores dedup/cutoff in SQLite;
- sends alerts through Telegram Bot API;
- never applies, messages employers, or changes an HH profile.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import re
import sqlite3
import time
from typing import Any

import requests

from config import (
    HH_ACCESS_TOKEN,
    HH_AREA,
    HH_CLIENT_ID,
    HH_CLIENT_SECRET,
    HH_EMPLOYMENT_FORM,
    HH_EXPERIENCE,
    HH_INITIAL_LOOKBACK_HOURS,
    HH_MIN_SCORE,
    HH_POLL_INTERVAL,
    HH_PROFESSIONAL_ROLES,
    HH_PROJECT_ONLY,
    HH_REMOTE_ONLY,
    HH_REQUEST_DELAY,
    HH_SEARCH_FIELDS,
    HH_SEARCH_TEXT,
    HH_WORK_FORMAT,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)
from filters import FitResult, score_vacancy

API_BASE = "https://api.hh.ru"
OAUTH_TOKEN_URL = "https://hh.ru/oauth/token"
USER_AGENT = "ai-job-radar/1.0 (personal read-only vacancy monitor)"
DB_PATH = "hh_seen.sqlite3"
TOKEN_CACHE_PATH = "hh_app_token.json"

PER_PAGE = 100
MAX_PAGES = 20
OVERLAP_MINUTES = 10
TAG_RE = re.compile(r"<[^>]+>")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("hh_bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


def init_db(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, seen_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", value or "")).strip()


def _load_cached_token() -> str:
    try:
        with open(TOKEN_CACHE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return str(data.get("access_token") or "").strip()
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ""


def _save_cached_token(token: str) -> None:
    with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"access_token": token}, fh)


def get_access_token(force_generate: bool = False) -> str:
    """
    HH application token strategy:
    1) explicit HH_ACCESS_TOKEN from .env;
    2) locally cached application token;
    3) generate one via client_credentials only when no token exists.

    We intentionally do not refresh on a timer. HH application tokens are treated
    as durable credentials; if HH returns 401, delete/update the token explicitly.
    """
    if HH_ACCESS_TOKEN and not force_generate:
        return HH_ACCESS_TOKEN

    cached = _load_cached_token()
    if cached and not force_generate:
        return cached

    if not HH_CLIENT_ID or not HH_CLIENT_SECRET:
        raise RuntimeError(
            "Нет HH_ACCESS_TOKEN и нет HH_CLIENT_ID/HH_CLIENT_SECRET. "
            "Дождись одобрения приложения и заполни .env."
        )

    resp = requests.post(
        OAUTH_TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": HH_CLIENT_ID,
            "client_secret": HH_CLIENT_SECRET,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    resp.raise_for_status()
    token = str(resp.json()["access_token"])
    _save_cached_token(token)
    logger.info("Сгенерирован и локально сохранён HH app token")
    return token


def hh_api_get(path: str, params: dict[str, Any]) -> dict[str, Any] | None:
    token = get_access_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
    }
    resp = requests.get(f"{API_BASE}{path}", params=params, headers=headers, timeout=25)

    if resp.status_code == 401:
        raise RuntimeError(
            "HH вернул 401. Обнови HH_ACCESS_TOKEN в .env либо удали hh_app_token.json "
            "и сгенерируй новый app token."
        )
    if resp.status_code == 429:
        logger.warning("HH API: 429 rate limit; цикл будет повторён позже")
        return None
    if 500 <= resp.status_code < 600:
        logger.warning("HH API: %s; цикл будет повторён позже", resp.status_code)
        return None

    resp.raise_for_status()
    return resp.json()


def _add_multi(params: dict[str, Any], key: str, values: list[str]) -> None:
    if values:
        params[key] = values


def build_search_params(date_from_iso: str, page: int = 0) -> dict[str, Any]:
    params: dict[str, Any] = {
        "text": HH_SEARCH_TEXT,
        "area": HH_AREA,
        "order_by": "publication_time",
        "date_from": date_from_iso,
        "per_page": PER_PAGE,
        "page": page,
    }

    if HH_SEARCH_FIELDS:
        params["search_field"] = HH_SEARCH_FIELDS

    _add_multi(params, "professional_role", HH_PROFESSIONAL_ROLES)
    _add_multi(params, "experience", HH_EXPERIENCE)

    work_formats = list(HH_WORK_FORMAT)
    employment_forms = list(HH_EMPLOYMENT_FORM)
    if HH_REMOTE_ONLY and "REMOTE" not in work_formats:
        work_formats.append("REMOTE")
    if HH_PROJECT_ONLY and "PROJECT" not in employment_forms:
        employment_forms.append("PROJECT")

    _add_multi(params, "work_format", work_formats)
    _add_multi(params, "employment_form", employment_forms)
    return params


def fetch_vacancies_since(date_from_iso: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for page in range(MAX_PAGES):
        data = hh_api_get("/vacancies", build_search_params(date_from_iso, page=page))
        if data is None:
            break
        items.extend(data.get("items", []))
        if page + 1 >= int(data.get("pages", 0)):
            break
    return items


def fetch_full_vacancy(vacancy_id: str) -> dict[str, Any] | None:
    data = hh_api_get(f"/vacancies/{vacancy_id}", {})
    if data is None:
        return None
    data["description"] = strip_html(data.get("description") or "")
    return data


def _format_salary(vacancy: dict[str, Any], fit: FitResult) -> str:
    salary = vacancy.get("salary_range") or vacancy.get("salary") or {}
    if fit.salary_rub is None:
        return "не указана"
    currency = salary.get("currency") or "RUR"
    suffix = "₽" if currency in {"RUR", "RUB"} else currency
    low = salary.get("from")
    high = salary.get("to")
    if low and high:
        return f"{int(low):,}–{int(high):,} {suffix}".replace(",", " ")
    if low:
        return f"от {int(low):,} {suffix}".replace(",", " ")
    if high:
        return f"до {int(high):,} {suffix}".replace(",", " ")
    return f"{fit.salary_rub:,} {suffix}".replace(",", " ")


def format_message(vacancy: dict[str, Any], fit: FitResult) -> str:
    if fit.fit_score >= 80:
        marker = "🔥"
        verdict = "очень сильный матч"
    elif fit.fit_score >= 65:
        marker = "✅"
        verdict = "стоит смотреть"
    else:
        marker = "👀"
        verdict = "возможный матч"

    title = vacancy.get("name") or "Без названия"
    employer = (vacancy.get("employer") or {}).get("name") or "—"
    area = (vacancy.get("area") or {}).get("name") or "—"
    url = vacancy.get("alternate_url") or vacancy.get("url") or ""
    salary = _format_salary(vacancy, fit)

    mode = []
    if fit.remote:
        mode.append("удалённо")
    if fit.project:
        mode.append("проект/подработка")
    mode_str = " · ".join(mode) if mode else "формат не приоритетный"

    age = ""
    if fit.age_hours is not None:
        if fit.age_hours < 1:
            age = f"{max(1, int(fit.age_hours * 60))} мин назад"
        else:
            age = f"{fit.age_hours:.1f} ч назад"

    reasons = "\n".join(f"• {x}" for x in fit.reasons) or "• совпадение по ключевым навыкам"
    risks = "\n".join(f"• {x}" for x in fit.risks) or "• явных рисков по описанию не найдено"
    positive_flags = ""
    if fit.positive_flags:
        positive_flags = "\n\nПозитивные флаги:\n" + "\n".join(
            f"• {x}" for x in fit.positive_flags
        )

    return (
        f"{marker} Fit {fit.fit_score} / Money Risk {fit.money_risk} — {verdict}\n\n"
        f"{title}\n"
        f"🏢 {employer} · {area}\n"
        f"💰 {salary}\n"
        f"🧭 {mode_str}"
        + (f" · {age}" if age else "")
        + f"\n\nПочему подходит:\n{reasons}"
        + positive_flags
        + f"\n\nРиски:\n{risks}\n\n{url}"
    )


def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        raise RuntimeError("Заполни TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID для отправки уведомлений")
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        },
        timeout=20,
    )
    resp.raise_for_status()


def process_items(
    conn: sqlite3.Connection,
    items: list[dict[str, Any]],
    dry_run: bool,
) -> int:
    matched = 0
    for item in items:
        vid = str(item.get("id") or "")
        if not vid:
            continue
        if conn.execute("SELECT 1 FROM seen WHERE id = ?", (vid,)).fetchone():
            continue

        try:
            full = fetch_full_vacancy(vid)
        except Exception as exc:
            logger.warning("Не удалось загрузить вакансию %s: %s", vid, exc)
            continue
        time.sleep(HH_REQUEST_DELAY)
        if not full:
            continue

        fit = score_vacancy(full, min_score=HH_MIN_SCORE)

        # Mark processed vacancies only in real mode. Dry-run remains repeatable.
        if not dry_run:
            conn.execute(
                "INSERT OR IGNORE INTO seen (id, seen_at) VALUES (?, datetime('now'))",
                (vid,),
            )
            conn.commit()

        if not fit.is_fit:
            continue

        matched += 1
        message = format_message(full, fit)
        if dry_run:
            print("\n" + message + "\n" + ("-" * 72))
        else:
            send_telegram(message)
            logger.info(
                "Отправлена вакансия %s (Fit %s / Money Risk %s)",
                full.get("name"),
                fit.fit_score,
                fit.money_risk,
            )

    return matched


def run_once(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = get_meta(conn, "last_cutoff")
    if not cutoff:
        cutoff = (now - dt.timedelta(hours=HH_INITIAL_LOOKBACK_HOURS)).isoformat()

    items = fetch_vacancies_since(cutoff)
    logger.info("HH: получено %d вакансий", len(items))
    matched = process_items(conn, items, dry_run=dry_run)
    logger.info("Подходящих вакансий: %d", matched)

    if not dry_run:
        set_meta(
            conn,
            "last_cutoff",
            (now - dt.timedelta(minutes=OVERLAP_MINUTES)).isoformat(),
        )
    return matched


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only AI Job Radar for HH.ru")
    parser.add_argument("--once", action="store_true", help="один цикл и выход")
    parser.add_argument("--dry-run", action="store_true", help="не писать БД и не отправлять Telegram")
    parser.add_argument(
        "--fixtures",
        metavar="PATH",
        help="локальный JSON-массив вакансий: проверить scoring вообще без HH API",
    )
    args = parser.parse_args()

    if args.fixtures:
        with open(args.fixtures, encoding="utf-8") as fh:
            fixtures = json.load(fh)
        for vacancy in fixtures:
            fit = score_vacancy(vacancy, min_score=HH_MIN_SCORE)
            print(format_message(vacancy, fit))
            print("-" * 72)
        return

    conn = init_db()
    get_access_token()

    if args.once:
        run_once(conn, dry_run=args.dry_run)
        return

    while True:
        try:
            run_once(conn, dry_run=args.dry_run)
        except Exception:
            logger.exception("Ошибка цикла HH")
        time.sleep(HH_POLL_INTERVAL)


if __name__ == "__main__":
    main()
