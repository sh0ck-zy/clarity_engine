"""Team name normalization: football-data.co.uk → FotMob convention."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MAPPING_PATH = _PROJECT_ROOT / "data" / "mappings" / "team_name_map.json"

# Canonical manual mapping: football-data.co.uk CSV name → FotMob name
CSV_TO_FOTMOB: Dict[str, str] = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton & Hove Albion",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds": "Leeds United",
    "Leicester": "Leicester City",
    "Liverpool": "Liverpool",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Spurs": "Tottenham Hotspur",
    "Tottenham": "Tottenham Hotspur",
    "West Ham": "West Ham United",
    "Wolves": "Wolverhampton Wanderers",
    "Ipswich": "Ipswich Town",
    "Luton": "Luton Town",
    # Portuguese teams
    "Sp Lisbon": "Sporting CP",
    "Sporting": "Sporting CP",
    "Benfica": "SL Benfica",
    "Porto": "FC Porto",
    "Braga": "SC Braga",
    "Guimaraes": "Vitória SC",
    "Famalicao": "FC Famalicão",
    "Gil Vicente": "Gil Vicente FC",
    "Moreirense": "Moreirense FC",
    "Rio Ave": "Rio Ave FC",
    "Santa Clara": "Santa Clara",
    "Casa Pia": "Casa Pia AC",
    "Estrela Amadora": "CF Estrela da Amadora",
    "Estoril": "GD Estoril Praia",
    "Arouca": "FC Arouca",
    "Boavista": "Boavista FC",
    "Nacional": "CD Nacional",
    "AVS": "AVS",
}

_FUZZY_THRESHOLD = 90
_reviewed_cache: Dict[str, str] | None = None


def load_reviewed_mapping() -> Dict[str, str]:
    """Load data/mappings/team_name_map.json if exists."""
    global _reviewed_cache
    if _reviewed_cache is not None:
        return _reviewed_cache
    if _MAPPING_PATH.exists():
        with open(_MAPPING_PATH) as f:
            _reviewed_cache = json.load(f)
    else:
        _reviewed_cache = {}
    return _reviewed_cache


def save_reviewed_mapping(mapping: Dict[str, str]) -> None:
    """Persist reviewed fuzzy matches to data/mappings/team_name_map.json."""
    global _reviewed_cache
    _MAPPING_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_MAPPING_PATH, "w") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False, sort_keys=True)
    _reviewed_cache = mapping


def normalize_team_name(csv_name: str) -> str:
    """Map football-data team name → FotMob convention.

    Priority:
    1. Exact match in CSV_TO_FOTMOB manual dict
    2. Exact match in persisted reviewed mapping
    3. rapidfuzz fallback at 90% threshold against known FotMob names
    4. Returns original if no match found (with warning)
    """
    # 1. Manual dict
    if csv_name in CSV_TO_FOTMOB:
        return CSV_TO_FOTMOB[csv_name]

    # 2. Persisted reviewed mapping
    reviewed = load_reviewed_mapping()
    if csv_name in reviewed:
        return reviewed[csv_name]

    # 3. Fuzzy match against all known FotMob names
    known_names = list(set(CSV_TO_FOTMOB.values()))
    if not known_names:
        logger.warning("No known FotMob names for fuzzy matching: %s", csv_name)
        return csv_name

    result = process.extractOne(csv_name, known_names, scorer=fuzz.ratio)
    if result and result[1] >= _FUZZY_THRESHOLD:
        matched_name = result[0]
        logger.info("Fuzzy match: '%s' → '%s' (score=%d)", csv_name, matched_name, result[1])
        return matched_name

    logger.warning("No match found for team: '%s'", csv_name)
    return csv_name


def build_mapping_from_csv(csv_path: Path) -> Dict[str, str]:
    """Extract unique team names from a CSV, normalize each.

    Returns {csv_name: fotmob_name} for all teams in the file.
    Auto-saves new fuzzy matches to reviewed mapping file.
    """
    import pandas as pd

    df = pd.read_csv(csv_path)

    # Detect column names
    if "HomeTeam" in df.columns:
        home_col, away_col = "HomeTeam", "AwayTeam"
    elif "Home" in df.columns:
        home_col, away_col = "Home", "Away"
    else:
        raise ValueError(f"Cannot detect team columns in {csv_path}")

    teams = set(df[home_col].dropna().unique()) | set(df[away_col].dropna().unique())
    mapping: Dict[str, str] = {}
    new_fuzzy: Dict[str, str] = {}
    reviewed = load_reviewed_mapping()

    for team in sorted(teams):
        team = str(team)
        normalized = normalize_team_name(team)
        mapping[team] = normalized
        # Track new fuzzy matches (not in manual dict or reviewed)
        if team not in CSV_TO_FOTMOB and team not in reviewed and normalized != team:
            new_fuzzy[team] = normalized

    if new_fuzzy:
        updated = {**reviewed, **new_fuzzy}
        save_reviewed_mapping(updated)
        logger.info("Saved %d new fuzzy matches to %s", len(new_fuzzy), _MAPPING_PATH)

    return mapping
