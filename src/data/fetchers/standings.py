from .base_fetcher import BaseFetcher
from typing import Dict, Any, List
from psycopg.rows import dict_row
import json


class StandingsFetcher(BaseFetcher):
    """Fetcher for league standings from API-Football"""

    def fetch_and_store(self, league_id: int = None, season: int = None) -> Dict[str, Any]:
        """
        Fetch league standings and store in database

        Args:
            league_id: League ID (defaults to Portuguese Liga)
            season: Season year (defaults to current season)

        Returns:
            Dict with operation results and statistics
        """

        league_id = league_id or self.get_target_league_id()
        season = season or self.get_current_season()

        # Initialize counters
        standings_processed = 0
        standings_updated = 0
        standings_new = 0
        standings_errors = 0

        try:
            # Fetch standings from API
            standings_data = self._fetch_standings(league_id, season)

            # Process and store standings
            def store_operation(conn):
                nonlocal standings_processed, standings_updated, standings_new, standings_errors

                with conn.cursor(row_factory=dict_row) as cursor:
                    for team_standing in standings_data:
                        try:
                            if not self.validate_standing_data(team_standing):
                                standings_errors += 1
                                continue

                            # Process single team standing
                            result = self._process_single_standing(cursor, team_standing, league_id, season)
                            if result['action'] == 'updated':
                                standings_updated += 1
                            elif result['action'] == 'inserted':
                                standings_new += 1

                            standings_processed += 1

                        except Exception as e:
                            self.logger.error(f"Error processing team standing: {str(e)}")
                            standings_errors += 1

                return {
                    'processed': standings_processed,
                    'updated': standings_updated,
                    'new': standings_new,
                    'errors': standings_errors
                }

            # Execute database operation
            db_results = self.safe_db_operation(store_operation)

            # Compile final results
            operation_results = {
                'success': True,
                'standings_processed': db_results['processed'],
                'standings_updated': db_results['updated'],
                'standings_new': db_results['new'],
                'standings_errors': db_results['errors'],
                'league_id': league_id,
                'season': season
            }

            # Log summary
            self.log_fetch_summary("Standings fetch", {
                'processed': db_results['processed'],
                'new': db_results['new'],
                'updated': db_results['updated'],
                'errors': db_results['errors']
            })

            return operation_results

        except Exception as e:
            error_msg = f"Standings fetch operation failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'standings_processed': standings_processed
            }

    def _fetch_standings(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Fetch standings from API-Football"""

        params = {
            'league': league_id,
            'season': season
        }

        self.logger.info(f"Fetching standings with params: {params}")

        # Make API call
        api_data = self.make_api_call('standings', params)

        # Extract standings data
        standings_data = []
        if api_data.get('response'):
            for league_standing in api_data['response']:
                if league_standing.get('league', {}).get('standings'):
                    standings_data.extend(league_standing['league']['standings'][0])

        self.logger.info(f"Retrieved {len(standings_data)} team standings")
        return standings_data

    def _process_single_standing(self, cursor, team_standing: Dict[str, Any],
                                league_id: int, season: int) -> Dict[str, str]:
        """Process and store a single team standing in the database"""

        team_id = team_standing['team']['id']
        rank = team_standing['rank']

        # Check if standing already exists
        cursor.execute("""
            SELECT id, rank, points 
            FROM standings_raw 
            WHERE team_data->>'id' = %s AND league_id = %s AND season = %s
        """, (str(team_id), league_id, season))
        existing = cursor.fetchone()

        # Prepare comprehensive standing data
        db_standing_data = {
            'team_data': json.dumps(team_standing['team']),
            'league_id': league_id,
            'season': season,
            'sport': self.sport,
            'rank': rank,
            'points': team_standing['points'],
            'goals_diff': team_standing['goalsDiff'],
            'form': team_standing.get('form', ''),
            'all_stats': json.dumps(team_standing.get('all', {})),
            'raw_response': json.dumps(team_standing)
        }

        if existing:
            # Update existing standing
            cursor.execute("""
                UPDATE standings_raw SET
                    team_data = %(team_data)s,
                    sport = %(sport)s,
                    rank = %(rank)s,
                    points = %(points)s,
                    goals_diff = %(goals_diff)s,
                    form = %(form)s,
                    all_stats = %(all_stats)s,
                    raw_response = %(raw_response)s,
                    queried_at = NOW()
                WHERE team_data->>'id' = %(team_id)s AND league_id = %(league_id)s AND season = %(season)s
            """, {**db_standing_data, 'team_id': str(team_id)})

            # Log significant changes
            if existing['rank'] != db_standing_data['rank']:
                self.logger.info(
                    f"Team {team_id} rank changed: {existing['rank']} -> {db_standing_data['rank']}"
                )

            return {'action': 'updated', 'team_id': team_id}

        else:
            # Insert new standing
            cursor.execute("""
                INSERT INTO standings_raw (
                    team_data, league_id, season, sport, rank, points, goals_diff,
                    form, all_stats, raw_response
                ) VALUES (
                    %(team_data)s, %(league_id)s, %(season)s, %(sport)s,
                    %(rank)s, %(points)s, %(goals_diff)s,
                    %(form)s, %(all_stats)s, %(raw_response)s
                )
            """, db_standing_data)

            self.logger.debug(f"Inserted new standing for team {team_id}")
            return {'action': 'inserted', 'team_id': team_id}

    def validate_standing_data(self, standing: Dict[str, Any]) -> bool:
        """Validate standing data before processing"""
        
        required_fields = ['team', 'rank', 'points']
        for field in required_fields:
            if field not in standing:
                self.logger.warning(f"Missing required field '{field}' in standing data")
                return False

        if not isinstance(standing['team'], dict) or 'id' not in standing['team']:
            self.logger.warning("Invalid team data in standing")
            return False

        return True

    def get_standings_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics about stored standings"""

        def stats_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Overall stats
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_standings,
                        COUNT(DISTINCT league_id) as leagues_covered,
                        COUNT(DISTINCT season) as seasons_covered,
                        MAX(queried_at) as last_updated
                    FROM standings_raw
                """)

                stats = cursor.fetchone()

                # League breakdown
                cursor.execute("""
                    SELECT league_id, COUNT(*) as team_count
                    FROM standings_raw
                    GROUP BY league_id
                    ORDER BY league_id
                """)

                league_breakdown = {row['league_id']: row['team_count'] for row in cursor.fetchall()}

                return {
                    'total_standings': stats['total_standings'],
                    'leagues_covered': stats['leagues_covered'],
                    'seasons_covered': stats['seasons_covered'],
                    'last_updated': stats['last_updated'].isoformat() if stats['last_updated'] else None,
                    'league_breakdown': league_breakdown
                }

        try:
            return self.safe_db_operation(stats_operation)
        except Exception as e:
            self.logger.error(f"Error getting standings stats: {str(e)}")
            return {'error': str(e)}
