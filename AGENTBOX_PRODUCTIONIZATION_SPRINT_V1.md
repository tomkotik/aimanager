# AgentBox Productionization Sprint (v1)

## Цель
Сделать AgentBox платформой, где каждый новый агент запускается по стандарту надежности, а не вручную «на удаче».

Ключевой принцип: **ничего не сломать в текущем рабочем поведении**.

---

## 1) Reliability Core (критично)
- [ ] Единый state-contract для всех transactional сценариев.
- [x] Жёсткий deterministic post-processor (truth from backend only).
- [x] Idempotency + dedupe + anti-reorder как стандартный middleware.

## 2) Eval & QA Core
- [x] Авто-регрессия (free/busy/switch/duplicate/incomplete/escalation).
- [x] Проверка outcome-полей: `booking_event_id`, `booking_status`, `automation_trace`.
- [ ] Запрет релиза при падении хотя бы 1 критического кейса.

## 3) Platform / Builder Core
- [ ] Шаблон «агент под бронирование» в 1 клик.
- [ ] UI-конфиг → валидатор → генерация runtime-конфига без ручного кода.
- [ ] Версионирование схемы + миграции.

## 4) Ops Core
- [ ] Канареечный релиз + rollback.
- [ ] SLO-дашборд (availability, success-rate booking, p95 latency, incident count).
- [ ] Postmortem-шаблон и weekly reliability review.

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
- `RELEASE_GATE.md` — правила блокировки релиза при падении критики.
