# Workspace Projects Analysis

**Date:** 2026-02-15  
**Scope:** clarity_engine, bethub, clarity-odds-core, clarity-notebook-v1, clarity-odds-ml (and external project_bh / side projects)

---

## 1. Where Is the Finished Webapp (with logos)?

**Single location:** **`bethub/archive/webapp-paused/`**

- **Path:** `/Users/joao/Projects/bethub/archive/webapp-paused/`
- **Status:** Paused and archived. There is **no active `src/` at bethub root** — all app code lives under `archive/webapp-paused/`.

**What’s in that webapp:**

| Feature | Status |
|--------|--------|
| **Tech** | Next.js 15, App Router, TypeScript, Tailwind, Radix/shadcn, Supabase Auth |
| **Match UI** | `MatchCard`, `LeagueSection`, `MatchRow`, `AnalysisTabs` (AI / Stats / Odds) |
| **Logos** | ✅ **Fully wired** |
| **Logo sources** | `TeamLogo.tsx` (hardcoded map: logos-world.net, UEFA, freebiesupply), `LeagueLogo`, API `crest`/`emblem` via `simple-api.ts`, `comprehensiveLogoService.ts` (TheSportsDB for competitions), fallbacks in `api/v1/today/route.ts` (placehold.co) |
| **Image domains** | next.config: `logos-world.net`, `placehold.co`, `images.unsplash.com`, `logos.fandom.com` |
| **Dark theme** | Professional sportsbook-style UI |

So the “finished” (built) webapp UI with logos is **only** in **`bethub/archive/webapp-paused/`**. To run it: `cd archive/webapp-paused && pnpm dev` (see bethub README/CLAUDE.md).

---

## 2. Project-by-Project: Good vs Trash

### ✅ Good – Keep and Use

**clarity_engine**  
- **Role:** Match context builder + LLM analysis (pre-match intelligence).  
- **Highlights:** `RobustBuilder`, form interpreter, FotMob + API-Football strategy documented, clear schema (fixtures, team_stats, odds_snapshots, player_injuries).  
- **Docs:** `ESTADO_ACTUAL.md`, `AUDIT_DADOS.md`, `docs/DATA_SOURCES_ANALYSIS.md`.  
- **Verdict:** Core analysis engine. Data issues are **documented** (team_stats gaps, fixture dupes, name inconsistency); fix with backfill + dedupe, don’t discard.

**clarity-odds-core**  
- **Role:** Odds/betting pipeline: API-Football fetchers, DB, Telegram bot, FastAPI, analysis engine.  
- **Highlights:** Fetchers (fixtures, predictions, odds, standings, injuries, statistics, lineups), migrations, `DATA_INVENTORY.md`, clear layering (fetchers → engine → bot/formatters).  
- **Verdict:** Production-grade data and delivery. The many deleted markdown files in git are old status docs — cleanup, not “trash” code.

**bethub (archive/webapp-paused)**  
- **Role:** The only full webapp UI (match cards, logos, analysis tabs, auth).  
- **Verdict:** **Good asset.** Paused ≠ bad. When you resume the webapp, this is the codebase to use.

---

### ⚠️ Weak / Trash – Low Value or Unclear

**clarity-notebook-v1**  
- **Contents:** Essentially a single Jupyter notebook + venv (soccerdata, selenium, etc.).  
- **Verdict:** Exploratory one-off. **Trash** unless you still use that notebook; otherwise safe to archive or delete.

**clarity-odds-ml**  
- **Contents:** Repo appears to be mostly `.venv` (e.g. SQLAlchemy). ML was moved out of clarity-odds-core into this repo, but there’s no clear project layout (no obvious `ml/`, `scripts/`, or README at top level).  
- **Verdict:** **Unclear.** Either ML code was never fully migrated here or it’s in a structure not visible from a quick scan. Treat as **weak** until you confirm what’s supposed to live here; if it’s only a venv, consider it trash or a stub.

**project_bh / side projects (external drive)**  
- **Verdict:** Likely copies or side work. Only relevant if you’re actively using them; otherwise treat as backup/archive.

---

## 3. Data Depth and Cleanliness

### clarity_engine

| Aspect | Assessment |
|--------|------------|
| **Depth** | Good: fixtures, team_stats (xG, xGA, PPDA, tilt, Elo), odds_snapshots, player_injuries. FotMob vs API-Football roles defined (FotMob primary for match intelligence). |
| **Cleanliness** | **Known issues** (see `AUDIT_DADOS.md`): (1) `team_stats` missing for R22–R24 → wrong form; (2) fixture duplicates (e.g. “Leeds United” vs “Leeds”); (3) team name inconsistency across tables. |
| **Action** | Backfill team_stats for R22–R24; dedupe fixtures (e.g. keep rows with `round`); introduce `team_aliases` or canonical names. |

### clarity-odds-core

| Aspect | Assessment |
|--------|------------|
| **Depth** | **Strong:** fixtures_raw, predictions_raw, odds_raw, standings_raw, injuries_raw, statistics_raw, lineups_raw, etc. Full API responses stored in JSONB. |
| **Cleanliness** | **Good:** Migrations, single source of truth (DATA_INVENTORY), repositories, no duplicate “competing” pipelines. |
| **Action** | Keep current design; ensure daily_update and fetchers stay in sync with docs. |

### bethub (webapp)

| Aspect | Assessment |
|--------|------------|
| **Depth** | UI expects: match + league + team logos, analysis payload (from ingest), odds. Backend data comes from clarity-odds-core (or Supabase when used). |
| **Cleanliness** | Types and API shapes are defined; when resumed, wire to core’s webapp API (e.g. `/api/webapp/matches/by-date`, match detailed). |

---

## 4. Summary Table

| Project | Verdict | Notes |
|---------|---------|--------|
| **clarity_engine** | ✅ Good | Analysis engine; fix data (backfill, dedupe, names). |
| **clarity-odds-core** | ✅ Good | Odds/bot/data backbone; clean architecture. |
| **bethub** (webapp in archive) | ✅ Good | **Only** finished webapp UI with logos; use when resuming. |
| **clarity-notebook-v1** | ⚠️ Trash | One notebook + venv; archive or delete if unused. |
| **clarity-odds-ml** | ⚠️ Weak | Mostly venv; confirm if any ML code lives here. |
| **project_bh / side projects** | ⚠️ Archive | External; treat as backup unless in use. |

---

## 5. Quick Reference: Webapp with Logos

- **Path:** `bethub/archive/webapp-paused/`
- **Run:** `cd /Users/joao/Projects/bethub/archive/webapp-paused && pnpm dev`
- **Logo usage:** `TeamLogo`, `LeagueLogo`; API fields `home_team_logo`, `away_team_logo`, `league_logo`; fallbacks in `today/route.ts` and `TeamLogo.tsx` map.
