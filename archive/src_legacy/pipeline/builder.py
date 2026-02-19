"""
Context Builder

Orchestrates all data sources to build PreMatchContext and PostMatchReality.
Single source of truth for building match data.

Uses the existing clarity_football database.
"""

from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, List, Tuple
import logging
import os
import psycopg2
from psycopg2.extras import RealDictCursor

from src.models import (
    Fixture,
    TeamSnapshot,
    TeamSeasonStats,
    PlayerAbsence,
    TeamAvailability,
    HeadToHead,
    MatchOdds,
    MatchNarratives,
    PreMatchContext,
    PostMatchReality,
    Goal,
    GoalType,
    TeamLineup,
    PlayerInLineup,
    TeamMatchStats,
    MatchStatistics,
    FormTrend,
)
from src.data.team_registry import normalize_team_name

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Builds PreMatchContext and PostMatchReality from the clarity_football database.
    
    Usage:
        builder = ContextBuilder()
        pre_match = builder.build_pre_match("2026-01-19_Liverpool_Manchester_City")
    """
    
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or os.getenv("DATABASE_URL", "postgresql://joao@localhost:5432/clarity_football")
        self._sources_used: List[str] = []
    
    def _get_connection(self):
        """Get database connection."""
        return psycopg2.connect(self.db_url)
    
    # =========================================================
    # PRE-MATCH BUILDING
    # =========================================================
    
    def build_pre_match(
        self,
        fixture_id: str,
        as_of: Optional[date] = None
    ) -> PreMatchContext:
        """
        Build complete pre-match context for a fixture.
        
        Args:
            fixture_id: The fixture ID (e.g., "2026-01-19_Liverpool_Manchester_City")
            as_of: Point in time for historical builds (None = match date)
            
        Returns:
            PreMatchContext with all available data
        """
        self._sources_used = []
        
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Get fixture info
                fixture = self._build_fixture(cur, fixture_id)
                if not fixture:
                    raise ValueError(f"Fixture not found: {fixture_id}")
                
                # Use match date as point-in-time if not specified
                point_in_time = as_of or fixture.match_date
                
                # Use original IDs for fixture/stats tables, canonical for injuries
                home_original = fixture.home_team_id
                away_original = fixture.away_team_id
                home_canonical = fixture.home_team_name
                away_canonical = fixture.away_team_name
                
                # 2. Get team snapshots (standings at that point) - uses fixtures table
                home_snapshot = self._build_team_snapshot(
                    cur, home_original, point_in_time, is_home=True
                )
                home_snapshot.name = home_canonical  # Display canonical name
                
                away_snapshot = self._build_team_snapshot(
                    cur, away_original, point_in_time, is_home=False
                )
                away_snapshot.name = away_canonical
                
                # 3. Get season stats from team_stats table - uses original names
                home_stats = self._build_team_stats(cur, home_original, point_in_time)
                away_stats = self._build_team_stats(cur, away_original, point_in_time)
                
                # 4. Get availability (injuries) - uses canonical names
                home_availability = self._build_availability(
                    cur, home_canonical, point_in_time
                )
                away_availability = self._build_availability(
                    cur, away_canonical, point_in_time
                )
                
                # 5. Get H2H - uses original names (from fixtures)
                h2h = self._build_h2h(
                    cur, home_original, away_original, point_in_time
                )
                
                # 6. Get odds
                odds = self._build_odds(cur, fixture_id)
                
                # 7. Build narratives (calculated)
                narratives = self._build_narratives(
                    fixture_id, home_snapshot, away_snapshot
                )
                
                # 8. Calculate coverage score
                coverage = self._calculate_coverage(
                    fixture, home_snapshot, away_snapshot,
                    home_stats, away_stats,
                    home_availability, away_availability,
                    h2h, odds
                )
                
                return PreMatchContext(
                    fixture=fixture,
                    home_snapshot=home_snapshot,
                    away_snapshot=away_snapshot,
                    home_stats=home_stats,
                    away_stats=away_stats,
                    home_availability=home_availability,
                    away_availability=away_availability,
                    head_to_head=h2h,
                    odds=odds,
                    narratives=narratives,
                    coverage_score=coverage,
                    sources=self._sources_used.copy(),
                    built_at=datetime.now(),
                )
    
    # =========================================================
    # FIXTURE
    # =========================================================
    
    def _build_fixture(self, cur, fixture_id: str) -> Optional[Fixture]:
        """Build Fixture from database."""
        cur.execute("""
            SELECT id, date, season, league, home_team, away_team, 
                   home_score, away_score, status, round
            FROM fixtures 
            WHERE id = %s
        """, (fixture_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        self._sources_used.append("db_fixtures")
        
        # Normalize team names for consistent lookups across tables
        home_name = row['home_team']
        away_name = row['away_team']
        home_canonical = normalize_team_name(home_name)
        away_canonical = normalize_team_name(away_name)
        
        return Fixture(
            fixture_id=row['id'],
            competition=row['league'] or "Premier League",
            competition_id=39,  # Premier League
            season=row['season'],
            round=str(row['round']) if row['round'] else "",
            match_date=row['date'],
            kickoff_time=datetime.combine(row['date'], datetime.min.time()),
            venue="",  # Not in current DB
            home_team_id=home_name,  # Keep original for fixture lookups
            away_team_id=away_name,
            home_team_name=home_canonical,  # Use canonical for display & other queries
            away_team_name=away_canonical,
        )
    
    # =========================================================
    # TEAM SNAPSHOT
    # =========================================================
    
    def _build_team_snapshot(
        self, cur, team_name: str, as_of: date, is_home: bool
    ) -> TeamSnapshot:
        """Build TeamSnapshot from fixtures history."""
        
        # Get all finished fixtures before this date
        cur.execute("""
            SELECT home_team, away_team, home_score, away_score, date
            FROM fixtures
            WHERE (home_team = %s OR away_team = %s)
              AND date < %s
              AND status = 'FINISHED'
            ORDER BY date DESC
        """, (team_name, team_name, as_of))
        
        matches = cur.fetchall()
        
        # Calculate standings from match history
        points = 0
        wins = draws = losses = 0
        goals_for = goals_against = 0
        home_w = home_d = home_l = 0
        away_w = away_d = away_l = 0
        form = []
        
        for m in matches:
            is_home_match = m['home_team'] == team_name
            team_score = m['home_score'] if is_home_match else m['away_score']
            opp_score = m['away_score'] if is_home_match else m['home_score']
            
            if team_score is None or opp_score is None:
                continue
                
            goals_for += team_score
            goals_against += opp_score
            
            if team_score > opp_score:
                points += 3
                wins += 1
                form.append('W')
                if is_home_match:
                    home_w += 1
                else:
                    away_w += 1
            elif team_score == opp_score:
                points += 1
                draws += 1
                form.append('D')
                if is_home_match:
                    home_d += 1
                else:
                    away_d += 1
            else:
                losses += 1
                form.append('L')
                if is_home_match:
                    home_l += 1
                else:
                    away_l += 1
        
        # Get last 5 form
        form_last_5 = ''.join(form[:5]) if form else ""
        
        # Determine form trend
        if len(form) >= 5:
            recent_3 = form[:3].count('W') * 3 + form[:3].count('D')
            older_3 = form[2:5].count('W') * 3 + form[2:5].count('D')
            if recent_3 > older_3 + 2:
                form_trend = FormTrend.IMPROVING
            elif recent_3 < older_3 - 2:
                form_trend = FormTrend.DECLINING
            elif abs(recent_3 - older_3) <= 1:
                form_trend = FormTrend.STABLE
            else:
                form_trend = FormTrend.VOLATILE
        else:
            form_trend = FormTrend.STABLE
        
        # Get ELO from most recent team_stats
        cur.execute("""
            SELECT elo FROM team_stats 
            WHERE team_name = %s AND elo IS NOT NULL
            ORDER BY fixture_id DESC
            LIMIT 1
        """, (team_name,))
        elo_row = cur.fetchone()
        elo = elo_row['elo'] if elo_row else 1500
        
        # Calculate league position (simplified - count teams with more points)
        cur.execute("""
            WITH team_points AS (
                SELECT 
                    team,
                    SUM(pts) as total_points
                FROM (
                    SELECT home_team as team,
                           CASE WHEN home_score > away_score THEN 3
                                WHEN home_score = away_score THEN 1
                                ELSE 0 END as pts
                    FROM fixtures WHERE date < %s AND status = 'FINISHED'
                    UNION ALL
                    SELECT away_team as team,
                           CASE WHEN away_score > home_score THEN 3
                                WHEN away_score = home_score THEN 1
                                ELSE 0 END as pts
                    FROM fixtures WHERE date < %s AND status = 'FINISHED'
                ) x
                GROUP BY team
            )
            SELECT COUNT(*) + 1 as position
            FROM team_points
            WHERE total_points > (SELECT total_points FROM team_points WHERE team = %s)
        """, (as_of, as_of, team_name))
        pos_row = cur.fetchone()
        league_position = pos_row['position'] if pos_row else 10
        
        self._sources_used.append("db_fixtures")
        
        return TeamSnapshot(
            team_id=team_name,
            name=team_name,
            league_position=league_position,
            points=points,
            played=wins + draws + losses,
            wins=wins,
            draws=draws,
            losses=losses,
            goals_for=goals_for,
            goals_against=goals_against,
            goal_difference=goals_for - goals_against,
            form_last_5=form_last_5,
            form_trend=form_trend,
            home_record=f"{home_w}W-{home_d}D-{home_l}L",
            away_record=f"{away_w}W-{away_d}D-{away_l}L",
            elo=elo,
        )
    
    # =========================================================
    # TEAM STATS
    # =========================================================
    
    def _build_team_stats(self, cur, team_name: str, as_of: date) -> TeamSeasonStats:
        """Build TeamSeasonStats from team_stats table."""
        
        # Get aggregated stats from matches before this date
        cur.execute("""
            SELECT 
                AVG(ts.xg) as avg_xg,
                AVG(ts.xga) as avg_xga,
                AVG(ts.ppda) as avg_ppda,
                AVG(ts.field_tilt) as avg_field_tilt,
                COUNT(*) as matches
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s
              AND f.date < %s
              AND ts.xg IS NOT NULL
        """, (team_name, as_of))
        
        row = cur.fetchone()
        
        if row and row['matches'] and row['matches'] > 0:
            self._sources_used.append("db_team_stats")
            xg_for = float(row['avg_xg']) if row['avg_xg'] else 0.0
            xg_against = float(row['avg_xga']) if row['avg_xga'] else 0.0
            ppda = float(row['avg_ppda']) if row['avg_ppda'] else None
        else:
            xg_for = xg_against = 0.0
            ppda = None
        
        # Calculate possession from field_tilt (field_tilt ≈ possession dominance)
        avg_possession = float(row['avg_field_tilt']) if row and row['avg_field_tilt'] else 50.0
        
        return TeamSeasonStats(
            team_id=team_name,
            xg_for=xg_for * (row['matches'] if row and row['matches'] else 1),  # Total xG
            xg_against=xg_against * (row['matches'] if row and row['matches'] else 1),
            xg_diff=(xg_for - xg_against) * (row['matches'] if row and row['matches'] else 1),
            avg_possession=avg_possession,
            shots_per_game=0.0,  # Not in current DB
            shots_against_per_game=0.0,
            shots_on_target_per_game=0.0,
            corners_per_game=0.0,
            set_piece_goals=0,
            set_piece_conceded=0,
            ppda=ppda,
        )
    
    # =========================================================
    # AVAILABILITY (INJURIES)
    # =========================================================
    
    def _build_availability(self, cur, team_name: str, as_of: date) -> TeamAvailability:
        """Build TeamAvailability from player_injuries_historical."""
        
        # Normalize team name and get canonical version
        canonical = normalize_team_name(team_name)
        
        # Find injuries active on this date - search both original and canonical names
        # Also use ILIKE for case-insensitive partial matching
        cur.execute("""
            SELECT player_name, position, injury_reason, from_date, end_date, games_missed
            FROM player_injuries_historical
            WHERE (team_name = %s OR team_name = %s OR team_name ILIKE %s)
              AND from_date <= %s
              AND (end_date IS NULL OR end_date >= %s)
        """, (team_name, canonical, f"%{canonical.split()[0]}%", as_of, as_of))
        
        rows = cur.fetchall()
        
        absences = []
        total_importance = 0.0
        missing_key = 0
        adapted_count = 0
        
        for row in rows:
            # Estimate importance based on position and games missed
            games_missed = row['games_missed'] or 0
            position = row['position'] or "Unknown"
            
            # Simple importance heuristic
            if position in ['Goalkeeper', 'GK']:
                base_importance = 7.0
            elif position in ['Centre-Back', 'CB', 'Defender']:
                base_importance = 6.0
            elif position in ['Central Midfield', 'CM', 'Midfield']:
                base_importance = 6.5
            elif position in ['Centre-Forward', 'CF', 'Striker', 'Forward']:
                base_importance = 7.5
            else:
                base_importance = 5.0
            
            # Adjust based on games missed (key players miss = noticed)
            importance = min(10.0, base_importance + (games_missed * 0.2))
            
            # Team adapted if out 3+ games
            team_adapted = games_missed >= 3
            if team_adapted:
                adapted_count += 1
            
            absence = PlayerAbsence(
                player_id=row['player_name'],  # Using name as ID
                player_name=row['player_name'],
                team_id=team_name,
                position=position,
                reason="injury",
                injury_type=row['injury_reason'],
                out_since=row['from_date'],
                expected_return=row['end_date'],
                games_missed=games_missed,
                importance=importance,
                team_adapted=team_adapted,
                replacement_quality=5.0,  # Default
            )
            absences.append(absence)
            total_importance += importance
            if importance >= 7:
                missing_key += 1
        
        self._sources_used.append("db_injuries")
        
        return TeamAvailability(
            team_id=team_name,
            absences=absences,
            total_missing=len(absences),
            missing_key_players=missing_key,
            total_importance_lost=total_importance,
            adapted_absences=adapted_count,
        )
    
    # =========================================================
    # HEAD TO HEAD
    # =========================================================
    
    def _build_h2h(
        self, cur, home_team: str, away_team: str, before_date: date
    ) -> HeadToHead:
        """Build HeadToHead from historical fixtures."""
        
        cur.execute("""
            SELECT home_team, away_team, home_score, away_score, date
            FROM fixtures
            WHERE ((home_team = %s AND away_team = %s) OR (home_team = %s AND away_team = %s))
              AND date < %s
              AND status = 'FINISHED'
            ORDER BY date DESC
            LIMIT 10
        """, (home_team, away_team, away_team, home_team, before_date))
        
        matches = cur.fetchall()
        
        home_wins = draws = away_wins = 0
        total_goals = 0
        home_goals = 0
        away_goals = 0
        results = []
        home_results = []
        
        for m in matches:
            h_score = m['home_score'] or 0
            a_score = m['away_score'] or 0
            total_goals += h_score + a_score
            
            # Determine winner from perspective of our home team
            if m['home_team'] == home_team:
                # This match had our home team at home
                home_goals += h_score
                away_goals += a_score
                home_results.append(f"{h_score}-{a_score}")
                
                if h_score > a_score:
                    home_wins += 1
                elif h_score == a_score:
                    draws += 1
                else:
                    away_wins += 1
            else:
                # Our home team was away in this match
                home_goals += a_score
                away_goals += h_score
                
                if a_score > h_score:
                    home_wins += 1
                elif a_score == h_score:
                    draws += 1
                else:
                    away_wins += 1
            
            results.append(f"{h_score}-{a_score}")
        
        n = len(matches) or 1
        
        # Determine pattern
        avg_goals = total_goals / n
        if avg_goals > 3.0:
            pattern = "high_scoring"
        elif avg_goals < 2.0:
            pattern = "tight"
        elif home_wins > away_wins + 2:
            pattern = "home_dominant"
        elif away_wins > home_wins + 2:
            pattern = "away_dominant"
        else:
            pattern = "balanced"
        
        self._sources_used.append("db_h2h")
        
        return HeadToHead(
            home_team_id=home_team,
            away_team_id=away_team,
            matches_analyzed=len(matches),
            home_wins=home_wins,
            draws=draws,
            away_wins=away_wins,
            avg_total_goals=avg_goals,
            avg_home_goals=home_goals / n,
            avg_away_goals=away_goals / n,
            last_5_results=results[:5],
            last_5_home_results=home_results[:5],
            pattern=pattern,
        )
    
    # =========================================================
    # ODDS
    # =========================================================
    
    def _build_odds(self, cur, fixture_id: str) -> Optional[MatchOdds]:
        """Build MatchOdds from odds_snapshots."""
        
        # Get odds for home/draw/away from the market structure
        cur.execute("""
            SELECT market_key, selection_key, odds_decimal, captured_at, source
            FROM odds_snapshots
            WHERE fixture_id = %s
              AND market_key = '1x2'
            ORDER BY captured_at DESC
        """, (fixture_id,))
        
        rows = cur.fetchall()
        if not rows:
            return None
        
        self._sources_used.append("db_odds")
        
        # Parse odds from rows
        home_odds = draw_odds = away_odds = 0.0
        captured_at = None
        source = 'unknown'
        
        for row in rows:
            if captured_at is None:
                captured_at = row['captured_at']
                source = row['source'] or 'unknown'
            
            selection = row['selection_key'].lower()
            odds = float(row['odds_decimal'])
            
            if selection in ['home', '1', 'h']:
                home_odds = odds
            elif selection in ['draw', 'x', 'd']:
                draw_odds = odds
            elif selection in ['away', '2', 'a']:
                away_odds = odds
        
        if home_odds == 0 and draw_odds == 0 and away_odds == 0:
            return None
        
        return MatchOdds(
            fixture_id=fixture_id,
            captured_at=captured_at or datetime.now(),
            bookmaker=source,
            home_win=home_odds,
            draw=draw_odds,
            away_win=away_odds,
        )
    
    # =========================================================
    # NARRATIVES
    # =========================================================
    
    def _build_narratives(
        self,
        fixture_id: str,
        home: TeamSnapshot,
        away: TeamSnapshot
    ) -> MatchNarratives:
        """Build MatchNarratives from calculated data."""
        
        # Known derbies/rivalries (Premier League)
        DERBIES = {
            ("Liverpool", "Everton"), ("Everton", "Liverpool"),
            ("Manchester United", "Manchester City"), ("Manchester City", "Manchester United"),
            ("Arsenal", "Tottenham"), ("Tottenham", "Arsenal"),
            ("Chelsea", "Fulham"), ("Fulham", "Chelsea"),
        }
        
        RIVALRIES = {
            ("Liverpool", "Manchester United"), ("Manchester United", "Liverpool"),
            ("Arsenal", "Chelsea"), ("Chelsea", "Arsenal"),
            ("Arsenal", "Manchester United"), ("Manchester United", "Arsenal"),
        }
        
        is_derby = (home.name, away.name) in DERBIES
        is_rivalry = (home.name, away.name) in RIVALRIES
        
        # Six pointer: teams within 6 points and 4 positions
        is_six_pointer = (
            abs(home.league_position - away.league_position) <= 4 and
            abs(home.points - away.points) <= 6
        )
        
        # Pressure: no win in last 4
        def under_pressure(form: str) -> bool:
            return len(form) >= 4 and 'W' not in form[:4]
        
        # Calculate stakes
        def calc_stakes(team: TeamSnapshot) -> str:
            pos = team.league_position
            if pos <= 1:
                return "Defending/chasing title"
            elif pos <= 4:
                return "Champions League qualification"
            elif pos <= 6:
                return "European qualification"
            elif pos <= 10:
                return "Upper mid-table push"
            elif pos <= 14:
                return "Mid-table security"
            elif pos <= 17:
                return "Avoiding relegation battle"
            else:
                return "Relegation fight - must win"
        
        return MatchNarratives(
            fixture_id=fixture_id,
            is_derby=is_derby,
            is_rivalry=is_rivalry,
            is_six_pointer=is_six_pointer,
            home_stakes=calc_stakes(home),
            away_stakes=calc_stakes(away),
            home_under_pressure=under_pressure(home.form_last_5),
            away_under_pressure=under_pressure(away.form_last_5),
        )
    
    # =========================================================
    # COVERAGE
    # =========================================================
    
    def _calculate_coverage(self, *components) -> float:
        """Calculate how complete the context is (0-100)."""
        
        weights = {
            'fixture': 15,
            'home_snapshot': 15,
            'away_snapshot': 15,
            'home_stats': 10,
            'away_stats': 10,
            'home_availability': 10,
            'away_availability': 10,
            'h2h': 10,
            'odds': 5,
        }
        
        score = 0
        
        # Check each component
        fixture, home_snap, away_snap, home_stats, away_stats, \
        home_avail, away_avail, h2h, odds = components
        
        if fixture:
            score += weights['fixture']
        if home_snap and home_snap.played > 0:
            score += weights['home_snapshot']
        if away_snap and away_snap.played > 0:
            score += weights['away_snapshot']
        if home_stats and home_stats.xg_for > 0:
            score += weights['home_stats']
        if away_stats and away_stats.xg_for > 0:
            score += weights['away_stats']
        if home_avail:
            score += weights['home_availability']
        if away_avail:
            score += weights['away_availability']
        if h2h and h2h.matches_analyzed > 0:
            score += weights['h2h']
        if odds:
            score += weights['odds']
        
        return score
    
    # =========================================================
    # LIST FIXTURES
    # =========================================================
    
    def list_fixtures(
        self, 
        round_num: Optional[int] = None,
        status: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict]:
        """List fixtures with optional filters."""
        
        with self._get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT id, date, round, home_team, away_team, home_score, away_score, status FROM fixtures WHERE 1=1"
                params = []
                
                if round_num:
                    query += " AND round = %s"
                    params.append(round_num)
                if status:
                    query += " AND status = %s"
                    params.append(status)
                
                query += " ORDER BY date DESC LIMIT %s"
                params.append(limit)
                
                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
