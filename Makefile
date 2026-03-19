PYTHON := python
LEAGUE ?= PL
LEAGUE_ID ?= 47

# All league code → ID mappings (exclude BR — different season calendar)
ALL_LEAGUES := PL:47 ES:87 IT:55 DE:54 FR:53 PT:61 NL:57

.PHONY: sync kg round board refresh backfill-players status track \
        sync-all kg-all backfill-all status-all odds odds-all daily daily-run

# ── Single league ──────────────────────────────────────────────

# Scrape latest match data
sync:
	$(PYTHON) scripts/sync_provider_playwright.py --league $(LEAGUE) --details --finished-only

# Rebuild team_states + player_states
kg:
	$(PYTHON) scripts/populate_kg_states.py --league-id $(LEAGUE_ID)

# Generate predictions + MI for a round + restart bot
round:
	$(PYTHON) scripts/generate_round.py $(ROUND) --league $(LEAGUE) --league-id $(LEAGUE_ID) --intelligence --publish

# Regenerate board from cached MI (no LLM calls)
board:
	$(PYTHON) scripts/generate_round.py $(ROUND) --league $(LEAGUE) --league-id $(LEAGUE_ID) --board-only

# Full pipeline: sync → KG → round + publish
refresh: sync kg round

# One-time: fill missing player performances
backfill-players:
	$(PYTHON) scripts/sync_provider_playwright.py --league $(LEAGUE) --extract-players-from-raw
	$(PYTHON) scripts/sync_provider_playwright.py --league $(LEAGUE) --backfill-players
	$(PYTHON) scripts/populate_kg_states.py --league-id $(LEAGUE_ID)

# Quick data health check
status:
	@$(PYTHON) -c "import psycopg2; c=psycopg2.connect('dbname=clarity_football'); cur=c.cursor(); \
	cur.execute(\"SELECT status, COUNT(*) FROM provider_matches WHERE league_id=$(LEAGUE_ID) GROUP BY status\"); \
	print('Matches:'); [print(f'  {r[0]}: {r[1]}') for r in cur.fetchall()]; \
	cur.execute(\"SELECT COUNT(DISTINCT fp.provider_match_id) FROM provider_player_performances fp JOIN provider_matches fm ON fm.provider_match_id=fp.provider_match_id WHERE fm.league_id=$(LEAGUE_ID)\"); \
	print(f'With player data: {cur.fetchone()[0]}'); \
	cur.execute(\"SELECT MAX(round_number) FROM player_states WHERE league_id=$(LEAGUE_ID)\"); \
	print(f'player_states max round: {cur.fetchone()[0]}'); c.close()"

# Track record
track:
	$(PYTHON) scripts/build_track_record.py --aggregate --league $(LEAGUE)

# ── Odds backfill ─────────────────────────────────────────────

odds:
	$(PYTHON) scripts/backfill_odds.py --league-id $(LEAGUE_ID)

odds-all:
	$(PYTHON) scripts/backfill_odds.py

# ── All leagues ────────────────────────────────────────────────

sync-all:
	@for pair in $(ALL_LEAGUES); do \
		code=$${pair%%:*}; id=$${pair##*:}; \
		echo "\n=== Syncing $$code (id=$$id) ==="; \
		$(PYTHON) scripts/sync_provider_playwright.py --league $$code --details --finished-only; \
	done

kg-all:
	@for pair in $(ALL_LEAGUES); do \
		code=$${pair%%:*}; id=$${pair##*:}; \
		echo "\n=== KG rebuild $$code (id=$$id) ==="; \
		$(PYTHON) scripts/populate_kg_states.py --league-id $$id; \
	done

backfill-all:
	@for pair in $(ALL_LEAGUES); do \
		code=$${pair%%:*}; id=$${pair##*:}; \
		echo "\n=== Backfill $$code (id=$$id) ==="; \
		$(PYTHON) scripts/sync_provider_playwright.py --league $$code --extract-players-from-raw; \
		$(PYTHON) scripts/sync_provider_playwright.py --league $$code --backfill-players; \
		$(PYTHON) scripts/populate_kg_states.py --league-id $$id; \
	done

# Daily ops: check today's MI coverage (dry-run)
daily:
	$(PYTHON) scripts/daily_pipeline.py

# Daily ops: generate missing MI for today
daily-run:
	$(PYTHON) scripts/daily_pipeline.py --run

refresh-all: sync-all kg-all

status-all:
	@for pair in $(ALL_LEAGUES); do \
		code=$${pair%%:*}; id=$${pair##*:}; \
		echo "\n=== $$code (id=$$id) ==="; \
		$(PYTHON) -c "import psycopg2; c=psycopg2.connect('dbname=clarity_football'); cur=c.cursor(); \
		cur.execute(\"SELECT status, COUNT(*) FROM provider_matches WHERE league_id=$$id GROUP BY status\"); \
		print('Matches:'); [print(f'  {r[0]}: {r[1]}') for r in cur.fetchall()]; \
		cur.execute(\"SELECT COUNT(DISTINCT fp.provider_match_id) FROM provider_player_performances fp JOIN provider_matches fm ON fm.provider_match_id=fp.provider_match_id WHERE fm.league_id=$$id\"); \
		print(f'With player data: {cur.fetchone()[0]}'); \
		cur.execute(\"SELECT MAX(round_number) FROM player_states WHERE league_id=$$id\"); \
		print(f'player_states max round: {cur.fetchone()[0]}'); c.close()"; \
	done
