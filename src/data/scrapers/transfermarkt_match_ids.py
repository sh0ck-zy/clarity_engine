"""
Transfermarkt Match ID Finder

Finds Transfermarkt match IDs (spielbericht IDs) for our fixtures.

Strategy:
1. Fetch team's schedule page (/spielplan/)
2. Parse match rows → extract spielbericht ID, opponent, date
3. Match with our fixtures by date + teams
4. Store mapping in tm_match_mapping table

URLs:
    Schedule: https://www.transfermarkt.com/{slug}/spielplan/verein/{id}/saison_id/{year}/plus/1#gesamt

Usage:
    finder = TransfermarktMatchFinder()
    mapping = finder.find_match_id("Arsenal", "Aston Villa", date(2025, 1, 18))
    # Returns: {"tm_match_id": "4361082", "home_team_id": "11", "away_team_id": "405"}
"""

import re
import sys
import time
import logging
from pathlib import Path
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.ingestion.transfermarkt_teams import get_team_info, normalize_team_name, PL_TEAMS, TEAM_ALIASES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MatchMapping:
    """Mapping between our fixture ID and Transfermarkt match ID."""
    fixture_id: str
    tm_match_id: str
    match_date: date
    home_team: str
    away_team: str
    tm_home_id: str
    tm_away_id: str


class TransfermarktMatchFinder:
    """
    Finds Transfermarkt match IDs by scraping team schedule pages.
    """

    BASE_URL = "https://www.transfermarkt.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    def __init__(self, delay: float = 2.0, max_retries: int = 3):
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._schedule_cache: dict[str, list[dict]] = {}  # team_id -> list of matches

    def _fetch(self, url: str) -> Optional[str]:
        """Fetch URL with retry logic."""
        for attempt in range(self.max_retries):
            try:
                time.sleep(self.delay)
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.delay * (attempt + 1))
                else:
                    logger.error(f"All attempts failed for {url}")
                    return None
        return None

    def get_season_matches(self, season: str, competition: str = "GB1") -> list[dict]:
        """
        Fetch all matches for a season by iterating through matchdays.

        Args:
            season: Season start year (e.g., "2025" for 2025-26)
            competition: Competition code (GB1 = Premier League)

        Returns:
            List of match info dicts
        """
        cache_key = f"{competition}_{season}"
        if cache_key in self._schedule_cache:
            return self._schedule_cache[cache_key]

        all_matches = []

        # Premier League has 38 matchdays
        for matchday in range(1, 39):
            url = f"{self.BASE_URL}/premier-league/spieltag/wettbewerb/{competition}/saison_id/{season}/spieltag/{matchday}"
            logger.info(f"Fetching matchday {matchday}")

            html = self._fetch(url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Find all spielbericht links
            for link in soup.find_all("a", href=re.compile(r"/spielbericht/index/spielbericht/")):
                href = link.get("href", "")
                match_id_match = re.search(r"/spielbericht/(\d+)", href)
                if match_id_match:
                    tm_match_id = match_id_match.group(1)
                    # Avoid duplicates
                    if not any(m["tm_match_id"] == tm_match_id for m in all_matches):
                        all_matches.append({
                            "tm_match_id": tm_match_id,
                            "matchday": matchday,
                        })

        logger.info(f"Found {len(all_matches)} unique matches for season {season}")
        self._schedule_cache[cache_key] = all_matches
        return all_matches

    def get_match_details(self, tm_match_id: str) -> Optional[dict]:
        """
        Fetch match details from the spielbericht page.

        Args:
            tm_match_id: Transfermarkt match ID

        Returns:
            Dict with match_date, home_team, away_team, home_id, away_id
        """
        url = f"{self.BASE_URL}/spielbericht/index/spielbericht/{tm_match_id}"
        logger.debug(f"Fetching match details: {url}")

        html = self._fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        result = {
            "tm_match_id": tm_match_id,
            "home_team": None,
            "away_team": None,
            "home_id": None,
            "away_id": None,
            "match_date": None,
        }

        # Get teams from header
        teams = soup.find_all("a", class_="sb-vereinslink")
        if len(teams) >= 2:
            result["home_team"] = teams[0].get_text(strip=True)
            result["away_team"] = teams[1].get_text(strip=True)

            # Extract team IDs
            for i, team in enumerate(teams[:2]):
                href = team.get("href", "")
                id_match = re.search(r"/verein/(\d+)", href)
                if id_match:
                    if i == 0:
                        result["home_id"] = id_match.group(1)
                    else:
                        result["away_id"] = id_match.group(1)

        # Get date from sb-datum
        date_box = soup.find("p", class_="sb-datum")
        if date_box:
            date_text = date_box.get_text(strip=True)
            # Format: "1. Matchday|Fri, 15/08/25|  9:00 PM"
            parts = date_text.split("|")
            if len(parts) >= 2:
                date_str = parts[1].strip()
                # Remove day name prefix like "Fri, "
                date_str = re.sub(r"^[A-Za-z]+,\s*", "", date_str)
                result["match_date"] = self._parse_date(date_str)

        return result

    def _parse_date(self, date_text: str) -> Optional[date]:
        """Parse date from various Transfermarkt formats."""
        if not date_text:
            return None

        formats = [
            "%m/%d/%y",      # 1/18/25
            "%m/%d/%Y",      # 1/18/2025
            "%d/%m/%y",      # 18/1/25
            "%d/%m/%Y",      # 18/1/2025
            "%b %d, %Y",     # Jan 18, 2025
            "%B %d, %Y",     # January 18, 2025
            "%Y-%m-%d",      # 2025-01-18
        ]

        cleaned = date_text.strip()
        for fmt in formats:
            try:
                return datetime.strptime(cleaned, fmt).date()
            except ValueError:
                continue

        return None

    def find_match_id(
        self,
        home_team: str,
        away_team: str,
        match_date: date,
        season: Optional[str] = None
    ) -> Optional[MatchMapping]:
        """
        Find Transfermarkt match ID for a specific fixture.

        Args:
            home_team: Home team name
            away_team: Away team name
            match_date: Match date
            season: Season start year (auto-detected if not provided)

        Returns:
            MatchMapping or None if not found
        """
        # Auto-detect season from date
        if season is None:
            if match_date.month < 8:
                season = str(match_date.year - 1)
            else:
                season = str(match_date.year)

        # Normalize team names
        home_normalized = normalize_team_name(home_team)
        away_normalized = normalize_team_name(away_team)

        home_info = get_team_info(home_normalized)
        away_info = get_team_info(away_normalized)

        if not home_info or not away_info:
            logger.warning(f"Could not find team info for {home_team} vs {away_team}")
            return None

        # Check the match details cache first
        cache_key = f"details_{season}"
        if cache_key not in self._schedule_cache:
            self._schedule_cache[cache_key] = {}

        details_cache = self._schedule_cache[cache_key]

        # Get all matches for the season
        all_matches = self.get_season_matches(season)

        for match_stub in all_matches:
            tm_match_id = match_stub["tm_match_id"]

            # Get cached or fetch details
            if tm_match_id not in details_cache:
                details = self.get_match_details(tm_match_id)
                if details:
                    details_cache[tm_match_id] = details

            details = details_cache.get(tm_match_id)
            if not details:
                continue

            # Check if this is our match
            if details["match_date"] != match_date:
                continue
            if details["home_id"] != home_info["id"]:
                continue
            if details["away_id"] != away_info["id"]:
                continue

            # Found it!
            fixture_id = f"{match_date.isoformat()}_{home_team.replace(' ', '_')}_{away_team.replace(' ', '_')}"
            return MatchMapping(
                fixture_id=fixture_id,
                tm_match_id=tm_match_id,
                match_date=match_date,
                home_team=home_normalized,
                away_team=away_normalized,
                tm_home_id=home_info["id"],
                tm_away_id=away_info["id"],
            )

        logger.warning(f"Match not found: {home_team} vs {away_team} on {match_date}")
        return None

    def save_mapping_to_db(self, mapping: MatchMapping) -> bool:
        """Save a match mapping to the database."""
        conn = get_connection()
        if not conn:
            logger.error("Could not connect to database")
            return False

        try:
            cur = conn.cursor()

            # Ensure table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tm_match_mapping (
                    fixture_id TEXT PRIMARY KEY,
                    tm_match_id TEXT NOT NULL,
                    match_date DATE,
                    home_team TEXT,
                    away_team TEXT,
                    tm_home_id TEXT,
                    tm_away_id TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            cur.execute("""
                INSERT INTO tm_match_mapping
                (fixture_id, tm_match_id, match_date, home_team, away_team, tm_home_id, tm_away_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (fixture_id) DO UPDATE SET
                    tm_match_id = EXCLUDED.tm_match_id,
                    match_date = EXCLUDED.match_date
            """, (
                mapping.fixture_id,
                mapping.tm_match_id,
                mapping.match_date,
                mapping.home_team,
                mapping.away_team,
                mapping.tm_home_id,
                mapping.tm_away_id,
            ))

            conn.commit()
            logger.info(f"Saved mapping: {mapping.fixture_id} -> {mapping.tm_match_id}")
            return True

        except Exception as e:
            logger.error(f"Database error: {e}")
            conn.rollback()
            return False

        finally:
            conn.close()

    def get_cached_mapping(self, fixture_id: str) -> Optional[str]:
        """Get cached Transfermarkt match ID from database."""
        conn = get_connection()
        if not conn:
            return None

        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT tm_match_id FROM tm_match_mapping WHERE fixture_id = %s",
                (fixture_id,)
            )
            row = cur.fetchone()
            return row[0] if row else None
        except Exception:
            return None
        finally:
            conn.close()


def build_mappings_for_season(season: str, team_filter: Optional[str] = None) -> int:
    """
    Build Transfermarkt match ID mappings for all fixtures in a season.

    Args:
        season: Season start year (e.g., "2025")
        team_filter: Optional team name to filter

    Returns:
        Number of mappings created
    """
    conn = get_connection()
    if not conn:
        logger.error("Could not connect to database")
        return 0

    try:
        cur = conn.cursor()

        # Get fixtures for the season
        season_str = f"{season}-{int(season)+1}"
        query = "SELECT id, date, home_team, away_team FROM fixtures WHERE season = %s"
        params = [season_str]

        if team_filter:
            query += " AND (home_team LIKE %s OR away_team LIKE %s)"
            params.extend([f"%{team_filter}%", f"%{team_filter}%"])

        cur.execute(query, params)
        fixtures = cur.fetchall()

        logger.info(f"Found {len(fixtures)} fixtures for season {season_str}")

    finally:
        conn.close()

    finder = TransfermarktMatchFinder(delay=2.0)
    count = 0

    for fixture_id, match_date, home_team, away_team in fixtures:
        # Skip if already mapped
        if finder.get_cached_mapping(fixture_id):
            continue

        mapping = finder.find_match_id(
            home_team=home_team,
            away_team=away_team,
            match_date=match_date,
            season=season
        )

        if mapping:
            if finder.save_mapping_to_db(mapping):
                count += 1

    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Find Transfermarkt match IDs")
    parser.add_argument("--season", default="2025", help="Season start year")
    parser.add_argument("--team", help="Filter by team name")
    parser.add_argument("--test", action="store_true", help="Test with a single match")
    parser.add_argument("--matchday", type=int, help="Fetch specific matchday only")
    args = parser.parse_args()

    if args.test:
        finder = TransfermarktMatchFinder(delay=2.0)

        print("Testing match details fetch...")
        # Test with a known match ID
        details = finder.get_match_details("4625774")
        if details:
            print(f"Match: {details['home_team']} vs {details['away_team']}")
            print(f"Date: {details['match_date']}")
            print(f"IDs: {details['home_id']} vs {details['away_id']}")

        print("\nTesting find_match_id...")
        from datetime import date
        mapping = finder.find_match_id(
            home_team="Liverpool",
            away_team="Bournemouth",
            match_date=date(2025, 8, 15),
            season="2025"
        )
        if mapping:
            print(f"Found: {mapping.fixture_id} -> {mapping.tm_match_id}")
        else:
            print("Not found")
    else:
        count = build_mappings_for_season(args.season, args.team)
        print(f"Created {count} match mappings")
