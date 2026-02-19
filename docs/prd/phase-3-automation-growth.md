# Phase 3 PRD: Automation + Growth

## Goals
- Automate end‑to‑end publishing (analysis → evaluation → distribution).
- Maintain quality while scaling coverage and cadence.
- Build the funnel from free value to paid access.

## Scope
- Scheduled batch runs for analyses and evaluations.
- Publishing pipeline to Telegram.
- Content packaging (headline, narrative, key bullets).
- Access controls (free tier + paid access gating).

## Success Metrics
- Publish cadence reliability (>= target schedule adherence).
- Engagement rate in Telegram (CTR, read rate, saves).
- Conversion rate to paid tier (baseline to be defined).
- Quality guardrails not regressing.

## Deliverables
- Cron/job scheduler for daily rounds.
- Telegram publisher with retries and logging.
- Content templates for free vs paid.
- Monitoring dashboard for pipeline health.

## Task Breakdown (Agile)
1) P3-001 Define publishing cadence and coverage targets
2) P3-002 Build scheduler for batch runs
3) P3-003 Telegram publishing pipeline
4) P3-004 Free vs paid access gating
5) P3-005 Quality guardrails in publishing
6) P3-006 Content templating for distribution
7) P3-007 Monitoring dashboard for pipeline health
8) P3-008 Engagement tracking

Full task details live in: docs/prd/phase-3-automation-growth.json

## Risks
- Automation errors causing bad outputs or missed games.
- Over‑publishing without quality control.
- Growth focus before product trust is earned.

## Dependencies
- Stable Phase 1 + Phase 2 pipelines.
- Telegram API credentials + publishing policy.
- User access strategy (pricing + gating rules).

## Timeline
- Week 1: job scheduling + publishing prototype.
- Week 2: templating + gating rules.
- Week 3: reliability monitoring + alerting.
- Week 4: stabilize cadence and measure engagement.
