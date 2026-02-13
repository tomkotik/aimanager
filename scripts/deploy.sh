#!/bin/bash
# Скрипт деплоя AgentBox на сервер
# Использование: ./scripts/deploy.sh <domain>

set -e

DOMAIN="${1:?Укажите домен: ./scripts/deploy.sh example.com}"

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

# 4. Запуск
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build

# 5. Миграции
sleep 10
docker compose -f docker-compose.prod.yml exec app alembic upgrade head

echo ""
echo "=== AgentBox запущен ==="
echo "Панель: https://$DOMAIN"
echo "API:    https://$DOMAIN/api/v1/health"
echo ""
echo "Следующий шаг: зарегистрируй агента через панель или CLI"

