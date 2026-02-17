# Release Gate (AgentBox Productionization Sprint v1)

Минимальный gate перед rollout в production:

1. Пройти авто-регрессию:

```bash
AGENT_ID=<agent_uuid> \
DATABASE_URL=<postgresql+asyncpg://...> \
python3 scripts/regression_matrix.py --base-url http://127.0.0.1:8000
```

2. Если скрипт вернул `exit code != 0` — релиз блокируется.

3. Для production-деплоя gate встроен в `scripts/deploy.sh` (stage 2):

```bash
GATE_AGENT_ID=<agent_uuid> ./scripts/deploy.sh <domain>
```

Если `GATE_AGENT_ID` не задан и `GATE_ENABLED=1`, деплой будет остановлен.

4. Проверить обязательные outcome-поля по каждому кейсу:
- `booking_event_id`
- `booking_status`
- `automation_trace` (в БД metadata)

5. Критерии “готовности к рекламе”:
- Booking success (free-slot) ≥ 99%
- False-confirmation = 0
- Busy detection precision ≥ 99%
- p95 latency < 3s (без внешних API)
- 7 дней без критических инцидентов

## Примечание
Скрипт покрывает ядро transactional-сценариев:
- free_single
- busy_single
- busy_switch_room
- incomplete
- duplicate_after_created

Эскалация проверяется через состояние (`booking_status`, `manager_notified_busy`) и trace.
