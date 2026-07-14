# VKR.Format

Веб-сервис автоматизированного оформления выпускных квалификационных
работ МИИГАиК. Принимает `.docx`, прогоняет через детерминированный
конвейер (без LLM/ML), отдаёт исправленный документ и отчёт о
нарушениях со ссылками на пункты нормативной базы №697-01.

Техническое задание: [docs/ТЗ.docx](docs/ТЗ.docx).
Нормативная база МИИГАиК: [docs/normative/](docs/normative/).

## Структура репозитория

```
services/
  api/         FastAPI: роутеры, alembic-миграции
  worker/      Celery worker (обработка документов в фоне)
  core/        бизнес-логика, движок форматирования, модели, схемы
frontend/      React 18 + Vite + Tailwind + Zustand
infra/         Dockerfile.api, Dockerfile.frontend, nginx.conf
tests/
  unit/        unit-тесты движка (heading_scoring, formulas, pipeline…)
  integration/ API contract
  e2e/         Playwright — сквозные сценарии
  quality/     замер F1, бенчмарк производительности, синтетический корпус
  fixtures/    минимальные .docx-фикстуры
docs/          ТЗ + нормативная база
  archive/     архивные версии ТЗ
  normative/   приказ №697-01 (.pdf/.docx), ГОСТ 7.32-2017
```

## Быстрый старт

```bash
cp .env.example .env
docker compose up --build
```

- Фронтенд: http://localhost
- API-docs: http://localhost/api/docs
- MinIO console: http://localhost:9001 (логин/пароль из `.env`)

## Локальная разработка без docker

```bash
pip install -r services/core/requirements.txt \
            -r services/api/requirements.txt \
            -r services/worker/requirements.txt
SYNC_PROCESSING=true uvicorn services.api.app.main:app --reload
cd frontend && npm install && npm run dev
```

Под `SYNC_PROCESSING=true` обработка идёт прямо в request-thread,
без Celery — удобно для отладки.

## Команды

```bash
make up              # docker compose up --build
make down
make test            # pytest -q
make backend-test    # compileall + pytest
make lint            # ruff check
make format          # ruff format
make frontend-build  # vite build
make coverage        # coverage ≥ 50% по engine/, отчёт в reports/
make quality-report  # F1 + бенчмарк + сводка → reports/quality_summary.json
make e2e             # Playwright E2E (требует поднятого стека)
```

## Авто-проверки

CI (`.github/workflows/ci.yml`): три job'а — `backend` (ruff + pytest),
`quality` (coverage + F1 на синтетическом корпусе + бенчмарк производительности,
результаты загружаются как артефакты), `frontend` (vite build).
Конфиг линтера — в [pyproject.toml](pyproject.toml).

## Хранилище

Файлы хранятся 90 дней (`Document.expires_at`), затем удаляются
автоматически (Celery beat → `cleanup_expired_documents`). Переключатель
`USE_S3` в `.env`: `true` → MinIO/S3, `false` → локальный `./storage`.

## Ключевые правила

- Никаких LLM/ML — всё детерминированно.
- Титульный лист неприкосновенен.
- Содержательная часть документа важнее любого нарушения форматирования.
