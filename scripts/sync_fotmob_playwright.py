#!/usr/bin/env python3
"""
Sync FotMob data using Playwright (browser-based).

This is the ONLY reliable method - avoids rate limiting and blocks.
Fetches COMPLETE data: list + details + stats + shotmap + lineups.

Usage:
    python scripts/sync_fotmob_playwright.py --league ES --season "2025/2026"
    python scripts/sync_fotmob_playwright.py --league ES --details  # Also fetch match details
    python scripts/sync_fotmob_playwright.py --all --details        # All leagues, full data
"""

import argparse
import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.sync_api import sync_playwright

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sync_fotmob")

BASE_URL = "https://www.fotmob.com"

# League mapping
LEAGUES = {
    'PT': 61,    # Liga Portugal
    'PL': 47,    # Premier League
    'ES': 87,    # La Liga
    'IT': 55,    # Serie A
    'DE': 54,    # Bundesliga
    'FR': 53,    # Ligue 1
    'NL': 57,    # Eredivisie
    'UCL': 42,   # Champions League
    'BR': 268,   # Brasileirão
}


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        host='localhost',
        database='clarity_football',
        user='joao'
    )


def fetch_league_matches(page, league_id: int) -> list[dict]:
    """Fetch all matches for a league using Playwright."""
    url = f"{BASE_URL}/leagues/{league_id}/matches"
    
    logger.info(f"Fetching league {league_id} from {url}")
    
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=30000)
        time.sleep(2)  # Wait for JS to load
        html = page.content()
    except Exception as e:
        logger.error(f"Failed to load {url}: {e}")
        return []
    
    # Extract __NEXT_DATA__
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not match:
        logger.warning(f"No __NEXT_DATA__ for league {league_id}")
        return []
    
    try:
        data = json.loads(match.group(1))
        page_props = (data.get('props') or {}).get('pageProps') or {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for league {league_id}: {e}")
        return []
    
    # Find matches in the data structure
    matches = []
    
    # Try different paths
    fallback = page_props.get('fallback') or {}
    for key in fallback:
        if 'matches' in key.lower() or 'fixtures' in key.lower():
            content = fallback[key]
            if isinstance(content, dict):
                all_matches = content.get('allMatches', [])
                if all_matches:
                    matches = all_matches
                    break
    
    # Alternative path
    if not matches:
        fixtures = page_props.get('fixtures') or {}
        matches = fixtures.get('allMatches') or []
    
    logger.info(f"Found {len(matches)} matches for league {league_id}")
    return matches


def fetch_match_details(page, match_id: int) -> dict | None:
    """Fetch complete match details from FotMob."""
    url = f"{BASE_URL}/match/{match_id}"
    
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(1)
        html = page.content()
    except Exception as e:
        logger.error(f"Failed to load {url}: {e}")
        return None
    
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not match:
        logger.warning(f"No __NEXT_DATA__ for match {match_id}")
        return None
    
    try:
        data = json.loads(match.group(1))
        return (data.get('props') or {}).get('pageProps') or {}
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse error for match {match_id}: {e}")
        return None


def parse_basic_match(m: dict, league_id: int, season: str) -> dict | None:
    """Parse basic match info from league listing."""
    if not m or not m.get('id'):
        return None
    
    try:
        status_info = m.get('status') or {}
        home = m.get('home') or {}
        away = m.get('away') or {}
        
        # Parse date and full kickoff timestamp
        utc_time = status_info.get('utcTime', '')
        match_date = None
        kickoff_time = None
        if utc_time:
            try:
                kickoff_dt = datetime.fromisoformat(utc_time.replace('Z', '+00:00'))
                match_date = kickoff_dt.date()
                kickoff_time = kickoff_dt
            except Exception:
                pass
        
        # Parse round
        round_val = m.get('round', m.get('roundName', 0))
        if isinstance(round_val, str):
            nums = re.findall(r'\d+', round_val)
            round_val = int(nums[0]) if nums else None
        
        # Parse status — normalize to canonical values
        status_short = (status_info.get('reason') or {}).get('short', '')
        if status_short:
            normalized = status_short.lower()
            # FT, AET are both finished games
            status = 'finished' if normalized in ('ft', 'aet') else normalized
        elif status_info.get('finished'):
            status = 'finished'
        elif status_info.get('started'):
            status = 'live'
        else:
            status = 'scheduled'
        
        return {
            'fotmob_match_id': m.get('id'),
            'league_id': league_id,
            'season': season,
            'match_date': match_date,
            'kickoff_time': kickoff_time,
            'round_number': round_val,
            'home_team_id': home.get('id'),
            'home_team_name': home.get('name', 'Unknown'),
            'away_team_id': away.get('id'),
            'away_team_name': away.get('name', 'Unknown'),
            'home_score': home.get('score'),
            'away_score': away.get('score'),
            'status': status,
            'raw_json': json.dumps(m),  # Store the raw match data
        }
    except Exception as e:
        logger.warning(f"Error parsing match: {e}")
        return None


def _flatten_player_stats(stats_groups: list) -> dict:
    """Flatten FotMob player stat groups into a simple dict.

    Stats come as: [{"key": "top_stats", "stats": {"Goals": {"key": "goals", "stat": {"value": 1}}, ...}}, ...]
    Returns: {"goals": 1, "assists": 0, "minutes_played": 90, ...}
    """
    flat = {}
    for group in stats_groups:
        if not isinstance(group, dict):
            continue
        group_stats = group.get('stats') or {}
        if not isinstance(group_stats, dict):
            continue
        for _label, entry in group_stats.items():
            if not isinstance(entry, dict):
                continue
            key = entry.get('key')
            if not key:
                continue
            stat = entry.get('stat') or {}
            flat[key] = stat.get('value')
            # For fraction stats (e.g. accurate_passes), also store total
            if stat.get('total') is not None:
                flat[f'{key}_total'] = stat['total']
    return flat


def extract_player_performances(conn, match_id: int, raw_data: dict) -> int:
    """Extract player performances from raw match data and upsert into DB.

    Returns number of players inserted.
    """
    content = raw_data.get('content') or {}
    lineup = content.get('lineup') or {}
    player_stats = content.get('playerStats') or {}

    if not lineup:
        return 0

    players = []
    for side, is_home in [('homeTeam', True), ('awayTeam', False)]:
        team_data = lineup.get(side) or {}
        if not team_data:
            continue
        team_id = team_data.get('id')
        team_name = team_data.get('name', '')
        starters = team_data.get('starters') or []
        subs = team_data.get('subs') or []

        for is_starter, player_list in [(True, starters), (False, subs)]:
            for player in player_list:
                pid = player.get('id')
                if not pid:
                    continue

                # Get detailed stats from playerStats section
                detailed = player_stats.get(str(pid)) or {}
                stats = _flatten_player_stats(detailed.get('stats') or [])
                performance = player.get('performance') or {}

                # Map FotMob keys to DB columns
                rating = performance.get('rating') or stats.get('rating_title')
                minutes = stats.get('minutes_played')

                players.append({
                    'fotmob_match_id': match_id,
                    'player_id': pid,
                    'player_name': player.get('name', detailed.get('name', 'Unknown')),
                    'team_id': team_id,
                    'team_name': team_name,
                    'is_home': is_home,
                    'is_starter': is_starter,
                    'position_id': player.get('positionId'),
                    'shirt_number': str(player.get('shirtNumber', '')) or None,
                    'rating': rating,
                    'minutes_played': minutes,
                    'goals': stats.get('goals', 0),
                    'assists': stats.get('assists', 0),
                    'xg': stats.get('expected_goals'),
                    'xgot': stats.get('expected_goals_on_target'),
                    'xa': stats.get('expected_assists'),
                    'shots': stats.get('total_shots') or stats.get('shots'),
                    'shots_on_target': stats.get('shots_on_target') or stats.get('ontarget_scoring_att'),
                    'passes': stats.get('accurate_passes_total'),
                    'passes_accurate': stats.get('accurate_passes'),
                    'chances_created': stats.get('chances_created'),
                    'tackles': stats.get('matchstats.headers.tackles'),
                    'interceptions': stats.get('interceptions'),
                    'defensive_actions': stats.get('defensive_actions'),
                    'fantasy_score': str(performance.get('fantasyScore', '')) or None,
                    'stats_json': json.dumps(stats) if stats else None,
                })

    if not players:
        return 0

    with conn.cursor() as cur:
        for p in players:
            cur.execute("""
                INSERT INTO fotmob_player_performances (
                    fotmob_match_id, player_id, player_name, team_id, team_name,
                    is_home, is_starter, position_id, shirt_number, rating,
                    minutes_played, goals, assists, xg, xgot, xa,
                    shots, shots_on_target, passes, passes_accurate,
                    chances_created, tackles, interceptions, defensive_actions,
                    fantasy_score, stats_json
                ) VALUES (
                    %(fotmob_match_id)s, %(player_id)s, %(player_name)s, %(team_id)s, %(team_name)s,
                    %(is_home)s, %(is_starter)s, %(position_id)s, %(shirt_number)s, %(rating)s,
                    %(minutes_played)s, %(goals)s, %(assists)s, %(xg)s, %(xgot)s, %(xa)s,
                    %(shots)s, %(shots_on_target)s, %(passes)s, %(passes_accurate)s,
                    %(chances_created)s, %(tackles)s, %(interceptions)s, %(defensive_actions)s,
                    %(fantasy_score)s, %(stats_json)s
                )
                ON CONFLICT (fotmob_match_id, player_id) DO UPDATE SET
                    player_name = EXCLUDED.player_name,
                    rating = COALESCE(EXCLUDED.rating, fotmob_player_performances.rating),
                    minutes_played = COALESCE(EXCLUDED.minutes_played, fotmob_player_performances.minutes_played),
                    goals = EXCLUDED.goals,
                    assists = EXCLUDED.assists,
                    xg = COALESCE(EXCLUDED.xg, fotmob_player_performances.xg),
                    xgot = COALESCE(EXCLUDED.xgot, fotmob_player_performances.xgot),
                    xa = COALESCE(EXCLUDED.xa, fotmob_player_performances.xa),
                    shots = COALESCE(EXCLUDED.shots, fotmob_player_performances.shots),
                    shots_on_target = COALESCE(EXCLUDED.shots_on_target, fotmob_player_performances.shots_on_target),
                    passes = COALESCE(EXCLUDED.passes, fotmob_player_performances.passes),
                    passes_accurate = COALESCE(EXCLUDED.passes_accurate, fotmob_player_performances.passes_accurate),
                    chances_created = COALESCE(EXCLUDED.chances_created, fotmob_player_performances.chances_created),
                    tackles = COALESCE(EXCLUDED.tackles, fotmob_player_performances.tackles),
                    interceptions = COALESCE(EXCLUDED.interceptions, fotmob_player_performances.interceptions),
                    defensive_actions = COALESCE(EXCLUDED.defensive_actions, fotmob_player_performances.defensive_actions),
                    fantasy_score = COALESCE(EXCLUDED.fantasy_score, fotmob_player_performances.fantasy_score),
                    stats_json = COALESCE(EXCLUDED.stats_json, fotmob_player_performances.stats_json)
            """, p)
        conn.commit()

    logger.info(f"Match {match_id}: extracted {len(players)} player performances")
    return len(players)


def parse_match_details(data: dict) -> dict:
    """Extract all details from match page data."""
    if not data:
        return {}
    
    general = data.get('general', {}) or {}
    content = data.get('content', {}) or {}
    header = data.get('header', {}) or {}
    
    result = {}

    # Scores from detail page (header.teams or header.status)
    teams = header.get('teams', [])
    if isinstance(teams, list) and len(teams) >= 2:
        result['home_score'] = teams[0].get('score')
        result['away_score'] = teams[1].get('score')
    # Also try status.scoreStr "2 - 1" format
    if result.get('home_score') is None:
        score_str = (header.get('status') or {}).get('scoreStr', '')
        if ' - ' in str(score_str):
            parts = str(score_str).split(' - ')
            try:
                result['home_score'] = int(parts[0])
                result['away_score'] = int(parts[1])
            except (ValueError, IndexError):
                pass

    # Status from detail page
    finished_flag = (header.get('status') or {}).get('finished')
    if finished_flag:
        result['status'] = 'finished'

    # Basic info
    result['venue'] = general.get('matchName') or (general.get('venue') or {}).get('name')
    result['attendance'] = general.get('attendance')
    result['referee'] = None
    if 'matchOfficials' in general:
        refs = general.get('matchOfficials', [])
        if refs:
            result['referee'] = refs[0].get('name')
    
    # Half-time scores
    ht_scores = header.get('htScore') or {}
    if ht_scores:
        result['ht_home_score'] = ht_scores.get('home')
        result['ht_away_score'] = ht_scores.get('away')
    
    # Lineups and formations
    lineup = content.get('lineup') or {}
    if lineup:
        home_lineup = lineup.get('homeTeam') or {}
        away_lineup = lineup.get('awayTeam') or {}
        
        result['formation_home'] = home_lineup.get('formation')
        result['formation_away'] = away_lineup.get('formation')
        result['home_lineup'] = json.dumps(home_lineup.get('players', []))
        result['away_lineup'] = json.dumps(away_lineup.get('players', []))
        
        # Team ratings
        result['home_avg_rating'] = home_lineup.get('rating')
        result['away_avg_rating'] = away_lineup.get('rating')
    
    # Stats
    stats_data = content.get('stats') or {}
    periods = stats_data.get('Periods', {})
    all_stats = (periods.get('All') or {}).get('stats', [])
    result['stats'] = json.dumps(all_stats)

    # Shotmap
    shotmap_data = content.get('shotmap') or {}
    shotmap = shotmap_data.get('shots', [])
    result['shotmap'] = json.dumps(shotmap)
    
    # Momentum
    momentum = content.get('momentum') or {}
    result['momentum'] = json.dumps((momentum.get('main') or {}).get('data', []))

    # Events (goals, cards, subs)
    match_facts = content.get('matchFacts') or {}
    events_section = match_facts.get('events') or {}
    events = events_section.get('events', [])
    result['events'] = json.dumps(events)
    result['match_facts'] = json.dumps({
        'highlights': match_facts.get('highlights', {}),
        'topPlayers': match_facts.get('topPlayers', []),
        'insights': match_facts.get('insights', []),
    })
    
    # Man of the Match
    motm = match_facts.get('playerOfTheMatch') or {}
    if motm:
        result['motm_player_id'] = motm.get('playerId')
        result['motm_player_name'] = (motm.get('name') or {}).get('fullName')
    
    return result


def upsert_match(conn, match: dict, details: dict = None) -> bool:
    """Insert or update a single match."""
    if not match or not match.get('fotmob_match_id'):
        return False
    
    # Merge basic match data with details
    data = {**match}
    if details:
        data.update(details)
    
    # For new matches, include raw_json from details if available
    if details:
        data['raw_json'] = json.dumps(details)  # Full detail as raw_json
    
    with conn.cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO fotmob_matches (
                    fotmob_match_id, league_id, season, round_number, match_date, kickoff_time,
                    home_team_id, home_team_name, away_team_id, away_team_name,
                    home_score, away_score, ht_home_score, ht_away_score,
                    status, venue, attendance, referee,
                    formation_home, formation_away,
                    events, stats, home_lineup, away_lineup, shotmap,
                    momentum, match_facts, 
                    home_avg_rating, away_avg_rating,
                    motm_player_id, motm_player_name,
                    raw_json, fetched_at, updated_at
                ) VALUES (
                    %(fotmob_match_id)s, %(league_id)s, %(season)s, %(round_number)s, %(match_date)s, %(kickoff_time)s,
                    %(home_team_id)s, %(home_team_name)s, %(away_team_id)s, %(away_team_name)s,
                    %(home_score)s, %(away_score)s, %(ht_home_score)s, %(ht_away_score)s,
                    %(status)s, %(venue)s, %(attendance)s, %(referee)s,
                    %(formation_home)s, %(formation_away)s,
                    %(events)s, %(stats)s, %(home_lineup)s, %(away_lineup)s, %(shotmap)s,
                    %(momentum)s, %(match_facts)s,
                    %(home_avg_rating)s, %(away_avg_rating)s,
                    %(motm_player_id)s, %(motm_player_name)s,
                    %(raw_json)s, NOW(), NOW()
                )
                ON CONFLICT (fotmob_match_id) DO UPDATE SET
                    round_number = COALESCE(EXCLUDED.round_number, fotmob_matches.round_number),
                    match_date = COALESCE(EXCLUDED.match_date, fotmob_matches.match_date),
                    kickoff_time = COALESCE(EXCLUDED.kickoff_time, fotmob_matches.kickoff_time),
                    home_score = COALESCE(EXCLUDED.home_score, fotmob_matches.home_score),
                    away_score = COALESCE(EXCLUDED.away_score, fotmob_matches.away_score),
                    ht_home_score = COALESCE(EXCLUDED.ht_home_score, fotmob_matches.ht_home_score),
                    ht_away_score = COALESCE(EXCLUDED.ht_away_score, fotmob_matches.ht_away_score),
                    status = EXCLUDED.status,
                    venue = COALESCE(EXCLUDED.venue, fotmob_matches.venue),
                    attendance = COALESCE(EXCLUDED.attendance, fotmob_matches.attendance),
                    referee = COALESCE(EXCLUDED.referee, fotmob_matches.referee),
                    formation_home = COALESCE(EXCLUDED.formation_home, fotmob_matches.formation_home),
                    formation_away = COALESCE(EXCLUDED.formation_away, fotmob_matches.formation_away),
                    events = COALESCE(EXCLUDED.events, fotmob_matches.events),
                    stats = COALESCE(EXCLUDED.stats, fotmob_matches.stats),
                    home_lineup = COALESCE(EXCLUDED.home_lineup, fotmob_matches.home_lineup),
                    away_lineup = COALESCE(EXCLUDED.away_lineup, fotmob_matches.away_lineup),
                    shotmap = COALESCE(EXCLUDED.shotmap, fotmob_matches.shotmap),
                    momentum = COALESCE(EXCLUDED.momentum, fotmob_matches.momentum),
                    match_facts = COALESCE(EXCLUDED.match_facts, fotmob_matches.match_facts),
                    home_avg_rating = COALESCE(EXCLUDED.home_avg_rating, fotmob_matches.home_avg_rating),
                    away_avg_rating = COALESCE(EXCLUDED.away_avg_rating, fotmob_matches.away_avg_rating),
                    motm_player_id = COALESCE(EXCLUDED.motm_player_id, fotmob_matches.motm_player_id),
                    motm_player_name = COALESCE(EXCLUDED.motm_player_name, fotmob_matches.motm_player_name),
                    raw_json = COALESCE(EXCLUDED.raw_json, fotmob_matches.raw_json),
                    updated_at = NOW()
            """, {
                'fotmob_match_id': data.get('fotmob_match_id'),
                'league_id': data.get('league_id'),
                'season': data.get('season'),
                'round_number': data.get('round_number'),
                'match_date': data.get('match_date'),
                'kickoff_time': data.get('kickoff_time'),
                'home_team_id': data.get('home_team_id'),
                'home_team_name': data.get('home_team_name'),
                'away_team_id': data.get('away_team_id'),
                'away_team_name': data.get('away_team_name'),
                'home_score': data.get('home_score'),
                'away_score': data.get('away_score'),
                'ht_home_score': data.get('ht_home_score'),
                'ht_away_score': data.get('ht_away_score'),
                'status': data.get('status', 'unknown'),
                'venue': data.get('venue'),
                'attendance': data.get('attendance'),
                'referee': data.get('referee'),
                'formation_home': data.get('formation_home'),
                'formation_away': data.get('formation_away'),
                'events': data.get('events'),
                'stats': data.get('stats'),
                'home_lineup': data.get('home_lineup'),
                'away_lineup': data.get('away_lineup'),
                'shotmap': data.get('shotmap'),
                'momentum': data.get('momentum'),
                'match_facts': data.get('match_facts'),
                'home_avg_rating': data.get('home_avg_rating'),
                'away_avg_rating': data.get('away_avg_rating'),
                'motm_player_id': data.get('motm_player_id'),
                'motm_player_name': data.get('motm_player_name'),
                'raw_json': data.get('raw_json'),
            })
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error upserting match {data.get('fotmob_match_id')}: {e}")
            conn.rollback()
            return False


def sync_league(league_code: str, season: str = "2025/2026", fetch_details: bool = False,
                status_filter: list[str] = None, date_filter: str = None) -> dict:
    """
    Sync a single league using Playwright.

    Args:
        league_code: League code (PT, PL, ES, etc.)
        season: Season string
        fetch_details: If True, fetch full details for each match
        status_filter: Only fetch details for matches with these statuses
        date_filter: Only process matches on this date (YYYY-MM-DD)
    """
    league_id = LEAGUES.get(league_code)
    if not league_id:
        return {"error": f"Unknown league: {league_code}"}
    
    logger.info(f"=== Syncing {league_code} (id={league_id}) ===")
    
    stats = {
        "league": league_code,
        "matches_found": 0,
        "matches_upserted": 0,
        "details_fetched": 0,
        "errors": 0,
    }
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        try:
            # 1. Fetch league listing
            raw_matches = fetch_league_matches(page, league_id)
            stats["matches_found"] = len(raw_matches)
            
            if not raw_matches:
                return {"error": "No matches found", **stats}
            
            conn = get_db_connection()
            
            try:
                for i, m in enumerate(raw_matches):
                    match_id = m.get('id')
                    if not match_id:
                        continue
                    
                    # Parse basic match info
                    basic = parse_basic_match(m, league_id, season)
                    if not basic:
                        continue

                    # Date filter — skip matches not on the target date
                    if date_filter and basic.get('match_date'):
                        if str(basic['match_date']) != date_filter:
                            continue

                    # Decide if we should fetch details
                    should_fetch_details = fetch_details
                    if status_filter and basic.get('status') not in status_filter:
                        should_fetch_details = False

                    # Skip if we already have scores + player data for this match
                    if should_fetch_details:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT home_score, (SELECT COUNT(*) FROM fotmob_player_performances WHERE fotmob_match_id = %s) "
                            "FROM fotmob_matches WHERE fotmob_match_id = %s",
                            (match_id, match_id)
                        )
                        existing = cur.fetchone()
                        if existing and existing[0] is not None and existing[1] > 0:
                            stats["matches_upserted"] += 1
                            continue

                    details = None
                    raw_details = None
                    if should_fetch_details:
                        logger.info(f"[{i+1}/{len(raw_matches)}] Fetching details: {basic['home_team_name']} vs {basic['away_team_name']}")
                        raw_details = fetch_match_details(page, match_id)
                        if raw_details:
                            details = parse_match_details(raw_details)
                            stats["details_fetched"] += 1
                        time.sleep(0.5)  # Be nice

                    # Upsert to database
                    if upsert_match(conn, basic, details):
                        stats["matches_upserted"] += 1
                        # Extract player performances when we have full details
                        if raw_details:
                            extract_player_performances(conn, match_id, raw_details)
                    else:
                        stats["errors"] += 1
                    
                    # Progress log
                    if (i + 1) % 50 == 0:
                        logger.info(f"Progress: {i+1}/{len(raw_matches)} matches processed")
                
            finally:
                conn.close()
            
            stats["success"] = True
            return stats
            
        except Exception as e:
            logger.exception(f"Error syncing {league_code}: {e}")
            return {"error": str(e), **stats}
        finally:
            browser.close()


def sync_all_leagues(season: str = "2025/2026", fetch_details: bool = False, date_filter: str = None) -> dict:
    """Sync all leagues."""
    results = {}

    for code in LEAGUES.keys():
        if code == 'BR':  # Skip Brasileirão (different season)
            continue

        result = sync_league(code, season, fetch_details, date_filter=date_filter)
        results[code] = result
        
        if result.get('success'):
            logger.info(f"✅ {code}: {result.get('matches_upserted', 0)} matches")
        else:
            logger.error(f"❌ {code}: {result.get('error', 'Unknown error')}")
        
        time.sleep(3)  # Be nice to FotMob between leagues
    
    return results


def backfill_missing_details(league_code: str, season: str = "2025/2026") -> dict:
    """Fetch details for matches that don't have stats yet."""
    league_id = LEAGUES.get(league_code)
    if not league_id:
        return {"error": f"Unknown league: {league_code}"}
    
    conn = get_db_connection()
    
    # Find matches needing details
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT fotmob_match_id, home_team_name, away_team_name, status
            FROM fotmob_matches
            WHERE league_id = %s
              AND status = 'finished'
              AND (stats IS NULL OR stats = '[]' OR stats = 'null')
            ORDER BY match_date DESC
        """, (league_id,))
        matches = cur.fetchall()
    
    if not matches:
        logger.info(f"No matches needing details for {league_code}")
        return {"matches_processed": 0}
    
    logger.info(f"Found {len(matches)} matches needing details for {league_code}")
    
    stats = {"matches_processed": 0, "success": 0, "errors": 0}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()
        
        try:
            for i, m in enumerate(matches):
                match_id = m['fotmob_match_id']
                logger.info(f"[{i+1}/{len(matches)}] {m['home_team_name']} vs {m['away_team_name']}")
                
                raw_details = fetch_match_details(page, match_id)
                if raw_details:
                    details = parse_match_details(raw_details)
                    
                    # Update only the details fields
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE fotmob_matches SET
                                venue = COALESCE(%s, venue),
                                attendance = COALESCE(%s, attendance),
                                referee = COALESCE(%s, referee),
                                ht_home_score = COALESCE(%s, ht_home_score),
                                ht_away_score = COALESCE(%s, ht_away_score),
                                formation_home = COALESCE(%s, formation_home),
                                formation_away = COALESCE(%s, formation_away),
                                home_lineup = COALESCE(%s, home_lineup),
                                away_lineup = COALESCE(%s, away_lineup),
                                home_avg_rating = COALESCE(%s, home_avg_rating),
                                away_avg_rating = COALESCE(%s, away_avg_rating),
                                stats = COALESCE(%s, stats),
                                shotmap = COALESCE(%s, shotmap),
                                momentum = COALESCE(%s, momentum),
                                events = COALESCE(%s, events),
                                match_facts = COALESCE(%s, match_facts),
                                motm_player_id = COALESCE(%s, motm_player_id),
                                motm_player_name = COALESCE(%s, motm_player_name),
                                raw_json = %s,
                                updated_at = NOW()
                            WHERE fotmob_match_id = %s
                        """, (
                            details.get('venue'),
                            details.get('attendance'),
                            details.get('referee'),
                            details.get('ht_home_score'),
                            details.get('ht_away_score'),
                            details.get('formation_home'),
                            details.get('formation_away'),
                            details.get('home_lineup'),
                            details.get('away_lineup'),
                            details.get('home_avg_rating'),
                            details.get('away_avg_rating'),
                            details.get('stats'),
                            details.get('shotmap'),
                            details.get('momentum'),
                            details.get('events'),
                            details.get('match_facts'),
                            details.get('motm_player_id'),
                            details.get('motm_player_name'),
                            json.dumps(raw_details),
                            match_id,
                        ))
                        conn.commit()
                    
                    # Extract player performances
                    extract_player_performances(conn, match_id, raw_details)

                    stats["success"] += 1
                else:
                    stats["errors"] += 1

                stats["matches_processed"] += 1
                time.sleep(1)  # Rate limit

        finally:
            browser.close()

    conn.close()
    return stats


def find_matches_missing_xg(league_code: str, season: str = "2025/2026") -> list[dict]:
    """Find finished matches that have stats but no xG data."""
    league_id = LEAGUES.get(league_code)
    if not league_id:
        return []

    conn = get_db_connection()
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT fotmob_match_id, home_team_name, away_team_name, round_number
            FROM fotmob_matches
            WHERE league_id = %s
              AND season = %s
              AND status = 'finished'
              AND stats IS NOT NULL AND stats != '[]'
              AND stats::text NOT LIKE '%%expected_goals%%'
              AND stats::text NOT LIKE '%%Expected goals%%'
            ORDER BY round_number, match_date
        """, (league_id, season))
        matches = cur.fetchall()
    conn.close()
    return matches


def force_rescrape_xg(league_code: str, season: str = "2025/2026") -> dict:
    """Re-scrape match details for matches missing xG data."""
    matches = find_matches_missing_xg(league_code, season)
    if not matches:
        logger.info(f"No matches missing xG for {league_code}")
        return {"matches_processed": 0}

    logger.info(f"Found {len(matches)} matches missing xG for {league_code}")
    stats = {"matches_processed": 0, "success": 0, "errors": 0}

    conn = get_db_connection()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            for i, m in enumerate(matches):
                match_id = m['fotmob_match_id']
                logger.info(f"[{i+1}/{len(matches)}] R{m['round_number']} {m['home_team_name']} vs {m['away_team_name']}")

                raw_details = fetch_match_details(page, match_id)
                if raw_details:
                    details = parse_match_details(raw_details)

                    # Direct SET (not COALESCE) — we're replacing incomplete stats
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE fotmob_matches SET
                                stats = %s,
                                shotmap = %s,
                                events = %s,
                                match_facts = %s,
                                home_lineup = %s,
                                away_lineup = %s,
                                formation_home = %s,
                                formation_away = %s,
                                home_avg_rating = %s,
                                away_avg_rating = %s,
                                motm_player_id = %s,
                                motm_player_name = %s,
                                raw_json = %s,
                                updated_at = NOW()
                            WHERE fotmob_match_id = %s
                        """, (
                            details.get('stats'),
                            details.get('shotmap'),
                            details.get('events'),
                            details.get('match_facts'),
                            details.get('home_lineup'),
                            details.get('away_lineup'),
                            details.get('formation_home'),
                            details.get('formation_away'),
                            details.get('home_avg_rating'),
                            details.get('away_avg_rating'),
                            details.get('motm_player_id'),
                            details.get('motm_player_name'),
                            json.dumps(raw_details),
                            match_id,
                        ))
                        conn.commit()

                    # Extract player performances
                    extract_player_performances(conn, match_id, raw_details)

                    stats["success"] += 1
                else:
                    stats["errors"] += 1

                stats["matches_processed"] += 1
                time.sleep(1)

        finally:
            browser.close()

    conn.close()
    return stats


def extract_players_from_existing(league_code: str) -> dict:
    """Extract player performances from matches that already have playerStats in raw_json."""
    league_id = LEAGUES.get(league_code)
    if not league_id:
        return {"error": f"Unknown league: {league_code}"}

    conn = get_db_connection()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT m.fotmob_match_id, m.home_team_name, m.away_team_name, m.raw_json
            FROM fotmob_matches m
            WHERE m.league_id = %s
              AND m.raw_json::text LIKE '%%playerStats%%'
              AND m.fotmob_match_id NOT IN (
                  SELECT DISTINCT fotmob_match_id FROM fotmob_player_performances
              )
            ORDER BY m.match_date
        """, (league_id,))
        matches = cur.fetchall()

    if not matches:
        logger.info(f"No matches with extractable player data for {league_code}")
        conn.close()
        return {"matches_processed": 0, "players_extracted": 0}

    logger.info(f"Found {len(matches)} matches with extractable player data for {league_code}")

    stats = {"matches_processed": 0, "players_extracted": 0, "errors": 0}

    for i, m in enumerate(matches):
        match_id = m['fotmob_match_id']
        logger.info(f"[{i+1}/{len(matches)}] {m['home_team_name']} vs {m['away_team_name']}")

        try:
            raw_data = m['raw_json'] if isinstance(m['raw_json'], dict) else json.loads(m['raw_json'])
            count = extract_player_performances(conn, match_id, raw_data)
            stats["players_extracted"] += count
            stats["matches_processed"] += 1
        except Exception as e:
            logger.error(f"Error extracting players for match {match_id}: {e}")
            conn.rollback()
            stats["errors"] += 1

    conn.close()
    return stats


def backfill_player_performances(league_code: str, season: str = "2025/2026") -> dict:
    """Re-scrape details and extract player performances for matches missing them."""
    league_id = LEAGUES.get(league_code)
    if not league_id:
        return {"error": f"Unknown league: {league_code}"}

    conn = get_db_connection()

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT m.fotmob_match_id, m.home_team_name, m.away_team_name, m.round_number
            FROM fotmob_matches m
            WHERE m.league_id = %s
              AND m.season = %s
              AND m.status = 'finished'
              AND m.fotmob_match_id NOT IN (
                  SELECT DISTINCT fotmob_match_id FROM fotmob_player_performances
              )
            ORDER BY m.match_date
        """, (league_id, season))
        matches = cur.fetchall()

    if not matches:
        logger.info(f"No matches missing player performances for {league_code}")
        conn.close()
        return {"matches_processed": 0}

    logger.info(f"Found {len(matches)} matches missing player performances for {league_code}")

    stats = {"matches_processed": 0, "players_extracted": 0, "success": 0, "errors": 0}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = context.new_page()

        try:
            for i, m in enumerate(matches):
                match_id = m['fotmob_match_id']
                logger.info(f"[{i+1}/{len(matches)}] R{m.get('round_number', '?')} {m['home_team_name']} vs {m['away_team_name']}")

                raw_details = fetch_match_details(page, match_id)
                if raw_details:
                    # Also update raw_json in the match record
                    details = parse_match_details(raw_details)
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE fotmob_matches SET
                                stats = COALESCE(%s, stats),
                                raw_json = %s,
                                updated_at = NOW()
                            WHERE fotmob_match_id = %s
                        """, (details.get('stats'), json.dumps(raw_details), match_id))
                        conn.commit()

                    count = extract_player_performances(conn, match_id, raw_details)
                    stats["players_extracted"] += count
                    stats["success"] += 1
                else:
                    stats["errors"] += 1

                stats["matches_processed"] += 1
                time.sleep(1)

        finally:
            browser.close()

    conn.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Sync FotMob data using Playwright")
    parser.add_argument("--league", type=str, help="League code (PT, PL, ES, etc.)")
    parser.add_argument("--season", type=str, default="2025/2026", help="Season")
    parser.add_argument("--all", action="store_true", help="Sync all enabled leagues")
    parser.add_argument("--details", action="store_true", help="Also fetch match details (slower)")
    parser.add_argument("--backfill", action="store_true", help="Backfill missing details only")
    parser.add_argument("--finished-only", action="store_true", help="Only fetch details for finished matches")
    parser.add_argument("--force-rescrape", action="store_true", help="Re-scrape matches missing xG data")
    parser.add_argument("--backfill-players", action="store_true", help="Re-scrape and extract player performances for matches missing them")
    parser.add_argument("--extract-players-from-raw", action="store_true", help="Extract player performances from existing raw_json (no scraping)")
    parser.add_argument("--today", action="store_true", help="Only sync today's matches (fast)")
    parser.add_argument("--date", type=str, help="Only sync matches on this date (YYYY-MM-DD)")

    args = parser.parse_args()

    status_filter = ['finished'] if args.finished_only else None
    date_filter = None
    if args.today:
        date_filter = datetime.now().strftime("%Y-%m-%d")
    elif args.date:
        date_filter = args.date

    if args.extract_players_from_raw and args.league:
        result = extract_players_from_existing(args.league)
        print(json.dumps(result, indent=2, default=str))
    elif args.backfill_players and args.league:
        result = backfill_player_performances(args.league, args.season)
        print(json.dumps(result, indent=2, default=str))
    elif args.force_rescrape and args.league:
        result = force_rescrape_xg(args.league, args.season)
        print(json.dumps(result, indent=2, default=str))
    elif args.backfill and args.league:
        result = backfill_missing_details(args.league, args.season)
        print(json.dumps(result, indent=2, default=str))
    elif args.all:
        results = sync_all_leagues(args.season, args.details, date_filter=date_filter)
        print(json.dumps(results, indent=2, default=str))
    elif args.league:
        result = sync_league(args.league, args.season, args.details, status_filter, date_filter=date_filter)
        print(json.dumps(result, indent=2, default=str))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
