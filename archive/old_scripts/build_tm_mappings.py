#!/usr/bin/env python3
"""
Build Transfermarkt Match ID Mappings

Maps our fixture IDs to Transfermarkt spielbericht IDs for lineup scraping.

Strategy:
1. Iterate through Premier League matchdays on Transfermarkt
2. For each match, fetch the spielbericht page to get teams and date
3. Match with our fixtures table
4. Store mapping in tm_match_mapping table

Usage:
    python scripts/build_tm_mappings.py --season 2025
    python scripts/build_tm_mappings.py --season 2025 --matchday 1
"""

import argparse
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
from src.ingestion.transfermarkt_teams import PL_TEAMS, normalize_team_name

BASE_URL = "https://www.transfermarkt.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def fetch(url: str, delay: float = 2.0) -> str | None:
    """Fetch URL with rate limiting."""
    time.sleep(delay)
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}")
        return None


def get_matchday_matches(season: str, matchday: int) -> list[str]:
    """Get all match IDs from a specific matchday."""
    url = f"{BASE_URL}/premier-league/spieltag/wettbewerb/GB1/saison_id/{season}/spieltag/{matchday}"
    print(f"Fetching matchday {matchday}...")

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    match_ids = []

    for link in soup.find_all("a", href=re.compile(r"/spielbericht/index/spielbericht/")):
        href = link.get("href", "")
        match = re.search(r"/spielbericht/(\d+)", href)
        if match:
            match_id = match.group(1)
            if match_id not in match_ids:
                match_ids.append(match_id)

    print(f"  Found {len(match_ids)} matches")
    return match_ids


def get_match_details(tm_match_id: str) -> dict | None:
    """Fetch match details from spielbericht page."""
    url = f"{BASE_URL}/spielbericht/index/spielbericht/{tm_match_id}"

    html = fetch(url, delay=1.5)
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

        for i, team in enumerate(teams[:2]):
            href = team.get("href", "")
            id_match = re.search(r"/verein/(\d+)", href)
            if id_match:
                if i == 0:
                    result["home_id"] = id_match.group(1)
                else:
                    result["away_id"] = id_match.group(1)

    # Get date
    date_box = soup.find("p", class_="sb-datum")
    if date_box:
        date_text = date_box.get_text(strip=True)
        parts = date_text.split("|")
        if len(parts) >= 2:
            date_str = parts[1].strip()
            date_str = re.sub(r"^[A-Za-z]+,\s*", "", date_str)
            result["match_date"] = parse_date(date_str)

    return result


def parse_date(date_text: str) -> date | None:
    """Parse date from Transfermarkt format."""
    formats = [
        "%d/%m/%y",
        "%d/%m/%Y",
        "%m/%d/%y",
        "%m/%d/%Y",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def find_fixture_id(conn, match_date: date, home_id: str, away_id: str) -> str | None:
    """Find our fixture ID matching a Transfermarkt match."""
    # Map TM team IDs to fixture table names
    tm_id_to_fixture_name = {
        "11": "Arsenal",
        "405": "Aston Villa",
        "989": "Bournemouth",
        "1148": "Brentford",
        "1237": "Brighton",
        "631": "Chelsea",
        "873": "Crystal Palace",
        "29": "Everton",
        "931": "Fulham",
        "677": "Ipswich",
        "1003": "Leicester",
        "31": "Liverpool",
        "281": "Manchester City",
        "985": "Manchester Utd",
        "762": "Newcastle Utd",
        "703": "Nott'ham Forest",
        "180": "Southampton",
        "148": "Tottenham",
        "379": "West Ham",
        "543": "Wolves",
        # Additional teams from different leagues/promoted
        "399": "Leeds United",
        "71": "Burnley",
        "289": "Sunderland",  # Sunderland AFC
        "1132": "Burnley",    # Some seasons use different ID
    }

    home_name = tm_id_to_fixture_name.get(home_id)
    away_name = tm_id_to_fixture_name.get(away_id)

    if not home_name or not away_name:
        print(f"    Unknown team ID: home={home_id}, away={away_id}")
        return None

    cur = conn.cursor()

    # Try exact match
    cur.execute(
        """
        SELECT id FROM fixtures
        WHERE date = %s
        AND home_team = %s
        AND away_team = %s
        """,
        (match_date, home_name, away_name)
    )
    row = cur.fetchone()
    if row:
        return row[0]

    # Try with LIKE for minor variations
    cur.execute(
        """
        SELECT id FROM fixtures
        WHERE date = %s
        AND home_team LIKE %s
        AND away_team LIKE %s
        """,
        (match_date, f"%{home_name}%", f"%{away_name}%")
    )
    row = cur.fetchone()
    return row[0] if row else None


def save_mapping(conn, fixture_id: str, tm_match_id: str, details: dict) -> bool:
    """Save mapping to database."""
    cur = conn.cursor()

    # Create table if not exists
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

    cur.execute(
        """
        INSERT INTO tm_match_mapping
        (fixture_id, tm_match_id, match_date, home_team, away_team, tm_home_id, tm_away_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (fixture_id) DO UPDATE SET
            tm_match_id = EXCLUDED.tm_match_id
        """,
        (
            fixture_id,
            tm_match_id,
            details["match_date"],
            details["home_team"],
            details["away_team"],
            details["home_id"],
            details["away_id"],
        )
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Build TM match ID mappings")
    parser.add_argument("--season", default="2025", help="Season start year")
    parser.add_argument("--matchday", type=int, help="Specific matchday to process")
    parser.add_argument("--start", type=int, default=1, help="Start matchday")
    parser.add_argument("--end", type=int, default=38, help="End matchday")
    args = parser.parse_args()

    conn = get_connection()
    if not conn:
        print("Could not connect to database")
        return 1

    try:
        matchdays = [args.matchday] if args.matchday else range(args.start, args.end + 1)
        total_mapped = 0
        total_failed = 0

        for matchday in matchdays:
            match_ids = get_matchday_matches(args.season, matchday)

            for tm_match_id in match_ids:
                details = get_match_details(tm_match_id)
                if not details or not details["match_date"]:
                    print(f"  Could not get details for {tm_match_id}")
                    total_failed += 1
                    continue

                fixture_id = find_fixture_id(
                    conn,
                    details["match_date"],
                    details["home_id"],
                    details["away_id"]
                )

                if fixture_id:
                    save_mapping(conn, fixture_id, tm_match_id, details)
                    print(f"  {details['home_team']} vs {details['away_team']} -> {fixture_id}")
                    total_mapped += 1
                else:
                    print(f"  No fixture found: {details['home_team']} vs {details['away_team']} ({details['match_date']})")
                    total_failed += 1

            conn.commit()

        print(f"\nTotal mapped: {total_mapped}, Failed: {total_failed}")

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
