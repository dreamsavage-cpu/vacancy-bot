# AI Job Radar — HH.ru

Персональный **read-only** радар вакансий на базе свежего форка
[aos-developer-sys/vacancy-bot](https://github.com/aos-developer-sys/vacancy-bot).

Эта ветка переделана под четыре направления:

1. **AI Video** — Higgsfield, Runway, Veo, Kling, Seedance, CapCut, AI UGC, short-form.
2. **AI / LLM automation** — GPT, OpenAI, Claude, RAG, AI agents, n8n, MCP.
3. **Bots / parsers / API** — Telegram bots, parsers, scraping, API integrations, Python automation.
4. **3D** — Blender, FreeCAD, CAD, простое 3D-моделирование/визуализация.

## Что делает

```
HH.ru API
  ↓
новые вакансии + полное описание
  ↓
локальные Fit Score + Money Risk (каждый 0–100)
  ↓
SQLite dedup/cutoff
  ↓
Telegram Bot API
```

В сообщении показываются:

- `Fit Score` 0–100 — насколько вакансия подходит по направлению и формату;
- `Money Risk` 0–100 — риск собственных расходов или слишком дорогой/тяжёлой доставки;
- зарплата;
- remote/project;
- свежесть;
- причины совпадения;
- риски;
- отдельно — кто оплачивает AI-сервисы, если это можно понять из текста;
- позитивный флаг, если клиент явно предоставляет AI-доступы или кредиты.

Первая строка Telegram-уведомления выглядит так:

```text
🔥 Fit 86 / Money Risk 22 — очень сильный матч
```

Оценки независимы: вакансия может хорошо совпадать по теме, но иметь высокий
`Money Risk` из-за собственных подписок, конвейерного объёма или full-time нагрузки.

## Чего НЕ делает

- не откликается на вакансии;
- не пишет работодателям;
- не меняет резюме/профиль;
- не использует аккаунт соискателя;
- не обходит CAPTCHA/лимиты;
- не требует платного LLM API для scoring.

## HH OAuth

После прекращения applicant API используется **токен приложения**.

Предпочтительный вариант после одобрения приложения:

```env
HH_ACCESS_TOKEN=...
```

Если текущего app token ещё нет, можно оставить `HH_ACCESS_TOKEN` пустым и
задать `HH_CLIENT_ID` / `HH_CLIENT_SECRET`; бот один раз запросит токен и
сохранит его в локальный `hh_app_token.json` (файл исключён из git).

Бот **не делает периодический refresh** app token.

## Быстрый тест без одобрения HH

Пока приложение HH рассматривается, scoring можно проверить вообще без ключей:

```bash
git clone https://github.com/dreamsavage-cpu/vacancy-bot.git
cd vacancy-bot
git checkout ai-job-radar

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python hh_bot.py --fixtures fixtures/sample_vacancies.json
python -m unittest discover -s tests -v
```

## Настройка после одобрения HH

```bash
cp .env.example .env
```

Минимум:

```env
HH_ACCESS_TOKEN=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Затем:

```bash
python hh_bot.py --once --dry-run
```

Если выдача адекватная:

```bash
python hh_bot.py --once
```

Постоянный монитор:

```bash
python hh_bot.py
```

По умолчанию интервал — 30 минут.

## Фильтры

По умолчанию remote и project **не являются жёстким фильтром**. За них начисляется
бонус к score, чтобы не потерять нормальную постоянную удалёнку.

Если нужен только remote:

```env
HH_REMOTE_ONLY=true
```

Только project:

```env
HH_PROJECT_ONLY=true
```

Также можно передать явные значения справочников HH:

```env
HH_WORK_FORMAT=REMOTE
HH_EMPLOYMENT_FORM=PROJECT
```

## Как считается второй слой

`Fit Score` повышают:

- AI Video и AI-content production;
- простая AI-автоматизация, n8n/Make/Zapier;
- Telegram-боты, парсеры и API-интеграции;
- простое 3D в Blender/FreeCAD;
- remote, project/part-time, свежесть и указанная зарплата;
- явное обещание клиента предоставить AI-доступы/кредиты.

Сильный штраф к `Fit Score` получают Senior Backend, DevOps, ML Engineer,
System Design, Kubernetes, highload и production engineering. Один случайный
технический термин не равен senior-роли: самый сильный штраф применяется к
заголовку тяжёлой роли или сочетанию нескольких обязательных технологий.

`Money Risk` повышают отдельные сигналы:

- свои платные AI-подписки/аккаунты: `+45`;
- платные AI-инструменты без указания плательщика: `+18`;
- senior/heavy production stack: `+32…38`;
- обязательный coding-heavy стек: `+22`;
- высокая скорость или объём производства: `+28`;
- обязательная full-time/40h+ загрузка: `+24`.

Итог ограничивается диапазоном 0–100. Правила находятся в `filters.py`, работают
локально и детерминированно — никакой платный LLM для оценки не вызывается.

## Telegram

Для HH используется обычный **Telegram Bot API** — личный Telegram user-session не нужен.

Старый `vacancy_bot.py` оставлен только как опциональный listener Telegram-каналов.
Для него отдельно установи:

```bash
pip install -r requirements-telegram-listener.txt
```

## Безопасность

`.env`, app token, SQLite и session-файлы исключены из git. Не коммить секреты.
