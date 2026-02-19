"""
FotMob Data Models

Dataclass schemas for data extracted from FotMob's internal API.
Covers league-level match listings and detailed match data including
lineups, player stats, shotmaps, momentum, and match facts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# ============================================================
# LEAGUE-LEVEL (from /api/leagues)
# ============================================================


@dataclass
class FotMobLeagueMatch:
    """Lightweight match info from the league fixtures endpoint."""

    id: int
    round: Optional[int]
    home_name: str
    away_name: str
    home_id: int
    away_id: int
    score_str: Optional[str]
    finished: bool
    utc_time: Optional[str]


@dataclass
class FotMobLeagueRound:
    """A collection of matches in a single round."""

    round_number: int
    matches: List[FotMobLeagueMatch] = field(default_factory=list)


# ============================================================
# MATCH DETAIL (from /api/matchDetails)
# ============================================================


@dataclass
class FotMobTeamRef:
    """Minimal team reference."""

    id: int
    name: str
    score: Optional[int] = None


@dataclass
class FotMobMatchEvent:
    """A single match event (goal, card, sub, etc.)."""

    type: Optional[str] = None
    time: Optional[int] = None
    player_id: Optional[int] = None
    player_name: Optional[str] = None
    is_home: Optional[bool] = None
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    assist_player_id: Optional[int] = None
    swap_player_id: Optional[int] = None
    card: Optional[str] = None


@dataclass
class FotMobStatValue:
    """A single stat comparison (home vs away)."""

    title: str
    key: str
    home: Optional[str] = None
    away: Optional[str] = None


@dataclass
class FotMobStatCategory:
    """Category of stats (e.g. 'Top stats', 'Shots')."""

    title: str
    stats: List[FotMobStatValue] = field(default_factory=list)


@dataclass
class FotMobCoach:
    """Coach info."""

    id: Optional[int] = None
    name: Optional[str] = None


@dataclass
class FotMobPlayer:
    """Player in a lineup."""

    id: Optional[int] = None
    name: Optional[str] = None
    shirt_number: Optional[str] = None
    position_id: Optional[int] = None
    rating: Optional[float] = None
    market_value: Optional[str] = None
    fantasy_score: Optional[str] = None
    is_starter: bool = True
    events: Optional[Dict[str, Any]] = None
    substitution_events: Optional[Dict[str, Any]] = None


@dataclass
class FotMobTeamLineup:
    """Full lineup for one team."""

    team_id: Optional[int] = None
    team_name: Optional[str] = None
    formation: Optional[str] = None
    avg_rating: Optional[float] = None
    starters: List[FotMobPlayer] = field(default_factory=list)
    subs: List[FotMobPlayer] = field(default_factory=list)
    coach: Optional[FotMobCoach] = None
    unavailable: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FotMobPlayerDetailedStats:
    """Detailed per-player stats from content.playerStats."""

    player_id: Optional[int] = None
    name: Optional[str] = None
    team_id: Optional[int] = None
    stats: Optional[Dict[str, Any]] = None


@dataclass
class FotMobShot:
    """A single shot from the shotmap."""

    player_name: Optional[str] = None
    player_id: Optional[int] = None
    x: Optional[float] = None
    y: Optional[float] = None
    min: Optional[int] = None
    expected_goals: Optional[float] = None
    event_type: Optional[str] = None
    is_on_target: Optional[bool] = None
    team_id: Optional[int] = None


@dataclass
class FotMobMomentum:
    """Momentum data point."""

    minute: int
    value: float


@dataclass
class FotMobMatchFacts:
    """Match facts: MOTM, top players, insights, info box."""

    player_of_the_match: Optional[Dict[str, Any]] = None
    top_players: Optional[Dict[str, Any]] = None
    insights: List[str] = field(default_factory=list)
    info_box: Optional[Dict[str, str]] = None
    team_form: Optional[List[Any]] = None


@dataclass
class FotMobMatchDetail:
    """
    Top-level model for a full match detail response from /api/matchDetails.
    Contains everything: lineups, stats, events, shotmap, momentum, facts.
    """

    fotmob_match_id: int
    season: Optional[str] = None
    round_number: Optional[int] = None
    round_name: Optional[str] = None
    match_date: Optional[datetime] = None
    venue: Optional[str] = None
    attendance: Optional[int] = None
    referee: Optional[str] = None

    home_team: Optional[FotMobTeamRef] = None
    away_team: Optional[FotMobTeamRef] = None
    status: Optional[str] = None

    ht_score_home: Optional[int] = None
    ht_score_away: Optional[int] = None

    events: List[FotMobMatchEvent] = field(default_factory=list)

    # All / FirstHalf / SecondHalf -> list of stat categories
    stat_periods: Dict[str, List[FotMobStatCategory]] = field(default_factory=dict)

    home_lineup: Optional[FotMobTeamLineup] = None
    away_lineup: Optional[FotMobTeamLineup] = None

    player_stats: Dict[str, FotMobPlayerDetailedStats] = field(default_factory=dict)

    shotmap: List[FotMobShot] = field(default_factory=list)
    momentum: List[FotMobMomentum] = field(default_factory=list)

    match_facts: Optional[FotMobMatchFacts] = None

    raw_json: Dict[str, Any] = field(default_factory=dict)
    fetched_at: Optional[datetime] = None
