"""
Deterministic scoring for the personal AI job radar.

No paid LLM is required. The scorer is intentionally transparent: it rewards
the user's actual directions (AI video, AI/LLM automation, bots/parsers/API,
and simple 3D), remote/project work and freshness, while flagging heavy
engineering requirements and unclear AI-generation costs.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import re
from typing import Any


CATEGORY_TERMS: dict[str, list[tuple[str, int]]] = {
    "AI Video": [
        ("ai video", 20), ("ai creator", 18), ("ai-generated video", 18),
        ("генеративное видео", 18), ("нейросет", 8), ("higgsfield", 16),
        ("runway", 12), ("veo", 12), ("kling", 10), ("seedance", 10),
        ("pika", 7), ("capcut", 6), ("ugc", 6), ("short-form", 6),
        ("reels", 4), ("shorts", 4), ("lip-sync", 6), ("lipsync", 6),
    ],
    "AI / LLM automation": [
        ("ai automation", 20), ("автоматизац", 9), ("llm", 16),
        ("gpt", 12), ("openai", 10), ("claude", 9), ("rag", 11),
        ("ai agent", 18), ("ai-агент", 18), ("ии-агент", 18),
        ("нейроагент", 18), ("n8n", 11), ("make.com", 8), ("zapier", 8),
        ("mcp", 10), ("prompt engineering", 8),
    ],
    "Bots / parsers / API": [
        ("telegram bot", 20), ("telegram-бот", 20), ("телеграм-бот", 20),
        ("чат-бот", 16), ("chatbot", 14), ("парсер", 16), ("parser", 14),
        ("scraping", 14), ("web scraping", 14), ("playwright", 8),
        ("selenium", 8), ("api integration", 12), ("api интеграц", 12),
        ("python automation", 12), ("мониторинг", 6), ("webhook", 7),
    ],
    "3D": [
        ("blender", 18), ("freecad", 18), ("cad", 10), ("3d model", 14),
        ("3d modeling", 14), ("3д модел", 14), ("3d визуал", 10),
        ("3д визуал", 10), ("3d render", 8),
    ],
}

IRRELEVANT_TITLE_TERMS = [
    "бухгалтер", "кассир", "водитель", "кладовщик", "курьер", "официант",
    "повар", "медсест", "врач", "юрист", "охранник", "электрик", "сварщик",
]

HEAVY_ENGINEERING_TERMS = [
    "kubernetes", "django", "fastapi", "postgresql", "redis", "microservice",
    "микросервис", "ci/cd", "system design", "алгоритм", "leetcode",
    "highload", "high load", "golang", "java spring",
]
HEAVY_TITLE_TERMS = [
    "senior backend", "senior developer", "senior python developer",
    "backend developer", "backend engineer", "ml engineer", "data scientist",
    "devops engineer",
]

CREDIT_PROVIDED_TERMS = [
    "предоставим доступ", "предоставляем доступ", "доступы предостав",
    "оплачиваем подписк", "подписки оплачивает", "credits provided",
    "we provide access", "subscriptions covered", "company account",
    "full access to higgsfield", "access to higgsfield",
]
CREDIT_OWN_TERMS = [
    "свои подписк", "собственные подписк", "свои аккаунт", "собственные аккаунт",
    "за свой счет", "за свой счёт", "own subscription", "own account",
    "your own subscription", "your own account",
]
PAID_AI_TOOL_TERMS = [
    "higgsfield", "runway", "veo", "kling", "seedance", "midjourney",
    "elevenlabs", "flux", "pika", "suno",
]


@dataclass
class FitResult:
    score: int
    is_fit: bool
    categories: list[str]
    reasons: list[str]
    risks: list[str]
    credit_status: str
    remote: bool
    project: bool
    age_hours: float | None
    salary_rub: int | None


def _contains(text: str, term: str) -> bool:
    text = text.lower()
    term = term.lower()
    if re.fullmatch(r"[a-z0-9+#.-]{2,4}", term):
        return re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", text) is not None
    return term in text


def _ids(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, dict):
        return {str(value.get("id", ""))}
    result: set[str] = set()
    if isinstance(value, list):
        for item in value:
            result |= _ids(item)
    return {x for x in result if x}


def _published_age_hours(value: str | None, now: dt.datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    now = now or dt.datetime.now(dt.timezone.utc)
    return max(0.0, (now - parsed.astimezone(dt.timezone.utc)).total_seconds() / 3600)


def extract_salary_rub(vacancy: dict) -> int | None:
    salary = vacancy.get("salary_range") or vacancy.get("salary")
    if not isinstance(salary, dict) or salary.get("currency") not in {"RUR", "RUB"}:
        return None
    values = [salary.get("from"), salary.get("to")]
    numeric = [int(v) for v in values if isinstance(v, (int, float)) and v > 0]
    return max(numeric) if numeric else None


def _vacancy_text(vacancy: dict) -> str:
    parts = [
        vacancy.get("name") or "",
        (vacancy.get("employer") or {}).get("name") or "",
        vacancy.get("description") or "",
        ((vacancy.get("snippet") or {}).get("requirement") or ""),
        ((vacancy.get("snippet") or {}).get("responsibility") or ""),
    ]
    skills = vacancy.get("key_skills") or []
    for skill in skills:
        if isinstance(skill, dict):
            parts.append(skill.get("name") or "")
        elif isinstance(skill, str):
            parts.append(skill)
    return " ".join(parts)


def score_vacancy(vacancy: dict, min_score: int = 45, now: dt.datetime | None = None) -> FitResult:
    text = _vacancy_text(vacancy)
    title = (vacancy.get("name") or "").lower()

    category_scores: dict[str, int] = {}
    category_hits: dict[str, list[str]] = {}
    for category, terms in CATEGORY_TERMS.items():
        hits: list[str] = []
        score = 0
        for term, weight in terms:
            if _contains(text, term):
                hits.append(term)
                score += weight
        if hits:
            # Avoid one description with a giant keyword dump dominating the score.
            category_scores[category] = min(score, 46)
            category_hits[category] = hits

    skill_score = min(sum(category_scores.values()), 58)
    score = skill_score
    reasons: list[str] = []
    risks: list[str] = []

    ranked_categories = sorted(category_scores, key=category_scores.get, reverse=True)
    for category in ranked_categories[:2]:
        sample = ", ".join(category_hits[category][:4])
        reasons.append(f"{category}: {sample}")

    title_category_hit = any(
        _contains(title, term)
        for terms in CATEGORY_TERMS.values()
        for term, _weight in terms
    )
    if title_category_hit:
        score += 8
        reasons.append("ключевая специализация прямо в названии")

    work_formats = _ids(vacancy.get("work_format"))
    schedules = _ids(vacancy.get("schedule"))
    remote = "REMOTE" in work_formats or "remote" in schedules
    if remote:
        score += 12
        reasons.append("удалённо")

    employment_forms = _ids(vacancy.get("employment_form"))
    legacy_employment = _ids(vacancy.get("employment"))
    project = bool(
        employment_forms & {"PROJECT", "SIDE_JOB"}
        or legacy_employment & {"project", "part"}
    )
    if project:
        score += 10
        reasons.append("проект / подработка")

    age_hours = _published_age_hours(vacancy.get("published_at"), now=now)
    if age_hours is not None:
        if age_hours <= 2:
            score += 12
            reasons.append("опубликована менее 2 часов назад")
        elif age_hours <= 6:
            score += 8
            reasons.append("опубликована менее 6 часов назад")
        elif age_hours <= 24:
            score += 4
            reasons.append("опубликована сегодня")

    salary_rub = extract_salary_rub(vacancy)
    if salary_rub is not None:
        if salary_rub >= 150_000:
            score += 12
        elif salary_rub >= 100_000:
            score += 8
        elif salary_rub >= 70_000:
            score += 4
        reasons.append(f"доход до/от {salary_rub:,} ₽".replace(",", " "))

    lower = text.lower()
    has_paid_tools = any(_contains(lower, term) for term in PAID_AI_TOOL_TERMS)
    if any(_contains(lower, term) for term in CREDIT_PROVIDED_TERMS):
        credit_status = "provided"
        score += 4
        reasons.append("работодатель явно предоставляет AI-доступы/подписки")
    elif any(_contains(lower, term) for term in CREDIT_OWN_TERMS):
        credit_status = "own"
        score -= 14
        risks.append("требуются свои платные AI-подписки/аккаунты")
    elif has_paid_tools:
        credit_status = "unspecified"
        score -= 4
        risks.append("не указано, кто оплачивает AI-сервисы/кредиты")
    else:
        credit_status = "not_applicable"

    heavy_hits = [term for term in HEAVY_ENGINEERING_TERMS if _contains(lower, term)]
    heavy_title = any(term in title for term in HEAVY_TITLE_TERMS)
    if heavy_title or len(heavy_hits) >= 3:
        score -= 20
        risks.append("сильный уклон в полноценную backend/engineering-разработку")

    if any(term in title for term in IRRELEVANT_TITLE_TERMS) and skill_score < 25:
        score = min(score, 10)
        risks.append("нерелевантная основная профессия")

    score = max(0, min(100, int(score)))
    is_fit = bool(ranked_categories) and score >= min_score

    return FitResult(
        score=score,
        is_fit=is_fit,
        categories=ranked_categories,
        reasons=reasons[:6],
        risks=risks[:4],
        credit_status=credit_status,
        remote=remote,
        project=project,
        age_hours=age_hours,
        salary_rub=salary_rub,
    )


def is_vacancy_suitable(text: str, min_score: int = 35) -> bool:
    """Compatibility wrapper for the optional Telegram-channel listener."""
    return score_vacancy(
        {"name": "", "description": text, "employer": {}, "snippet": {}},
        min_score=min_score,
    ).is_fit
