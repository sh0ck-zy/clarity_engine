"""
Transfermarkt Lineup Scraper

Scrapes historical lineup data from Transfermarkt match pages.

Strategy:
1. Get match page URL from fixture data
2. Fetch match page → extract starting XI and bench
3. Parse formation and player positions
4. Store in lineups_historical table

URLs:
    Match: https://www.transfermarkt.com/spielbericht/index/spielbericht/{match_id}
    Lineup: https://www.transfermarkt.com/spielbericht/aufstellung/spielbericht/{match_id}

Usage:
    scraper = TransfermarktLineupScraper()
    lineup = scraper.get_match_lineup(match_id="12345")
    scraper.save_to_db([lineup])
"""

import re
import sys
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional, List

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PlayerLineup:
    """Single player in a lineup."""
    player_id: str
    player_name: str
    position: str  # GK, CB, LB, RB, DM, CM, AM, LW, RW, CF, etc.
    shirt_number: Optional[int] = None
    is_starter: bool = True
    is_captain: bool = False
    minute_in: Optional[int] = None   # For subs: minute entered
    minute_out: Optional[int] = None  # For starters: minute left (if subbed)


@dataclass
class MatchLineup:
    """Complete lineup for a match."""
    match_id: str
    fixture_id: str  # Our internal fixture ID
    match_date: date
    home_team: str
    away_team: str
    home_formation: Optional[str] = None
    away_formation: Optional[str] = None
    home_starters: List[PlayerLineup] = field(default_factory=list)
    away_starters: List[PlayerLineup] = field(default_factory=list)
    home_bench: List[PlayerLineup] = field(default_factory=list)
    away_bench: List[PlayerLineup] = field(default_factory=list)
    source: str = "transfermarkt"


class TransfermarktLineupScraper:
    """
    Scraper for Transfermarkt lineup data.

    Note: Transfermarkt uses internal match IDs that differ from our fixture IDs.
    We need a mapping or search mechanism to find the right match.
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

    def get_tm_match_id(self, fixture_id: str) -> Optional[str]:
        """
        Get Transfermarkt match ID from our mapping table.

        Args:
            fixture_id: Our internal fixture ID

        Returns:
            Transfermarkt match ID or None
        """
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
        finally:
            conn.close()

    def get_lineup_for_fixture(self, fixture_id: str) -> Optional[MatchLineup]:
        """
        Get lineup for a fixture using the TM mapping.

        Args:
            fixture_id: Our internal fixture ID

        Returns:
            MatchLineup or None
        """
        tm_match_id = self.get_tm_match_id(fixture_id)
        if not tm_match_id:
            logger.warning(f"No TM mapping found for {fixture_id}")
            return None

        lineup = self.get_match_lineup(tm_match_id)
        if lineup:
            lineup.fixture_id = fixture_id
        return lineup

    def get_match_lineup(self, match_id: str) -> Optional[MatchLineup]:
        """
        Fetch lineup data for a specific Transfermarkt match ID.

        Args:
            match_id: Transfermarkt match/spielbericht ID

        Returns:
            MatchLineup object or None if not found
        """
        # Use main spielbericht page which has lineup data
        url = f"{self.BASE_URL}/spielbericht/index/spielbericht/{match_id}"
        logger.info(f"Fetching lineup: {url}")

        html = self._fetch(url)
        if not html:
            return None

        soup = BeautifulSoup(html, "html.parser")

        # Extract match info from header
        match_info = self._extract_match_info_v2(soup)
        if not match_info:
            logger.warning(f"Could not extract match info from {url}")
            return None

        # Extract formations from "Starting Line-up: X-X-X" text
        home_formation, away_formation = self._extract_formations_v2(soup)

        # Extract lineups from aufstellung boxes
        home_starters, home_bench, away_starters, away_bench = self._extract_lineups_v2(soup)

        return MatchLineup(
            match_id=match_id,
            fixture_id="",
            match_date=match_info.get("date", date.today()),
            home_team=match_info.get("home_team", "Unknown"),
            away_team=match_info.get("away_team", "Unknown"),
            home_formation=home_formation,
            away_formation=away_formation,
            home_starters=home_starters,
            away_starters=away_starters,
            home_bench=home_bench,
            away_bench=away_bench,
        )

    def _extract_match_info_v2(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extract match info from spielbericht page header."""
        info = {}

        # Team names from sb-vereinslink
        teams = soup.find_all("a", class_="sb-vereinslink")
        if len(teams) >= 2:
            info["home_team"] = teams[0].get_text(strip=True)
            info["away_team"] = teams[1].get_text(strip=True)

        # Date from sb-datum
        date_box = soup.find("p", class_="sb-datum")
        if date_box:
            date_text = date_box.get_text(strip=True)
            parts = date_text.split("|")
            if len(parts) >= 2:
                date_str = parts[1].strip()
                date_str = re.sub(r"^[A-Za-z]+,\s*", "", date_str)
                info["date"] = self._parse_date(date_str)

        return info if info else None

    def _extract_formations_v2(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
        """Extract formations from page."""
        formations = []

        # Look for "Starting Line-up: X-X-X" text
        for div in soup.find_all("div", class_="formation-subtitle"):
            text = div.get_text(strip=True)
            match = re.search(r"(\d-\d-\d(-\d)?)", text)
            if match:
                formations.append(match.group(1))

        home_formation = formations[0] if len(formations) > 0 else None
        away_formation = formations[1] if len(formations) > 1 else None
        return home_formation, away_formation

    def _extract_lineups_v2(self, soup: BeautifulSoup) -> tuple[list, list, list, list]:
        """Extract all lineups from page structure."""
        home_starters = []
        home_bench = []
        away_starters = []
        away_bench = []

        # Find the two large-6 columns (one per team)
        team_columns = soup.find_all("div", class_=lambda x: x and "large-6" in x and "columns" in x if x else False)

        for col_idx, col in enumerate(team_columns):
            is_home = col_idx == 0

            # Find aufstellung-vereinsseite divs with players
            seite_divs = col.find_all("div", class_="aufstellung-vereinsseite")

            starters = []
            bench = []

            for div in seite_divs:
                player_links = div.find_all("a", href=re.compile(r"/spieler/\d+"))
                if not player_links:
                    continue

                # Check if this is bench (ersatzbank) or starters
                is_bench = "aufstellung-ersatzbank-box" in " ".join(div.get("class", []))

                players = self._parse_player_rows(div, is_starter=not is_bench)

                if is_bench:
                    bench.extend(players)
                else:
                    starters.extend(players)

            if is_home:
                home_starters = starters
                home_bench = bench
            else:
                away_starters = starters
                away_bench = bench

        return home_starters, home_bench, away_starters, away_bench

    def _parse_player_rows(self, container, is_starter: bool) -> list[PlayerLineup]:
        """Parse player rows from a container div."""
        players = []

        # Find all player links
        for link in container.find_all("a", href=re.compile(r"/spieler/\d+")):
            try:
                href = link.get("href", "")
                match = re.search(r"/spieler/(\d+)", href)
                if not match:
                    continue

                player_id = match.group(1)
                player_name = link.get_text(strip=True)

                if not player_name:
                    continue

                # Try to find shirt number
                shirt_number = None
                parent_tr = link.find_parent("tr")
                if parent_tr:
                    num_td = parent_tr.find("td", class_=lambda x: x and "nummer" in x.lower() if x else False)
                    if num_td:
                        try:
                            shirt_number = int(num_td.get_text(strip=True))
                        except ValueError:
                            pass

                players.append(PlayerLineup(
                    player_id=player_id,
                    player_name=player_name,
                    position="",  # Not easily available
                    shirt_number=shirt_number,
                    is_starter=is_starter,
                ))
            except Exception as e:
                logger.debug(f"Error parsing player: {e}")
                continue

        return players

    def _extract_match_info(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extract basic match info from lineup page."""
        info = {}

        # Try to find team names in header
        header = soup.find("div", class_="sb-team")
        if header:
            team_links = header.find_all("a", class_="sb-vereinslink")
            if len(team_links) >= 2:
                info["home_team"] = team_links[0].get_text(strip=True)
                info["away_team"] = team_links[1].get_text(strip=True)

        # Try to find date
        date_box = soup.find("p", class_="sb-datum")
        if date_box:
            date_text = date_box.get_text(strip=True)
            info["date"] = self._parse_date(date_text)

        return info if info else None

    def _extract_formation(self, soup: BeautifulSoup, is_home: bool) -> Optional[str]:
        """Extract formation (e.g., '4-3-3') for a team."""
        # Formations are typically in div.aufstellung-spielfeld-container
        containers = soup.find_all("div", class_="aufstellung-spielfeld-container")
        if not containers:
            return None

        idx = 0 if is_home else 1
        if idx >= len(containers):
            return None

        container = containers[idx]
        formation_el = container.find("div", class_="aufstellung-formation")
        if formation_el:
            return formation_el.get_text(strip=True)

        return None

    def _extract_team_lineup(
        self, soup: BeautifulSoup, is_home: bool
    ) -> tuple[List[PlayerLineup], List[PlayerLineup]]:
        """Extract starters and bench for a team."""
        starters = []
        bench = []

        # Find lineup container
        containers = soup.find_all("div", class_="aufstellung-spielfeld-container")
        if not containers:
            return starters, bench

        idx = 0 if is_home else 1
        if idx >= len(containers):
            return starters, bench

        container = containers[idx]

        # Extract starters from the pitch graphic
        player_items = container.find_all("div", class_="aufstellung-spieler-container")
        for item in player_items:
            player = self._parse_player_item(item, is_starter=True)
            if player:
                starters.append(player)

        # Extract bench - usually in a separate table
        bench_tables = soup.find_all("table", class_="aufstellung-bank")
        if bench_tables and idx < len(bench_tables):
            bench_table = bench_tables[idx]
            rows = bench_table.find_all("tr")
            for row in rows:
                player = self._parse_bench_row(row)
                if player:
                    bench.append(player)

        return starters, bench

    def _parse_player_item(self, item, is_starter: bool) -> Optional[PlayerLineup]:
        """Parse a player item from the pitch graphic."""
        try:
            # Player link
            link = item.find("a")
            if not link:
                return None

            href = link.get("href", "")
            match = re.search(r"/spieler/(\d+)", href)
            player_id = match.group(1) if match else ""

            player_name = link.get_text(strip=True)

            # Position from class or parent
            position = ""
            pos_class = item.get("class", [])
            for cls in pos_class:
                if cls.startswith("pos-"):
                    position = cls.replace("pos-", "").upper()
                    break

            # Shirt number
            shirt_el = item.find("span", class_="aufstellung-rueckennummer")
            shirt_number = None
            if shirt_el:
                try:
                    shirt_number = int(shirt_el.get_text(strip=True))
                except ValueError:
                    pass

            return PlayerLineup(
                player_id=player_id,
                player_name=player_name,
                position=position,
                shirt_number=shirt_number,
                is_starter=is_starter,
            )
        except Exception as e:
            logger.warning(f"Error parsing player item: {e}")
            return None

    def _parse_bench_row(self, row) -> Optional[PlayerLineup]:
        """Parse a bench player from table row."""
        try:
            link = row.find("a", class_="spielprofil_tooltip")
            if not link:
                return None

            href = link.get("href", "")
            match = re.search(r"/spieler/(\d+)", href)
            player_id = match.group(1) if match else ""

            player_name = link.get_text(strip=True)

            return PlayerLineup(
                player_id=player_id,
                player_name=player_name,
                position="SUB",
                is_starter=False,
            )
        except Exception as e:
            logger.warning(f"Error parsing bench row: {e}")
            return None

    def _parse_date(self, date_text: str) -> date:
        """Parse date from Transfermarkt format."""
        # Various formats: "Sat Dec 21, 2024", "21/12/2024", etc.
        formats = [
            "%a %b %d, %Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
            "%b %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_text.strip(), fmt).date()
            except ValueError:
                continue
        return date.today()

    def save_to_db(self, lineups: List[MatchLineup]) -> int:
        """Save lineup records to database."""
        if not lineups:
            return 0

        conn = get_connection()
        if not conn:
            logger.error("Could not connect to database")
            return 0

        try:
            cur = conn.cursor()

            # Ensure table exists
            cur.execute("""
                CREATE TABLE IF NOT EXISTS lineups_historical (
                    id SERIAL PRIMARY KEY,
                    fixture_id TEXT,
                    match_id TEXT,
                    match_date DATE,
                    team_name TEXT NOT NULL,
                    is_home BOOLEAN,
                    formation TEXT,
                    starters JSONB,
                    bench JSONB,
                    source TEXT DEFAULT 'transfermarkt',
                    ingested_at TIMESTAMP DEFAULT NOW()
                )
            """)

            count = 0
            for lineup in lineups:
                import json

                # Insert home team lineup
                cur.execute("""
                    INSERT INTO lineups_historical
                    (fixture_id, match_id, match_date, team_name, is_home, formation, starters, bench, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    lineup.fixture_id,
                    lineup.match_id,
                    lineup.match_date,
                    lineup.home_team,
                    True,
                    lineup.home_formation,
                    json.dumps([vars(p) for p in lineup.home_starters]),
                    json.dumps([vars(p) for p in lineup.home_bench]),
                    lineup.source,
                ))
                count += 1

                # Insert away team lineup
                cur.execute("""
                    INSERT INTO lineups_historical
                    (fixture_id, match_id, match_date, team_name, is_home, formation, starters, bench, source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    lineup.fixture_id,
                    lineup.match_id,
                    lineup.match_date,
                    lineup.away_team,
                    False,
                    lineup.away_formation,
                    json.dumps([vars(p) for p in lineup.away_starters]),
                    json.dumps([vars(p) for p in lineup.away_bench]),
                    lineup.source,
                ))
                count += 1

            conn.commit()
            logger.info(f"Inserted {count} lineup records")
            return count

        except Exception as e:
            logger.error(f"Database error: {e}")
            conn.rollback()
            return 0

        finally:
            conn.close()


if __name__ == "__main__":
    # Test with a known match ID (need to find one)
    scraper = TransfermarktLineupScraper(delay=2.0)

    # Example match ID - this would need to be discovered
    # test_match_id = "4361082"  # Example
    # lineup = scraper.get_match_lineup(test_match_id)

    print("Transfermarkt Lineup Scraper ready.")
    print("Note: Need match ID mapping to link with our fixtures.")
