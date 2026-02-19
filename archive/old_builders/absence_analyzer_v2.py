"""
Absence Analyzer V2 — Enhanced impact calculation.

Improvements:
1. Player goal contribution (% of team goals)
2. Team record WITHOUT the player
3. xG contribution if available
4. Position-specific impact (ST missing vs CB missing = different effect)
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Dict
import psycopg2
from psycopg2.extras import RealDictCursor
import os


@dataclass
class EnhancedAbsence:
    """Absence with full impact analysis."""
    player_name: str
    team_name: str
    position: str
    injury_type: str
    
    # Time out
    out_since: date
    days_out: int
    games_missed: int
    
    # Player contribution (season)
    season_goals: int
    season_assists: int
    team_total_goals: int
    goal_contribution_pct: float  # (goals + assists) / team_goals
    
    # Team WITHOUT this player
    team_record_without: str      # "2W-1D-3L"
    team_ppg_without: float       # Points per game without
    team_ppg_with: float          # Points per game with
    performance_drop: float       # Difference (negative = worse without)
    
    # Impact scores
    base_impact: float            # Position-based (0-10)
    contribution_impact: float    # Goal contribution (0-10)
    absence_impact: float         # How team performs without (0-10)
    final_impact: float           # Weighted combination
    
    # Flags
    team_adapted: bool
    is_top_scorer: bool
    is_key_creator: bool


class AbsenceAnalyzerV2:
    """Enhanced absence analysis with real impact metrics."""
    
    POSITION_WEIGHTS = {
        'Goalkeeper': 7.0, 'GK': 7.0,
        'Centre-Back': 6.0, 'CB': 6.0, 'Defender': 5.5,
        'Left-Back': 5.0, 'Right-Back': 5.0, 'LB': 5.0, 'RB': 5.0,
        'Defensive Midfield': 6.5, 'CDM': 6.5, 'DM': 6.5,
        'Central Midfield': 6.0, 'CM': 6.0, 'Midfield': 5.5,
        'Attacking Midfield': 7.5, 'CAM': 7.5, 'AM': 7.5,
        'Left Winger': 7.0, 'Right Winger': 7.0, 'LW': 7.0, 'RW': 7.0,
        'Centre-Forward': 9.0, 'CF': 9.0, 'Striker': 9.0, 'ST': 9.0,
        'Forward': 8.5,
    }
    
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://joao@localhost:5432/clarity_football"
        )
    
    def _get_conn(self):
        return psycopg2.connect(self.db_url)
    
    def analyze_absences(
        self, 
        team_name: str, 
        match_date: date,
        season: str = "2025-2026"
    ) -> List[EnhancedAbsence]:
        """Get all absences with full impact analysis."""
        
        with self._get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get raw absences
                absences = self._get_raw_absences(cur, team_name, match_date)
                
                # Get team's season data for context
                team_goals = self._get_team_goals(cur, team_name, match_date, season)
                
                # Analyze each absence
                enhanced = []
                for absence in absences:
                    enhanced.append(
                        self._enhance_absence(
                            cur, absence, team_name, match_date, season, team_goals
                        )
                    )
                
                return enhanced
    
    def _get_raw_absences(self, cur, team_name: str, match_date: date) -> List[dict]:
        """Get current injuries from DB."""
        # Search with flexible name matching
        canonical = team_name.replace("'", "").replace("Nott", "Nott%")
        
        cur.execute("""
            SELECT player_name, team_name, position, injury_reason, 
                   from_date, end_date, games_missed
            FROM player_injuries_historical
            WHERE (team_name ILIKE %s OR team_name ILIKE %s)
              AND from_date <= %s
              AND (end_date IS NULL OR end_date >= %s)
        """, (f"%{team_name}%", f"%{canonical}%", match_date, match_date))
        
        return [dict(r) for r in cur.fetchall()]
    
    def _get_team_goals(
        self, cur, team_name: str, before_date: date, season: str
    ) -> int:
        """Get total team goals in season."""
        cur.execute("""
            SELECT 
                SUM(CASE 
                    WHEN home_team ILIKE %s THEN home_score 
                    WHEN away_team ILIKE %s THEN away_score 
                    ELSE 0 
                END) as goals
            FROM fixtures
            WHERE (home_team ILIKE %s OR away_team ILIKE %s)
              AND season = %s
              AND date < %s
              AND status = 'FINISHED'
        """, (f"%{team_name}%", f"%{team_name}%", 
              f"%{team_name}%", f"%{team_name}%",
              season, before_date))
        
        result = cur.fetchone()
        return int(result['goals'] or 0)
    
    def _get_team_record_without_player(
        self, cur, team_name: str, player_out_since: date, before_date: date
    ) -> Dict:
        """Calculate team's record in games WITHOUT the player."""
        
        # Games played while player was out
        cur.execute("""
            SELECT 
                home_team, away_team, home_score, away_score
            FROM fixtures
            WHERE (home_team ILIKE %s OR away_team ILIKE %s)
              AND date >= %s
              AND date < %s
              AND status = 'FINISHED'
        """, (f"%{team_name}%", f"%{team_name}%", player_out_since, before_date))
        
        games = cur.fetchall()
        
        wins = draws = losses = 0
        for g in games:
            is_home = team_name.lower() in g['home_team'].lower()
            team_score = g['home_score'] if is_home else g['away_score']
            opp_score = g['away_score'] if is_home else g['home_score']
            
            if team_score > opp_score:
                wins += 1
            elif team_score == opp_score:
                draws += 1
            else:
                losses += 1
        
        total = wins + draws + losses
        ppg = (wins * 3 + draws) / total if total > 0 else 0
        
        return {
            'record': f"{wins}W-{draws}D-{losses}L",
            'games': total,
            'ppg': round(ppg, 2)
        }
    
    def _get_team_record_with_player(
        self, cur, team_name: str, player_out_since: date, season: str
    ) -> Dict:
        """Calculate team's record in games WITH the player (before injury)."""
        
        cur.execute("""
            SELECT 
                home_team, away_team, home_score, away_score
            FROM fixtures
            WHERE (home_team ILIKE %s OR away_team ILIKE %s)
              AND season = %s
              AND date < %s
              AND status = 'FINISHED'
        """, (f"%{team_name}%", f"%{team_name}%", season, player_out_since))
        
        games = cur.fetchall()
        
        wins = draws = losses = 0
        for g in games:
            is_home = team_name.lower() in g['home_team'].lower()
            team_score = g['home_score'] if is_home else g['away_score']
            opp_score = g['away_score'] if is_home else g['home_score']
            
            if team_score > opp_score:
                wins += 1
            elif team_score == opp_score:
                draws += 1
            else:
                losses += 1
        
        total = wins + draws + losses
        ppg = (wins * 3 + draws) / total if total > 0 else 0
        
        return {
            'record': f"{wins}W-{draws}D-{losses}L",
            'games': total,
            'ppg': round(ppg, 2)
        }
    
    def _enhance_absence(
        self, cur, absence: dict, team_name: str, 
        match_date: date, season: str, team_goals: int
    ) -> EnhancedAbsence:
        """Add full impact analysis to an absence."""
        
        player_name = absence['player_name']
        position = absence['position'] or 'Unknown'
        out_since = absence['from_date']
        days_out = (match_date - out_since).days
        games_missed = absence['games_missed'] or 0
        
        # Get team record WITH and WITHOUT player
        record_without = self._get_team_record_without_player(
            cur, team_name, out_since, match_date
        )
        record_with = self._get_team_record_with_player(
            cur, team_name, out_since, season
        )
        
        performance_drop = record_with['ppg'] - record_without['ppg']
        
        # Estimate player goals (we don't have individual stats, so estimate by position)
        # For a proper system, we'd have player_stats table
        estimated_goals = self._estimate_player_goals(position, team_goals, games_missed)
        estimated_assists = estimated_goals // 2
        
        goal_contribution = (estimated_goals + estimated_assists) / max(team_goals, 1)
        
        # Calculate impact scores
        base_impact = self.POSITION_WEIGHTS.get(position, 5.0)
        
        # Contribution impact (strikers with high % = higher impact)
        contribution_impact = min(10, goal_contribution * 30)  # Scale 0-30% to 0-10
        
        # Absence impact (how much worse is team without player)
        absence_impact = min(10, max(0, performance_drop * 5))  # Scale PPG drop to 0-10
        
        # Team adapted?
        team_adapted = games_missed >= 3
        adaptation_factor = 0.4 if team_adapted else 1.0
        
        # Final weighted impact
        final_impact = (
            base_impact * 0.3 +
            contribution_impact * 0.4 +
            absence_impact * 0.3
        ) * adaptation_factor
        
        return EnhancedAbsence(
            player_name=player_name,
            team_name=team_name,
            position=position,
            injury_type=absence['injury_reason'] or 'Unknown',
            out_since=out_since,
            days_out=days_out,
            games_missed=games_missed,
            season_goals=estimated_goals,
            season_assists=estimated_assists,
            team_total_goals=team_goals,
            goal_contribution_pct=round(goal_contribution * 100, 1),
            team_record_without=record_without['record'],
            team_ppg_without=record_without['ppg'],
            team_ppg_with=record_with['ppg'],
            performance_drop=round(performance_drop, 2),
            base_impact=base_impact,
            contribution_impact=round(contribution_impact, 1),
            absence_impact=round(absence_impact, 1),
            final_impact=round(final_impact, 1),
            team_adapted=team_adapted,
            is_top_scorer=position in ['ST', 'CF', 'Striker', 'Centre-Forward'] and contribution_impact > 5,
            is_key_creator=position in ['CAM', 'AM', 'Attacking Midfield'] and contribution_impact > 4
        )
    
    def _estimate_player_goals(
        self, position: str, team_goals: int, games_missed: int
    ) -> int:
        """Estimate player goals based on position (fallback if no player stats)."""
        # Rough estimation based on typical distribution
        position_goal_share = {
            'ST': 0.35, 'CF': 0.35, 'Striker': 0.35, 'Centre-Forward': 0.35,
            'LW': 0.15, 'RW': 0.15, 'Winger': 0.15,
            'CAM': 0.12, 'AM': 0.12, 'Attacking Midfield': 0.12,
            'CM': 0.05, 'Central Midfield': 0.05,
        }
        share = position_goal_share.get(position, 0.03)
        return int(team_goals * share)
    
    def summarize(self, absences: List[EnhancedAbsence]) -> dict:
        """Create impact summary."""
        if not absences:
            return {
                'total_missing': 0,
                'total_impact': 0,
                'key_missing': [],
                'verdict': 'No significant absences'
            }
        
        total_impact = sum(a.final_impact for a in absences)
        key_missing = [a for a in absences if a.final_impact > 3]
        
        # Generate verdict
        if total_impact > 15:
            verdict = "CRITICAL: Major absences severely weaken the team"
        elif total_impact > 8:
            verdict = "SIGNIFICANT: Key players missing will impact performance"
        elif total_impact > 4:
            verdict = "MODERATE: Some impact but team should cope"
        else:
            verdict = "MINOR: Absences unlikely to affect result"
        
        return {
            'total_missing': len(absences),
            'total_impact': round(total_impact, 1),
            'key_missing': [
                {'name': a.player_name, 'impact': a.final_impact, 'reason': a.injury_type}
                for a in key_missing
            ],
            'adapted_count': sum(1 for a in absences if a.team_adapted),
            'verdict': verdict
        }


if __name__ == "__main__":
    from datetime import date
    
    analyzer = AbsenceAnalyzerV2()
    
    match_date = date(2026, 2, 6)
    absences = analyzer.analyze_absences("Nottingham Forest", match_date)
    
    print(f"\n{'='*60}")
    print(f"ENHANCED ABSENCE ANALYSIS: Nottingham Forest")
    print(f"{'='*60}\n")
    
    for a in absences:
        print(f"🔴 {a.player_name} ({a.position})")
        print(f"   Injury: {a.injury_type}")
        print(f"   Out: {a.days_out} days, {a.games_missed} games")
        print(f"   Team WITHOUT: {a.team_record_without} ({a.team_ppg_without} PPG)")
        print(f"   Team WITH: {a.team_ppg_with} PPG → Drop: {a.performance_drop}")
        print(f"   Goal contribution: ~{a.goal_contribution_pct}%")
        print(f"   Impact: base={a.base_impact} contrib={a.contribution_impact} absence={a.absence_impact}")
        print(f"   → FINAL: {a.final_impact} {'(adapted)' if a.team_adapted else '(FRESH)'}")
        print()
    
    summary = analyzer.summarize(absences)
    print(f"{'='*60}")
    print(f"VERDICT: {summary['verdict']}")
    print(f"Total Impact: {summary['total_impact']}")
