# Описание системы: LLM-бот для проведения качественных исследований

**Проект:** Выпускная квалификационная работа  
**Тема:** Разработка LLM-бота для качественных исследований  
**Статус:** Система развёрнута, протестирована и готова к проведению полевого исследования

---

## 1. Назначение системы

Система автоматизирует проведение структурированных качественных интервью через Telegram. Бот последовательно задаёт вопросы сценария, генерирует контекстно-осведомлённые подтверждения ответов с помощью LLM, распознаёт уклонение и уточняющие вопросы от респондентов, а результаты накапливаются в базе данных для последующего анализа.

**Проблема, которую решает система:**  
Классическое качественное интервью требует участия живого интервьюера, ограничивая масштабируемость и внося интервьюерский эффект. Бот проводит структурированные интервью в асинхронном режиме — респондент отвечает в удобное время, LLM обеспечивает естественность диалога, а данные поступают исследователю без ручной обработки.

**Целевые пользователи:**
- **Респонденты** — проходят интервью в Telegram
- **Исследователь** — управляет исследованиями через Telegram-меню и веб-панель, анализирует результаты

---

## 2. Функциональное описание

### 2.1 Для респондентов (Telegram-бот)

**Сценарий взаимодействия:**
```
/start → Приветственный экран + кнопка «▶ Начать интервью»
       → [кнопка нажата] → Вопрос 1
       → Ответ → LLM-подтверждение + Вопрос 2
       → Ответ → LLM-подтверждение + Вопрос 3
       → Ответ → LLM-завершение → кнопка «🔄 Пройти ещё раз»
```

| Функция | Описание |
|---|---|
| Двухшаговый старт | `/start` показывает приветствие из активного исследования и кнопку «Начать интервью» — без немедленного сброса сессии |
| Последовательные вопросы | Все вопросы берутся из активного сценария исследования |
| Прогресс-метка | Каждый вопрос сопровождается меткой «Вопрос N из M» |
| LLM-подтверждение | После каждого ответа LLM генерирует 1–2 нейтральных предложения, опционально отражая контекст предыдущих ответов |
| LLM-завершение | После последнего ответа LLM формирует персонализированное финальное сообщение |
| Распознавание уклонения | LLM-классификатор (ДА/НЕТ) + keyword-эвристика определяют нерелевантные ответы; бот мягко возвращает к текущему вопросу |
| Распознавание уточнений | LLM-классификатор выявляет вопросы о формулировке («?»); бот даёт пояснение без продвижения вперёд |
| Fallback-режим | При недоступности LLM — статичные тексты из скрипта; интервью не прерывается |
| Возобновление сессии | Незавершённое интервью сохраняется в БД; можно продолжить позже |
| Rate limiting | Не более 10 сообщений за 60 сек на пользователя; мягкое предупреждение без блокировки |

### 2.2 Для исследователя (Telegram-меню)

Доступно командой `/researcher` пользователям из whitelist (`RESEARCHER_TELEGRAM_IDS`):

| Функция | Описание |
|---|---|
| Список исследований | Все созданные Study с их статусами |
| Активация исследования | Переключение активного сценария — применяется **мгновенно**, без перезапуска бота |
| Статистика | Количество завершённых сессий |
| Экспорт данных | CSV с ответами всех респондентов прямо в Telegram |
| Переключение LLM | Смена провайдера (GigaChat / OpenAI / статичный режим) в runtime |

### 2.3 Веб-административная панель

Доступна по адресу `https://soc-oprosnik.duckdns.org/admin` (HTTPS + Basic Auth):

| Маршрут | Функции |
|---|---|
| `/admin/studies` | Список всех исследований, создание нового |
| `/admin/studies/new` | Создание сценария через веб-форму (YAML-формат вопросов) |
| `/admin/studies/{id}` | Просмотр, редактирование, активация исследования |
| `/admin/analytics` | Страница метрик: completion rate, dropout, средняя длина ответов, продолжительность |
| `/admin/analytics/export` | Скачать CSV со всеми ответами |
| `/admin/sessions` | Список всех сессий респондентов (с пагинацией) |
| `/admin/sessions/{id}` | Полная история диалога одного респондента (пары вопрос/ответ) |
| `/health` | JSON `{"status":"ok"}` для мониторинга |

**Формат сценария интервью (YAML):**
```yaml
title: "Исследование пользовательского опыта"
description: "Качественное интервью об ИИ-инструментах"
questions:
  - id: q1
    text: "Расскажите, как ИИ-инструменты вошли в вашу повседневную жизнь."
  - id: q2
    text: "Какие задачи вы решаете с их помощью чаще всего?"
```

При активации исследования через веб-панель на странице появляется предупреждение с инструкцией по перезапуску бота. Активация через Telegram-меню (`/researcher`) применяется мгновенно без перезапуска.

---

## 3. Архитектура системы

### 3.1 Общая схема

```
Интернет
    │
    ▼
[Cloudflare Worker]  ← проксирует запросы к Telegram API
    │
    ▼
[Cloud.ru VM: Ubuntu 22.04]
    │
    ├─► [nginx :443 / :80]  ← TLS termination, HTTP→HTTPS redirect
    │       │
    │       ▼
    │   [uvicorn :8000]  ← FastAPI web-admin   (systemd: interview-web.service)
    │
    └─► [Python polling]  ← Telegram-бот       (systemd: interview-bot.service)

Оба процесса работают с общим файлом:
    /srv/interview/interview.db  (SQLite + WAL mode)
```

### 3.2 Компоненты системы

| Компонент | Технология | Назначение |
|---|---|---|
| Telegram-бот | python-telegram-bot 20.x | Интерфейс респондентов |
| Web API | FastAPI + Jinja2 | Административный интерфейс |
| ASGI-сервер | Uvicorn | Запуск FastAPI в продакшене |
| База данных | SQLite (WAL mode) | Хранение сессий и исследований |
| ORM | SQLAlchemy 2.x | Работа с БД |
| LLM-провайдер | GigaChat (Sber) / OpenAI | Генерация подтверждений, классификация |
| Прокси | Cloudflare Worker | Обход сетевых ограничений |
| Обратный прокси | nginx | Роутинг, TLS termination |
| Управление процессами | systemd | Автозапуск, Restart=always |
| CI | GitHub Actions | Автозапуск pytest на каждый push/PR |

### 3.3 Структура кода

```
app/
├── core/
│   ├── config.py           # Конфигурация через .env (Pydantic Settings)
│   └── security.py         # HTTP Basic Auth для веб-панели
├── bot/
│   ├── adapter.py          # Telegram Application builder, обработчики
│   ├── keyboards.py        # InlineKeyboard builders (CALLBACK_BEGIN, CALLBACK_RESTART)
│   ├── rate_limiter.py     # Защита от спама (sliding window)
│   └── researcher_menu.py  # Меню исследователя в Telegram
├── services/
│   ├── dialog_manager.py   # Конечный автомат диалога (welcome/begin/process)
│   ├── prompt_engine.py    # PromptEngine Protocol + StaticPromptEngine
│   └── session_store.py    # Protocol SessionStore + InMemorySessionStore
├── llm/
│   ├── client.py           # Клиенты GigaChat и OpenAI (LLMClient Protocol)
│   ├── engine.py           # LLMPromptEngine: acknowledgment, closing, classifiers
│   └── guardrails.py       # Валидация LLM-вывода (validate_ack, validate_closing, validate_clarify)
├── db/
│   ├── database.py         # Инициализация БД, build_engine, init_db
│   ├── models.py           # SQLAlchemy ORM-модели (Study, InterviewSession, Answer)
│   └── repository.py       # CRUD: SQLiteSessionStore, get_all_sessions
├── analysis/
│   ├── metrics.py          # completion_rate, dropout_distribution, avg_answer_length, duration_stats
│   └── export.py           # SessionRecord, AnswerRecord, to_csv
├── researcher/
│   ├── models.py           # StudyDefinition, QuestionDef, StudyTexts (Pydantic)
│   └── repository.py       # StudyRepository (CRUD для Study)
├── admin/
│   ├── router.py           # FastAPI роуты /admin/*, /health
│   ├── templates/          # Jinja2 шаблоны (base, studies, analytics, sessions)
│   └── static/             # admin.css
└── main.py                 # FastAPI app, lifespan, глобальный error handler

deploy/
├── interview-web.service   # systemd unit для uvicorn
├── interview-bot.service   # systemd unit для бота
├── nginx.conf              # Конфиг nginx (HTTPS + proxy_pass)
├── interview-backup.cron   # Ежедневный backup + PRAGMA integrity_check
├── RUNBOOK.md              # Операционная инструкция: deploy, rollback, диагностика
└── OPS_REFERENCE.md        # Шпаргалка: journalctl, nginx, certbot, SQLite

scripts/
└── smoke_check.sh          # Post-deploy проверка: systemd + /health + /admin + TLS

.github/
└── workflows/tests.yml     # CI: pytest на каждый push и PR в main

tests/                      # 249 тестов (pytest)
```

---

## 4. Модель данных

### Study (исследование)

| Поле | Тип | Описание |
|---|---|---|
| id | INTEGER PK | Идентификатор |
| title | TEXT | Название исследования |
| description | TEXT | Описание |
| questions_json | TEXT | JSON-массив вопросов (question_id + text) |
| texts_json | TEXT | JSON тексты: greeting, closing, already_done, redirect |
| is_active | BOOLEAN | Активное исследование (только одно одновременно) |
| created_at | DATETIME | Дата создания |

### InterviewSession (сессия)

| Поле | Тип | Описание |
|---|---|---|
| id | INTEGER PK | Идентификатор |
| user_id | INTEGER | Telegram user_id |
| study_id | INTEGER FK | Привязка к исследованию |
| current_question_index | INTEGER | Индекс текущего вопроса (0-based) |
| finished | BOOLEAN | Интервью завершено |
| started_at | DATETIME | Начало сессии |
| finished_at | DATETIME | Завершение (NULL если не завершено) |

### Answer (ответ)

| Поле | Тип | Описание |
|---|---|---|
| id | INTEGER PK | Идентификатор |
| session_id | INTEGER FK | Привязка к сессии |
| question_id | TEXT | ID вопроса (q1, q2, ...) |
| text | TEXT | Текст ответа |
| answered_at | DATETIME | Время ответа |

---

## 5. LLM-интеграция

### Архитектура LLM-слоя

Система построена на двух реализациях Protocol `PromptEngine`:

**`StaticPromptEngine`** — детерминированный режим:
- Тексты берутся из `StudyDefinition` (если исследование активно) или из `interview_script.py`
- Off-topic: keyword-эвристика
- Уточняющий вопрос: проверка окончания на «?»
- Используется как fallback при недоступности LLM

**`LLMPromptEngine`** — режим с языковой моделью:
- Wraps `StaticPromptEngine` для статичных текстов; LLM добавляет только динамические элементы
- Acknowledgment: 1–2 нейтральных предложения с учётом истории Q&A (до текущего вопроса)
- Closing: персонализированное финальное сообщение с кратким отражением всех ответов
- Off-topic classifier: промпт ДА/НЕТ + keyword fallback
- Clarify classifier: промпт ДА/НЕТ + «?»-эвристика fallback
- Clarify response: LLM-разъяснение + статичный вопрос из скрипта

### Guardrails (защита от некорректного LLM-вывода)

| Guardrail | Условие отклонения | Fallback |
|---|---|---|
| `validate_ack` | Содержит «?», длиннее 300 символов, пустой | Пустой ack — участник видит только вопрос |
| `validate_closing` | Содержит «?», длиннее 800 символов, пустой | `script.CLOSING` |
| `validate_clarify` | Содержит «?», длиннее 400 символов, пустой | Статичный fallback с текстом вопроса |

### Поддерживаемые провайдеры

| Провайдер | Модель | Особенности |
|---|---|---|
| GigaChat (Sber) | GigaChat | Основной провайдер; российская юрисдикция |
| OpenAI | gpt-4o-mini | Альтернативный провайдер |
| Статичный | — | Без LLM; детерминированные тексты |

Переключение провайдера доступно через Telegram researcher-меню без перезапуска.

### Conversation history

`LLMPromptEngine._build_history()` передаёт LLM все предыдущие пары «вопрос / ответ» при генерации acknowledgment и closing. Это позволяет модели формировать контекстно-осведомлённые фразы подтверждения (не цитируя ответы дословно).

---

## 6. Диалоговый автомат

`DialogManager` управляет состоянием сессии и реализует следующую логику:

```
welcome()  → engine.intro() + «Нажмите кнопку ниже, чтобы начать.»
begin()    → store.reset() → engine.question(idx=0)
process()  →
    if session.finished      → already_done()
    if is_off_topic(text)    → redirect() + текущий вопрос (без продвижения, без сохранения)
    if is_clarifying(text)   → clarify() + текущий вопрос (без продвижения, без сохранения)
    else                     → сохранить ответ, advance index
                               if есть следующий вопрос → question()
                               else → session.finished=True, closing()
```

`DialogResult` возвращает `text` и `kind` (`question` / `closing` / `already_done` / `redirect` / `clarify`) — Telegram-слой использует `kind` для выбора markup (кнопки появляются только при `closing` и `already_done`).

---

## 7. Безопасность

| Мера | Реализация |
|---|---|
| Аутентификация веб-панели | HTTP Basic Auth (`secrets.compare_digest`) поверх HTTPS |
| Шифрование транспорта | TLS 1.2/1.3 (Let's Encrypt + Duck DNS, автообновление certbot.timer) |
| Rate limiting бота | Sliding window: 10 сообщений / 60 сек на пользователя; 20 callback / 60 сек |
| Ограничение размера ввода | Сообщения > 2000 символов отклоняются с мягким ответом |
| Таймаут LLM | 30 сек для GigaChat и OpenAI |
| Audit logging | Все действия исследователя: `[AUDIT] action=... user_id=...` |
| Whitelist исследователей | `RESEARCHER_TELEGRAM_IDS` в `.env` |
| Секреты | `.env` файл, права 600, исключён из git |
| Uvicorn | Слушает только 127.0.0.1 (доступен снаружи только через nginx) |
| Глобальный error handler | 500-ошибки возвращают страницу без stack trace |

---

## 8. Развёртывание и операционная зрелость

### Инфраструктура

| Параметр | Значение |
|---|---|
| Облако | Cloud.ru (Ubuntu 22.04 LTS, ru-central) |
| VM | 2 vCPU, 4 GB RAM, 20 GB SSD |
| Домен | `soc-oprosnik.duckdns.org` (бесплатный Duck DNS) |
| HTTPS | Let's Encrypt (Certbot), автообновление через `certbot.timer` |
| Прокси | Cloudflare Worker (обход сетевых ограничений для Telegram API) |

### CI/CD

**CI:** GitHub Actions — `python -m pytest tests/ -q --tb=short` на каждый push и pull request в `main`. Тесты проходят за 30–60 секунд.

**CD:** Ручной деплой (`git pull && systemctl restart`) с pre-deploy checklist по `deploy/RUNBOOK.md`.

**Post-deploy проверка:**
```bash
bash scripts/smoke_check.sh
# → [OK] All checks passed (5/5)
```
Скрипт проверяет: статус systemd-сервисов, `/health`, `/admin/studies` с Basic Auth, TLS-сертификат.

### Бэкап

Ежедневный `sqlite3 .backup` (hot backup API) с последующей проверкой целостности:
```bash
sqlite3 backup.db "PRAGMA integrity_check;"  # → ok
```
Ротация 14 дней; файлы в `/srv/interview/backups/`. При ошибке целостности — запись в системный журнал через `logger`.

---

## 9. Аналитика

Страница `/admin/analytics` отображает метрики активного исследования:

| Метрика | Описание |
|---|---|
| Completion rate | Доля завершённых интервью |
| Dropout distribution | Количество прерванных сессий по каждому вопросу |
| Avg answer length | Средняя длина ответа (в символах) по каждому вопросу |
| Duration stats | Min / среднее / max время прохождения интервью |

Данные доступны в браузере (таблицы) и в виде CSV (кнопка «📥 Скачать CSV»).

---

## 10. Известные ограничения

| Ограничение | Обоснование / Митигация |
|---|---|
| SQLite вместо PostgreSQL | Достаточно для нагрузки ВКР (< 100 сессий); WAL mode обеспечивает конкурентное чтение |
| In-memory rate limiter | Сбрасывается при перезапуске; для production-нагрузки — Redis |
| Один воркер uvicorn | Достаточно для единственного исследователя |
| Веб-активация без hot reload | Требует `systemctl restart interview-bot`; активация через Telegram-меню мгновенна |
| Backup на том же диске | Защита от ошибок данных, не от потери диска; для production — rsync на внешний хост |

---

## 11. Доступ для тестирования

| Ресурс | Адрес | Доступ |
|---|---|---|
| Telegram-бот | @soc_oprosnik_bot | Открытый — отправить `/start` |
| Веб-панель | `https://soc-oprosnik.duckdns.org/admin` | Basic Auth (запросить у автора) |
| Health check | `https://soc-oprosnik.duckdns.org/health` | Открытый |
| Исходный код | github.com/Sashizo/oprosnik_bot | Публичный репозиторий |

---

## 12. Стек технологий

| Категория | Технология | Версия |
|---|---|---|
| Язык | Python | 3.13 |
| Telegram SDK | python-telegram-bot | 20.x |
| Web framework | FastAPI | — |
| Шаблонизатор | Jinja2 | — |
| ORM | SQLAlchemy | 2.x |
| Валидация конфига | Pydantic Settings | v2 |
| LLM (основной) | GigaChat SDK | — |
| LLM (альтернатива) | OpenAI SDK | — |
| ASGI сервер | Uvicorn | — |
| Обратный прокси | nginx | — |
| БД | SQLite | WAL mode |
| ОС сервера | Ubuntu | 22.04 LTS |
| Облако | Cloud.ru | Evolution |
| CDN/прокси | Cloudflare Workers | Free tier |
| Тестирование | pytest | 249 тестов |
| CI | GitHub Actions | — |

---

*Документ актуален по состоянию на завершение Milestone 20 (Operational Maturity).*  
*Вопросы и комментарии научного руководителя приветствуются.*
