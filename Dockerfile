FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir .

COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY src ./src
COPY tenants ./tenants
COPY scripts ./scripts

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
