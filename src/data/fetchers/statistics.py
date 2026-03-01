"""
Statistics Fetcher - Fetch match statistics including xG from API-Football
Critical for model quality (xG is better than actual goals)
"""

import time
from datetime import datetime
from typing import Dict, List, Any
from fetchers.base_fetcher import BaseFetcher


class StatisticsFetcher(BaseFetcher):
    """Fetch match statistics (xG, shots, possession, etc.) for fixtures"""

    def fetch_and_store(
        self,
        fixture_ids: List[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch match statistics and store in database

        Args:
            fixture_ids: List of fixture IDs to fetch statistics for

        Returns:
            Dict with processing results
        """

        statistics_processed = 0
        statistics_new = 0
        statistics_updated = 0
        statistics_errors = 0
        api_calls_made = 0

        def store_operation(conn):
            nonlocal statistics_processed, statistics_new, statistics_updated, statistics_errors, api_calls_made

            with conn.cursor() as cursor:
                if fixture_ids:
                    for fixture_id in fixture_ids:
                        try:
                            # Fetch statistics for this fixture
                            api_data = self.make_api_call('fixtures/statistics', {'fixture': fixture_id})
                            api_calls_made += 1

                            if not api_data.get('response'):
                                self.logger.debug(f"No statistics data for fixture {fixture_id}")
                                continue

                            # API returns array of 2 items (home team, away team)
                            for team_stats in api_data['response']:
                                result = self._process_single_team_stats(
                                    cursor,
                                    fixture_id,
                                    team_stats,
                                    api_data
                                )

                                if result['action'] == 'updated':
                                    statistics_updated += 1
                                elif result['action'] == 'inserted':
                                    statistics_new += 1

                                statistics_processed += 1

                            # Rate limiting
                            time.sleep(0.1)

                        except Exception as e:
                            self.logger.error(f"Error processing statistics for fixture {fixture_id}: {str(e)}")
                            statistics_errors += 1
                            continue

                conn.commit()
                return {
                    'processed': statistics_processed,
                    'new': statistics_new,
                    'updated': statistics_updated,
                    'errors': statistics_errors
                }

        # Execute database operation
        db_results = self.safe_db_operation(store_operation)

        # Compile results
        operation_results = {
            'success': True,
            'statistics_processed': db_results['processed'],
            'statistics_new': db_results['new'],
            'statistics_updated': db_results['updated'],
            'statistics_errors': db_results['errors'],
            'api_calls': api_calls_made
        }

        # Log summary
        self.logger.info(
            f"Statistics fetch complete: {db_results['processed']} processed, "
            f"{db_results['new']} new, {db_results['updated']} updated, "
            f"{db_results['errors']} errors, API calls: {api_calls_made}"
        )

        return operation_results

    def _process_single_team_stats(
        self,
        cursor,
        fixture_id: int,
        team_stats: Dict[str, Any],
        api_response: Dict[str, Any]
    ) -> Dict[str, str]:
        """Process and store statistics for one team in a match"""

        try:
            # Extract team info
            team = team_stats.get('team', {})
            team_id = team.get('id')
            
            # Extract statistics array
            statistics = team_stats.get('statistics', [])
            
            # Helper function to find stat value by type
            def get_stat(stat_type: str):
                for stat in statistics:
                    if stat.get('type') == stat_type:
                        value = stat.get('value')
                        # Handle different value types
                        if value is None:
                            return None
                        if isinstance(value, str):
                            # Remove % sign if present
                            if '%' in value:
                                return float(value.replace('%', ''))
                            # Try to convert to number
                            try:
                                return float(value) if '.' in value else int(value)
                            except:
                                return None
                        return value
                return None

            # Extract all statistics
            expected_goals = get_stat('expected_goals')  # xG ⭐ CRITICAL
            
            # Shooting
            shots_total = get_stat('Total Shots')
            shots_on_target = get_stat('Shots on Goal')
            shots_off_target = get_stat('Shots off Goal')
            shots_inside_box = get_stat('Shots insidebox')
            shots_outside_box = get_stat('Shots outsidebox')
            blocked_shots = get_stat('Blocked Shots')
            
            # Possession
            possession_pct = get_stat('Ball Possession')
            
            # Passing
            passes_total = get_stat('Total passes')
            passes_completed = get_stat('Passes accurate')
            passes_accuracy_pct = get_stat('Passes %')
            passes_key = get_stat('Key Passes')
            
            # Attack
            attacks_total = get_stat('Total attacks')  # Might not exist
            attacks_dangerous = get_stat('Dangerous attacks')  # Might not exist
            
            # Other
            corners = get_stat('Corner Kicks')
            offsides = get_stat('Offsides')
            fouls = get_stat('Fouls')
            yellow_cards = get_stat('Yellow Cards')
            red_cards = get_stat('Red Cards')
            goalkeeper_saves = get_stat('Goalkeeper Saves')

            # Check if record exists
            cursor.execute("""
                SELECT id FROM statistics_raw
                WHERE fixture_id = %s AND team_id = %s
            """, (fixture_id, team_id))

            existing = cursor.fetchone()

            if existing:
                # Update existing record
                cursor.execute("""
                    UPDATE statistics_raw
                    SET expected_goals = %s,
                        shots_total = %s,
                        shots_on_target = %s,
                        shots_off_target = %s,
                        shots_inside_box = %s,
                        shots_outside_box = %s,
                        blocked_shots = %s,
                        possession_pct = %s,
                        passes_total = %s,
                        passes_completed = %s,
                        passes_accuracy_pct = %s,
                        passes_key = %s,
                        attacks_total = %s,
                        attacks_dangerous = %s,
                        corners = %s,
                        offsides = %s,
                        fouls = %s,
                        yellow_cards = %s,
                        red_cards = %s,
                        goalkeeper_saves = %s,
                        queried_at = NOW(),
                        raw_response = %s
                    WHERE id = %s
                """, (
                    expected_goals,
                    shots_total,
                    shots_on_target,
                    shots_off_target,
                    shots_inside_box,
                    shots_outside_box,
                    blocked_shots,
                    possession_pct,
                    passes_total,
                    passes_completed,
                    passes_accuracy_pct,
                    passes_key,
                    attacks_total,
                    attacks_dangerous,
                    corners,
                    offsides,
                    fouls,
                    yellow_cards,
                    red_cards,
                    goalkeeper_saves,
                    api_response,
                    existing[0]
                ))
                return {'action': 'updated', 'id': existing[0]}
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO statistics_raw (
                        fixture_id,
                        team_id,
                        expected_goals,
                        shots_total,
                        shots_on_target,
                        shots_off_target,
                        shots_inside_box,
                        shots_outside_box,
                        blocked_shots,
                        possession_pct,
                        passes_total,
                        passes_completed,
                        passes_accuracy_pct,
                        passes_key,
                        attacks_total,
                        attacks_dangerous,
                        corners,
                        offsides,
                        fouls,
                        yellow_cards,
                        red_cards,
                        goalkeeper_saves,
                        queried_at,
                        raw_response
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, NOW(), %s
                    )
                    RETURNING id
                """, (
                    fixture_id,
                    team_id,
                    expected_goals,
                    shots_total,
                    shots_on_target,
                    shots_off_target,
                    shots_inside_box,
                    shots_outside_box,
                    blocked_shots,
                    possession_pct,
                    passes_total,
                    passes_completed,
                    passes_accuracy_pct,
                    passes_key,
                    attacks_total,
                    attacks_dangerous,
                    corners,
                    offsides,
                    fouls,
                    yellow_cards,
                    red_cards,
                    goalkeeper_saves,
                    api_response
                ))
                new_id = cursor.fetchone()[0]
                return {'action': 'inserted', 'id': new_id}

        except Exception as e:
            self.logger.error(f"Error processing statistics for team {team.get('name')}: {str(e)}")
            raise

    def get_statistics_for_fixture(self, fixture_id: int) -> List[Dict[str, Any]]:
        """Get all statistics for a specific fixture"""

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        id,
                        fixture_id,
                        team_id,
                        expected_goals,
                        shots_total,
                        shots_on_target,
                        possession_pct,
                        passes_total,
                        passes_completed,
                        corners,
                        fouls,
                        yellow_cards,
                        red_cards,
                        queried_at
                    FROM statistics_raw
                    WHERE fixture_id = %s
                    ORDER BY team_id
                """, (fixture_id,))

                return cursor.fetchall()

        results = self.safe_db_operation(query_operation)
        return results if results else []

    def get_xg_summary(self, fixture_id: int) -> Dict[str, Any]:
        """
        Get xG summary for a fixture

        Returns:
            Dict with home_xG, away_xG, total_xG
        """

        def query_operation(conn):
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        team_id,
                        expected_goals
                    FROM statistics_raw
                    WHERE fixture_id = %s
                    ORDER BY team_id
                """, (fixture_id,))

                results = cursor.fetchall()
                
                if len(results) == 2:
                    return {
                        'home_xG': float(results[0][1]) if results[0][1] else 0.0,
                        'away_xG': float(results[1][1]) if results[1][1] else 0.0,
                        'total_xG': (float(results[0][1]) if results[0][1] else 0.0) + 
                                   (float(results[1][1]) if results[1][1] else 0.0)
                    }
                
                return {'home_xG': 0.0, 'away_xG': 0.0, 'total_xG': 0.0}

        results = self.safe_db_operation(query_operation)
        return results if results else {'home_xG': 0.0, 'away_xG': 0.0, 'total_xG': 0.0}


if __name__ == '__main__':
    """Test the statistics fetcher"""
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
    fetcher = StatisticsFetcher(API_KEY, DB_CONFIG)

    print("=" * 80)
    print("STATISTICS FETCHER TEST")
    print("=" * 80)

    # Test with a finished match (has statistics)
    test_fixture_id = 1035112  # Replace with actual fixture

    print(f"\nTest 1: Fetching statistics for fixture {test_fixture_id}...")
    result = fetcher.fetch_and_store(fixture_ids=[test_fixture_id])
    print(f"Result: {result}")

    # Test 2: Get statistics
    print(f"\nTest 2: Getting stored statistics...")
    stats = fetcher.get_statistics_for_fixture(test_fixture_id)
    print(f"Found {len(stats)} team statistics")
    for stat in stats:
        print(f"  Team {stat['team_id']}:")
        print(f"    xG: {stat['expected_goals']}")
        print(f"    Shots: {stat['shots_total']} ({stat['shots_on_target']} on target)")
        print(f"    Possession: {stat['possession_pct']}%")

    # Test 3: Get xG summary
    print(f"\nTest 3: Getting xG summary...")
    xg_summary = fetcher.get_xg_summary(test_fixture_id)
    print(f"xG Summary: {xg_summary}")

    print("\n" + "=" * 80)
    print("STATISTICS FETCHER TEST COMPLETE")
    print("=" * 80)



