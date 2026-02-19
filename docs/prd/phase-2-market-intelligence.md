# Phase 2 PRD: Market Intelligence (Backtested Betting Layer)

## Goals
- Add a transparent market layer that explains odds and edge without tipster vibes.
- Prove betting value through backtests and ongoing evaluation.
- Establish a strict bet/no‑bet gating system.

## Scope
- Odds ingestion + implied probabilities.
- Internal probability model + edge calculation.
- Bet/no‑bet decision logic with confidence bands.
- Market validation dashboard views.

## Success Metrics
- Positive ROI proxy over backtest window.
- No‑bet gate success rate (losses avoided).
- Tip accuracy improvement vs baseline (controlled sample).
- User trust: no “locks” language, clear uncertainty.

## Deliverables
- Market data pipeline (opening/closing odds + movement).
- Market intelligence module (edge + alignment + bet/no‑bet).
- Backtest evaluation job.
- Dashboard: edge vs outcome, confidence buckets, no‑bet success.

## Task Breakdown (Agile)
1) P2-001 Define market schema and required fields
2) P2-002 Odds ingestion + history snapshots
3) P2-003 Implied probability calculator
4) P2-004 Internal probability model
5) P2-005 Edge + alignment computation
6) P2-006 Bet/no-bet gate
7) P2-007 Backtest evaluation job
8) P2-008 Market validation dashboard
9) P2-009 Baseline market benchmarks
10) P2-010 Time-travel safety checks for market data

Full task details live in: docs/prd/phase-2-market-intelligence.json

## Risks
- Limited odds history reduces signal quality.
- Edge calculation noise with small samples.
- Regulatory/positioning risk if messaging feels like tipster content.

## Dependencies
- Stable match intelligence pipeline (Phase 1).
- Odds snapshots + provider reliability.
- Schema extensions for market analysis and outcomes.

## Timeline
- Week 1: odds ingestion + implied prob pipeline.
- Week 2: edge model + bet/no‑bet gate.
- Week 3: backtest job + evaluation metrics.
- Week 4: dashboard market validation + iteration.
