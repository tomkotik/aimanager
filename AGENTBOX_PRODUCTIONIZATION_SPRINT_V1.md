# AgentBox Productionization Sprint (v1)

## Цель
Сделать AgentBox платформой, где каждый новый агент запускается по стандарту надежности, а не вручную «на удаче».

Ключевой принцип: **ничего не сломать в текущем рабочем поведении**.

---

## 1) Reliability Core (критично)
- [x] Единый state-contract для всех transactional сценариев.
- [x] Жёсткий deterministic post-processor (truth from backend only).
- [x] Idempotency + dedupe + anti-reorder как стандартный middleware.

## 2) Eval & QA Core
- [x] Авто-регрессия (free/busy/switch/duplicate/incomplete/escalation).
- [x] Проверка outcome-полей: `booking_event_id`, `booking_status`, `automation_trace`.
- [x] Запрет релиза при падении хотя бы 1 критического кейса.

## 3) Platform / Builder Core
- [x] Шаблон «агент под бронирование» в 1 клик.
- [x] UI-конфиг → валидатор → генерация runtime-конфига без ручного кода. *(включая UI wiring через /config/validate-runtime)*
- [x] Версионирование схемы + миграции. *(config_schema.py + /api/v1/agents/config/schema|migrate)*

## 4) Ops Core
- [x] Канареечный релиз + rollback (runbook + staged deploy).
- [ ] SLO-дашборд (availability, success-rate booking, p95 latency, incident count). *(API-слой реализован: `/api/v1/analytics/reliability`)*
- [x] Postmortem-шаблон и weekly reliability review.

---

## KPI «готовности к рекламе»
- Booking success (free-slot) ≥ 99%
- False-confirmation = 0
- Busy detection precision ≥ 99%
- p95 latency < 3s (без внешних API задержек)
- 7 дней без критических инцидентов

---

## Внешние ориентиры
- Anthropic: простые composable workflows > «магические» сложные агенты.
- Stripe: обязательная идемпотентность для надёжных повторов.
- Rasa Forms: строгое slot-filling поведение для многокроковых диалогов.
- AWS Reliability + Google SRE: SLO/error budget/postmortem как обязательная эксплуатационная рамка.

---

## Примечание к исполнению
Этот sprint-план должен реализовываться инкрементально с обязательным regression-gate перед каждым rollout.

## Артефакты выполнения (v1)
- `scripts/regression_matrix.py` — автопрогон критичных transactional-сценариев.
- `scripts/release_gate.sh` — gate-обёртка: release block при падении критичных кейсов.
- `RELEASE_GATE.md` — правила блокировки релиза при падении критики.
- `src/core/state_contract.py` — нормализация/валидация transactional flow-state.
- `tenants/_booking_template/*` + `agentbox init-booking` — 1-click booking template.
- `src/core/runtime_config.py` + `scripts/build_runtime_config.py` — versioned runtime config builder.
- `src/core/config_schema.py` + `/api/v1/agents/config/schema|migrate|validate-runtime` — versioned config schema + migration/validation API.
- `web/src/app/agents/[id]/page.tsx` — UI wiring: validate-runtime before save.
- `ops/CANARY_ROLLBACK_RUNBOOK.md` — canary/rollback runbook.
- `ops/POSTMORTEM_TEMPLATE.md` — шаблон постмортема.
- `ops/WEEKLY_RELIABILITY_REVIEW_TEMPLATE.md` — weekly reliability review.
- `scripts/reliability_report.py` — KPI snapshot (success/false-confirm/p95/busy precision).
- `scripts/reliability_cycle.py` + `scripts/install_reliability_cron.sh` — daily/weekly automation contour.
  - установлен cron в production на `f5daae28-ff35-455e-a6a3-db655ba4ef6a` (daily + weekly jobs).
- `ops/RELIABILITY_AUTOMATION.md` — инструкция по автоконтру reliability.
- `GET /api/v1/analytics/reliability` — SLO/KPI API для дашборда.
