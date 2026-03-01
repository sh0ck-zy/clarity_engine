"""
Team Registry - Single source of truth for Premier League team names and identifiers.

Provides canonical team names and normalization functions to ensure consistent
team naming across all data sources (API-Football, Understat, Transfermarkt, CSV files).
"""

PREMIER_LEAGUE_TEAMS = {
    "arsenal": {
        "canonical": "Arsenal",
        "aliases": ["Arsenal", "Arsenal FC"],
        "transfermarkt_id": "fc-arsenal",
        "api_football_id": 42,
    },
    "aston_villa": {
        "canonical": "Aston Villa",
        "aliases": ["Aston Villa", "Aston Villa FC", "Villa"],
        "transfermarkt_id": "aston-villa",
        "api_football_id": 66,
    },
    "bournemouth": {
        "canonical": "Bournemouth",
        "aliases": ["Bournemouth", "AFC Bournemouth", "Bmouth"],
        "transfermarkt_id": "afc-bournemouth",
        "api_football_id": 35,
    },
    "brentford": {
        "canonical": "Brentford",
        "aliases": ["Brentford", "Brentford FC"],
        "transfermarkt_id": "fc-brentford",
        "api_football_id": 55,
    },
    "brighton": {
        "canonical": "Brighton",
        "aliases": ["Brighton", "Brighton & Hove Albion", "Brighton and Hove Albion", "Brighton Hove Albion"],
        "transfermarkt_id": "brighton-amp-hove-albion",
        "api_football_id": 51,
    },
    "chelsea": {
        "canonical": "Chelsea",
        "aliases": ["Chelsea", "Chelsea FC"],
        "transfermarkt_id": "fc-chelsea",
        "api_football_id": 49,
    },
    "crystal_palace": {
        "canonical": "Crystal Palace",
        "aliases": ["Crystal Palace", "Crystal Palace FC", "Palace"],
        "transfermarkt_id": "crystal-palace",
        "api_football_id": 52,
    },
    "everton": {
        "canonical": "Everton",
        "aliases": ["Everton", "Everton FC"],
        "transfermarkt_id": "fc-everton",
        "api_football_id": 45,
    },
    "fulham": {
        "canonical": "Fulham",
        "aliases": ["Fulham", "Fulham FC"],
        "transfermarkt_id": "fc-fulham",
        "api_football_id": 36,
    },
    "ipswich_town": {
        "canonical": "Ipswich Town",
        "aliases": ["Ipswich Town", "Ipswich", "Ipswich Town FC"],
        "transfermarkt_id": "ipswich-town",
        "api_football_id": 57,
    },
    "leicester_city": {
        "canonical": "Leicester City",
        "aliases": ["Leicester City", "Leicester", "Leicester City FC", "LCFC"],
        "transfermarkt_id": "leicester-city",
        "api_football_id": 46,
    },
    "liverpool": {
        "canonical": "Liverpool",
        "aliases": ["Liverpool", "Liverpool FC", "LFC"],
        "transfermarkt_id": "fc-liverpool",
        "api_football_id": 40,
    },
    "manchester_city": {
        "canonical": "Manchester City",
        "aliases": ["Manchester City", "Man City", "MCFC", "Manchester City FC"],
        "transfermarkt_id": "manchester-city",
        "api_football_id": 50,
    },
    "manchester_united": {
        "canonical": "Manchester United",
        "aliases": ["Manchester United", "Man United", "Man Utd", "Manchester Utd", "MUFC", "Manchester United FC"],
        "transfermarkt_id": "manchester-united",
        "api_football_id": 33,
    },
    "newcastle_united": {
        "canonical": "Newcastle United",
        "aliases": ["Newcastle United", "Newcastle", "Newcastle Utd", "NUFC"],
        "transfermarkt_id": "newcastle-united",
        "api_football_id": 34,
    },
    "nottingham_forest": {
        "canonical": "Nottingham Forest",
        "aliases": ["Nottingham Forest", "Nott'm Forest", "Nottm Forest", "Nott'ham Forest", "Forest", "NFFC"],
        "transfermarkt_id": "nottingham-forest",
        "api_football_id": 65,
    },
    "southampton": {
        "canonical": "Southampton",
        "aliases": ["Southampton", "Southampton FC", "Saints"],
        "transfermarkt_id": "fc-southampton",
        "api_football_id": 41,
    },
    "tottenham_hotspur": {
        "canonical": "Tottenham Hotspur",
        "aliases": ["Tottenham Hotspur", "Tottenham", "Spurs", "THFC"],
        "transfermarkt_id": "tottenham-hotspur",
        "api_football_id": 47,
    },
    "west_ham_united": {
        "canonical": "West Ham United",
        "aliases": ["West Ham United", "West Ham", "West Ham Utd", "WHUFC"],
        "transfermarkt_id": "west-ham-united",
        "api_football_id": 48,
    },
    "wolverhampton_wanderers": {
        "canonical": "Wolverhampton Wanderers",
        "aliases": ["Wolverhampton Wanderers", "Wolves", "Wolverhampton", "WWFC"],
        "transfermarkt_id": "wolverhampton-wanderers",
        "api_football_id": 39,
    },
}


def normalize_team_name(name: str) -> str:
    """
    Convert any team name or alias to its canonical form.

    Args:
        name: Team name (can be any known alias)

    Returns:
        Canonical team name, or the original name if not found

    Examples:
        >>> normalize_team_name("Man City")
        'Manchester City'
        >>> normalize_team_name("Nott'm Forest")
        'Nottingham Forest'
        >>> normalize_team_name("Spurs")
        'Tottenham Hotspur'
    """
    if not name:
        return name

    # Normalize for comparison (lowercase, strip whitespace)
    normalized = name.strip().lower()

    # Check each team's aliases
    for team_key, team_info in PREMIER_LEAGUE_TEAMS.items():
        for alias in team_info["aliases"]:
            if alias.lower() == normalized:
                return team_info["canonical"]

    # If not found, return original name
    return name


def get_team_info(name: str) -> dict:
    """
    Get full team information by any alias.

    Args:
        name: Team name (can be any known alias)

    Returns:
        Dictionary with team info (canonical, aliases, IDs), or None if not found

    Examples:
        >>> info = get_team_info("Man City")
        >>> info["canonical"]
        'Manchester City'
        >>> info["api_football_id"]
        50
    """
    if not name:
        return None

    # Normalize for comparison
    normalized = name.strip().lower()

    # Check each team's aliases
    for team_key, team_info in PREMIER_LEAGUE_TEAMS.items():
        for alias in team_info["aliases"]:
            if alias.lower() == normalized:
                return team_info

    return None


def get_all_canonical_names() -> list[str]:
    """
    Get list of all canonical team names.

    Returns:
        List of canonical team names in alphabetical order
    """
    return sorted([team["canonical"] for team in PREMIER_LEAGUE_TEAMS.values()])


def is_premier_league_team(name: str) -> bool:
    """
    Check if a team name is a known Premier League team.

    Args:
        name: Team name (can be any known alias)

    Returns:
        True if team is recognized, False otherwise
    """
    return get_team_info(name) is not None
