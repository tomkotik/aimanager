# Reliability Automation

Этот контур автоматизирует ежедневный KPI snapshot и weekly reliability review baseline.

## Компоненты
- `scripts/reliability_report.py` — считает KPI по окну времени.
- `scripts/reliability_cycle.py` — пишет daily/weekly JSON+MD отчёты.
- `scripts/install_reliability_cron.sh` — ставит cron jobs.

## Быстрый запуск

```bash
AGENT_ID=<agent_uuid> ./scripts/install_reliability_cron.sh
```

По умолчанию jobs:
- Daily: каждый день в 09:05 UTC
- Weekly: понедельник в 09:15 UTC

Отчёты складываются в контейнере в:
- `/app/tenants/_ops_reports/daily`
- `/app/tenants/_ops_reports/weekly`

Cron-лог на хосте:
- `ops/reports/cron.log`

## Ручной запуск

```bash
# inside app container
python3 /app/scripts/reliability_cycle.py --mode daily --agent-id <agent_uuid> --out-dir /app/tenants/_ops_reports
python3 /app/scripts/reliability_cycle.py --mode weekly --agent-id <agent_uuid> --out-dir /app/tenants/_ops_reports
```
