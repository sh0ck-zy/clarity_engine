"""
ZeroZero.pt web scraper provider implementation.

This provider scrapes data from zerozero.pt to supplement API-Football data,
particularly for Portuguese league specific information, injuries, and detailed statistics.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .base import DataProvider, ProviderRecord, ProviderResponse


class ZeroZeroProvider(DataProvider):
    """Web scraper for zerozero.pt football data."""

    name = "zerozero"

    def __init__(
        self,
        *,
        base_url: str = "https://www.zerozero.pt",
        min_request_interval: float = 1.0,  # Be respectful with requests
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
        user_agent: str = "Mozilla/5.0 (compatible; ClarityOdds/1.0; +https://github.com/your-repo)",
    ):
        self.base_url = base_url.rstrip('/')
        self.min_request_interval = min_request_interval
        self.last_request_time = 0.0
        
        self.session = session or requests.Session()
        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-PT,pt;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        self.logger = logger or logging.getLogger(self.__class__.__name__)

    def _rate_limit(self) -> None:
        """Ensure we don't make requests too frequently."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()

    def _make_request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Optional[BeautifulSoup]:
        """Make a rate-limited request and return parsed HTML."""
        self._rate_limit()
        
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            # Handle encoding issues common with Portuguese sites
            response.encoding = response.apparent_encoding or 'utf-8'
            
            return BeautifulSoup(response.text, 'lxml')
            
        except requests.RequestException as e:
            self.logger.error(f"Request failed for {url}: {e}")
            return None

    def _normalize_team_name(self, name: str) -> str:
        """Normalize team names to match API-Football format."""
        # Common Portuguese team name mappings
        mappings = {
            'Sporting CP': 'Sporting',
            'Sporting': 'Sporting',
            'SL Benfica': 'Benfica',
            'Benfica': 'Benfica',
            'FC Porto': 'Porto',
            'Porto': 'Porto',
            'SC Braga': 'Braga',
            'Braga': 'Braga',
        }
        return mappings.get(name.strip(), name.strip())

    def fetch_fixtures(
        self,
        *,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        fixture_ids: Optional[List[int]] = None,
    ) -> ProviderResponse:
        """Fetch fixtures from zerozero.pt."""
        # For now, focus on Portuguese leagues
        if league_id and league_id not in [94, 95]:  # Liga Portugal, Liga Portugal 2
            return ProviderResponse(errors=["ZeroZero only supports Portuguese leagues"])
        
        response = ProviderResponse()
        
        # Map to zerozero competition IDs
        competition_map = {
            94: "1",  # Liga Portugal
            95: "2",  # Liga Portugal 2
        }
        
        comp_id = competition_map.get(league_id, "1")
        
        # Build URL for fixtures
        url = f"{self.base_url}/competition.php?id_competition={comp_id}"
        
        soup = self._make_request(url)
        if not soup:
            response.errors.append("Failed to fetch fixtures page")
            return response
        
        # Parse fixtures from the page
        fixtures = self._parse_fixtures(soup, league_id)
        
        for fixture in fixtures:
            response.records.append(ProviderRecord(
                resource="fixtures",
                payload=fixture,
                source=self.name,
                metadata={"scraped_at": datetime.now().isoformat()}
            ))
        
        return response

    def _parse_fixtures(self, soup: BeautifulSoup, league_id: Optional[int]) -> List[Dict[str, Any]]:
        """Parse fixtures from the HTML page."""
        fixtures = []
        
        # Look for match rows - this will need to be updated based on actual HTML structure
        match_rows = soup.find_all('tr', class_=re.compile(r'match|game|fixture'))
        
        for row in match_rows:
            try:
                # Extract match data - structure will depend on actual HTML
                home_team_elem = row.find('td', class_=re.compile(r'home|team1'))
                away_team_elem = row.find('td', class_=re.compile(r'away|team2'))
                date_elem = row.find('td', class_=re.compile(r'date|time'))
                score_elem = row.find('td', class_=re.compile(r'score|result'))
                
                if not all([home_team_elem, away_team_elem]):
                    continue
                
                home_team = self._normalize_team_name(home_team_elem.get_text(strip=True))
                away_team = self._normalize_team_name(away_team_elem.get_text(strip=True))
                
                fixture = {
                    'home_team': home_team,
                    'away_team': away_team,
                    'league_id': league_id,
                    'source': self.name,
                }
                
                if date_elem:
                    fixture['date'] = self._parse_date(date_elem.get_text(strip=True))
                
                if score_elem:
                    score_text = score_elem.get_text(strip=True)
                    if '-' in score_text:
                        home_score, away_score = score_text.split('-', 1)
                        fixture['home_score'] = int(home_score.strip())
                        fixture['away_score'] = int(away_score.strip())
                
                fixtures.append(fixture)
                
            except Exception as e:
                self.logger.warning(f"Failed to parse fixture row: {e}")
                continue
        
        return fixtures

    def _parse_date(self, date_str: str) -> str:
        """Parse Portuguese date format to ISO format."""
        # This will need to be implemented based on actual date formats used
        # Common Portuguese formats: "15/01/2024", "15 Jan 2024", etc.
        try:
            # Try common formats
            for fmt in ['%d/%m/%Y', '%d %b %Y', '%d %B %Y']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.isoformat()
                except ValueError:
                    continue
        except Exception:
            pass
        
        return date_str  # Return as-is if parsing fails

    def fetch_predictions(
        self,
        *,
        fixture_ids: List[int],
    ) -> ProviderResponse:
        """ZeroZero doesn't provide predictions - delegate to other providers."""
        return ProviderResponse(errors=["ZeroZero doesn't provide prediction data"])

    def fetch_odds(
        self,
        *,
        fixture_id: int,
        bookmaker_id: Optional[str] = None,
        market: Optional[str] = None,
    ) -> ProviderResponse:
        """ZeroZero doesn't provide odds - delegate to other providers."""
        return ProviderResponse(errors=["ZeroZero doesn't provide odds data"])

    def fetch_injuries(
        self,
        *,
        fixture_ids: Optional[List[int]] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        team_id: Optional[int] = None,
    ) -> ProviderResponse:
        """Fetch injury data from zerozero.pt."""
        response = ProviderResponse()
        
        # This would need to be implemented based on actual site structure
        # For now, return empty response
        self.logger.info("Injury data scraping not yet implemented")
        
        return response

    def fetch_team_statistics(
        self,
        *,
        team_id: Optional[int] = None,
        team_name: Optional[str] = None,
        season: Optional[int] = None,
    ) -> ProviderResponse:
        """Fetch detailed team statistics from zerozero.pt."""
        response = ProviderResponse()
        
        if not team_name:
            response.errors.append("Team name required for ZeroZero statistics")
            return response
        
        # Build team page URL
        team_slug = team_name.lower().replace(' ', '-')
        url = f"{self.base_url}/team.php?id_team={team_slug}"
        
        soup = self._make_request(url)
        if not soup:
            response.errors.append(f"Failed to fetch team page for {team_name}")
            return response
        
        # Parse team statistics
        stats = self._parse_team_statistics(soup, team_name)
        
        if stats:
            response.records.append(ProviderRecord(
                resource="team_statistics",
                payload=stats,
                source=self.name,
                metadata={"scraped_at": datetime.now().isoformat()}
            ))
        
        return response

    def _parse_team_statistics(self, soup: BeautifulSoup, team_name: str) -> Dict[str, Any]:
        """Parse team statistics from the team page."""
        stats = {
            'team_name': team_name,
            'source': self.name,
        }
        
        # Look for statistics sections
        # This will need to be implemented based on actual HTML structure
        stats_sections = soup.find_all('div', class_=re.compile(r'stats|statistics|data'))
        
        for section in stats_sections:
            # Parse different types of statistics
            # Goals, possession, shots, etc.
            pass
        
        return stats

    def fetch_match_statistics(
        self,
        *,
        fixture_id: int,
        match_url: Optional[str] = None,
    ) -> ProviderResponse:
        """Fetch detailed match statistics from zerozero.pt."""
        response = ProviderResponse()
        
        if not match_url:
            response.errors.append("Match URL required for ZeroZero statistics")
            return response
        
        soup = self._make_request(match_url)
        if not soup:
            response.errors.append(f"Failed to fetch match page for fixture {fixture_id}")
            return response
        
        # Parse match statistics
        stats = self._parse_match_statistics(soup, fixture_id)
        
        if stats:
            response.records.append(ProviderRecord(
                resource="match_statistics",
                payload=stats,
                source=self.name,
                metadata={"scraped_at": datetime.now().isoformat()}
            ))
        
        return response

    def _parse_match_statistics(self, soup: BeautifulSoup, fixture_id: int) -> Dict[str, Any]:
        """Parse match statistics from the match page."""
        stats = {
            'fixture_id': fixture_id,
            'source': self.name,
        }
        
        # Look for statistics tables
        stats_tables = soup.find_all('table', class_=re.compile(r'stats|statistics'))
        
        for table in stats_tables:
            # Parse possession, shots, cards, etc.
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                if len(cells) >= 3:
                    stat_name = cells[0].get_text(strip=True)
                    home_value = cells[1].get_text(strip=True)
                    away_value = cells[2].get_text(strip=True)
                    
                    # Map common statistics
                    if 'posse' in stat_name.lower():
                        stats['possession_home'] = self._parse_percentage(home_value)
                        stats['possession_away'] = self._parse_percentage(away_value)
                    elif 'remate' in stat_name.lower():
                        stats['shots_home'] = self._parse_number(home_value)
                        stats['shots_away'] = self._parse_number(away_value)
        
        return stats

    def _parse_percentage(self, value: str) -> Optional[float]:
        """Parse percentage value from string."""
        try:
            # Remove % and convert to float
            clean_value = value.replace('%', '').strip()
            return float(clean_value)
        except (ValueError, AttributeError):
            return None

    def _parse_number(self, value: str) -> Optional[int]:
        """Parse integer value from string."""
        try:
            # Extract numbers only
            numbers = re.findall(r'\d+', value)
            return int(numbers[0]) if numbers else None
        except (ValueError, IndexError):
            return None

