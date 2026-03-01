"""
Lineups Fetcher - Fetch team lineups and formations from API-Football
Important for formation matchup analysis
"""

import time
from datetime import datetime
from typing import Dict, List, Any
from fetchers.base_fetcher import BaseFetcher


class LineupsFetcher(BaseFetcher):
    """Fetch team lineups, formations, and starting XI for fixtures"""

    def fetch_and_store(
        self,
        fixture_ids: List[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch lineups and store in database

        Args:
            fixture_ids: List of fixture IDs to fetch lineups for

        Returns:
            Dict with processing results
        """

        lineups_processed = 0
        lineups_new = 0
        lineups_updated = 0
        lineups_errors = 0
        api_calls_made = 0

        def store_operation(conn):
            nonlocal lineups_processed, lineups_new, lineups_updated, lineups_errors, api_calls_made

            with conn.cursor() as cursor:
                if fixture_ids:
                    for fixture_id in fixture_ids:
                        try:
                            # Fetch lineups for this fixture
                            api_data = self.make_api_call('fixtures/lineups', {'fixture': fixture_id})
                            api_calls_made += 1

                            if not api_data.get('response'):
                                self.logger.debug(f"No lineups data for fixture {fixture_id}")
                                continue

                            # API returns array of 2 items (home team, away team)
                            for team_lineup in api_data['response']:
                                result = self._process_single_team_lineup(
                                    cursor,
                                    fixture_id,
                                    team_lineup,
                                    api_data
                                )

                                if result['action'] == 'updated':
                                    lineups_updated += 1
                                elif result['action'] == 'inserted':
                                    lineups_new += 1

                                lineups_processed += 1

                            # Rate limiting
                            time.sleep(0.1)

                        except Exception as e:
                            self.logger.error(f"Error processing lineups for fixture {fixture_id}: {str(e)}")
                            lineups_errors += 1
                            continue

                conn.commit()
                return {
                    'processed': lineups_processed,
                    'new': lineups_new,
                    'updated': lineups_updated,
                    'errors': lineups_errors
                }

        # Execute database operation
        db_results = self.safe_db_operation(store_operation)

        # Compile results
        operation_results = {
            'success': True,
            'lineups_processed': db_results['processed'],
            'lineups_new': db_results['new'],
            'lineups_updated': db_results['updated'],
            'lineups_errors': db_results['errors'],
            'api_calls': api_calls_made
        }

        # Log summary
        self.logger.info(
            f"Lineups fetch complete: {db_results['processed']} processed, "
            f"{db_results['new']} new, {db_results['updated']} updated, "
            f"{db_results['errors']} errors, API calls: {api_calls_made}"
        )

        return operation_results

    def _process_single_team_lineup(
        self,
        cursor,
        fixture_id: int,
        team_lineup: Dict[str, Any],
        api_response: Dict[str, Any]
    ) -> Dict[str, str]:
        """Process and store lineup for one team in a match"""

        try:
            # Extract team info
            team = team_lineup.get('team', {})
            team_id = team.get('id')
            team_name = team.get('name')
            team_logo = team.get('logo')

            # Extract formation
            formation = team_lineup.get('formation')

            # Extract coach
            coach_data = team_lineup.get('coach', {})
            coach = coach_data.get('name')
            coach_photo = coach_data.get('photo')

            # Extract starting XI
            starting_xi_raw = team_lineup.get('startXI', [])
            starting_xi = []
            for player in starting_xi_raw:
                player_info = player.get('player', {})
                starting_xi.append({
                    'id': player_info.get('id'),
                    'name': player_info.get('name'),
                    'number': player_info.get('number'),
                    'pos': player_info.get('pos'),  # Position code (G, D, M, F)
                    'grid': player_info.get('grid')  # Position on grid (e.g., "1:1")
                })

            # Extract substitutes
            substitutes_raw = team_lineup.get('substitutes', [])
            substitutes = []
            for player in substitutes_raw:
                player_info = player.get('player', {})
                substitutes.append({
                    'id': player_info.get('id'),
                    'name': player_info.get('name'),
                    'number': player_info.get('number'),
                    'pos': player_info.get('pos'),
                    'grid': player_info.get('grid')
                })

            # Check if record exists
            cursor.execute("""
                SELECT id FROM lineups_raw
                WHERE fixture_id = %s AND team_id = %s AND sport = %s
            """, (fixture_id, team_id, self.sport))

            existing = cursor.fetchone()

            if existing:
                # Update existing record
                cursor.execute("""
                    UPDATE lineups_raw
                    SET team_name = %s,
                        team_logo = %s,
                        formation = %s,
                        starting_xi = %s,
                        substitutes = %s,
                        coach = %s,
                        coach_photo = %s,
                        sport = %s,
                        queried_at = NOW(),
                        raw_response = %s
                    WHERE id = %s
                """, (
                    team_name,
                    team_logo,
                    formation,
                    starting_xi,  # JSONB
                    substitutes,  # JSONB
                    coach,
                    coach_photo,
                    self.sport,
                    api_response,
                    existing[0]
                ))
                return {'action': 'updated', 'id': existing[0]}
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO lineups_raw (
                        fixture_id,
                        team_id,
                        sport,
                        team_name,
                        team_logo,
                        formation,
                        starting_xi,
                        substitutes,
                        coach,
                        coach_photo,
                        queried_at,
                        raw_response
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
                    RETURNING id
                """, (
                    fixture_id,
                    team_id,
                    self.sport,
                    team_name,
                    team_logo,
                    formation,
                    starting_xi,  # JSONB
                    substitutes,  # JSONB
                    coach,
                    coach_photo,
                    api_response
                ))
                new_id = cursor.fetchone()[0]
                return {'action': 'inserted', 'id': new_id}

        except Exception as e:
            self.logger.error(f"Error processing lineup for team {team.get('name')}: {str(e)}")
            raise

    def get_lineups_for_fixture(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Get all lineups for a specific fixture"""

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        id,
                        fixture_id,
                        team_id,
                        team_name,
                        formation,
                        starting_xi,
                        substitutes,
                        coach,
                        queried_at
                    FROM lineups_raw
                    WHERE fixture_id = %s
                    ORDER BY team_id
                """, (fixture_id,))

                return cursor.fetchall()

        results = self.safe_db_operation(query_operation)
        return results if results else []

    def get_formations(self, fixture_id: int) -> Dict[str, str]:
        """
        Get formations for both teams in a fixture

        Returns:
            Dict with 'home_formation' and 'away_formation'
        """

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        team_id,
                        formation
                    FROM lineups_raw
                    WHERE fixture_id = %s
                    ORDER BY team_id
                """, (fixture_id,))

                results = cursor.fetchall()
                
                if len(results) == 2:
                    return {
                        'home_formation': results[0][1],
                        'away_formation': results[1][1]
                    }
                
                return {'home_formation': None, 'away_formation': None}

        results = self.safe_db_operation(query_operation)
        return results if results else {'home_formation': None, 'away_formation': None}

    def count_players_by_position(self, fixture_id: int, team_id: int) -> Dict[str, int]:
        """
        Count starting XI players by position for a team

        Returns:
            Dict with counts for G (Goalkeeper), D (Defender), M (Midfielder), F (Forward)
        """

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT starting_xi
                    FROM lineups_raw
                    WHERE fixture_id = %s AND team_id = %s
                """, (fixture_id, team_id))

                result = cursor.fetchone()
                
                if result and result[0]:
                    starting_xi = result[0]  # This is JSONB, psycopg3 auto-converts
                    
                    counts = {'G': 0, 'D': 0, 'M': 0, 'F': 0}
                    for player in starting_xi:
                        pos = player.get('pos', '')
                        if pos in counts:
                            counts[pos] += 1
                    
                    return counts
                
                return {'G': 0, 'D': 0, 'M': 0, 'F': 0}

        results = self.safe_db_operation(query_operation)
        return results if results else {'G': 0, 'D': 0, 'M': 0, 'F': 0}


if __name__ == '__main__':
    """Test the lineups fetcher"""
    import os
    from dotenv import load_dotenv

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
    fetcher = LineupsFetcher(API_KEY, DB_CONFIG)

    print("=" * 80)
    print("LINEUPS FETCHER TEST")
    print("=" * 80)

    # Test with a match that has lineups
    test_fixture_id = 1035112  # Replace with actual fixture

    print(f"\nTest 1: Fetching lineups for fixture {test_fixture_id}...")
    result = fetcher.fetch_and_store(fixture_ids=[test_fixture_id])
    print(f"Result: {result}")

    # Test 2: Get lineups
    print(f"\nTest 2: Getting stored lineups...")
    lineups = fetcher.get_lineups_for_fixture(test_fixture_id)
    print(f"Found {len(lineups)} team lineups")
    for lineup in lineups:
        print(f"  Team: {lineup['team_name']}")
        print(f"    Formation: {lineup['formation']}")
        print(f"    Coach: {lineup['coach']}")
        print(f"    Starting XI: {len(lineup['starting_xi'])} players")
        print(f"    Substitutes: {len(lineup['substitutes'])} players")

    # Test 3: Get formations
    print(f"\nTest 3: Getting formations...")
    formations = fetcher.get_formations(test_fixture_id)
    print(f"Formations: {formations}")

    # Test 4: Count players by position (if we have team_id)
    if lineups and len(lineups) > 0:
        team_id = lineups[0]['team_id']
        print(f"\nTest 4: Counting players by position for team {team_id}...")
        position_counts = fetcher.count_players_by_position(test_fixture_id, team_id)
        print(f"Position counts: {position_counts}")

    print("\n" + "=" * 80)
    print("LINEUPS FETCHER TEST COMPLETE")
    print("=" * 80)

