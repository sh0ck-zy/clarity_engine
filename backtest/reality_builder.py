"""
Reality Builder - Generate rich match reports from actual results.

This creates the "ground truth" we compare agent analyses against.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.database.config import get_connection


@dataclass
class MatchReality:
    """Rich representation of what actually happened."""
    
    fixture_id: str
    home_team: str
    away_team: str
    
    # Score
    home_score: int
    away_score: int
    result: str  # "H", "D", "A"
    
    # Key stats
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None
    home_possession: Optional[int] = None
    home_shots: Optional[int] = None
    away_shots: Optional[int] = None
    home_shots_on_target: Optional[int] = None
    away_shots_on_target: Optional[int] = None
    
    # Events
    goals: List[Dict] = None
    
    # Match insights (from FotMob)
    insights: List[str] = None
    
    # The narrative
    match_narrative: str = ""
    
    def generate_narrative(self) -> str:
        """Generate a narrative of what actually happened."""
        
        lines = []
        
        # Result line
        if self.result == "H":
            winner = self.home_team
            loser = self.away_team
            lines.append(f"{winner} beat {loser} {self.home_score}-{self.away_score} at home.")
        elif self.result == "A":
            winner = self.away_team
            loser = self.home_team
            lines.append(f"{winner} won {self.away_score}-{self.home_score} away at {loser}.")
        else:
            lines.append(f"{self.home_team} and {self.away_team} drew {self.home_score}-{self.away_score}.")
        
        # xG story
        if self.home_xg and self.away_xg:
            if self.result == "H" and self.home_xg < self.away_xg:
                lines.append(f"Despite lower xG ({self.home_xg:.2f} vs {self.away_xg:.2f}), {self.home_team} were clinical.")
            elif self.result == "A" and self.away_xg < self.home_xg:
                lines.append(f"Despite lower xG ({self.away_xg:.2f} vs {self.home_xg:.2f}), {self.away_team} were clinical.")
            elif self.result == "H" and self.home_xg > self.away_xg:
                lines.append(f"The xG ({self.home_xg:.2f} vs {self.away_xg:.2f}) reflected {self.home_team}'s dominance.")
            elif self.result == "A" and self.away_xg > self.home_xg:
                lines.append(f"The xG ({self.away_xg:.2f} vs {self.home_xg:.2f}) reflected {self.away_team}'s dominance.")
        
        # Possession vs result
        if self.home_possession:
            if self.result == "A" and self.home_possession > 55:
                lines.append(f"{self.home_team} had {self.home_possession}% possession but couldn't convert.")
            elif self.result == "H" and self.home_possession < 45:
                lines.append(f"{self.home_team} won despite only {self.home_possession}% possession.")
        
        # Shots story
        if self.home_shots and self.away_shots:
            if self.result == "A" and self.home_shots > self.away_shots * 2:
                lines.append(f"{self.home_team} had {self.home_shots} shots vs {self.away_shots} but couldn't score.")
            elif self.result == "H" and self.away_shots > self.home_shots:
                lines.append(f"{self.home_team} were efficient with {self.home_shots} shots vs {self.away_shots}.")
        
        # Goal timeline
        if self.goals:
            early_goals = [g for g in self.goals if g.get('time', 90) < 20]
            late_goals = [g for g in self.goals if g.get('time', 0) > 75]
            
            if early_goals:
                first = early_goals[0]
                scorer_team = self.away_team if not first.get('is_home') else self.home_team
                lines.append(f"Early goal from {first.get('player_name', 'unknown')} ({first.get('time')}') set the tone for {scorer_team}.")
            
            if late_goals:
                lines.append(f"Late drama with {len(late_goals)} goal(s) after 75'.")
        
        # Key insight
        if self.insights:
            for insight in self.insights[:2]:
                if "haven't lost" in insight.lower() or "unbeaten" in insight.lower():
                    lines.append(f"Key context: {insight}")
                    break
        
        self.match_narrative = " ".join(lines)
        return self.match_narrative


def build_reality(fixture_id: str) -> Optional[MatchReality]:
    """Build rich reality from database."""
    
    conn = get_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT 
                fotmob_match_id,
                home_team_name,
                away_team_name,
                home_score,
                away_score,
                stats,
                match_facts,
                events
            FROM fotmob_matches 
            WHERE fotmob_match_id = %s
        """, (fixture_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        home_score = row[3]
        away_score = row[4]
        
        if home_score is None:
            return None
        
        # Determine result
        if home_score > away_score:
            result = "H"
        elif away_score > home_score:
            result = "A"
        else:
            result = "D"
        
        # Parse stats
        home_xg = away_xg = None
        home_poss = home_shots = away_shots = None
        home_sot = away_sot = None
        
        stats = row[5]
        if stats and isinstance(stats, dict) and 'All' in stats:
            import re
            
            # Stats are stored as string representations
            all_stats_str = str(stats['All'])
            
            # Extract xG
            xg_match = re.search(r"key='expected_goals', home='([\d.]+)', away='([\d.]+)'", all_stats_str)
            if xg_match:
                try:
                    home_xg = float(xg_match.group(1))
                    away_xg = float(xg_match.group(2))
                except:
                    pass
            
            # Extract possession
            poss_match = re.search(r"key='BallPossesion', home='(\d+)', away='(\d+)'", all_stats_str)
            if poss_match:
                try:
                    home_poss = int(poss_match.group(1))
                except:
                    pass
            
            # Extract shots
            shots_match = re.search(r"key='total_shots', home='(\d+)', away='(\d+)'", all_stats_str)
            if shots_match:
                try:
                    home_shots = int(shots_match.group(1))
                    away_shots = int(shots_match.group(2))
                except:
                    pass
            
            # Extract shots on target
            sot_match = re.search(r"key='ShotsOnTarget', home='(\d+)', away='(\d+)'", all_stats_str)
            if sot_match:
                try:
                    home_sot = int(sot_match.group(1))
                    away_sot = int(sot_match.group(2))
                except:
                    pass
        
        # Parse events
        goals = []
        events = row[7]
        if events:
            if isinstance(events, str):
                events = json.loads(events)
            
            for e in events:
                if isinstance(e, dict) and e.get('type') == 'goal':
                    goals.append(e)
        
        # Parse insights
        insights = []
        facts = row[6]
        if facts:
            if isinstance(facts, str):
                facts = json.loads(facts)
            
            if isinstance(facts, dict) and 'insights' in facts:
                insights = facts['insights']
        
        reality = MatchReality(
            fixture_id=str(row[0]),
            home_team=row[1],
            away_team=row[2],
            home_score=home_score,
            away_score=away_score,
            result=result,
            home_xg=home_xg,
            away_xg=away_xg,
            home_possession=home_poss,
            home_shots=home_shots,
            away_shots=away_shots,
            home_shots_on_target=home_sot,
            away_shots_on_target=away_sot,
            goals=goals,
            insights=insights,
        )
        
        reality.generate_narrative()
        return reality
        
    finally:
        conn.close()


def build_round_realities(round_number: int) -> Dict[str, MatchReality]:
    """Build realities for all matches in a round."""
    
    conn = get_connection()
    if not conn:
        return {}
    
    try:
        cur = conn.cursor()
        
        cur.execute("""
            SELECT fotmob_match_id
            FROM fotmob_matches 
            WHERE round_number = %s
            AND league_id = 47
            AND home_score IS NOT NULL
        """, (round_number,))
        
        realities = {}
        for row in cur.fetchall():
            fixture_id = str(row[0])
            reality = build_reality(fixture_id)
            if reality:
                realities[fixture_id] = reality
        
        return realities
        
    finally:
        conn.close()


if __name__ == "__main__":
    # Test with Burnley vs West Ham
    realities = build_round_realities(25)
    
    for fid, r in realities.items():
        print(f"\n{'='*60}")
        print(f"{r.home_team} {r.home_score}-{r.away_score} {r.away_team}")
        print(f"{'='*60}")
        print(f"xG: {r.home_xg} - {r.away_xg}")
        print(f"Shots: {r.home_shots} - {r.away_shots}")
        print(f"Possession: {r.home_possession}%")
        print(f"\nNarrative: {r.match_narrative}")
        print(f"\nGoals: {len(r.goals or [])}")
        for g in (r.goals or []):
            print(f"  {g.get('time')}' - {g.get('player_name')}")
