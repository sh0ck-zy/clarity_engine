# Clarity Engine — Architecture

*Last updated: 2026-02-28*

## System Overview

```
DATA (facts) → ML (probabilities) → REASONING (narrative) → OUTPUT (telegram/html)
```

Clarity Engine is a football prediction and match intelligence system.
It ingests match data, computes probabilistic predictions, generates
expert narrative analysis, and delivers through Telegram and HTML.

---

## 1. Data Layer

### Database: PostgreSQL (`clarity_football`)

#### `team_states` — Team snapshots per round (520 rows, 20 teams × 26 rounds)

**Used by ML model:**
| Field | Description |
|-------|-------------|
| `position` | League position |
| `goal_difference` | Season GD |
| `form_points` | Last 5 games (0-15) |
| `xg_diff_last5` | xG for - xG against (last 5) |
| `home_points` / `away_points` | Venue-split points |
| `clean_sheets_last5` | Clean sheets in last 5 |

**Used by Context (not ML):**
| Field | Description |
|-------|-------------|
| `points`, `played`, `wins`, `draws`, `losses` | Season record |
| `form_string` | e.g. "LWWDW" |
| `form_trend` | "improving" / "stable" / "declining" |
| `position_change_last5` | Movement in last 5 rounds |
| `goals_scored_last5`, `goals_conceded_last5` | Recent goal record |
| `xg_for_last5`, `xg_against_last5` | Raw xG last 5 |
| `avg_possession` | Season average possession % |
| `primary_formation` | Most used formation |
| `shots_per_game`, `shots_on_target_per_game` | Attacking volume |
| `xg_per_game`, `big_chances_per_game` | Attacking quality |
| `shots_against_per_game`, `xg_against_per_game` | Defensive quality |
| `home_wins/draws/losses`, `away_wins/draws/losses` | Venue split W-D-L |

#### `fotmob_player_performances` — Per-player per-match (10,393 rows)

| Field | Description |
|-------|-------------|
| `player_name`, `team_name` | Identity |
| `is_home`, `is_starter`, `position_id` | Role |
| `rating` | FotMob match rating |
| `minutes_played` | Minutes |
| `goals`, `assists` | Output |
| `xg`, `xgot`, `xa` | Expected metrics |
| `shots`, `shots_on_target` | Shot volume |
| `passes`, `passes_accurate`, `chances_created` | Creativity |
| `tackles`, `interceptions`, `defensive_actions` | Defense |

#### `fotmob_matches` — Match data (380 rows, 260 finished)

| Field | Description |
|-------|-------------|
| `formation_home`, `formation_away` | Tactical setup |
| `venue`, `attendance`, `referee` | Match context |
| `home_avg_rating`, `away_avg_rating` | Team performance |
| `stats` (JSONB) | Possession, shots, passes, xG per half |
| `shotmap` (JSONB) | Per-shot xG and position |
| `events` (JSONB) | Goals, cards, substitutions |
| `momentum` (JSONB) | Momentum timeline |

#### `manager_history` — Manager stints (31 rows)

| Field | Description |
|-------|-------------|
| `manager_name` | Name |
| `first_match_round`, `last_match_round` | Tenure |
| `matches`, `wins`, `draws`, `losses` | Record |
| `is_current` | Active flag |

#### External: ELO ratings (ClubELO cache)

Per-team ELO ratings fetched by date. Used for `elo_delta` feature.

---

## 2. Feature Layer

### ML Features (8, used in LogisticRegression v1.4)

| Feature | Formula |
|---------|---------|
| `xg_diff_last5_delta` | home_xg_diff - away_xg_diff |
| `form_points_delta` | home_form - away_form |
| `goal_diff_season_delta` | home_gd - away_gd |
| `position_delta` | away_position - home_position |
| `home_strength_delta` | home_venue_pts - away_venue_pts |
| `elo_delta` | home_elo - away_elo |
| `home_venue_points` | Home team's home points |
| `away_venue_points` | Away team's away points |

### Context Features (for narrative, not ML)

Everything from team_states + player aggregates + manager + recent results.
See `context.json` structure in `src/intelligence/match_context.py`.

### Overlap

ML uses 8 deltas computed from `team_states`. Context uses the FULL
`team_states` record plus `player_performances`, `manager_history`, and
`fotmob_matches` for recent results and H2H.

---

## 3. Processing Layers

```
┌──────────────────────────────────────────────────────────────────┐
│ DATA                                                             │
│ team_states + player_performances + manager_history + matches    │
│ → facts.json (raw stats)                                        │
│ → context.json (structured: factual / ml_inference / angles)     │
├──────────────────────────────────────────────────────────────────┤
│ ML                                                               │
│ LogisticRegression(C=0.01, balanced, 8 features)                │
│ Walk-forward: train on R2..N-1, predict RN                      │
│ → report.json (probabilities, drivers, confidence, risk_flags)   │
├──────────────────────────────────────────────────────────────────┤
│ REASONING                                                        │
│ LLM narrator (gpt-4o-mini) + 4 pillar sections                 │
│ 📝 a_historia (journalist) — narrative arc, stakes              │
│ ⚽ onde_se_decide (pundit) — tactical matchup, key battles      │
│ 🔬 o_que_pode_correr_mal (analyst) — risks, contrarian data     │
│ 💡 bottom_line (synthesis) — one-sentence read                  │
│ → narrative.json                                                 │
├──────────────────────────────────────────────────────────────────┤
│ OUTPUT                                                           │
│ render_html.py → HTML review page (4 sections per match card)   │
│ match_renderer.py → Telegram / X drafts                         │
│ clarity-odds-core bot → subscriber delivery                     │
└──────────────────────────────────────────────────────────────────┘
```

### Output per match (in `output/rounds/PL_R28/matches/Arsenal_vs_Chelsea/`):

| File | Layer | Content |
|------|-------|---------|
| `facts.json` | DATA | Raw team stats, computed features, market odds |
| `context.json` | DATA | Full structured context (factual + ml_inference + narrative_angles) |
| `report.json` | ML | Probabilities, drivers, confidence, risk flags |
| `narrative.json` | REASONING | 4 pillar sections from LLM |
| `quality_checks.json` | EVAL | MIS score per section |
| `review.json` | WORKFLOW | Editorial status (pending/approved/published) |
| `drafts/telegram.txt` | OUTPUT | Formatted Telegram message |
| `drafts/x.txt` | OUTPUT | Formatted X/Twitter post |

---

## 4. Evaluation

### ML Evaluation

| Metric | v1.4 Value | Benchmark |
|--------|-----------|-----------|
| Log loss | 1.0629 | Uniform: 1.0986 |
| Accuracy | 40.6% | Random: 33% |
| Draw recall | 27.3% | v1.1: 1.9% |
| vs Market | +5.1% worse | Bet365: 1.0118 |

Walk-forward evaluation: train R2..N-1, predict RN, for N in [8..28].

### Narrative Evaluation (MIS — Match Intelligence Score)

Per-section scoring, weighted:

| Section | Pillar | Weight | Checks |
|---------|--------|--------|--------|
| `a_historia` | Journalist | 25% | storytelling_flow, emotional_hook, specific_context |
| `onde_se_decide` | Pundit | 30% | tactical_insight, formation_mentioned, key_battle_identified |
| `o_que_pode_correr_mal` | Analyst | 25% | min_3_risks, data_backed, contrarian_view |
| `bottom_line` | Synthesis | 20% | concise, actionable, not_fence_sitting |

### Post-Match Validation

After matches are played:
1. Extract verifiable claims from narrative sections
2. Compare to actual match data
3. Score accuracy per section
4. Track over time for learning

---

## 5. Key Scripts

| Script | Purpose |
|--------|---------|
| `scripts/generate_round.py` | Generate full round: predictions + context + narratives |
| `scripts/render_html.py` | HTML review page with 4-pillar match cards |
| `scripts/quality_check.py` | MIS scoring per section |
| `scripts/validate_postmatch.py` | Post-match claim validation |
| `scripts/publish_preview.py` | Preview + export for Telegram |
| `scripts/populate_kg_states.py` | Compute team_states from raw match data |
| `scripts/backfill_fotmob.py` | Ingest match data from FotMob |

---

## 6. Product Strategy

```
Phase 1 (NOW):    Free elite ball knowledge → build audience
Phase 2 (LATER):  Paid full match intelligence after traction
Phase 3 (FUTURE): Proven edge strategies → high-ticket, transparent
```

Three visible intelligence pillars:
- 📝 **Journalist** — storytelling, emotional context
- ⚽ **Pundit** — tactical analysis, matchup insight
- 🔬 **Analyst** — data-driven, contrarian risks

Internal (not visible to users):
- 🕵️ **Market Intelligence** — odds comparison, value detection, EV analysis
