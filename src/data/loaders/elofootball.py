#!/usr/bin/env python3
"""
EloFootball.com Data Loader
Fetches ELO ratings from elofootball.com
"""

import requests
import logging
from typing import Optional, Dict
from datetime import datetime
import re

logger = logging.getLogger(__name__)


class EloFootballLoader:
    """
    Load ELO ratings from elofootball.com
    """
    
    BASE_URL = "https://elofootball.com"
    
    # Team name to elofootball club ID mapping (Premier League)
    TEAM_TO_CLUB_ID = {
        'Arsenal': 246,
        'Aston Villa': 250,
        'Bournemouth': 251,
        'Brentford': 252,
        'Brighton': 253,
        'Burnley': 254,
        'Chelsea': 255,
        'Crystal Palace': 256,
        'Everton': 257,
        'Fulham': 258,
        'Leeds': 259,
        'Liverpool': 260,
        'Manchester City': 261,
        'Manchester United': 262,
        'Newcastle': 263,
        'Nottingham Forest': 264,
        'Sunderland': 265,
        'Tottenham': 266,
        'West Ham': 267,
        'Wolves': 268,
    }
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def get_team_elo(self, team_name: str, date: Optional[datetime] = None, season: int = 2025) -> Optional[float]:
        """
        Get ELO rating for a team from elofootball.com
        
        Args:
            team_name: Team name
            date: Date to get ELO for (if None, uses current)
            season: Season year
        
        Returns:
            ELO rating or None if not found
        """
        club_id = self.TEAM_TO_CLUB_ID.get(team_name)
        if not club_id:
            logger.warning(f"Team '{team_name}' not found in club ID mapping")
            return None
        
        try:
            # Elofootball.com uses club.php?clubid=X&season=Y format
            season_str = f"{season-1}-{season}"
            url = f"{self.BASE_URL}/club.php?clubid={club_id}&season={season_str}"
            
            logger.info(f"Fetching ELO for {team_name} from {url}")
            response = self.session.get(url, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch: status {response.status_code}")
                return None
            
            # Parse HTML to find ELO rating
            # ELO is usually displayed in the page, need to extract it
            html = response.text
            
            # Try to find ELO in various formats
            # Look for patterns like "ELO: 1937" or "Rating: 1937" or in a table
            elo_patterns = [
                r'ELO[:\s]+(\d+)',
                r'Rating[:\s]+(\d+)',
                r'Elo[:\s]+(\d+)',
                r'<td[^>]*>(\d{4})</td>',  # 4-digit number in table cell
                r'current.*?(\d{4})',  # Current rating followed by 4 digits
            ]
            
            for pattern in elo_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    try:
                        # Take the first reasonable ELO value (between 1000-3000)
                        for match in matches:
                            elo = float(match)
                            if 1000 <= elo <= 3000:
                                logger.info(f"Found ELO for {team_name}: {elo}")
                                return elo
                    except ValueError:
                        continue
            
            # Alternative: Look for JSON data in the page
            json_pattern = r'var\s+eloData\s*=\s*({[^}]+})'
            json_match = re.search(json_pattern, html)
            if json_match:
                import json
                try:
                    data = json.loads(json_match.group(1))
                    if 'elo' in data:
                        return float(data['elo'])
                except:
                    pass
            
            logger.warning(f"Could not find ELO for {team_name} in HTML")
            return None
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error for {team_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error parsing ELO for {team_name}: {e}")
            return None
    
    def verify_elo_values(self, team_elos: Dict[str, float]) -> Dict[str, Dict]:
        """
        Verify ELO values against elofootball.com
        
        Args:
            team_elos: Dict of {team_name: elo_value}
        
        Returns:
            Dict with verification results
        """
        results = {}
        
        for team_name, expected_elo in team_elos.items():
            actual_elo = self.get_team_elo(team_name)
            
            results[team_name] = {
                'expected': expected_elo,
                'actual': actual_elo,
                'match': actual_elo is not None and abs(actual_elo - expected_elo) < 10,  # Within 10 points
                'difference': actual_elo - expected_elo if actual_elo else None
            }
        
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    loader = EloFootballLoader()
    
    # Test with provided values
    test_elos = {
        'Leeds': 1937,
        'Aston Villa': 2151
    }
    
    print("Verifying ELO values from elofootball.com...")
    print()
    
    results = loader.verify_elo_values(test_elos)
    
    for team, result in results.items():
        print(f"{team}:")
        print(f"  Expected: {result['expected']}")
        print(f"  Actual: {result['actual']}")
        if result['actual']:
            print(f"  Difference: {result['difference']:.0f}")
            print(f"  Match: {'✅' if result['match'] else '❌'}")
        else:
            print(f"  Status: ❌ Could not fetch")
        print()






