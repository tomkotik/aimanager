#!/bin/bash
# Скрипт деплоя AgentBox на сервер
# Использование:
#   GATE_AGENT_ID=<agent_uuid> ./scripts/deploy.sh <domain>
#   (или GATE_ENABLED=0 чтобы временно пропустить release gate)

set -euo pipefail

DOMAIN="${1:?Укажите домен: ./scripts/deploy.sh example.com}"
GATE_ENABLED="${GATE_ENABLED:-1}"
GATE_AGENT_ID="${GATE_AGENT_ID:-${AGENT_ID:-}}"

echo "=== Деплой AgentBox на $DOMAIN ==="

# 1. Подставить домен в nginx конфиг
sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" nginx/nginx.conf
sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" .env.production

# 2. Генерация паролей если не заданы
if grep -q "сгенерировать" .env.production; then
  DB_PASS=$(openssl rand -base64 24)
  SECRET=$(openssl rand -base64 32)
  sed -i "s|сгенерировать-длинный-пароль|$DB_PASS|g" .env.production
  sed -i "s|сгенерировать-длинный-ключ|$SECRET|g" .env.production
  echo "Пароли сгенерированы"
fi

# 3. Получить SSL-сертификат (первый раз)
if [ ! -d "nginx/certbot/conf/live/$DOMAIN" ]; then
  echo "=== Получение SSL-сертификата ==="
  # Сначала запускаем nginx без SSL для challenge
  docker compose -f docker-compose.prod.yml up -d nginx
  sleep 2
  docker compose -f docker-compose.prod.yml run --rm certbot certonly \
    --webroot --webroot-path=/var/www/certbot \
    --email admin@$DOMAIN --agree-tos --no-eff-email \
    -d $DOMAIN
  docker compose -f docker-compose.prod.yml down
fi

# 4. Stage 1: поднимаем только backend-кандидат (db/redis/app)
echo "=== Stage 1: Backend candidate ==="
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build db redis app

# 5. Миграции
sleep 10
docker compose -f docker-compose.prod.yml --env-file .env.production exec -T app alembic upgrade head

# 6. Release gate (блокирует релиз при провале критических кейсов)
if [[ "$GATE_ENABLED" == "1" ]]; then
  if [[ -z "$GATE_AGENT_ID" ]]; then
    echo "ERROR: GATE_AGENT_ID не задан. Деплой остановлен release-gate'ом." >&2
    echo "Подсказка: GATE_AGENT_ID=<uuid> ./scripts/deploy.sh $DOMAIN" >&2
    exit 1
  fi

  echo "=== Stage 2: Release gate ==="
  DB_PASS="$(grep '^DB_PASSWORD=' .env.production | head -n1 | cut -d'=' -f2-)"
  APP_DB_URL="postgresql+asyncpg://agentbox:${DB_PASS}@db:5432/agentbox"

  docker compose -f docker-compose.prod.yml --env-file .env.production exec -T app \
    env AGENT_ID="$GATE_AGENT_ID" DATABASE_URL="$APP_DB_URL" BASE_URL="http://127.0.0.1:8000" \
    ./scripts/release_gate.sh
else
  echo "=== Release gate пропущен (GATE_ENABLED=0) ==="
fi

# 7. Stage 3: после успешного gate поднимаем остальной стек
echo "=== Stage 3: Full stack ==="
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build worker beat web nginx

echo ""
echo "=== AgentBox запущен ==="
echo "Панель: https://$DOMAIN"
echo "API:    https://$DOMAIN/api/v1/health"
echo ""
echo "Следующий шаг: зарегистрируй агента через панель или CLI"

