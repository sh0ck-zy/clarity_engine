"""
ELO rating cache with pre-match date guard.

Wraps the existing src/data/loaders/elo.py loader with a local JSON file cache.
Uses match_date - 1 day for lookups to prevent same-day leakage.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import sys

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from data.loaders.elo import get_elo_for_date, ELO_MAPPING

CACHE_DIR = _PROJECT_ROOT / "data" / "cache" / "elo"

# Direct provider team name -> ClubELO club name mapping
# provider uses full official names; ClubELO uses shorter forms
_PROVIDER_TO_ELO: Dict[str, str] = {
    "AFC Bournemouth": "Bournemouth",
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Brentford": "Brentford",
    "Brighton & Hove Albion": "Brighton",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds United": "Leeds",
    "Leicester City": "Leicester",
    "Liverpool": "Liverpool",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Forest",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Ipswich Town": "Ipswich",
    "Luton Town": "Luton",
    # Portuguese teams (provider name -> ClubELO name)
    "Sporting CP": "Sporting",
    "SL Benfica": "Benfica",
    "FC Porto": "Porto",
    "SC Braga": "Braga",
    "Vitória SC": "Guimaraes",
    "Vitória de Guimarães": "Guimaraes",
    "Famalicão": "Famalicao",
    "FC Famalicão": "Famalicao",
    "Gil Vicente FC": "Gil Vicente",
    "Moreirense FC": "Moreirense",
    "Rio Ave FC": "Rio Ave",
    "Santa Clara": "Santa Clara",
    "Casa Pia AC": "Casa Pia",
    "CF Estrela da Amadora": "Amadora",
    "Estrela da Amadora": "Amadora",
    "GD Estoril Praia": "Estoril",
    "Estoril Praia": "Estoril",
    "Arouca": "Arouca",
    "FC Arouca": "Arouca",
    "Boavista FC": "Boavista",
    "Nacional": "Nacional",
    "CD Nacional": "Nacional",
    "AVS": "AVS",
}
# Also populate from the existing ELO_MAPPING (ClubELO -> short name)
for elo_name, short_name in ELO_MAPPING.items():
    if short_name not in _PROVIDER_TO_ELO:
        _PROVIDER_TO_ELO[short_name] = elo_name


def _cache_path(d: date) -> Path:
    return CACHE_DIR / f"{d.isoformat()}.json"


def _load_cache(d: date) -> Optional[Dict[str, float]]:
    path = _cache_path(d)
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _save_cache(d: date, ratings: Dict[str, float]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(_cache_path(d), "w") as f:
        json.dump(ratings, f, indent=2)


def _fetch_and_cache(d: date, countries: Optional[List[str]] = None) -> Dict[str, float]:
    """Fetch ELO ratings for a date from ClubELO API and cache locally.

    Args:
        d: Date to fetch ratings for
        countries: Country codes to include (e.g. ["ENG", "POR"]).
                   Default ["ENG"]. ClubELO is UEFA-only, so no Brazil.
    """
    if countries is None:
        countries = ["ENG"]

    cached = _load_cache(d)
    if cached is not None:
        # Check if cached data already includes requested countries
        # (if we previously cached ENG only but now need POR too, re-fetch)
        cache_key = f"{d.isoformat()}_{'_'.join(sorted(countries))}"
        cache_path_multi = CACHE_DIR / f"{cache_key}.json"
        if cache_path_multi.exists():
            with open(cache_path_multi) as f:
                return json.load(f)
        # If only one country and it's ENG, the old cache works
        if countries == ["ENG"]:
            return cached

    date_str = d.strftime("%Y-%m-%d")
    df = get_elo_for_date(date_str)

    ratings: Dict[str, float] = {}
    if df is not None and not df.empty:
        df_filtered = df[df["Country"].isin(countries)]
        for _, row in df_filtered.iterrows():
            club_name = row["Club"]
            elo_value = float(row["Elo"])
            # Store under both ClubELO name and provider name
            ratings[club_name] = elo_value
            provider_name = ELO_MAPPING.get(club_name)
            if provider_name and provider_name != club_name:
                ratings[provider_name] = elo_value
            # Also check the provider-to-ELO reverse mapping
            for fm_name, elo_name in _PROVIDER_TO_ELO.items():
                if elo_name == club_name and fm_name not in ratings:
                    ratings[fm_name] = elo_value

    # Save with country-specific cache key
    cache_key = f"{d.isoformat()}_{'_'.join(sorted(countries))}"
    cache_path_multi = CACHE_DIR / f"{cache_key}.json"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(cache_path_multi, "w") as f:
        json.dump(ratings, f, indent=2)

    # Also save under the old path for backward compatibility
    _save_cache(d, ratings)
    return ratings


def get_team_elo(
    team_name: str,
    match_date: date,
    countries: Optional[List[str]] = None,
) -> Optional[float]:
    """
    Get pre-match ELO for a team.

    Uses match_date - 1 day to avoid same-day leakage.
    """
    pre_match_elo_date = match_date - timedelta(days=1)
    ratings = _fetch_and_cache(pre_match_elo_date, countries=countries)

    # Try direct lookup (team_name might already be a ClubELO name)
    if team_name in ratings:
        return ratings[team_name]

    # Try provider -> ClubELO mapping
    elo_name = _PROVIDER_TO_ELO.get(team_name)
    if elo_name and elo_name in ratings:
        return ratings[elo_name]

    # Try case-insensitive partial match as last resort
    team_lower = team_name.lower()
    for club, elo in ratings.items():
        if club.lower() == team_lower or team_lower.startswith(club.lower()):
            return elo

    return None


def bulk_fetch(
    match_dates: List[date],
    sleep_seconds: float = 0.2,
    countries: Optional[List[str]] = None,
) -> None:
    """
    Pre-fetch and cache ELO ratings for all unique match dates.

    Uses match_date - 1 day for each date.
    """
    if countries is None:
        countries = ["ENG"]

    unique_dates = sorted(set(d - timedelta(days=1) for d in match_dates))

    fetched = 0
    skipped = 0
    for d in unique_dates:
        # Check country-specific cache
        cache_key = f"{d.isoformat()}_{'_'.join(sorted(countries))}"
        cache_path = CACHE_DIR / f"{cache_key}.json"
        if cache_path.exists():
            skipped += 1
            continue
        _fetch_and_cache(d, countries=countries)
        fetched += 1
        if fetched < len(unique_dates) - skipped:
            time.sleep(sleep_seconds)

    print(f"ELO cache: {fetched} fetched, {skipped} cached, {len(unique_dates)} total dates")


def report_coverage(
    team_names: List[str], match_dates: List[date]
) -> Dict[str, int]:
    """
    Check ELO coverage for a list of (team, date) pairs.

    Returns dict with 'total', 'found', 'missing', and 'missing_teams' list.
    """
    total = len(team_names)
    missing_teams: List[str] = []
    found = 0

    for team_name, match_date in zip(team_names, match_dates):
        elo = get_team_elo(team_name, match_date)
        if elo is not None:
            found += 1
        else:
            missing_teams.append(team_name)

    return {
        "total": total,
        "found": found,
        "missing": total - found,
        "missing_rate": (total - found) / total if total > 0 else 0.0,
        "missing_teams": list(set(missing_teams)),
    }
