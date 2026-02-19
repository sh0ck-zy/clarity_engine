"""
Transfermarkt Injury Scraper

Scrapes injury data from Transfermarkt for Premier League teams.

Strategy:
1. Fetch squad page → extract player IDs from DOM
2. For each player → fetch /verletzungen/ (injuries) page
3. Parse HTML <table> with BeautifulSoup
4. Store in player_injuries_historical table

URLs:
    Squad: https://www.transfermarkt.com/{slug}/kader/verein/{id}/saison_id/{year}
    Injuries: https://www.transfermarkt.com/{player-slug}/verletzungen/spieler/{player-id}

Usage:
    scraper = TransfermarktInjuryScraper()
    injuries = scraper.scrape_team_injuries("Arsenal", "2024")
    scraper.save_to_db(injuries)
"""

import re
import sys
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.ingestion.transfermarkt_teams import get_team_info, normalize_team_name, PL_TEAMS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PlayerInfo:
    """Basic player info extracted from squad page."""
    player_id: str
    player_name: str
    player_slug: str
    position: str


@dataclass
class InjuryRecord:
    """Single injury record for a player."""
    player_id: str
    player_name: str
    team_id: str
    team_name: str
    season: str
    injury_type: str
    from_date: Optional[date]
    to_date: Optional[date]  # None = ongoing
    days_missed: Optional[int]
    games_missed: Optional[int]
    position: Optional[str] = None  # Player position (GK, CB, LW, etc.)


class TransfermarktInjuryScraper:
    """
    Scraper for Transfermarkt injury data.

    Implements rate limiting and retry logic to avoid bans.
    """

    BASE_URL = "https://www.transfermarkt.com"
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    def __init__(self, delay: float = 2.0, max_retries: int = 3):
        """
        Initialize scraper.

        Args:
            delay: Seconds to wait between requests (rate limiting)
            max_retries: Max retry attempts on failure
        """
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _fetch(self, url: str) -> Optional[str]:
        """
        Fetch URL with retry logic.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None on failure
        """
        for attempt in range(self.max_retries):
            try:
                time.sleep(self.delay)
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.delay * (attempt + 1))  # Exponential backoff
                else:
                    logger.error(f"All attempts failed for {url}")
                    return None
        return None

    def get_squad_players(self, team_name: str, season: str) -> list[PlayerInfo]:
        """
        Fetch squad page and extract player info.

        Args:
            team_name: Team name (e.g., "Arsenal")
            season: Season year (e.g., "2024" for 2024-25)

        Returns:
            List of PlayerInfo objects
        """
        team_info = get_team_info(team_name)
        if not team_info:
            logger.error(f"Team not found: {team_name}")
            return []

        url = f"{self.BASE_URL}/{team_info['slug']}/kader/verein/{team_info['id']}/saison_id/{season}"
        logger.info(f"Fetching squad: {url}")

        html = self._fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        players = []

        # Find player rows in the squad table
        # Players are in table with class "items"
        table = soup.find("table", class_="items")
        if not table:
            logger.warning(f"No squad table found for {team_name}")
            return []

        rows = table.find_all("tr", class_=["odd", "even"])
        for row in rows:
            try:
                # Player link is in td.hauptlink > a
                player_cell = row.find("td", class_="hauptlink")
                if not player_cell:
                    continue

                player_link = player_cell.find("a")
                if not player_link:
                    continue

                href = player_link.get("href", "")
                # Extract player ID from URL: /player-name/profil/spieler/12345
                match = re.search(r"/spieler/(\d+)", href)
                if not match:
                    continue

                player_id = match.group(1)
                player_name = player_link.get_text(strip=True)

                # Extract slug from href
                slug_match = re.match(r"/([^/]+)/", href)
                player_slug = slug_match.group(1) if slug_match else ""

                # Position is in a separate cell
                position = ""
                pos_cells = row.find_all("td", class_="zentriert")
                for cell in pos_cells:
                    text = cell.get_text(strip=True)
                    if text in ["GK", "CB", "LB", "RB", "DM", "CM", "AM", "LM", "RM", "LW", "RW", "CF", "SS"]:
                        position = text
                        break

                players.append(PlayerInfo(
                    player_id=player_id,
                    player_name=player_name,
                    player_slug=player_slug,
                    position=position
                ))

            except Exception as e:
                logger.warning(f"Error parsing player row: {e}")
                continue

        logger.info(f"Found {len(players)} players for {team_name}")
        return players

    def get_player_injuries(
        self,
        player: PlayerInfo,
        team_id: str,
        team_name: str,
        season_filter: Optional[str] = None
    ) -> list[InjuryRecord]:
        """
        Fetch injury history for a player.

        Args:
            player: PlayerInfo object
            team_id: Transfermarkt team ID
            team_name: Team name
            season_filter: Optional season to filter (e.g., "24/25")

        Returns:
            List of InjuryRecord objects
        """
        url = f"{self.BASE_URL}/{player.player_slug}/verletzungen/spieler/{player.player_id}"
        logger.debug(f"Fetching injuries for {player.player_name}: {url}")

        html = self._fetch(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        injuries = []

        # Find injury table
        table = soup.find("table", class_="items")
        if not table:
            # No injury history for this player
            return []

        rows = table.find_all("tr")[1:]  # Skip header
        for row in rows:
            try:
                cells = row.find_all("td")
                if len(cells) < 6:
                    continue

                season = cells[0].get_text(strip=True)
                injury_type = cells[1].get_text(strip=True)
                from_str = cells[2].get_text(strip=True)
                to_str = cells[3].get_text(strip=True)
                days_str = cells[4].get_text(strip=True)
                games_str = cells[5].get_text(strip=True)

                # Filter by season if specified
                if season_filter and season != season_filter:
                    continue

                # Parse dates
                from_date = self._parse_date(from_str)
                to_date = self._parse_date(to_str) if to_str != "?" else None

                # Parse numbers
                days_missed = self._parse_int(days_str)
                games_missed = self._parse_int(games_str)

                injuries.append(InjuryRecord(
                    player_id=player.player_id,
                    player_name=player.player_name,
                    team_id=team_id,
                    team_name=team_name,
                    season=season,
                    injury_type=injury_type,
                    from_date=from_date,
                    to_date=to_date,
                    days_missed=days_missed,
                    games_missed=games_missed,
                    position=player.position
                ))

            except Exception as e:
                logger.warning(f"Error parsing injury row for {player.player_name}: {e}")
                continue

        return injuries

    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse Transfermarkt date format (e.g., 'Dec 22, 2024')."""
        if not date_str or date_str == "?" or date_str == "-":
            return None

        formats = [
            "%b %d, %Y",  # "Dec 22, 2024"
            "%d/%m/%Y",   # "22/12/2024"
            "%Y-%m-%d",   # "2024-12-22"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        logger.warning(f"Could not parse date: {date_str}")
        return None

    def _parse_int(self, value: str) -> Optional[int]:
        """Parse integer, handling empty/dash values."""
        if not value or value in ["-", "?"]:
            return None
        try:
            # Remove any non-digit characters
            digits = re.sub(r"[^\d]", "", value)
            return int(digits) if digits else None
        except ValueError:
            return None

    def scrape_team_injuries(
        self,
        team_name: str,
        season: str,
        season_filter: Optional[str] = None
    ) -> list[InjuryRecord]:
        """
        Scrape all injuries for a team.

        Args:
            team_name: Team name (e.g., "Arsenal")
            season: Season year for squad page (e.g., "2024")
            season_filter: Optional filter for injury seasons (e.g., "24/25")

        Returns:
            List of all InjuryRecord objects for the team
        """
        team_info = get_team_info(team_name)
        if not team_info:
            logger.error(f"Team not found: {team_name}")
            return []

        logger.info(f"Scraping injuries for {team_name} (season {season})")

        # Get squad
        players = self.get_squad_players(team_name, season)
        if not players:
            logger.warning(f"No players found for {team_name}")
            return []

        # Get injuries for each player
        all_injuries = []
        for i, player in enumerate(players):
            logger.info(f"  [{i+1}/{len(players)}] {player.player_name}")
            injuries = self.get_player_injuries(
                player=player,
                team_id=team_info["id"],
                team_name=team_name,
                season_filter=season_filter
            )
            all_injuries.extend(injuries)

        logger.info(f"Found {len(all_injuries)} total injury records for {team_name}")
        return all_injuries

    def save_to_db(self, injuries: list[InjuryRecord]) -> int:
        """
        Save injury records to database.

        Args:
            injuries: List of InjuryRecord objects

        Returns:
            Number of records inserted
        """
        if not injuries:
            return 0

        conn = get_connection()
        if not conn:
            logger.error("Could not connect to database")
            return 0

        try:
            cur = conn.cursor()

            # Insert query
            insert_sql = """
                INSERT INTO player_injuries_historical
                (player_id, player_name, team_id, team_name, season, injury_reason,
                 from_date, end_date, days_missed, games_missed, data_source, position, ingested_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT DO NOTHING
            """

            count = 0
            for injury in injuries:
                cur.execute(insert_sql, (
                    injury.player_id,
                    injury.player_name,
                    injury.team_id,
                    injury.team_name,
                    injury.season,
                    injury.injury_type,
                    injury.from_date,
                    injury.to_date,
                    injury.days_missed,
                    injury.games_missed,
                    "transfermarkt",
                    injury.position
                ))
                count += cur.rowcount

            conn.commit()
            logger.info(f"Inserted {count} injury records")
            return count

        except Exception as e:
            logger.error(f"Database error: {e}")
            conn.rollback()
            return 0

        finally:
            conn.close()

    def get_current_injuries(self, team_name: str, season: str) -> list[InjuryRecord]:
        """
        Get only current (ongoing) injuries for a team.

        Args:
            team_name: Team name
            season: Season year

        Returns:
            List of current injuries (where to_date is None or in future)
        """
        all_injuries = self.scrape_team_injuries(team_name, season)
        today = date.today()

        current = []
        for injury in all_injuries:
            # Ongoing (no end date) or end date in future
            if injury.to_date is None or injury.to_date >= today:
                current.append(injury)

        return current


if __name__ == "__main__":
    # Test with Arsenal
    scraper = TransfermarktInjuryScraper(delay=2.0)

    print("Testing squad fetch...")
    players = scraper.get_squad_players("Arsenal", "2024")
    print(f"Found {len(players)} players")
    for p in players[:5]:
        print(f"  - {p.player_name} ({p.position}) [ID: {p.player_id}]")

    if players:
        print("\nTesting injury fetch for first player...")
        team_info = get_team_info("Arsenal")
        injuries = scraper.get_player_injuries(
            player=players[0],
            team_id=team_info["id"],
            team_name="Arsenal"
        )
        print(f"Found {len(injuries)} injury records")
        for inj in injuries[:3]:
            print(f"  - {inj.injury_type}: {inj.from_date} to {inj.to_date or 'ongoing'}")
