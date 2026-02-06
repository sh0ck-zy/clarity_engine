"""
Enhanced Match Context Builder - Phase 1 (P1-003)

Builds deterministic match context using the strict schema.
Integrates both live data (fixtures/team_stats) and historical data
(fixtures_historical/match_features) where available.

Usage:
    from src.analysis.context_builder_v2 import ContextBuilderV2

    builder = ContextBuilderV2()
    context = builder.build_context(fixture_id)
    is_valid, errors = validate_context(context)
"""

import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Optional, List, Tuple, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.analysis.context_schema import (
    MatchContext, TeamContext, TeamIdentity, TeamForm, TeamAbsences,
    PlayerAbsence, HeadToHead, MarketOdds, ScheduleContext, LeaguePosition,
    TeamLineup, PlayerLineupInfo,
    validate_context, calculate_coverage_score,
    empty_team_identity, empty_team_form, empty_team_absences, empty_team_lineup,
    empty_head_to_head, empty_schedule_context, empty_league_position, empty_market_odds
)


class ContextBuilderV2:
    """
    Enhanced context builder that:
    1. Uses strict schema for all outputs
    2. Integrates injury/lineup data when available
    3. Tracks data coverage and quality
    4. Enforces time-travel safety
    """

    def __init__(self):
        self.conn = get_connection()
        self._missing_fields: List[str] = []
        self._warnings: List[str] = []

    def close(self):
        if self.conn:
            self.conn.close()

    def build_context(self, fixture_id: str) -> Optional[MatchContext]:
        """
        Build complete match context for a fixture.

        Args:
            fixture_id: Fixture ID (e.g., "2024-08-17_Arsenal_Wolves")

        Returns:
            MatchContext with all available data, or None if fixture not found
        """
        if not self.conn:
            return None

        self._missing_fields = []
        self._warnings = []

        # Get match details
        match = self._get_match_details(fixture_id)
        if match is None:
            return None

        match_date = match['date']
        season = match['season']
        league = match.get('league', 'Premier League')
        round_num = match.get('round')

        # Build team contexts
        home_context = self._build_team_context(
            fixture_id=fixture_id,
            team_name=match['home_team'],
            match_date=match_date,
            season=season,
            is_home=True
        )

        away_context = self._build_team_context(
            fixture_id=fixture_id,
            team_name=match['away_team'],
            match_date=match_date,
            season=season,
            is_home=False
        )

        # Build comparative contexts
        h2h = self._build_head_to_head(
            home_team=match['home_team'],
            away_team=match['away_team'],
            match_date=match_date
        )

        schedule = self._build_schedule_context(
            home_team=match['home_team'],
            away_team=match['away_team'],
            match_date=match_date
        )

        league_pos = self._build_league_position(
            home_team=match['home_team'],
            away_team=match['away_team'],
            match_date=match_date,
            season=season
        )

        odds = self._get_odds(fixture_id, match_date)

        # Create context object
        context = MatchContext(
            fixture_id=fixture_id,
            match_date=match_date if isinstance(match_date, date) else match_date.date(),
            season=season,
            league=league,
            round_number=round_num,
            home=home_context,
            away=away_context,
            head_to_head=h2h,
            schedule=schedule,
            league_position=league_pos,
            odds=odds,
            coverage_score=0.0,  # Will be calculated
            missing_fields=self._missing_fields.copy(),
            data_warnings=self._warnings.copy()
        )

        # Calculate coverage score
        context.coverage_score = calculate_coverage_score(context)

        return context

    # ============================================================
    # MATCH DETAILS
    # ============================================================

    def _get_match_details(self, fixture_id: str) -> Optional[pd.Series]:
        """Get basic match details from fixtures table."""
        df = pd.read_sql(
            "SELECT * FROM fixtures WHERE id = %s",
            self.conn, params=(fixture_id,)
        )
        if df.empty:
            return None
        return df.iloc[0]

    # ============================================================
    # TEAM CONTEXT
    # ============================================================

    def _build_team_context(
        self,
        fixture_id: str,
        team_name: str,
        match_date: datetime,
        season: str,
        is_home: bool
    ) -> TeamContext:
        """Build complete context for one team."""

        identity = self._build_team_identity(team_name, match_date, season)
        form = self._build_team_form(team_name, match_date)
        absences = self._build_team_absences(team_name, match_date, season)
        lineup = self._build_team_lineup(fixture_id, team_name, is_home)

        return TeamContext(
            identity=identity,
            form=form,
            absences=absences,
            lineup=lineup,
            is_home=is_home
        )

    def _build_team_identity(
        self,
        team_name: str,
        match_date: datetime,
        season: str
    ) -> TeamIdentity:
        """Build season-long identity metrics."""

        # Get season averages from team_stats
        sql = """
            SELECT
                AVG(ts.ppda) as ppda,
                AVG(ts.field_tilt) as field_tilt,
                AVG(ts.xg) as xg,
                AVG(ts.xga) as xga
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s
              AND f.season = %s
              AND f.date < %s
        """
        ident_df = pd.read_sql(sql, self.conn, params=(team_name, season, match_date))

        # Get current Elo
        sql_elo = """
            SELECT elo FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            WHERE ts.team_name = %s AND f.date < %s
            ORDER BY f.date DESC LIMIT 1
        """
        elo_df = pd.read_sql(sql_elo, self.conn, params=(team_name, match_date))
        elo = int(elo_df.iloc[0]['elo']) if not elo_df.empty and pd.notna(elo_df.iloc[0]['elo']) else 1500

        if ident_df.empty or pd.isna(ident_df.iloc[0]['xg']):
            self._missing_fields.append(f"{team_name}.identity.season_stats")
            return empty_team_identity(team_name)

        row = ident_df.iloc[0]
        xg = float(row['xg']) if pd.notna(row['xg']) else 0.0
        xga = float(row['xga']) if pd.notna(row['xga']) else 0.0

        return TeamIdentity(
            name=team_name,
            elo=elo,
            season_xg_per_match=round(xg, 2),
            season_xga_per_match=round(xga, 2),
            season_xg_diff=round(xg - xga, 2),
            season_ppda=round(float(row['ppda']) if pd.notna(row['ppda']) else 10.0, 1),
            season_field_tilt=round(float(row['field_tilt']) if pd.notna(row['field_tilt']) else 50.0, 1)
        )

    def _build_team_form(self, team_name: str, match_date: datetime) -> TeamForm:
        """Build last 5 matches form (time-travel safe)."""

        sql = """
            SELECT
                f.date, ts.xg, ts.xga, ts.ppda, ts.field_tilt,
                f.home_score, f.away_score, ts.is_home,
                ts_opp.elo as opponent_elo
            FROM team_stats ts
            JOIN fixtures f ON ts.fixture_id = f.id
            LEFT JOIN team_stats ts_opp ON f.id = ts_opp.fixture_id AND ts_opp.team_name != ts.team_name
            WHERE ts.team_name = %s
              AND f.date < %s
              AND f.status = 'FINISHED'
            ORDER BY f.date DESC
            LIMIT 5
        """
        form_df = pd.read_sql(sql, self.conn, params=(team_name, match_date))

        if form_df.empty:
            self._missing_fields.append(f"{team_name}.form")
            return empty_team_form()

        # Calculate form metrics
        results = []
        points = 0
        goals_for = 0
        goals_against = 0
        xg_total = 0.0
        xga_total = 0.0
        clean_sheets = 0
        failed_to_score = 0

        for _, row in form_df.iterrows():
            my_score = row['home_score'] if row['is_home'] else row['away_score']
            opp_score = row['away_score'] if row['is_home'] else row['home_score']

            if pd.notna(my_score) and pd.notna(opp_score):
                my_score = int(my_score)
                opp_score = int(opp_score)

                goals_for += my_score
                goals_against += opp_score

                if my_score > opp_score:
                    results.append("W")
                    points += 3
                elif my_score == opp_score:
                    results.append("D")
                    points += 1
                else:
                    results.append("L")

                if opp_score == 0:
                    clean_sheets += 1
                if my_score == 0:
                    failed_to_score += 1

            if pd.notna(row['xg']):
                xg_total += float(row['xg'])
            if pd.notna(row['xga']):
                xga_total += float(row['xga'])

        # Calculate days rest
        days_rest = 7
        if not form_df.empty and pd.notna(form_df.iloc[0]['date']):
            last_match = form_df.iloc[0]['date']
            if isinstance(last_match, str):
                last_match = pd.to_datetime(last_match)

            # Convert to date objects to avoid time/timezone issues
            last_match_date = last_match.date() if hasattr(last_match, 'date') else last_match
            match_date_d = match_date.date() if isinstance(match_date, datetime) else match_date

            days_rest = (match_date_d - last_match_date).days

        # Opponent Elo average
        opp_elo_vals = form_df['opponent_elo'].dropna()
        opponent_avg_elo = int(opp_elo_vals.mean()) if len(opp_elo_vals) > 0 else 1500

        return TeamForm(
            results="-".join(results),
            points=points,
            goals_for=goals_for,
            goals_against=goals_against,
            xg_total=round(xg_total, 2),
            xga_total=round(xga_total, 2),
            xg_diff=round(xg_total - xga_total, 2),
            clean_sheets=clean_sheets,
            failed_to_score=failed_to_score,
            opponent_avg_elo=opponent_avg_elo,
            days_rest=max(0, days_rest)
        )

    def _build_team_absences(
        self,
        team_name: str,
        match_date: datetime,
        season: str
    ) -> TeamAbsences:
        """
        Build injury/suspension context from Transfermarkt data.

        Uses player_injuries_historical table populated by the
        Transfermarkt scraper.
        """
        absences = empty_team_absences()
        players = []

        try:
            # Query injuries for this team that are active on match date
            sql = """
                SELECT
                    player_id,
                    player_name,
                    injury_reason,
                    from_date,
                    end_date,
                    days_missed,
                    games_missed
                FROM player_injuries_historical
                WHERE team_name = %s
                  AND from_date <= %s
                  AND (end_date IS NULL OR end_date > %s)
                ORDER BY from_date DESC
            """
            df = pd.read_sql(sql, self.conn, params=(team_name, match_date, match_date))

            if df.empty:
                return absences

            # Build player absences
            attackers = 0
            defenders = 0

            for _, row in df.iterrows():
                injury_type = row['injury_reason'] if pd.notna(row['injury_reason']) else "Unknown"

                # Use actual position from DB, with fallback to midfielder
                position = row.get('position', 'MF') if pd.notna(row.get('position')) else 'MF'

                player_absence = PlayerAbsence(
                    player_name=row['player_name'] or f"Player {row['player_id']}",
                    position=position,
                    reason="injury",
                    injury_type=injury_type,
                    impact_rating=None,  # Would need player stats to calculate
                    xg_per90=None,
                    xa_per90=None
                )
                players.append(player_absence)

            absences = TeamAbsences(
                total_missing=len(players),
                key_attackers_missing=attackers,
                key_defenders_missing=defenders,
                total_offensive_impact=0.0,  # Would need player stats
                total_defensive_impact=0.0,
                players=players
            )

        except Exception as e:
            self._warnings.append(f"Could not fetch injury data for {team_name}: {str(e)}")

        return absences

    # ============================================================
    # LINEUP
    # ============================================================

    def _build_team_lineup(
        self,
        fixture_id: str,
        team_name: str,
        is_home: bool
    ) -> Optional[TeamLineup]:
        """
        Build lineup context from lineups_historical table.

        For historical matches, this returns the actual lineup used.
        For future matches, this would return predicted/expected lineup.
        """
        try:
            sql = """
                SELECT formation, starters, bench, source
                FROM lineups_historical
                WHERE fixture_id = %s AND is_home = %s
                LIMIT 1
            """
            df = pd.read_sql(sql, self.conn, params=(fixture_id, is_home))

            if df.empty:
                return None

            row = df.iloc[0]

            # Parse starters and bench from JSONB
            starters_data = row['starters'] if isinstance(row['starters'], list) else []
            bench_data = row['bench'] if isinstance(row['bench'], list) else []

            starters = [
                PlayerLineupInfo(
                    player_id=p.get('player_id', ''),
                    player_name=p.get('player_name', 'Unknown'),
                    position=p.get('position', ''),
                    shirt_number=p.get('shirt_number')
                )
                for p in starters_data
            ]

            bench = [
                PlayerLineupInfo(
                    player_id=p.get('player_id', ''),
                    player_name=p.get('player_name', 'Unknown'),
                    position=p.get('position', ''),
                    shirt_number=p.get('shirt_number')
                )
                for p in bench_data
            ]

            return TeamLineup(
                formation=row['formation'],
                starters=starters,
                bench=bench,
                source=row.get('source', 'transfermarkt'),
                is_confirmed=True  # Historical data is confirmed
            )

        except Exception as e:
            self._warnings.append(f"Could not fetch lineup for {team_name}: {str(e)}")
            return None

    # ============================================================
    # HEAD TO HEAD
    # ============================================================

    def _build_head_to_head(
        self,
        home_team: str,
        away_team: str,
        match_date: datetime,
        limit: int = 5
    ) -> HeadToHead:
        """Get historical H2H record (time-travel safe)."""

        sql = """
            SELECT home_team, away_team, home_score, away_score
            FROM fixtures
            WHERE ((home_team = %s AND away_team = %s) OR (home_team = %s AND away_team = %s))
              AND date < %s
              AND status = 'FINISHED'
            ORDER BY date DESC
            LIMIT %s
        """
        h2h_df = pd.read_sql(
            sql, self.conn,
            params=(home_team, away_team, away_team, home_team, match_date, limit)
        )

        if h2h_df.empty:
            return empty_head_to_head()

        home_wins = 0
        draws = 0
        away_wins = 0
        total_home_goals = 0
        total_away_goals = 0

        for _, row in h2h_df.iterrows():
            if row['home_team'] == home_team:
                h_goals = int(row['home_score'])
                a_goals = int(row['away_score'])
            else:
                h_goals = int(row['away_score'])
                a_goals = int(row['home_score'])

            total_home_goals += h_goals
            total_away_goals += a_goals

            if h_goals > a_goals:
                home_wins += 1
            elif h_goals < a_goals:
                away_wins += 1
            else:
                draws += 1

        n = len(h2h_df)
        return HeadToHead(
            home_wins=home_wins,
            draws=draws,
            away_wins=away_wins,
            avg_total_goals=round((total_home_goals + total_away_goals) / n, 2) if n > 0 else 0.0,
            home_avg_goals=round(total_home_goals / n, 2) if n > 0 else 0.0,
            away_avg_goals=round(total_away_goals / n, 2) if n > 0 else 0.0,
            matches_played=n
        )

    # ============================================================
    # SCHEDULE CONTEXT
    # ============================================================

    def _build_schedule_context(
        self,
        home_team: str,
        away_team: str,
        match_date: datetime
    ) -> ScheduleContext:
        """Calculate rest days and fixture congestion."""

        def get_team_schedule(team: str) -> Tuple[int, int, int]:
            """Returns (rest_days, matches_7d, matches_14d)"""
            sql = """
                SELECT date FROM fixtures
                WHERE (home_team = %s OR away_team = %s)
                  AND date < %s
                  AND status = 'FINISHED'
                ORDER BY date DESC
                LIMIT 10
            """
            df = pd.read_sql(sql, self.conn, params=(team, team, match_date))

            if df.empty:
                return 7, 1, 2

            # Rest days
            last_match = pd.to_datetime(df.iloc[0]['date']).date()
            if isinstance(match_date, datetime):
                match_date_d = match_date.date()
            else:
                match_date_d = match_date
            rest_days = (match_date_d - last_match).days

            # Matches in windows
            cutoff_7d = pd.Timestamp(match_date_d - timedelta(days=7))
            cutoff_14d = pd.Timestamp(match_date_d - timedelta(days=14))

            df['date'] = pd.to_datetime(df['date'])
            matches_7d = len(df[df['date'] >= cutoff_7d])
            matches_14d = len(df[df['date'] >= cutoff_14d])

            return max(0, rest_days), matches_7d, matches_14d

        home_rest, home_7d, home_14d = get_team_schedule(home_team)
        away_rest, away_7d, away_14d = get_team_schedule(away_team)

        return ScheduleContext(
            home_rest_days=home_rest,
            away_rest_days=away_rest,
            home_matches_last_7d=home_7d,
            away_matches_last_7d=away_7d,
            home_matches_last_14d=home_14d,
            away_matches_last_14d=away_14d,
            is_home_congested=home_7d > 2,
            is_away_congested=away_7d > 2
        )

    # ============================================================
    # LEAGUE POSITION
    # ============================================================

    def _build_league_position(
        self,
        home_team: str,
        away_team: str,
        match_date: datetime,
        season: str
    ) -> LeaguePosition:
        """Calculate league position before match (time-travel safe)."""

        sql = """
            WITH team_results AS (
                SELECT
                    home_team as team,
                    CASE
                        WHEN home_score > away_score THEN 3
                        WHEN home_score = away_score THEN 1
                        ELSE 0
                    END as points,
                    home_score as gf,
                    away_score as ga
                FROM fixtures
                WHERE season = %s AND date < %s AND status = 'FINISHED'

                UNION ALL

                SELECT
                    away_team as team,
                    CASE
                        WHEN away_score > home_score THEN 3
                        WHEN away_score = home_score THEN 1
                        ELSE 0
                    END as points,
                    away_score as gf,
                    home_score as ga
                FROM fixtures
                WHERE season = %s AND date < %s AND status = 'FINISHED'
            ),
            standings AS (
                SELECT
                    team,
                    SUM(points) as points,
                    SUM(gf) - SUM(ga) as goal_diff,
                    ROW_NUMBER() OVER (ORDER BY SUM(points) DESC, SUM(gf) - SUM(ga) DESC, SUM(gf) DESC) as position
                FROM team_results
                GROUP BY team
            )
            SELECT team, points, goal_diff, position
            FROM standings
            WHERE team IN (%s, %s)
        """
        df = pd.read_sql(
            sql, self.conn,
            params=(season, match_date, season, match_date, home_team, away_team)
        )

        if df.empty:
            return empty_league_position()

        home_row = df[df['team'] == home_team]
        away_row = df[df['team'] == away_team]

        return LeaguePosition(
            home_position=int(home_row.iloc[0]['position']) if not home_row.empty else 10,
            away_position=int(away_row.iloc[0]['position']) if not away_row.empty else 10,
            home_points=int(home_row.iloc[0]['points']) if not home_row.empty else 0,
            away_points=int(away_row.iloc[0]['points']) if not away_row.empty else 0,
            home_goal_diff=int(home_row.iloc[0]['goal_diff']) if not home_row.empty else 0,
            away_goal_diff=int(away_row.iloc[0]['goal_diff']) if not away_row.empty else 0
        )

    # ============================================================
    # ODDS
    # ============================================================

    def _get_odds(self, fixture_id: str, match_date: datetime) -> MarketOdds:
        """Get pre-match odds (time-travel safe)."""

        # Try market_odds table first
        sql = "SELECT home_win, draw, away_win, provider FROM market_odds WHERE fixture_id = %s"
        df = pd.read_sql(sql, self.conn, params=(fixture_id,))

        if not df.empty:
            row = df.iloc[0]
            return MarketOdds(
                home_win=float(row['home_win']) if pd.notna(row['home_win']) else None,
                draw=float(row['draw']) if pd.notna(row['draw']) else None,
                away_win=float(row['away_win']) if pd.notna(row['away_win']) else None,
                source=row.get('provider', 'unknown')
            )

        # Try odds_snapshots table (from historical data)
        try:
            sql_snap = """
                SELECT selection_key, odds_decimal, captured_at, source
                FROM odds_snapshots
                WHERE fixture_id = %s
                  AND market_key = '1X2'
                  AND captured_at < %s
                ORDER BY captured_at DESC
            """
            snap_df = pd.read_sql(sql_snap, self.conn, params=(fixture_id, match_date))

            if not snap_df.empty:
                # Aggregate by selection
                odds = empty_market_odds()
                for _, row in snap_df.iterrows():
                    sel = row['selection_key']
                    val = float(row['odds_decimal'])
                    if sel == 'HOME' and odds.home_win is None:
                        odds.home_win = val
                    elif sel == 'DRAW' and odds.draw is None:
                        odds.draw = val
                    elif sel == 'AWAY' and odds.away_win is None:
                        odds.away_win = val

                    if odds.source == "unknown":
                        odds.source = row.get('source', 'odds_snapshot')
                    if odds.captured_at is None and pd.notna(row['captured_at']):
                        odds.captured_at = row['captured_at']
                return odds
        except Exception:
            # Table might not exist yet
            pass

        self._missing_fields.append("odds")
        return empty_market_odds()


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def build_match_context(fixture_id: str) -> Optional[MatchContext]:
    """
    Build match context for a fixture.

    Args:
        fixture_id: Fixture ID

    Returns:
        MatchContext or None if not found
    """
    builder = ContextBuilderV2()
    try:
        return builder.build_context(fixture_id)
    finally:
        builder.close()


def validate_and_build(fixture_id: str) -> Tuple[Optional[MatchContext], bool, List[str]]:
    """
    Build and validate context in one call.

    Returns:
        (context, is_valid, errors)
    """
    context = build_match_context(fixture_id)
    if context is None:
        return None, False, ["Fixture not found"]

    is_valid, errors = validate_context(context)
    return context, is_valid, errors


if __name__ == "__main__":
    print("Testing ContextBuilderV2...")

    builder = ContextBuilderV2()

    # Get a sample fixture
    conn = get_connection()
    if conn:
        df = pd.read_sql(
            "SELECT id FROM fixtures WHERE status = 'FINISHED' ORDER BY date DESC LIMIT 1",
            conn
        )
        conn.close()

        if not df.empty:
            fixture_id = df.iloc[0]['id']
            print(f"\nBuilding context for: {fixture_id}")

            context = builder.build_context(fixture_id)
            if context:
                print(f"\n✅ Context built successfully!")
                print(f"   Coverage Score: {context.coverage_score}%")
                print(f"   Home: {context.home.identity.name} (Elo: {context.home.identity.elo})")
                print(f"   Away: {context.away.identity.name} (Elo: {context.away.identity.elo})")
                print(f"   Home Form: {context.home.form.results}")
                print(f"   Away Form: {context.away.form.results}")

                is_valid, errors = validate_context(context)
                print(f"\n   Valid: {is_valid}")
                if errors:
                    print(f"   Errors: {errors}")
            else:
                print("❌ Failed to build context")

    builder.close()
