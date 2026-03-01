"""
Injuries Fetcher - Fetch player injuries and suspensions from API-Football
Critical for accurate match predictions
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, List

from fetchers.base_fetcher import BaseFetcher
from fetchers.providers.base import DataProvider, ProviderResponse


class InjuriesFetcher(BaseFetcher):
    """Fetch injuries and suspensions for fixtures"""

    def __init__(self, *, db_config: Dict[str, str], provider: DataProvider, sport: str = "football"):
        super().__init__(db_config=db_config, provider=provider, sport=sport)

    def fetch_and_store(
        self,
        fixture_ids: List[int] = None,
        league_id: int = None,
        season: int = None,
        team_id: int = None
    ) -> Dict[str, Any]:
        """
        Fetch injuries/suspensions and store in database

        Args:
            fixture_ids: List of fixture IDs to fetch injuries for
            league_id: League ID (alternative to fixture_ids)
            season: Season year (required if using league_id)
            team_id: Team ID (fetch injuries for specific team)

        Returns:
            Dict with processing results
        """

        injuries_processed = 0
        injuries_new = 0
        injuries_updated = 0
        injuries_errors = 0
        api_calls_made = 0

        def store_operation(conn):
            nonlocal injuries_processed, injuries_new, injuries_updated, injuries_errors, api_calls_made

            with conn.cursor() as cursor:
                # Strategy 1: Fetch by specific fixtures
                if fixture_ids:
                    for fixture_id in fixture_ids:
                        try:
                            provider_response: ProviderResponse = self.provider.fetch_injuries(
                                fixture_ids=[fixture_id]
                            )
                            api_calls_made += provider_response.metadata.get("api_calls", 0)

                            for error in provider_response.errors:
                                self.logger.warning(
                                    f"Provider error fetching injuries for fixture {fixture_id}: {error}"
                                )

                            if not provider_response.records:
                                self.logger.debug(f"No injuries data for fixture {fixture_id}")
                                continue

                            # Process each injury record
                            for record in provider_response.records:
                                injury_data = record.payload
                                result = self._process_single_injury(
                                    cursor, 
                                    fixture_id, 
                                    injury_data
                                )

                                if result['action'] == 'updated':
                                    injuries_updated += 1
                                elif result['action'] == 'inserted':
                                    injuries_new += 1

                                injuries_processed += 1

                            # Rate limiting
                            time.sleep(0.1)

                        except Exception as e:
                            self.logger.error(f"Error processing injuries for fixture {fixture_id}: {str(e)}")
                            injuries_errors += 1
                            continue

                # Strategy 2: Fetch by league and season
                elif league_id and season:
                    provider_response = self.provider.fetch_injuries(
                        league_id=league_id,
                        season=season
                    )
                    api_calls_made += provider_response.metadata.get("api_calls", 0)

                    for error in provider_response.errors:
                        self.logger.warning(
                            f"Provider error fetching injuries for league {league_id}, season {season}: {error}"
                        )

                    if provider_response.records:
                        for record in provider_response.records:
                            injury_data = record.payload
                            try:
                                # Extract fixture_id from injury data
                                fixture_id = injury_data.get('fixture', {}).get('id')
                                if not fixture_id:
                                    continue

                                result = self._process_single_injury(
                                    cursor,
                                    fixture_id,
                                    injury_data
                                )

                                if result['action'] == 'updated':
                                    injuries_updated += 1
                                elif result['action'] == 'inserted':
                                    injuries_new += 1

                                injuries_processed += 1

                            except Exception as e:
                                self.logger.error(f"Error processing injury: {str(e)}")
                                injuries_errors += 1
                                continue

                # Strategy 3: Fetch by team
                elif team_id:
                    provider_response = self.provider.fetch_injuries(team_id=team_id)
                    api_calls_made += provider_response.metadata.get("api_calls", 0)

                    for error in provider_response.errors:
                        self.logger.warning(
                            f"Provider error fetching injuries for team {team_id}: {error}"
                        )

                    if provider_response.records:
                        for record in provider_response.records:
                            injury_data = record.payload
                            try:
                                fixture_id = injury_data.get('fixture', {}).get('id')
                                if not fixture_id:
                                    continue

                                result = self._process_single_injury(
                                    cursor,
                                    fixture_id,
                                    injury_data
                                )

                                if result['action'] == 'updated':
                                    injuries_updated += 1
                                elif result['action'] == 'inserted':
                                    injuries_new += 1

                                injuries_processed += 1

                            except Exception as e:
                                self.logger.error(f"Error processing injury: {str(e)}")
                                injuries_errors += 1
                                continue

                conn.commit()
                return {
                    'processed': injuries_processed,
                    'new': injuries_new,
                    'updated': injuries_updated,
                    'errors': injuries_errors
                }

        # Execute database operation
        db_results = self.safe_db_operation(store_operation)

        # Compile results
        operation_results = {
            'success': True,
            'injuries_processed': db_results['processed'],
            'injuries_new': db_results['new'],
            'injuries_updated': db_results['updated'],
            'injuries_errors': db_results['errors'],
            'api_calls': api_calls_made
        }

        # Log summary
        self.logger.info(
            f"Injuries fetch complete: {db_results['processed']} processed, "
            f"{db_results['new']} new, {db_results['updated']} updated, "
            f"{db_results['errors']} errors, API calls: {api_calls_made}"
        )

        return operation_results

    def _process_single_injury(
        self,
        cursor,
        fixture_id: int,
        injury_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """Process and store a single injury record"""

        try:
            # Extract data
            player = injury_data.get('player', {})
            team = injury_data.get('team', {})

            player_id = player.get('id')
            player_name = player.get('name')
            player_position = player.get('type')  # 'Goalkeeper', 'Defender', etc.
            player_photo = player.get('photo')

            team_id = team.get('id')

            fixture_info = injury_data.get('fixture', {})
            league_info = injury_data.get('league', {})

            # Injury details
            injury_type = player.get('reason', '')  # This might be 'injury' or 'suspension'
            reason = player.get('reason', '')  # Specific reason like 'Hamstring', 'Red Card'

            # Try to determine if it's injury or suspension from reason
            reason_lower = reason.lower() if reason else ''
            if 'suspension' in reason_lower or 'card' in reason_lower or 'ban' in reason_lower:
                injury_type = 'suspension'
            elif 'injury' in reason_lower or 'muscle' in reason_lower or 'ankle' in reason_lower:
                injury_type = 'injury'
            else:
                injury_type = 'unknown'

            # Check if record exists
            cursor.execute("""
                SELECT id FROM injuries_raw
                WHERE fixture_id = %s
                  AND team_id = %s
                  AND player_id = %s
                  AND injury_type = %s
            """, (fixture_id, team_id, player_id, injury_type))

            existing = cursor.fetchone()

            if existing:
                # Update existing record
                cursor.execute("""
                    UPDATE injuries_raw
                    SET player_name = %s,
                        player_position = %s,
                        player_photo = %s,
                        reason = %s,
                        queried_at = NOW(),
                        raw_response = %s,
                        sport = %s
                    WHERE id = %s
                """, (
                    player_name,
                    player_position,
                    player_photo,
                    reason,
                    json.dumps(injury_data),
                    self.sport,
                    existing[0]
                ))
                return {'action': 'updated', 'id': existing[0]}
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO injuries_raw (
                        fixture_id,
                        team_id,
                        player_id,
                        player_name,
                        player_position,
                        player_photo,
                        injury_type,
                        reason,
                        queried_at,
                        raw_response,
                        sport
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s)
                    RETURNING id
                """, (
                    fixture_id,
                    team_id,
                    player_id,
                    player_name,
                    player_position,
                    player_photo,
                    injury_type,
                    reason,
                    json.dumps(injury_data),
                    self.sport
                ))
                new_id = cursor.fetchone()[0]
                return {'action': 'inserted', 'id': new_id}

        except Exception as e:
            self.logger.error(f"Error processing injury for player {player.get('name')}: {str(e)}")
            raise

    def get_injuries_for_fixture(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Get all injuries for a specific fixture"""

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        id,
                        fixture_id,
                        team_id,
                        player_id,
                        player_name,
                        player_position,
                        injury_type,
                        reason,
                        queried_at,
                        raw_response
                    FROM injuries_raw
                    WHERE fixture_id = %s
                    ORDER BY team_id, player_position, player_name
                """, (fixture_id,))

                return cursor.fetchall()

        results = self.safe_db_operation(query_operation)
        return results if results else []

    def count_injuries_by_team(self, fixture_id: int) -> Dict[int, Dict[str, int]]:
        """
        Count injuries/suspensions per team for a fixture

        Returns:
            Dict[team_id, {'injuries': count, 'suspensions': count, 'total': count}]
        """

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        team_id,
                        injury_type,
                        COUNT(*) as count
                    FROM injuries_raw
                    WHERE fixture_id = %s
                    GROUP BY team_id, injury_type
                """, (fixture_id,))

                results = cursor.fetchall()
                
                # Organize by team_id
                team_counts = {}
                for row in results:
                    team_id, injury_type, count = row
                    if team_id not in team_counts:
                        team_counts[team_id] = {
                            'injuries': 0,
                            'suspensions': 0,
                            'unknown': 0,
                            'total': 0
                        }
                    
                    if injury_type == 'injury':
                        team_counts[team_id]['injuries'] = count
                    elif injury_type == 'suspension':
                        team_counts[team_id]['suspensions'] = count
                    else:
                        team_counts[team_id]['unknown'] = count
                    
                    team_counts[team_id]['total'] += count

                return team_counts

        results = self.safe_db_operation(query_operation)
        return results if results else {}


if __name__ == '__main__':
    """Test the injuries fetcher"""
    import os
    from dotenv import load_dotenv
    from fetchers.providers.api_football import ApiFootballProvider

    load_dotenv()

    # Configuration
    API_KEY = os.getenv('FOOTBALL_API_KEY')
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'database': os.getenv('DB_NAME', 'clarity_odds'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD'),
        'port': int(os.getenv('DB_PORT', 5432))
    }

    # Create fetcher
    provider = ApiFootballProvider(API_KEY)
    fetcher = InjuriesFetcher(db_config=DB_CONFIG, provider=provider)

    print("=" * 80)
    print("INJURIES FETCHER TEST")
    print("=" * 80)

    # Test 1: Fetch injuries for a specific fixture
    # Replace with actual fixture ID
    test_fixture_id = 1035112  # Example fixture

    print(f"\nTest 1: Fetching injuries for fixture {test_fixture_id}...")
    result = fetcher.fetch_and_store(fixture_ids=[test_fixture_id])
    print(f"Result: {result}")

    # Test 2: Get injuries for fixture
    print(f"\nTest 2: Getting stored injuries for fixture {test_fixture_id}...")
    injuries = fetcher.get_injuries_for_fixture(test_fixture_id)
    print(f"Found {len(injuries)} injury records")
    for injury in injuries[:5]:  # Show first 5
        print(f"  - {injury['player_name']} ({injury['player_position']}): {injury['injury_type']} - {injury['reason']}")

    # Test 3: Count injuries by team
    print(f"\nTest 3: Counting injuries by team for fixture {test_fixture_id}...")
    counts = fetcher.count_injuries_by_team(test_fixture_id)
    print(f"Injury counts by team: {counts}")

    print("\n" + "=" * 80)
    print("INJURIES FETCHER TEST COMPLETE")
    print("=" * 80)
