# Current Status and Errors

**Date:** 2026-02-02

## Issue Summary

We're trying to run prediction performance comparison between old context (V2) and new context (V3 with agent enrichment), but encountering two main issues:

---

## Issue 1: Gemini API Quota Exhausted

### Error Message
```
429 RESOURCE_EXHAUSTED
You exceeded your current quota, please check your plan and billing details.

Quota violations:
- generativelanguage.googleapis.com/generate_content_free_tier_requests: limit 0
- generativelanguage.googleapis.com/generate_content_free_tier_input_token_count: limit 0
```

### What We Tested
- **GEMINI_API_KEY** (`AIzaSyAa6Xr8...`): ❌ Exhausted
- **GOOGLE_API_KEY** (`AIzaSyCCU1Pd...`): ❌ Exhausted
- **Model tested**: `gemini-2.0-flash`, `gemini-2.5-flash`

###Root Cause
Both API keys show `limit: 0` for free tier, meaning the quota has been completely used up.

### What the User Says
> "we have something wrong in the codebase because we have quota"

This suggests either:
1. The quota was recently added but hasn't propagated yet
2. There's a different API key that should be used
3. There's a paid tier that needs different configuration
4. The keys need to be refreshed/regenerated

---

## Issue 2: Database Missing Round 23/24 Scores

### Current Database State
```sql
SELECT id, round, home_team, away_team, home_score, away_score, status
FROM fixtures
WHERE round IN (23, 24)
LIMIT 5
```

**Result:**
| round | home_team | away_team | home_score | away_score | status |
|-------|-----------|-----------|------------|------------|--------|
| 23 | Bournemouth | Liverpool | None | None | SCHEDULED |
| 23 | Burnley | Tottenham | None | None | SCHEDULED |
| 23 | Fulham | Brighton | None | None | SCHEDULED |
| 23 | Manchester City | Wolves | None | None | SCHEDULED |
| 23 | West Ham | Sunderland | None | None | SCHEDULED |

### What the User Says
> "rounds 23 and 24 are done if you update data sources"

This means the fixtures have been played but our database hasn't been updated yet.

### Update Attempt
```bash
python scripts/update_from_sources.py --only scraper
```

**Result:**
```
🚛 Starting Selenium Ingestion for 2025-2026...
   🕵️  Launching Headless Chrome...
   📄 Parsing HTML tables...
❌ Error parsing HTML: No tables found
```

### Root Cause
The FBRef scraper couldn't find the fixture tables. Possible reasons:
1. Page structure changed on FBRef
2. Selenium timing issue (page didn't fully load)
3. Cloudflare/anti-bot protection
4. URL or season parameter incorrect

---

## What We've Built (Working)

### ✅ Complete Infrastructure
1. **Anti-hallucination agent architecture** (Claude/Gemini/OpenAI fallback)
2. **EnrichedContextBuilder** (V3) with validation
3. **Performance comparison script** ([scripts/compare_prediction_performance.py](../scripts/compare_prediction_performance.py))

### ✅ Schema Fixes Applied
- Fixed `LeaguePosition.home` → `LeaguePosition.home_position`
- Fixed `ScheduleContext.home_rest_hours` → `ScheduleContext.home_rest_days`

### ✅ Test Results (Before Quota Exhaustion)
From earlier successful test:
- **Base context**: 0 injuries for Leeds, 5 for Arsenal
- **Enriched context**: 4 injuries for Leeds (+4), 7 for Arsenal (+2)
- **Enrichment quality**: 60% (validation passed)
- **H2H enrichment**: 1 match (DB) → 5 matches (agent)

---

## What Needs to Happen

### Option A: Fix Gemini Quota
1. Check Google Cloud Console for actual quota limits
2. Verify billing is enabled if using paid tier
3. Try regenerating API keys
4. Wait for daily quota reset (if on free tier)

### Option B: Use Alternative for Testing
1. Use Claude API (we have ANTHROPIC_API_KEY capability)
2. Install anthropic package: `pip install anthropic`
3. Update comparison script to use Claude instead of Gemini

### Option C: Fix Data Update
1. Debug the FBRef scraper:
   - Check if URL is correct
   - Increase Selenium wait time
   - Add debugging to see what HTML is being returned
2. Manual data entry for Round 23/24 (last resort)
3. Use alternative data source (API Football, etc.)

---

## Recommendation

**Immediate next steps:**
1. **Verify Gemini quota** in Google Cloud Console
2. **Try Claude API** as alternative for predictions (we have the integration ready)
3. **Debug scraper** to understand why tables aren't being found

**For the comparison test:**
- If we can't get Rounds 23/24 data quickly, use **Rounds 19-21** (30 finished fixtures)
- These rounds have complete data and will give us a valid comparison

---

## Files Ready to Run

Once quota/data issues are resolved:

```bash
# Update data
python scripts/update_from_sources.py --only scraper

# Run comparison
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
python scripts/compare_prediction_performance.py
```

Expected output:
- 60 predictions (30 old + 30 new)
- Accuracy comparison metrics
- Winner determination
- JSON report saved to `docs/prediction_performance_comparison.json`
