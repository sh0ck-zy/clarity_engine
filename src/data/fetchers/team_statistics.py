from .base_fetcher import BaseFetcher
from typing import Dict, Any, List
from psycopg.rows import dict_row
import json


class TeamStatisticsFetcher(BaseFetcher):
    """Fetcher for team statistics from API-Football"""

    def fetch_and_store(self, league_id: int = None, season: int = None) -> Dict[str, Any]:
        """
        Fetch team statistics and store in database

        Args:
            league_id: League ID (defaults to Portuguese Liga)
            season: Season year (defaults to current season)

        Returns:
            Dict with operation results and statistics
        """

        league_id = league_id or self.get_target_league_id()
        season = season or self.get_current_season()

        # Initialize counters
        teams_processed = 0
        teams_updated = 0
        teams_new = 0
        teams_errors = 0

        try:
            # First get list of teams in the league
            teams = self._get_teams_in_league(league_id, season)
            
            if not teams:
                return {
                    'success': False,
                    'error': 'No teams found for league',
                    'league_id': league_id,
                    'season': season
                }

            # Process and store team statistics
            def store_operation(conn):
                nonlocal teams_processed, teams_updated, teams_new, teams_errors

                with conn.cursor(row_factory=dict_row) as cursor:
                    for team in teams:
                        try:
                            # Fetch team statistics
                            team_stats = self._fetch_team_statistics(team['id'], league_id, season)
                            
                            if not team_stats:
                                self.logger.warning(f"No statistics found for team {team['id']}")
                                continue

                            # Process single team statistics
                            result = self._process_single_team_stats(cursor, team_stats, team, league_id, season)
                            if result['action'] == 'updated':
                                teams_updated += 1
                            elif result['action'] == 'inserted':
                                teams_new += 1

                            teams_processed += 1

                        except Exception as e:
                            self.logger.error(f"Error processing team {team['id']}: {str(e)}")
                            teams_errors += 1

                return {
                    'processed': teams_processed,
                    'updated': teams_updated,
                    'new': teams_new,
                    'errors': teams_errors
                }

            # Execute database operation
            db_results = self.safe_db_operation(store_operation)

            # Compile final results
            operation_results = {
                'success': True,
                'teams_processed': db_results['processed'],
                'teams_updated': db_results['updated'],
                'teams_new': db_results['new'],
                'teams_errors': db_results['errors'],
                'league_id': league_id,
                'season': season
            }

            # Log summary
            self.log_fetch_summary("Team Statistics fetch", {
                'processed': db_results['processed'],
                'new': db_results['new'],
                'updated': db_results['updated'],
                'errors': db_results['errors']
            })

            return operation_results

        except Exception as e:
            error_msg = f"Team Statistics fetch operation failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'teams_processed': teams_processed
            }

    def _get_teams_in_league(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Get list of teams in the league from standings or teams endpoint"""
        
        # Try to get teams from standings first (more reliable)
        try:
            standings_data = self._fetch_standings_for_teams(league_id, season)
            if standings_data:
                return standings_data
        except Exception as e:
            self.logger.warning(f"Could not get teams from standings: {str(e)}")

        # Fallback to teams endpoint
        params = {
            'league': league_id,
            'season': season
        }

        self.logger.info(f"Fetching teams with params: {params}")

        api_data = self.make_api_call('teams', params)
        teams = []
        
        if api_data.get('response'):
            teams = [team for team in api_data['response']]

        self.logger.info(f"Retrieved {len(teams)} teams")
        return teams

    def _fetch_standings_for_teams(self, league_id: int, season: int) -> List[Dict[str, Any]]:
        """Get teams from standings data"""
        
        params = {
            'league': league_id,
            'season': season
        }

        api_data = self.make_api_call('standings', params)
        teams = []
        
        if api_data.get('response'):
            for league_standing in api_data['response']:
                if league_standing.get('league', {}).get('standings'):
                    for team_standing in league_standing['league']['standings'][0]:
                        teams.append(team_standing['team'])

        return teams

    def _fetch_team_statistics(self, team_id: int, league_id: int, season: int) -> Dict[str, Any]:
        """Fetch team statistics for a specific team"""

        params = {
            'team': team_id,
            'league': league_id,
            'season': season
        }

        self.logger.debug(f"Fetching team statistics for team {team_id} with params: {params}")

        # Make API call
        api_data = self.make_api_call('teams/statistics', params)

        # Extract team statistics
        if api_data.get('response'):
            return api_data['response']
        
        return {}

    def _process_single_team_stats(self, cursor, team_stats: Dict[str, Any], 
                                 team: Dict[str, Any], league_id: int, season: int) -> Dict[str, str]:
        """Process and store team statistics in the database"""

        team_id = team['id']

        # Check if team stats already exist
        cursor.execute("""
            SELECT id, team_id, league_id, season 
            FROM teams_stats_raw 
            WHERE team_id = %s AND league_id = %s AND season = %s
        """, (team_id, league_id, season))
        existing = cursor.fetchone()

        # Extract league data
        league_data = team_stats.get('league', {})
        
        # Prepare comprehensive team stats data
        db_stats_data = {
            'team_id': team_id,
            'league_id': league_id,
            'season': season,
            'sport': self.sport,
            'form': league_data.get('form', ''),
            'fixtures_stats': json.dumps(league_data.get('fixtures', {})),
            'goals_stats': json.dumps(league_data.get('goals', {})),
            'biggest_stats': json.dumps(league_data.get('biggest', {})),
            'clean_sheet_stats': json.dumps(league_data.get('clean_sheet', {})),
            'failed_to_score_stats': json.dumps(league_data.get('failed_to_score', {})),
            'penalty_stats': json.dumps(league_data.get('penalty', {})),
            'lineups_stats': json.dumps(league_data.get('lineups', [])),
            'cards_stats': json.dumps(league_data.get('cards', {})),
            'raw_response': json.dumps(team_stats)
        }

        if existing:
            # Update existing team stats
            cursor.execute("""
                UPDATE teams_stats_raw SET
                    form = %(form)s,
                    fixtures_stats = %(fixtures_stats)s,
                    goals_stats = %(goals_stats)s,
                    biggest_stats = %(biggest_stats)s,
                    clean_sheet_stats = %(clean_sheet_stats)s,
                    failed_to_score_stats = %(failed_to_score_stats)s,
                    penalty_stats = %(penalty_stats)s,
                    lineups_stats = %(lineups_stats)s,
                    cards_stats = %(cards_stats)s,
                    raw_response = %(raw_response)s,
                    sport = %(sport)s,
                    queried_at = NOW()
                WHERE team_id = %(team_id)s AND league_id = %(league_id)s AND season = %(season)s
            """, db_stats_data)

            self.logger.debug(f"Updated team statistics for team {team_id}")
            return {'action': 'updated', 'team_id': team_id}

        else:
            # Insert new team stats
            cursor.execute("""
                INSERT INTO teams_stats_raw (
                    team_id, league_id, season, sport, form, fixtures_stats, 
                    goals_stats, biggest_stats, clean_sheet_stats, 
                    failed_to_score_stats, penalty_stats, lineups_stats, 
                    cards_stats, raw_response
                ) VALUES (
                    %(team_id)s, %(league_id)s, %(season)s, %(sport)s, %(form)s,
                    %(fixtures_stats)s, %(goals_stats)s, %(biggest_stats)s,
                    %(clean_sheet_stats)s, %(failed_to_score_stats)s,
                    %(penalty_stats)s, %(lineups_stats)s, %(cards_stats)s,
                    %(raw_response)s
                )
            """, db_stats_data)

            self.logger.debug(f"Inserted new team statistics for team {team_id}")
            return {'action': 'inserted', 'team_id': team_id}

    def validate_team_stats_data(self, team_stats: Dict[str, Any]) -> bool:
        """Validate team stats data before processing"""
        
        if not isinstance(team_stats, dict):
            self.logger.warning("Invalid team stats data format")
            return False

        if 'league' not in team_stats:
            self.logger.warning("Missing league data in team stats")
            return False

        return True

    def get_team_stats_summary(self) -> Dict[str, Any]:
        """Get summary statistics about stored team stats"""

        def stats_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Overall stats
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_team_stats,
                        COUNT(DISTINCT league_id) as leagues_covered,
                        COUNT(DISTINCT season) as seasons_covered,
                        MAX(queried_at) as last_updated
                    FROM teams_stats_raw
                """)

                stats = cursor.fetchone()

                # League breakdown
                cursor.execute("""
                    SELECT league_id, COUNT(*) as team_count
                    FROM teams_stats_raw
                    GROUP BY league_id
                    ORDER BY league_id
                """)

                league_breakdown = {row['league_id']: row['team_count'] for row in cursor.fetchall()}

                return {
                    'total_team_stats': stats['total_team_stats'],
                    'leagues_covered': stats['leagues_covered'],
                    'seasons_covered': stats['seasons_covered'],
                    'last_updated': stats['last_updated'].isoformat() if stats['last_updated'] else None,
                    'league_breakdown': league_breakdown
                }

        try:
            return self.safe_db_operation(stats_operation)
        except Exception as e:
            self.logger.error(f"Error getting team stats summary: {str(e)}")
            return {'error': str(e)}
