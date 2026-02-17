# Canary + Rollback Runbook (AgentBox)

## Goal
Roll out safely without breaking production behavior.

## Canary flow
1. Deploy backend candidate only:
   - `db/redis/app`
2. Run migrations.
3. Run release gate (critical regression matrix).
4. If gate passes, continue with `worker/beat/web/nginx`.
5. Monitor 15-30 minutes:
   - error logs
   - booking outcomes
   - p95 latency

## Command
```bash
GATE_AGENT_ID=<agent_uuid> ./scripts/deploy.sh <domain>
```

## Abort criteria
Abort rollout if any of:
- release gate fails
- false-confirmation detected
- repeated 5xx / worker crashes
- booking outcome mismatch (`reply` vs backend fact)

## Rollback (manual)
1. Checkout previous stable commit/tag:
```bash
git checkout <stable_commit_or_tag>
```
2. Re-run deploy with same gate:
```bash
GATE_AGENT_ID=<agent_uuid> ./scripts/deploy.sh <domain>
```
3. Verify health + run smoke regression.

## Evidence required after rollback
- reason for rollback
- failing case IDs
- fixed-by commit or postmortem link
