"""
Absence Analyzer — Contextualizes injuries and suspensions.

Key insight from reverse engineering:
If a player has been out for 3+ games, the team has already adapted.
The recent results ALREADY reflect the absence, so the "real impact" is lower.
"""

import sys
from pathlib import Path
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection


@dataclass
class AbsenceRecord:
    """Raw absence data from database."""
    player_name: str
    position: str
    injury_type: Optional[str]
    out_since: date
    expected_return: Optional[date]


@dataclass
class ContextualizedAbsence:
    """Absence with adaptation context."""
    player_name: str
    position: str
    injury_type: Optional[str]
    out_since: date
    expected_return: Optional[date]
    
    # Calculated fields
    days_out: int
    games_missed: int
    team_adapted: bool
    
    # Impact
    base_impact: float      # 0-10, player importance
    real_impact: float      # Adjusted for adaptation
    
    # Context
    is_key_player: bool
    is_captain: bool
    likely_replacement: Optional[str]


class AbsenceAnalyzer:
    """Analyzes absences with adaptation context."""
    
    # Position importance weights
    POSITION_WEIGHTS = {
        'GK': 8.0,      # Goalkeeper very important
        'CB': 6.0,
        'LB': 5.0, 'RB': 5.0,
        'CDM': 6.5, 'CM': 6.0, 'CAM': 7.0,
        'LW': 7.0, 'RW': 7.0,
        'LM': 5.5, 'RM': 5.5,
        'CF': 8.0, 'ST': 8.5,  # Strikers crucial
        'MF': 5.5,      # Generic midfielder
    }
    
    def __init__(self):
        self.conn = get_connection()
    
    def get_team_absences(
        self, 
        team_name: str, 
        match_date: date,
        team_fixtures: List[dict] = None
    ) -> List[ContextualizedAbsence]:
        """
        Get all absences for a team with adaptation context.
        
        Args:
            team_name: The team name
            match_date: The date of the upcoming match
            team_fixtures: Recent fixtures to calculate games missed
        """
        # Get raw absences from DB
        raw_absences = self._get_raw_absences(team_name, match_date)
        
        # Get recent fixtures to count games missed
        if team_fixtures is None:
            team_fixtures = self._get_recent_fixtures(team_name, match_date, limit=10)
        
        # Contextualize each absence
        contextualized = []
        for absence in raw_absences:
            ctx = self._contextualize_absence(absence, match_date, team_fixtures)
            contextualized.append(ctx)
        
        return contextualized
    
    def _get_raw_absences(self, team_name: str, match_date: date) -> List[AbsenceRecord]:
        """Get current absences from database."""
        cur = self.conn.cursor()
        
        # Query injuries that are still active (no end_date or end_date > match_date)
        cur.execute("""
            SELECT player_name, position, injury_reason, from_date, end_date
            FROM player_injuries_historical
            WHERE team_name ILIKE %s
              AND from_date <= %s
              AND (end_date IS NULL OR end_date >= %s)
            ORDER BY from_date DESC
        """, (f"%{team_name}%", match_date, match_date))
        
        rows = cur.fetchall()
        cur.close()
        
        absences = []
        for row in rows:
            absences.append(AbsenceRecord(
                player_name=row[0],
                position=row[1] or 'MF',
                injury_type=row[2],
                out_since=row[3],
                expected_return=row[4]
            ))
        
        return absences
    
    def _get_recent_fixtures(
        self, 
        team_name: str, 
        before_date: date, 
        limit: int = 10
    ) -> List[dict]:
        """Get recent completed fixtures for the team."""
        cur = self.conn.cursor()
        
        # Handle team name variations (e.g., "Nottingham Forest" vs "Nott'ham Forest")
        team_pattern = team_name.replace("Nottingham", "Nott%").replace("'", "%")
        
        cur.execute("""
            SELECT id, date, home_team, away_team, home_score, away_score
            FROM fixtures
            WHERE (home_team ILIKE %s OR away_team ILIKE %s)
              AND date < %s
              AND status = 'FINISHED'
            ORDER BY date DESC
            LIMIT %s
        """, (f"%{team_pattern}%", f"%{team_pattern}%", before_date, limit))
        
        rows = cur.fetchall()
        cur.close()
        
        fixtures = []
        for row in rows:
            fixtures.append({
                'id': row[0],
                'date': row[1],
                'home_team': row[2],
                'away_team': row[3],
                'home_score': row[4],
                'away_score': row[5]
            })
        
        return fixtures
    
    def _contextualize_absence(
        self,
        absence: AbsenceRecord,
        match_date: date,
        team_fixtures: List[dict]
    ) -> ContextualizedAbsence:
        """Add adaptation context to an absence."""
        
        # Calculate days out
        days_out = (match_date - absence.out_since).days
        
        # Calculate games missed
        games_missed = sum(
            1 for f in team_fixtures 
            if f['date'] >= absence.out_since and f['date'] < match_date
        )
        
        # Determine if team has adapted
        team_adapted = games_missed >= 3
        
        # Get base impact from position
        base_impact = self.POSITION_WEIGHTS.get(absence.position, 5.0)
        
        # Calculate real impact with adaptation discount
        real_impact = self._calculate_real_impact(base_impact, games_missed)
        
        # Determine if key player (high base impact)
        is_key_player = base_impact >= 7.0
        
        return ContextualizedAbsence(
            player_name=absence.player_name,
            position=absence.position,
            injury_type=absence.injury_type,
            out_since=absence.out_since,
            expected_return=absence.expected_return,
            days_out=days_out,
            games_missed=games_missed,
            team_adapted=team_adapted,
            base_impact=base_impact,
            real_impact=real_impact,
            is_key_player=is_key_player,
            is_captain=False,  # TODO: Get from player data
            likely_replacement=None  # TODO: Infer from lineups
        )
    
    def _calculate_real_impact(self, base_impact: float, games_missed: int) -> float:
        """
        Calculate real impact adjusted for team adaptation.
        
        Key insight:
        - 0 games missed: Full impact (100%)
        - 1-2 games missed: High impact (70%)
        - 3-4 games missed: Medium impact (30%)
        - 5+ games missed: Low impact (10%)
        """
        if games_missed >= 5:
            return base_impact * 0.1
        elif games_missed >= 3:
            return base_impact * 0.3
        elif games_missed >= 1:
            return base_impact * 0.7
        else:
            return base_impact
    
    def summarize_absences(
        self, 
        absences: List[ContextualizedAbsence]
    ) -> dict:
        """Create a summary of all absences."""
        
        total_base_impact = sum(a.base_impact for a in absences)
        total_real_impact = sum(a.real_impact for a in absences)
        
        fresh_absences = [a for a in absences if not a.team_adapted]
        adapted_absences = [a for a in absences if a.team_adapted]
        
        return {
            'total_missing': len(absences),
            'total_base_impact': round(total_base_impact, 1),
            'total_real_impact': round(total_real_impact, 1),
            'adaptation_discount': round(total_base_impact - total_real_impact, 1),
            'fresh_absences': len(fresh_absences),
            'adapted_absences': len(adapted_absences),
            'key_players_missing': sum(1 for a in absences if a.is_key_player),
            'positions_affected': list(set(a.position for a in absences)),
            'most_impactful': max(absences, key=lambda a: a.real_impact).player_name if absences else None
        }
    
    def close(self):
        if self.conn:
            self.conn.close()


# ============================================================
# CLI for testing
# ============================================================

if __name__ == "__main__":
    from datetime import date
    
    analyzer = AbsenceAnalyzer()
    
    # Test with Nottingham Forest for Leeds match
    match_date = date(2026, 2, 6)
    absences = analyzer.get_team_absences("Nottingham Forest", match_date)
    
    print(f"\n{'='*60}")
    print(f"ABSENCES: Nottingham Forest (as of {match_date})")
    print(f"{'='*60}\n")
    
    for a in absences:
        adapted_str = "✅ ADAPTED" if a.team_adapted else "⚠️ FRESH"
        print(f"{a.player_name} ({a.position})")
        print(f"  Out since: {a.out_since} ({a.days_out} days)")
        print(f"  Games missed: {a.games_missed} → {adapted_str}")
        print(f"  Impact: {a.base_impact:.1f} base → {a.real_impact:.1f} real")
        print()
    
    summary = analyzer.summarize_absences(absences)
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total missing: {summary['total_missing']}")
    print(f"Base impact: {summary['total_base_impact']}")
    print(f"Real impact: {summary['total_real_impact']} (discount: {summary['adaptation_discount']})")
    print(f"Fresh absences: {summary['fresh_absences']}")
    print(f"Team adapted to: {summary['adapted_absences']}")
    
    analyzer.close()
