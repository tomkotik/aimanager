# AgentBox

AgentBox — платформа для развёртывания AI-агентов, которые общаются с клиентами в мессенджерах.

## Стек

- Python 3.12
- FastAPI
- PostgreSQL 16
- Redis 7
- Celery
- SQLAlchemy 2.0 + Alembic
- LiteLLM

## Быстрый старт (dev)

1. Создай файл `.env` на основе `.env.example`:

```bash
cp .env.example .env
```

2. Запусти инфраструктуру и приложение:

```bash
docker compose up -d --build
```

3. Запусти миграции (внутри контейнера `app`):

```bash
docker compose exec app alembic upgrade head
```

4. Проверка:

- `GET http://localhost:8000/health`
- `GET http://localhost:8000/docs`

## Миграции

```bash
docker compose exec app alembic current
docker compose exec app alembic upgrade head
```

## Тесты

```bash
pytest
```

## Тенанты

Конфигурация тенанта хранится в `tenants/<slug>/`:

- `agent.yaml`
- `dialogue_policy.yaml`
- `actions.yaml`
- `knowledge/*.md`
