"""
Transfermarkt Team Mappings

Maps team names used in the Clarity Engine database to Transfermarkt
URL slugs and IDs.

Transfermarkt URL pattern:
    https://www.transfermarkt.com/{slug}/kader/verein/{id}/saison_id/{year}
"""

# Premier League 2024-25 season
PL_TEAMS = {
    "Arsenal": {"slug": "fc-arsenal", "id": "11"},
    "Aston Villa": {"slug": "aston-villa", "id": "405"},
    "Bournemouth": {"slug": "afc-bournemouth", "id": "989"},
    "Brentford": {"slug": "fc-brentford", "id": "1148"},
    "Brighton": {"slug": "brighton-amp-hove-albion", "id": "1237"},
    "Chelsea": {"slug": "fc-chelsea", "id": "631"},
    "Crystal Palace": {"slug": "crystal-palace", "id": "873"},
    "Everton": {"slug": "fc-everton", "id": "29"},
    "Fulham": {"slug": "fc-fulham", "id": "931"},
    "Ipswich": {"slug": "ipswich-town", "id": "677"},
    "Leicester": {"slug": "leicester-city", "id": "1003"},
    "Liverpool": {"slug": "fc-liverpool", "id": "31"},
    "Man City": {"slug": "manchester-city", "id": "281"},
    "Man United": {"slug": "manchester-united", "id": "985"},
    "Newcastle": {"slug": "newcastle-united", "id": "762"},
    "Nottingham Forest": {"slug": "nottingham-forest", "id": "703"},
    "Southampton": {"slug": "fc-southampton", "id": "180"},
    "Tottenham": {"slug": "tottenham-hotspur", "id": "148"},
    "West Ham": {"slug": "west-ham-united", "id": "379"},
    "Wolves": {"slug": "wolverhampton-wanderers", "id": "543"},
}

# Alternative name mappings (for fuzzy matching from different data sources)
TEAM_ALIASES = {
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Nottm Forest": "Nottingham Forest",
    "Nott'm Forest": "Nottingham Forest",
    "Brighton and Hove Albion": "Brighton",
    "Brighton & Hove Albion": "Brighton",
    "AFC Bournemouth": "Bournemouth",
    "Leicester City": "Leicester",
    "Ipswich Town": "Ipswich",
    "Wolverhampton Wanderers": "Wolves",
    "Wolverhampton": "Wolves",
    "Spurs": "Tottenham",
    "Tottenham Hotspur": "Tottenham",
}


def get_team_info(team_name: str) -> dict | None:
    """
    Get Transfermarkt info for a team.

    Args:
        team_name: Team name (tries exact match first, then aliases)

    Returns:
        {"slug": "...", "id": "..."} or None if not found
    """
    # Try exact match
    if team_name in PL_TEAMS:
        return PL_TEAMS[team_name]

    # Try alias
    canonical = TEAM_ALIASES.get(team_name)
    if canonical and canonical in PL_TEAMS:
        return PL_TEAMS[canonical]

    return None


def normalize_team_name(team_name: str) -> str:
    """
    Normalize team name to the canonical form used in PL_TEAMS.

    Args:
        team_name: Any variant of the team name

    Returns:
        Canonical team name
    """
    if team_name in PL_TEAMS:
        return team_name

    return TEAM_ALIASES.get(team_name, team_name)


def get_all_teams() -> list[str]:
    """Get list of all team names."""
    return list(PL_TEAMS.keys())
