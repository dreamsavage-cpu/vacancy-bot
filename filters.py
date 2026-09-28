"""Transparent, deterministic scoring for the personal AI job radar.

Fit Score answers "how suitable is this work?". Money Risk answers "how likely
is the job to require the user's own money or an expensive delivery setup?".
The two values are intentionally independent and require no paid LLM API.
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import re
from typing import Any


CATEGORY_TERMS: dict[str, list[tuple[str, int]]] = {
    "AI Video": [
        ("ai video", 24), ("ai creator", 20), ("ai-generated video", 22),
        ("генеративное видео", 22), ("нейросет", 8), ("higgsfield", 18),
        ("runway", 14), ("veo", 14), ("kling", 12), ("seedance", 12),
        ("pika", 8), ("capcut", 7), ("ugc", 7), ("short-form", 7),
        ("reels", 5), ("shorts", 5), ("lip-sync", 7), ("lipsync", 7),
    ],
    "Simple AI automation": [
        ("ai automation", 24), ("простая автоматизац", 20),
        ("no-code", 12), ("low-code", 12), ("llm", 14), ("gpt", 12),
        ("openai", 10), ("claude", 9), ("ai agent", 18),
        ("ai-агент", 18), ("ии-агент", 18), ("нейроагент", 18),
        ("n8n", 16), ("make.com", 13), ("zapier", 13), ("mcp", 9),
        ("prompt engineering", 8),
    ],
    "Telegram bots / parsers / API": [
        ("telegram bot", 24), ("telegram-бот", 24), ("телеграм-бот", 24),
        ("чат-бот", 18), ("chatbot", 16), ("парсер", 20), ("parser", 17),
        ("scraping", 16), ("web scraping", 16), ("playwright", 9),
        ("selenium", 9), ("api integration", 18), ("api интеграц", 18),
        ("интеграция api", 18), ("python automation", 15),
        ("мониторинг", 7), ("webhook", 9),
    ],
    "Simple 3D": [
        ("blender", 22), ("freecad", 22), ("простое 3d", 22),
        ("простое 3д", 22), ("3d model", 16), ("3d modeling", 16),
        ("3д модел", 16), ("3d визуал", 12), ("3д визуал", 12),
        ("3d render", 10), ("cad", 8),
    ],
}

IRRELEVANT_TITLE_TERMS = [
    "бухгалтер", "кассир", "водитель", "кладовщик", "курьер", "официант",
    "повар", "медсест", "врач", "юрист", "охранник", "электрик", "сварщик",
]

SENIOR_ENGINEERING_TITLE_TERMS = [
    "senior backend", "senior developer", "senior software", "senior python",
    "lead backend", "backend lead", "tech lead", "тимлид", "team lead",
    "backend developer", "backend engineer", "devops engineer", "ml engineer",
    "machine learning engineer", "data scientist", "platform engineer",
    "site reliability engineer", "sre engineer", "архитектор систем",
]
HEAVY_ENGINEERING_TERMS = [
    "kubernetes", "k8s", "django", "fastapi", "postgresql", "redis",
    "microservice", "микросервис", "ci/cd", "system design", "системный дизайн",
    "production engineering", "production-grade", "production system",
    "промышленная разработка", "highload", "high load", "distributed system",
    "распределенные системы", "распределённые системы", "golang", "java spring",
    "pytorch", "tensorflow", "mlops", "airflow", "algorithms", "алгоритм",
]
CODING_HEAVY_TERMS = [
    "coding-heavy", "strong coding", "advanced python", "глубокое знание python",
    "коммерческая разработка", "code review", "unit testing", "integration testing",
    "software architecture", "архитектура по", "computer science",
]

CREDIT_PROVIDED_TERMS = [
    "предоставим доступ", "предоставляем доступ", "доступы предостав",
    "оплачиваем подписк", "подписки оплачивает", "кредиты предостав",
    "credits provided", "we provide access", "subscriptions covered",
    "company account", "company-provided account", "tools are provided",
    "full access to higgsfield", "access to higgsfield", "cover subscriptions",
]
CREDIT_OWN_TERMS = [
    "свои подписк", "собственные подписк", "свои аккаунт", "собственные аккаунт",
    "за свой счет", "за свой счёт", "личная подписка", "own subscription",
    "own account", "your own subscription", "your own account", "at your expense",
]
PAID_AI_TOOL_TERMS = [
    "higgsfield", "runway", "veo", "kling", "seedance", "midjourney",
    "elevenlabs", "flux", "pika", "suno", "heygen", "sora",
]
HIGH_VOLUME_TERMS = [
    "high volume", "high-volume", "large volume", "быстрый темп", "высокий темп",
    "большой объем", "большой объём", "массовое производство", "конвейер",
    "ежедневный выпуск", "каждый день", "daily output", "tight deadlines",
]
FULL_TIME_TERMS = [
    "full-time", "full time", "полный рабочий день", "полная занятость",
    "40 hours", "40+ hours", "40 часов", "forty hours",
]


@dataclass
class FitResult:
    fit_score: int
    money_risk: int
    is_fit: bool
    categories: list[str]
    reasons: list[str]
    risks: list[str]
    positive_flags: list[str]
    credit_status: str
    remote: bool
    project: bool
    age_hours: float | None
    salary_rub: int | None

    @property
    def score(self) -> int:
        """Backward-compatible alias for integrations using the old field."""
        return self.fit_score


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
    for skill in vacancy.get("key_skills") or []:
        parts.append((skill.get("name") or "") if isinstance(skill, dict) else str(skill))
    return " ".join(parts)


def _has_high_output_requirement(text: str) -> bool:
    if any(_contains(text, term) for term in HIGH_VOLUME_TERMS):
        return True
    quantity_patterns = [
        (r"\b(?:от\s*)?([1-9]\d*)\s*(?:видео|ролик\w*|креатив\w*)\s*(?:в|за)\s*(?:день|сутки)", 5),
        (r"\b(?:от\s*)?([1-9]\d*)\s*(?:видео|ролик\w*|креатив\w*)\s*(?:в|за)\s*недел", 20),
        (r"\b([1-9]\d*)\+?\s*(?:videos?|clips?|creatives?)\s*(?:per|a)\s*day", 5),
        (r"\b([1-9]\d*)\+?\s*(?:videos?|clips?|creatives?)\s*(?:per|a)\s*week", 20),
    ]
    for pattern, threshold in quantity_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match and int(match.group(1)) >= threshold:
            return True
    return False


def score_vacancy(vacancy: dict, min_score: int = 45, now: dt.datetime | None = None) -> FitResult:
    text = _vacancy_text(vacancy)
    lower = text.lower()
    title = (vacancy.get("name") or "").lower()

    category_scores: dict[str, int] = {}
    category_hits: dict[str, list[str]] = {}
    for category, terms in CATEGORY_TERMS.items():
        hits = [term for term, _weight in terms if _contains(text, term)]
        if hits:
            raw_score = sum(weight for term, weight in terms if term in hits)
            category_scores[category] = min(raw_score, 48)
            category_hits[category] = hits

    skill_score = min(sum(category_scores.values()), 62)
    fit_score = skill_score
    money_risk = 0
    reasons: list[str] = []
    risks: list[str] = []
    positive_flags: list[str] = []

    ranked_categories = sorted(category_scores, key=category_scores.get, reverse=True)
    for category in ranked_categories[:2]:
        reasons.append(f"{category}: {', '.join(category_hits[category][:4])}")

    if any(
        _contains(title, term)
        for terms in CATEGORY_TERMS.values()
        for term, _weight in terms
    ):
        fit_score += 10
        reasons.append("ключевая специализация прямо в названии")

    work_formats = _ids(vacancy.get("work_format"))
    schedules = _ids(vacancy.get("schedule"))
    remote = "REMOTE" in work_formats or "remote" in schedules
    if remote:
        fit_score += 12
        reasons.append("удалённо")

    employment_forms = _ids(vacancy.get("employment_form"))
    legacy_employment = _ids(vacancy.get("employment"))
    project = bool(
        employment_forms & {"PROJECT", "SIDE_JOB"}
        or legacy_employment & {"project", "part"}
    )
    if project:
        fit_score += 10
        reasons.append("проект / подработка")

    age_hours = _published_age_hours(vacancy.get("published_at"), now=now)
    if age_hours is not None:
        if age_hours <= 2:
            fit_score += 10
            reasons.append("опубликована менее 2 часов назад")
        elif age_hours <= 6:
            fit_score += 7
            reasons.append("опубликована менее 6 часов назад")
        elif age_hours <= 24:
            fit_score += 3
            reasons.append("опубликована сегодня")

    salary_rub = extract_salary_rub(vacancy)
    if salary_rub is not None:
        if salary_rub >= 150_000:
            fit_score += 10
        elif salary_rub >= 100_000:
            fit_score += 7
        elif salary_rub >= 70_000:
            fit_score += 4
        reasons.append(f"доход до/от {salary_rub:,} ₽".replace(",", " "))

    has_paid_tools = any(_contains(lower, term) for term in PAID_AI_TOOL_TERMS)
    has_provided_credits = any(_contains(lower, term) for term in CREDIT_PROVIDED_TERMS)
    has_own_credits = any(_contains(lower, term) for term in CREDIT_OWN_TERMS)
    if has_own_credits:
        credit_status = "own"
        money_risk += 45
        fit_score -= 12
        risks.append("нужны свои платные AI-подписки/аккаунты")
    elif has_provided_credits:
        credit_status = "provided"
        fit_score += 5
        positive_flags.append("клиент явно предоставляет AI-доступы/кредиты")
    elif has_paid_tools:
        credit_status = "unspecified"
        money_risk += 18
        fit_score -= 4
        risks.append("не указано, кто оплачивает AI-сервисы/кредиты")
    else:
        credit_status = "not_applicable"

    heavy_hits = [term for term in HEAVY_ENGINEERING_TERMS if _contains(lower, term)]
    coding_hits = [term for term in CODING_HEAVY_TERMS if _contains(lower, term)]
    senior_engineering = any(term in title for term in SENIOR_ENGINEERING_TITLE_TERMS)
    if senior_engineering:
        fit_score -= 48
        money_risk += 38
        risks.append("Senior Backend/DevOps/ML/production engineering — слишком тяжёлый стек")
    elif len(heavy_hits) >= 3:
        fit_score -= 38
        money_risk += 32
        risks.append("обязателен тяжёлый production/backend/ML-стек")
    elif heavy_hits or coding_hits:
        fit_score -= 22
        money_risk += 22
        risks.append("coding-heavy стек выходит за рамки простой автоматизации")

    if _has_high_output_requirement(lower):
        fit_score -= 8
        money_risk += 28
        risks.append("высокая скорость/объём производства")

    full_time_ids = {x.lower() for x in employment_forms | legacy_employment | schedules}
    full_time = bool(full_time_ids & {"full", "full_time", "fulltime", "fullday"}) or any(
        _contains(lower, term) for term in FULL_TIME_TERMS
    )
    if full_time and not project:
        fit_score -= 10
        money_risk += 24
        risks.append("обязательная full-time/40h+ загрузка")

    if any(term in title for term in IRRELEVANT_TITLE_TERMS) and skill_score < 25:
        fit_score = min(fit_score, 10)
        risks.append("нерелевантная основная профессия")

    fit_score = max(0, min(100, int(fit_score)))
    money_risk = max(0, min(100, int(money_risk)))
    is_fit = bool(ranked_categories) and fit_score >= min_score

    return FitResult(
        fit_score=fit_score,
        money_risk=money_risk,
        is_fit=is_fit,
        categories=ranked_categories,
        reasons=reasons[:6],
        risks=risks[:6],
        positive_flags=positive_flags,
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
