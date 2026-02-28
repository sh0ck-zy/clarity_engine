"""
Match Context Builder — assembles rich, structured context per match.

Queries all available DB tables (team_states, player_performances,
manager_history, fotmob_matches) and builds a context object that
separates FACTS from ML INFERENCE from NARRATIVE ANGLES.

The context feeds the LLM narrator and is also useful standalone
for any downstream consumer (HTML, Telegram, API).

Usage:
    builder = MatchContextBuilder(league_id=47)
    context = builder.build(round_number=28, report=report_dict,
                            fixture_id="4813646",
                            home_team="Arsenal", away_team="Chelsea")
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import psycopg2


def _safe(val: Any) -> Any:
    """Convert DB types to JSON-safe Python types."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return float(val)
    return val


# ──────────────────────────────────────────────────────────────
# Position ID → human-readable position name
# ──────────────────────────────────────────────────────────────
_POS_MAP = {
    11: "GK", 21: "RB", 22: "CB", 23: "LB",
    31: "RB", 32: "CB", 33: "CB", 34: "LB",
    37: "CB",  # centre-back variants
    41: "DM", 42: "CM", 43: "CM",
    51: "RM", 52: "AM", 53: "LM",
    61: "RW", 62: "CF", 63: "LW",
    71: "RW", 72: "SS", 73: "LW",
    74: "DM", 75: "DM", 76: "CM", 77: "CM", 78: "LB",
    91: "RW", 92: "CF", 93: "LW",
    101: "RW", 102: "AM", 103: "AM", 104: "LW",
    105: "CF", 106: "CF", 107: "CF",
}


class MatchContextBuilder:
    """Builds a rich MatchContext dict for a single match."""

    def __init__(self, league_id: int = 47, db_url: str = ""):
        self.league_id = league_id
        self._conn: Optional[psycopg2.extensions.connection] = None

    # ── connection management ─────────────────────────────────

    def _get_conn(self) -> psycopg2.extensions.connection:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                dbname="clarity_football", user="joao", host="localhost"
            )
        return self._conn

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ── public API ────────────────────────────────────────────

    def build(
        self,
        round_number: int,
        report: Dict,
        fixture_id: str,
        home_team: str,
        away_team: str,
    ) -> Dict:
        """Build full match context. Returns a JSON-serializable dict."""
        conn = self._get_conn()
        cur = conn.cursor()

        try:
            # 1. Team states (round N-1)
            home_state = self._get_team_state(cur, home_team, round_number)
            away_state = self._get_team_state(cur, away_team, round_number)

            # 2. Key players
            home_players = self._get_key_players(cur, home_team, round_number)
            away_players = self._get_key_players(cur, away_team, round_number)

            # 3. Manager
            home_manager = self._get_manager(cur, home_team)
            away_manager = self._get_manager(cur, away_team)

            # 4. Recent results (last 3)
            home_recent = self._get_recent_results(cur, home_team, round_number)
            away_recent = self._get_recent_results(cur, away_team, round_number)

            # 5. H2H this season
            h2h = self._get_h2h(cur, home_team, away_team, round_number)

            # 6. League context
            league_ctx = self._get_league_context(cur, round_number)

            # 7. Venue
            venue = self._get_venue(cur, fixture_id)

            # 8. Build team contexts
            home_ctx = self._build_team_context(
                home_state, home_players, home_manager, home_recent, is_home=True
            )
            away_ctx = self._build_team_context(
                away_state, away_players, away_manager, away_recent, is_home=False
            )

            # 9. ML inference (from report)
            ml_inference = self._extract_ml_inference(report)

            # 10. Narrative angles (deterministic)
            angles = self._compute_narrative_angles(home_ctx, away_ctx, ml_inference)

            return {
                "match": {
                    "fixture_id": str(fixture_id),
                    "round_number": round_number,
                    "match_date": report.get("fixture", {}).get("match_date", ""),
                    "venue": venue,
                },
                "factual": {
                    "home": home_ctx,
                    "away": away_ctx,
                    "h2h_this_season": h2h,
                    "league_context": league_ctx,
                },
                "ml_inference": ml_inference,
                "narrative_angles": angles,
                "context_version": "1.0",
                "built_at": datetime.utcnow().isoformat() + "Z",
            }
        finally:
            cur.close()

    # ── team state ────────────────────────────────────────────

    def _resolve_team_id(self, cur, team_name: str) -> Optional[int]:
        """Resolve team name → team_id via fotmob_matches."""
        cur.execute(
            """
            SELECT DISTINCT home_team_id FROM fotmob_matches
            WHERE home_team_name = %(t)s AND league_id = %(lid)s
            UNION
            SELECT DISTINCT away_team_id FROM fotmob_matches
            WHERE away_team_name = %(t)s AND league_id = %(lid)s
            LIMIT 1
            """,
            {"t": team_name, "lid": self.league_id},
        )
        row = cur.fetchone()
        return row[0] if row else None

    def _get_team_state(self, cur, team_name: str, round_number: int) -> Dict:
        """Get full team_states row for round N-1."""
        team_id = self._resolve_team_id(cur, team_name)
        if not team_id:
            return {}
        cur.execute(
            """
            SELECT *
            FROM team_states
            WHERE team_id = %(tid)s
              AND round_number = %(rn)s
              AND league_id = %(lid)s
            LIMIT 1
            """,
            {"tid": team_id, "lid": self.league_id, "rn": round_number - 1},
        )
        row = cur.fetchone()
        if not row:
            return {}
        cols = [d[0] for d in cur.description]
        return {c: _safe(v) for c, v in zip(cols, row)}

    # ── key players ───────────────────────────────────────────

    def _get_key_players(
        self, cur, team_name: str, round_number: int, limit: int = 5
    ) -> List[Dict]:
        """Top players by avg rating (season aggregates, rounds < N)."""
        cur.execute(
            """
            SELECT
                p.player_name,
                MODE() WITHIN GROUP (ORDER BY p.position_id) AS position_id,
                COUNT(*) AS appearances,
                SUM(p.goals) AS season_goals,
                SUM(p.assists) AS season_assists,
                COALESCE(SUM(p.xg), 0) AS season_xg,
                COALESCE(SUM(p.xa), 0) AS season_xa,
                ROUND(AVG(p.rating), 2) AS avg_rating,
                SUM(p.minutes_played) AS total_minutes
            FROM fotmob_player_performances p
            JOIN fotmob_matches m ON m.fotmob_match_id = p.fotmob_match_id
            WHERE p.team_name = %(team)s
              AND m.round_number < %(rn)s
              AND m.league_id = %(lid)s
              AND p.rating IS NOT NULL
            GROUP BY p.player_name
            HAVING COUNT(*) >= 3
            ORDER BY AVG(p.rating) DESC
            LIMIT %(lim)s
            """,
            {"team": team_name, "rn": round_number, "lid": self.league_id, "lim": limit},
        )
        rows = cur.fetchall()

        # Also find top scorer and top assister for this team
        top_scorer = None
        top_assister = None
        players = []
        for row in rows:
            p = {
                "name": row[0],
                "position": _POS_MAP.get(row[1], "?"),
                "appearances": row[2],
                "goals": int(row[3] or 0),
                "assists": int(row[4] or 0),
                "xg": round(float(row[5] or 0), 2),
                "xa": round(float(row[6] or 0), 2),
                "avg_rating": float(row[7] or 0),
                "minutes": int(row[8] or 0),
            }
            players.append(p)

        # Mark top scorer / assister from full squad
        if players:
            scorer = max(players, key=lambda x: x["goals"])
            if scorer["goals"] > 0:
                scorer["is_top_scorer"] = True
            assister = max(players, key=lambda x: x["assists"])
            if assister["assists"] > 0:
                assister["is_top_assister"] = True

        return players

    # ── manager ───────────────────────────────────────────────

    def _get_manager(self, cur, team_name: str) -> Dict:
        """Current manager info."""
        team_id = self._resolve_team_id(cur, team_name)
        if not team_id:
            return {"name": "Unknown", "matches": 0, "record": "0W-0D-0L"}
        cur.execute(
            """
            SELECT manager_name, matches, wins, draws, losses, first_match_round
            FROM manager_history
            WHERE team_id = %(tid)s AND is_current = true
            LIMIT 1
            """,
            {"tid": team_id},
        )
        row = cur.fetchone()
        if not row:
            return {"name": "Unknown", "matches": 0, "record": "0W-0D-0L"}
        return {
            "name": row[0],
            "matches": row[1],
            "record": f"{row[2]}W-{row[3]}D-{row[4]}L",
            "since_round": row[5],
        }

    # ── recent results ────────────────────────────────────────

    def _get_recent_results(
        self, cur, team_name: str, round_number: int, limit: int = 3
    ) -> List[Dict]:
        """Last N completed matches for the team before round_number."""
        cur.execute(
            """
            SELECT
                m.round_number,
                m.home_team_name,
                m.away_team_name,
                m.home_score,
                m.away_score,
                CASE WHEN m.home_team_name = %(team)s THEN true ELSE false END AS is_home
            FROM fotmob_matches m
            WHERE (m.home_team_name = %(team)s OR m.away_team_name = %(team)s)
              AND m.league_id = %(lid)s
              AND m.round_number < %(rn)s
              AND m.home_score IS NOT NULL
            ORDER BY m.round_number DESC
            LIMIT %(lim)s
            """,
            {"team": team_name, "lid": self.league_id, "rn": round_number, "lim": limit},
        )
        results = []
        for row in cur.fetchall():
            rnd, home_t, away_t, hs, as_, is_home = row
            opponent = away_t if is_home else home_t
            score = f"{hs}-{as_}" if is_home else f"{as_}-{hs}"
            results.append({
                "round": rnd,
                "opponent": opponent,
                "score": score,
                "is_home": is_home,
            })
        return results

    # ── H2H ───────────────────────────────────────────────────

    def _get_h2h(
        self, cur, home_team: str, away_team: str, round_number: int
    ) -> List[Dict]:
        """Head-to-head this season (reverse fixture if exists)."""
        cur.execute(
            """
            SELECT round_number, home_team_name, away_team_name,
                   home_score, away_score
            FROM fotmob_matches
            WHERE league_id = %(lid)s
              AND round_number < %(rn)s
              AND home_score IS NOT NULL
              AND (
                  (home_team_name = %(home)s AND away_team_name = %(away)s)
                  OR (home_team_name = %(away)s AND away_team_name = %(home)s)
              )
            ORDER BY round_number
            """,
            {"lid": self.league_id, "rn": round_number,
             "home": home_team, "away": away_team},
        )
        results = []
        for row in cur.fetchall():
            results.append({
                "round": row[0],
                "result": f"{row[1]} {row[3]}-{row[4]} {row[2]}",
            })
        return results

    # ── league context ────────────────────────────────────────

    def _get_league_context(self, cur, round_number: int) -> Dict:
        """Leader, gaps, etc. from team_states at round N-1."""
        cur.execute(
            """
            SELECT team_id, position, points
            FROM team_states
            WHERE league_id = %(lid)s AND round_number = %(rn)s
            ORDER BY position ASC
            """,
            {"lid": self.league_id, "rn": round_number - 1},
        )
        rows = cur.fetchall()
        if len(rows) < 2:
            return {}

        # Get team name for leader
        leader_id = rows[0][0]
        cur.execute(
            "SELECT DISTINCT home_team_name FROM fotmob_matches WHERE home_team_id = %s AND league_id = %s LIMIT 1",
            (leader_id, self.league_id),
        )
        leader_row = cur.fetchone()
        leader_name = leader_row[0] if leader_row else "?"

        pts_1st = rows[0][2] or 0
        pts_2nd = rows[1][2] or 0

        # Relegation gap (17th vs 18th if enough teams)
        rel_gap = None
        if len(rows) >= 18:
            pts_17 = rows[16][2] or 0
            pts_18 = rows[17][2] or 0
            rel_gap = pts_17 - pts_18

        return {
            "leader": leader_name,
            "pts_gap_1st_2nd": pts_1st - pts_2nd,
            "relegation_gap_17th_18th": rel_gap,
        }

    # ── venue ─────────────────────────────────────────────────

    def _get_venue(self, cur, fixture_id: str) -> Optional[str]:
        cur.execute(
            "SELECT venue FROM fotmob_matches WHERE fotmob_match_id = %s",
            (fixture_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None

    # ── build team context dict ───────────────────────────────

    def _build_team_context(
        self,
        state: Dict,
        players: List[Dict],
        manager: Dict,
        recent: List[Dict],
        is_home: bool,
    ) -> Dict:
        if not state:
            return {"name": "Unknown"}

        # Build W-D-L records
        if is_home:
            venue_record = {
                "w": state.get("home_wins", 0),
                "d": state.get("home_draws", 0),
                "l": state.get("home_losses", 0),
            }
        else:
            venue_record = {
                "w": state.get("away_wins", 0),
                "d": state.get("away_draws", 0),
                "l": state.get("away_losses", 0),
            }

        # Get team name from recent or state
        # We need to look it up — use the team_id from state
        team_id = state.get("team_id")

        return {
            "team_id": team_id,
            # Standing
            "position": state.get("position"),
            "points": state.get("points"),
            "played": state.get("played"),
            "goal_difference": state.get("goal_difference"),
            "wins": state.get("wins"),
            "draws": state.get("draws"),
            "losses": state.get("losses"),
            # Form
            "form_string": state.get("form_string"),
            "form_points": state.get("form_points"),
            "form_trend": state.get("form_trend"),
            "goals_scored_last5": state.get("goals_scored_last5"),
            "goals_conceded_last5": state.get("goals_conceded_last5"),
            "clean_sheets_last5": state.get("clean_sheets_last5"),
            "position_change_last5": state.get("position_change_last5"),
            # xG
            "xg_for_last5": state.get("xg_for_last5"),
            "xg_against_last5": state.get("xg_against_last5"),
            "xg_diff_last5": state.get("xg_diff_last5"),
            "xg_per_game": state.get("xg_per_game"),
            "xg_against_per_game": state.get("xg_against_per_game"),
            # Style
            "avg_possession": state.get("avg_possession"),
            "primary_formation": state.get("primary_formation"),
            "shots_per_game": state.get("shots_per_game"),
            "shots_on_target_per_game": state.get("shots_on_target_per_game"),
            "big_chances_per_game": state.get("big_chances_per_game"),
            "shots_against_per_game": state.get("shots_against_per_game"),
            # Venue
            "venue_record": venue_record,
            "venue_points": state.get("home_points") if is_home else state.get("away_points"),
            # Players
            "key_players": players,
            # Manager
            "manager": manager,
            # Recent
            "recent_results": recent,
        }

    # ── ML inference ──────────────────────────────────────────

    def _extract_ml_inference(self, report: Dict) -> Dict:
        probs = report.get("probabilities", {})
        pred = report.get("prediction", {})
        drivers = report.get("drivers", [])
        flags = report.get("risk_flags", [])

        # Get elo_delta from drivers if available
        elo_delta = None
        for d in drivers:
            if d.get("feature") == "elo_delta":
                elo_delta = d.get("value")
                break

        return {
            "probabilities": {
                "H": probs.get("home_win"),
                "D": probs.get("draw"),
                "A": probs.get("away_win"),
            },
            "predicted_result": pred.get("predicted_result"),
            "confidence": pred.get("confidence"),
            "margin_top2": pred.get("margin_top2"),
            "entropy_norm": pred.get("entropy_norm"),
            "drivers": drivers,
            "risk_flags": flags,
            "elo_delta": elo_delta,
        }

    # ── narrative angles (deterministic, no LLM) ─────────────

    def _compute_narrative_angles(
        self, home: Dict, away: Dict, ml: Dict
    ) -> Dict:
        """Generate angle hints from factual data. Seeds for the LLM."""
        angles: Dict[str, Any] = {}

        # Home story
        home_parts = []
        pos = home.get("position")
        form = home.get("form_string", "")
        trend = home.get("form_trend", "")
        vp = home.get("venue_points")
        recent = home.get("recent_results", [])

        if pos and pos <= 4:
            home_parts.append(f"title contender ({_ordinal(pos)} place)")
        elif pos and pos >= 17:
            home_parts.append(f"relegation battle ({_ordinal(pos)} place)")

        if trend == "improving":
            home_parts.append("form improving")
        elif trend == "declining":
            home_parts.append("form declining")

        if form:
            home_parts.append(f"form: {form}")

        if vp and vp >= 28:
            home_parts.append(f"strong at home ({vp} pts)")
        elif vp and vp <= 12:
            home_parts.append(f"struggling at home ({vp} pts)")

        if recent:
            best = [r for r in recent if r["score"].startswith(("3-", "4-", "5-"))]
            if best:
                r = best[0]
                home_parts.append(f"{r['score']} vs {r['opponent']} in R{r['round']}")

        angles["home_story"] = ", ".join(home_parts) if home_parts else "steady campaign"

        # Away story
        away_parts = []
        a_pos = away.get("position")
        a_form = away.get("form_string", "")
        a_trend = away.get("form_trend", "")
        a_vp = away.get("venue_points")

        if a_pos and a_pos <= 4:
            away_parts.append(f"title contender ({_ordinal(a_pos)} place)")
        elif a_pos and a_pos >= 17:
            away_parts.append(f"relegation battle ({_ordinal(a_pos)} place)")

        if a_trend == "improving":
            away_parts.append("form improving")
        elif a_trend == "declining":
            away_parts.append("form declining")

        if a_form:
            away_parts.append(f"form: {a_form}")

        # Key away players
        a_players = away.get("key_players", [])
        top_scorer = next((p for p in a_players if p.get("is_top_scorer")), None)
        if top_scorer:
            away_parts.append(
                f"{top_scorer['name']} ({top_scorer['goals']}G, "
                f"{top_scorer['assists']}A)"
            )

        away_draws = away.get("draws", 0)
        if away_draws and away_draws >= 8:
            away_parts.append(f"draw-prone ({away_draws} draws)")

        angles["away_story"] = ", ".join(away_parts) if away_parts else "steady campaign"

        # Key battle
        h_poss = home.get("avg_possession")
        a_poss = away.get("avg_possession")
        h_form_str = home.get("primary_formation", "")
        a_form_str = away.get("primary_formation", "")
        battle_parts = []

        if h_form_str and a_form_str:
            battle_parts.append(f"{h_form_str} vs {a_form_str}")

        if h_poss and a_poss:
            if abs(h_poss - a_poss) > 5:
                dom = "Home" if h_poss > a_poss else "Away"
                battle_parts.append(
                    f"{dom} possession dominance ({h_poss:.0f}% vs {a_poss:.0f}%)"
                )

        h_xg_ag = home.get("xg_against_per_game")
        a_xg_ag = away.get("xg_against_per_game")
        if h_xg_ag and a_xg_ag:
            if h_xg_ag < 0.8:
                battle_parts.append(f"home defence elite ({h_xg_ag:.2f} xGA/game)")
            if a_xg_ag > 1.3:
                battle_parts.append(f"away defence leaky ({a_xg_ag:.2f} xGA/game)")

        angles["key_battle"] = ", ".join(battle_parts) if battle_parts else "evenly matched"

        # Risks
        risks = []
        if ml.get("risk_flags"):
            for f in ml["risk_flags"]:
                risks.append(f"model flag: {f}")

        if away_draws and away_draws >= 7:
            played = away.get("played", 27)
            risks.append(f"away team drew {away_draws}/{played} games")

        h_recent = home.get("recent_results", [])
        h_draws = [r for r in h_recent if "-" in r["score"] and r["score"].split("-")[0] == r["score"].split("-")[1]]
        if h_draws:
            r = h_draws[0]
            risks.append(f"home drew {r['score']} vs {r['opponent']} in R{r['round']}")

        h_gc = home.get("goals_conceded_last5")
        if h_gc and h_gc >= 8:
            risks.append(f"home conceded {h_gc} in last 5")

        a_gc = away.get("goals_conceded_last5")
        if a_gc and a_gc >= 8:
            risks.append(f"away conceded {a_gc} in last 5")

        elo = ml.get("elo_delta")
        predicted = ml.get("predicted_result")
        if elo and predicted == "D" and abs(elo) > 100:
            risks.append(f"draw predicted despite ELO gap of {elo:+.0f}")

        angles["risks"] = risks if risks else ["no major red flags identified"]

        return angles


def _ordinal(n) -> str:
    if not isinstance(n, (int, float)):
        return str(n)
    n = int(n)
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(
        n % 10 if n % 100 not in (11, 12, 13) else 0, "th"
    )
    return f"{n}{suffix}"
