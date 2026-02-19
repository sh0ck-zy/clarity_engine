"""
FotMob provider - fetches match data from FotMob's internal REST API.

Endpoints used:
  - GET /api/leagues?id={league_id}&season={season}  -> league fixtures
  - GET /api/matchDetails?matchId={id}                -> full match detail
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from src.models.fotmob import (
    FotMobCoach,
    FotMobLeagueMatch,
    FotMobMatchDetail,
    FotMobMatchEvent,
    FotMobMatchFacts,
    FotMobMomentum,
    FotMobPlayer,
    FotMobPlayerDetailedStats,
    FotMobShot,
    FotMobStatCategory,
    FotMobStatValue,
    FotMobTeamLineup,
    FotMobTeamRef,
)

BASE_URL = "https://www.fotmob.com"

logger = logging.getLogger(__name__)


class FotMobProvider:
    """Adapter for FotMob's internal API."""

    def __init__(
        self,
        *,
        min_request_interval: float = 2.0,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ):
        self.min_request_interval = min_request_interval
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/",
            }
        )
        self._last_request_time = 0.0

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def fetch_league_matches(
        self, league_id: int = 47, season: str = "2025/2026"
    ) -> List[FotMobLeagueMatch]:
        """Fetch all matches for a league season from /api/leagues."""
        data = self._request("/api/leagues", {"id": league_id, "season": season})

        matches: List[FotMobLeagueMatch] = []
        raw_all = data.get("fixtures", {}).get("allMatches", [])
        # allMatches can be a list directly or a dict with a "matches" key
        if isinstance(raw_all, dict):
            all_matches = raw_all.get("matches", [])
        elif isinstance(raw_all, list):
            all_matches = raw_all
        else:
            all_matches = []

        for m in all_matches:
            status = m.get("status", {})
            home = m.get("home", {})
            away = m.get("away", {})

            # Round can be a string or int from the API
            round_val = m.get("round")
            if round_val is not None:
                try:
                    round_val = int(round_val)
                except (ValueError, TypeError):
                    pass

            matches.append(
                FotMobLeagueMatch(
                    id=m.get("id", 0),
                    round=round_val,
                    home_name=home.get("name", ""),
                    away_name=away.get("name", ""),
                    home_id=home.get("id", 0),
                    away_id=away.get("id", 0),
                    score_str=status.get("scoreStr"),
                    finished=status.get("finished", False),
                    utc_time=status.get("utcTime") or m.get("status", {}).get("utcTime"),
                )
            )

        logger.info("Fetched %d matches for league %d season %s", len(matches), league_id, season)
        return matches

    def fetch_match_details(self, match_id: int) -> FotMobMatchDetail:
        """Fetch full match details from /api/matchDetails."""
        raw = self._request("/api/matchDetails", {"matchId": match_id})
        return self._parse_match_details(match_id, raw)

    # ------------------------------------------------------------------ #
    # HTTP layer
    # ------------------------------------------------------------------ #

    def _request(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a request with rate limiting and retry with exponential backoff."""
        url = f"{BASE_URL}{path}"
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            self._respect_rate_limit()
            try:
                logger.info("FotMob request [%d/%d]: %s %s", attempt, self.max_retries, path, params)
                resp = self.session.get(url, params=params, timeout=30)
                self._last_request_time = time.time()
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict):
                    raise ValueError(f"Unexpected response type: {type(data)}")
                return data
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                status = exc.response.status_code if exc.response else 0
                if status == 429:
                    wait = 2 ** attempt * 5
                    logger.warning("Rate limited (429), waiting %ds before retry", wait)
                    time.sleep(wait)
                    continue
                if status >= 500:
                    wait = 2 ** attempt
                    logger.warning("Server error %d, retrying in %ds", status, wait)
                    time.sleep(wait)
                    continue
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning("Connection error, retrying in %ds: %s", wait, exc)
                time.sleep(wait)

        raise RuntimeError(
            f"FotMob request failed after {self.max_retries} attempts: {path}"
        ) from last_exc

    def _respect_rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    def _parse_match_details(
        self, match_id: int, raw: Dict[str, Any]
    ) -> FotMobMatchDetail:
        """Transform raw JSON into a FotMobMatchDetail dataclass."""
        general = raw.get("general", {})
        header = raw.get("header", {})
        content = raw.get("content", {})

        # Teams from header
        header_teams = header.get("teams", [])
        home_team_raw = header_teams[0] if len(header_teams) > 0 else {}
        away_team_raw = header_teams[1] if len(header_teams) > 1 else {}

        home_team = FotMobTeamRef(
            id=home_team_raw.get("id", 0),
            name=home_team_raw.get("name", ""),
            score=home_team_raw.get("score"),
        )
        away_team = FotMobTeamRef(
            id=away_team_raw.get("id", 0),
            name=away_team_raw.get("name", ""),
            score=away_team_raw.get("score"),
        )

        # Match date - prefer ISO format from matchTimeUTCDate
        match_date = None
        match_time_utc = general.get("matchTimeUTCDate") or header.get("status", {}).get("utcTime")
        if match_time_utc:
            try:
                match_date = datetime.fromisoformat(
                    match_time_utc.replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        # Status
        status_raw = general.get("started", False)
        finished = general.get("finished", False)
        if finished:
            status = "finished"
        elif status_raw:
            status = "live"
        else:
            status = "upcoming"

        # Match facts / info box - values can be dicts or primitives
        match_facts_raw = content.get("matchFacts", {})
        info_box_raw = match_facts_raw.get("infoBox", {})
        info_box: Dict[str, str] = {}

        if isinstance(info_box_raw, dict):
            for key, val in info_box_raw.items():
                if isinstance(val, dict):
                    info_box[key] = val.get("name") or val.get("text") or str(val)
                elif val is not None:
                    info_box[key] = str(val)
        elif isinstance(info_box_raw, list):
            for item in info_box_raw:
                if isinstance(item, dict):
                    info_box.update({k: str(v) for k, v in item.items()})

        # Half-time score from header.status.scoreStr or matchFacts
        ht_home = None
        ht_away = None
        header_status = header.get("status", {})
        ht_score_str = header_status.get("scoreStr")
        if ht_score_str and " - " in str(ht_score_str):
            # This is the final score, not HT - check halfs
            pass
        ht_data = match_facts_raw.get("halfTimeScore", {})
        if isinstance(ht_data, dict):
            ht_home = ht_data.get("home")
            ht_away = ht_data.get("away")

        # Venue from infoBox.Stadium (which is now a dict with name/city/country)
        stadium_raw = info_box_raw.get("Stadium") if isinstance(info_box_raw, dict) else None
        if isinstance(stadium_raw, dict):
            venue = stadium_raw.get("name")
        else:
            venue = info_box.get("Stadium")

        # Attendance
        attendance_raw = info_box_raw.get("Attendance") if isinstance(info_box_raw, dict) else None
        attendance = None
        if attendance_raw is not None:
            try:
                attendance = int(str(attendance_raw).replace(",", "").replace(".", "").strip())
            except (ValueError, TypeError):
                pass

        # Referee
        referee_raw = info_box_raw.get("Referee") if isinstance(info_box_raw, dict) else None
        if isinstance(referee_raw, dict):
            referee = referee_raw.get("text") or referee_raw.get("name")
        else:
            referee = info_box.get("Referee")

        # Round
        round_name = general.get("leagueRoundName", "")
        round_number = None
        if round_name:
            try:
                round_number = int("".join(c for c in round_name if c.isdigit()))
            except ValueError:
                pass

        # Events
        events = self._parse_events(header.get("events", {}))

        # Stats
        stat_periods = self._parse_stats(content.get("stats", {}))

        # Lineups
        lineup_data = content.get("lineup", {})
        home_lineup = self._parse_lineup(lineup_data.get("homeTeam"), is_home=True)
        away_lineup = self._parse_lineup(lineup_data.get("awayTeam"), is_home=False)

        # Player stats
        player_stats = self._parse_player_stats(content.get("playerStats", {}))

        # Shotmap
        shotmap = self._parse_shotmap(content.get("shotmap", {}))

        # Momentum
        momentum = self._parse_momentum(content.get("momentum", {}))

        # Match facts
        motm_raw = match_facts_raw.get("playerOfTheMatch", {})
        top_players_raw = match_facts_raw.get("topPlayers", {})
        insights_raw = match_facts_raw.get("insights", [])
        insights = []
        if isinstance(insights_raw, list):
            for ins in insights_raw:
                if isinstance(ins, dict):
                    insights.append(ins.get("text", str(ins)))
                elif isinstance(ins, str):
                    insights.append(ins)

        match_facts = FotMobMatchFacts(
            player_of_the_match=motm_raw if motm_raw else None,
            top_players=top_players_raw if top_players_raw else None,
            insights=insights,
            info_box=info_box if info_box else None,
            team_form=match_facts_raw.get("teamForm"),
        )

        return FotMobMatchDetail(
            fotmob_match_id=match_id,
            season=general.get("parentLeagueSeason") or general.get("leagueSeason"),
            round_number=round_number,
            round_name=round_name,
            match_date=match_date,
            venue=venue,
            attendance=attendance,
            referee=referee,
            home_team=home_team,
            away_team=away_team,
            status=status,
            ht_score_home=ht_home,
            ht_score_away=ht_away,
            events=events,
            stat_periods=stat_periods,
            home_lineup=home_lineup,
            away_lineup=away_lineup,
            player_stats=player_stats,
            shotmap=shotmap,
            momentum=momentum,
            match_facts=match_facts,
            raw_json=raw,
            fetched_at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------ #
    # Sub-parsers
    # ------------------------------------------------------------------ #

    def _parse_events(self, events_raw: Dict[str, Any]) -> List[FotMobMatchEvent]:
        """Parse header.events into a list of FotMobMatchEvent.

        Structure: {homeTeamGoals: {playerName: [event, ...]}, ...}
        Each side key maps to a dict of player names -> list of event dicts.
        """
        result: List[FotMobMatchEvent] = []
        if not events_raw:
            return result
        for side_key in ("homeTeamGoals", "awayTeamGoals", "homeTeamRedCards", "awayTeamRedCards"):
            is_home = side_key.startswith("home")
            ev_type = "goal" if "Goal" in side_key else "redcard"
            side_data = events_raw.get(side_key, {})

            # Can be {playerName: [events]} or a flat list
            event_list: List[Dict[str, Any]] = []
            if isinstance(side_data, dict):
                for player_events in side_data.values():
                    if isinstance(player_events, list):
                        event_list.extend(player_events)
                    elif isinstance(player_events, dict):
                        event_list.append(player_events)
            elif isinstance(side_data, list):
                event_list = side_data

            for ev in event_list:
                if not isinstance(ev, dict):
                    continue
                new_score = ev.get("newScore", [])
                result.append(
                    FotMobMatchEvent(
                        type=ev.get("type", ev_type).lower(),
                        time=ev.get("time"),
                        player_id=ev.get("playerId"),
                        player_name=ev.get("nameStr") or ev.get("fullName"),
                        is_home=ev.get("isHome", is_home),
                        home_score=new_score[0] if len(new_score) > 0 else ev.get("homeScore"),
                        away_score=new_score[1] if len(new_score) > 1 else ev.get("awayScore"),
                        assist_player_id=ev.get("assistPlayerId"),
                    )
                )
        return result

    def _parse_stats(
        self, stats_raw: Dict[str, Any]
    ) -> Dict[str, List[FotMobStatCategory]]:
        """Parse content.stats.Periods into stat_periods dict.

        Structure: Periods.{All|FirstHalf|SecondHalf} can be:
          - a dict with "stats" key containing list of categories
          - or a list of categories directly
        Each category has "stats" which is a list of stat items with
        "stats" being [homeValue, awayValue].
        """
        periods_raw = stats_raw.get("Periods", {})
        result: Dict[str, List[FotMobStatCategory]] = {}

        for period_name, period_data in periods_raw.items():
            # Normalize: extract the list of categories
            if isinstance(period_data, dict):
                categories = period_data.get("stats", [])
            elif isinstance(period_data, list):
                categories = period_data
            else:
                continue

            if not isinstance(categories, list):
                continue

            cats: List[FotMobStatCategory] = []
            for cat in categories:
                if not isinstance(cat, dict):
                    continue
                stat_values: List[FotMobStatValue] = []
                for s in cat.get("stats", []):
                    if not isinstance(s, dict):
                        continue
                    pair = s.get("stats", [])
                    stat_values.append(
                        FotMobStatValue(
                            title=s.get("title", ""),
                            key=s.get("key", ""),
                            home=str(pair[0]) if isinstance(pair, list) and len(pair) > 0 else None,
                            away=str(pair[1]) if isinstance(pair, list) and len(pair) > 1 else None,
                        )
                    )
                cats.append(
                    FotMobStatCategory(
                        title=cat.get("title", ""),
                        stats=stat_values,
                    )
                )
            result[period_name] = cats
        return result

    def _parse_lineup(
        self, team_raw: Optional[Dict[str, Any]], *, is_home: bool
    ) -> Optional[FotMobTeamLineup]:
        """Parse a single team's lineup from content.lineup."""
        if not team_raw:
            return None

        def parse_player(p: Dict[str, Any], starter: bool) -> FotMobPlayer:
            perf = p.get("performance", {}) or {}
            return FotMobPlayer(
                id=p.get("id"),
                name=p.get("name"),
                shirt_number=str(p.get("shirt", "")) if p.get("shirt") else None,
                position_id=p.get("positionId"),
                rating=_safe_float(perf.get("rating")),
                market_value=p.get("marketValue"),
                fantasy_score=str(perf.get("fantasyScore", "")) if perf.get("fantasyScore") else None,
                is_starter=starter,
                events=perf.get("events"),
                substitution_events=perf.get("substitutionEvents"),
            )

        starters = [parse_player(p, True) for p in team_raw.get("starters", []) if isinstance(p, dict)]
        subs = [parse_player(p, False) for p in team_raw.get("subs", []) if isinstance(p, dict)]

        coach_raw = team_raw.get("coach", {})
        coach = None
        if coach_raw and isinstance(coach_raw, dict):
            coach = FotMobCoach(id=coach_raw.get("id"), name=coach_raw.get("name"))

        # Average rating
        avg_rating = None
        ratings = [p.rating for p in starters if p.rating is not None]
        if ratings:
            avg_rating = round(sum(ratings) / len(ratings), 2)

        return FotMobTeamLineup(
            team_id=team_raw.get("id"),
            team_name=team_raw.get("name"),
            formation=team_raw.get("formation"),
            avg_rating=avg_rating,
            starters=starters,
            subs=subs,
            coach=coach,
            unavailable=team_raw.get("unavailable", []),
        )

    def _parse_player_stats(
        self, ps_raw: Dict[str, Any]
    ) -> Dict[str, FotMobPlayerDetailedStats]:
        """Parse content.playerStats into a dict keyed by player_id."""
        result: Dict[str, FotMobPlayerDetailedStats] = {}
        if not isinstance(ps_raw, dict):
            return result
        for pid_str, pdata in ps_raw.items():
            if not isinstance(pdata, dict):
                continue
            result[pid_str] = FotMobPlayerDetailedStats(
                player_id=_safe_int(pid_str),
                name=pdata.get("name"),
                team_id=pdata.get("teamId"),
                stats=pdata.get("stats"),
            )
        return result

    def _parse_shotmap(self, sm_raw: Dict[str, Any]) -> List[FotMobShot]:
        """Parse content.shotmap.shots."""
        shots_list = sm_raw.get("shots", []) if isinstance(sm_raw, dict) else []
        if isinstance(sm_raw, list):
            shots_list = sm_raw
        result: List[FotMobShot] = []
        for s in shots_list:
            if not isinstance(s, dict):
                continue
            result.append(
                FotMobShot(
                    player_name=s.get("playerName"),
                    player_id=s.get("playerId"),
                    x=_safe_float(s.get("x")),
                    y=_safe_float(s.get("y")),
                    min=s.get("min"),
                    expected_goals=_safe_float(s.get("expectedGoals")),
                    event_type=s.get("eventType"),
                    is_on_target=s.get("isOnTarget"),
                    team_id=s.get("teamId"),
                )
            )
        return result

    def _parse_momentum(self, mom_raw: Dict[str, Any]) -> List[FotMobMomentum]:
        """Parse content.momentum.main.data."""
        if not isinstance(mom_raw, dict):
            return []
        data = mom_raw.get("main", {}).get("data", [])
        result: List[FotMobMomentum] = []
        for pt in data:
            if isinstance(pt, dict) and "minute" in pt and "value" in pt:
                result.append(FotMobMomentum(minute=pt["minute"], value=pt["value"]))
        return result


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
