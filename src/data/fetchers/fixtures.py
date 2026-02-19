from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from psycopg.rows import dict_row
import json

from .base_fetcher import BaseFetcher
from fetchers.providers.base import DataProvider, ProviderResponse


class FixturesFetcher(BaseFetcher):
    """Fetcher for fixture data from API-Football with comprehensive storage"""

    def __init__(self, *, db_config: Dict[str, str], provider: DataProvider, sport: str = "football"):
        super().__init__(db_config=db_config, provider=provider, sport=sport)

    def fetch_and_store(self,
                       league_id: int = None,
                       season: int = None,
                       date_from: str = None,
                       date_to: str = None,
                       fixture_ids: List[int] = None) -> Dict[str, Any]:
        """
        Fetch fixtures for specified parameters and store in database

        Args:
            league_id: League ID (defaults to Portuguese Liga)
            season: Season year (defaults to current season)
            date_from: Start date (YYYY-MM-DD format)
            date_to: End date (YYYY-MM-DD format)
            fixture_ids: List of specific fixture IDs to fetch

        Returns:
            Dict with operation results and statistics
        """

        league_id = league_id or self.get_target_league_id()
        season = season or self.get_current_season()

        # Initialize counters
        fixtures_processed = 0
        fixtures_updated = 0
        fixtures_new = 0
        fixtures_errors = 0
        api_calls_made = 0

        try:
            provider_response: ProviderResponse

            # Determine fetch strategy and retrieve data
            if fixture_ids:
                provider_response = self._fetch_specific_fixtures(fixture_ids)
            else:
                provider_response = self._fetch_fixtures_by_criteria(
                    league_id, season, date_from, date_to
                )

            api_calls_made = provider_response.metadata.get("api_calls", 0)
            results = provider_response.records

            for error in provider_response.errors:
                self.logger.warning(f"Provider reported error during fixtures fetch: {error}")

            # Process and store fixtures
            def store_operation(conn):
                nonlocal fixtures_processed, fixtures_updated, fixtures_new, fixtures_errors

                with conn.cursor(row_factory=dict_row) as cursor:
                    for record in results:
                        fixture = record.payload
                        try:
                            if not self.validate_fixture_data(fixture):
                                fixtures_errors += 1
                                continue

                            # Process single fixture
                            result = self._process_single_fixture(cursor, fixture, league_id, season)
                            if result['action'] == 'updated':
                                fixtures_updated += 1
                            elif result['action'] == 'inserted':
                                fixtures_new += 1

                            fixtures_processed += 1

                        except Exception as e:
                            self.logger.error(f"Error processing fixture {fixture.get('fixture', {}).get('id', 'unknown')}: {str(e)}")
                            fixtures_errors += 1

                return {
                    'processed': fixtures_processed,
                    'updated': fixtures_updated,
                    'new': fixtures_new,
                    'errors': fixtures_errors
                }

            # Execute database operation
            db_results = self.safe_db_operation(store_operation)

            # Compile final results
            operation_results = {
                'success': True,
                'fixtures_processed': db_results['processed'],
                'fixtures_updated': db_results['updated'],
                'fixtures_new': db_results['new'],
                'fixtures_errors': db_results['errors'],
                'api_calls': api_calls_made,
                'league_id': league_id,
                'season': season
            }

            # Log summary
            self.log_fetch_summary("Fixtures fetch", {
                'processed': db_results['processed'],
                'new': db_results['new'],
                'updated': db_results['updated'],
                'errors': db_results['errors'],
                'api_calls': api_calls_made
            })

            return operation_results

        except Exception as e:
            error_msg = f"Fixtures fetch operation failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'fixtures_processed': fixtures_processed,
                'api_calls': api_calls_made
            }

    def _fetch_fixtures_by_criteria(
        self,
        league_id: int,
        season: int,
        date_from: str = None,
        date_to: str = None,
    ) -> ProviderResponse:
        """Fetch fixtures based on league, season, and date criteria."""

        if not date_from and not date_to:
            today = datetime.now().date()
            date_from = today.strftime("%Y-%m-%d")
            date_to = (today + timedelta(days=14)).strftime("%Y-%m-%d")

        return self.provider.fetch_fixtures(
            league_id=league_id,
            season=season,
            date_from=date_from,
            date_to=date_to,
        )

    def _fetch_specific_fixtures(self, fixture_ids: List[int]) -> ProviderResponse:
        """Fetch specific fixtures by ID."""

        return self.provider.fetch_fixtures(fixture_ids=fixture_ids)

    def _process_single_fixture(self, cursor, fixture: Dict[str, Any],
                               league_id: int, season: int) -> Dict[str, str]:
        """Process and store a single fixture in the database"""

        fixture_data = fixture['fixture']
        fixture_id = fixture_data['id']

        # Check if fixture already exists
        cursor.execute(
            "SELECT fixture_id, status FROM fixtures_raw WHERE fixture_id = %s",
            (fixture_id,)
        )
        existing = cursor.fetchone()

        # Prepare comprehensive fixture data
        db_fixture_data = {
            'fixture_id': fixture_id,
            'league_id': league_id,
            'season': season,
            'sport': self.sport,
            'date': fixture_data['date'],
            'status': fixture_data['status']['short'],
            'venue': json.dumps(fixture_data.get('venue')),
            'teams': json.dumps(fixture.get('teams')),
            'goals': json.dumps(fixture.get('goals')),
            'periods': json.dumps(fixture_data.get('periods')),
            'referee': json.dumps(fixture_data.get('referee')),
            'raw_response': json.dumps(fixture)
        }

        if existing:
            # Update existing fixture (status, goals, etc. might have changed)
            cursor.execute("""
                UPDATE fixtures_raw SET
                    status = %(status)s,
                    goals = %(goals)s,
                    periods = %(periods)s,
                    referee = %(referee)s,
                    raw_response = %(raw_response)s,
                    sport = %(sport)s,
                    queried_at = NOW()
                WHERE fixture_id = %(fixture_id)s
            """, db_fixture_data)

            # Log significant status changes
            if existing['status'] != db_fixture_data['status']:
                self.logger.info(
                    f"Fixture {fixture_id} status changed: {existing['status']} -> {db_fixture_data['status']}"
                )

            return {'action': 'updated', 'fixture_id': fixture_id}

        else:
            # Insert new fixture
            cursor.execute("""
                INSERT INTO fixtures_raw (
                    fixture_id, league_id, season, sport, date, status,
                    venue, teams, goals, periods, referee, raw_response
                ) VALUES (
                    %(fixture_id)s, %(league_id)s, %(season)s, %(sport)s,
                    %(date)s, %(status)s, %(venue)s, %(teams)s,
                    %(goals)s, %(periods)s, %(referee)s, %(raw_response)s
                )
            """, db_fixture_data)

            self.logger.debug(f"Inserted new fixture {fixture_id}")
            return {'action': 'inserted', 'fixture_id': fixture_id}

    def get_fixtures_needing_updates(self, status_filter: List[str] = None) -> List[int]:
        """Get list of fixture IDs that need updates (live matches, recent finished, etc.)"""

        if status_filter is None:
            # Default: get live matches and recently finished matches
            status_filter = ['LIVE', '1H', '2H', 'HT', 'ET', 'P', 'FT']

        def get_fixtures_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Get live matches
                cursor.execute("""
                    SELECT fixture_id
                    FROM fixtures_raw
                    WHERE status = ANY(%s)
                    ORDER BY date DESC
                    LIMIT 50
                """, (status_filter,))

                live_fixtures = [row['fixture_id'] for row in cursor.fetchall()]

                # Get recently finished matches that might need final score updates
                cursor.execute("""
                    SELECT fixture_id
                    FROM fixtures_raw
                    WHERE status = 'FT'
                      AND date > NOW() - INTERVAL '2 hours'
                      AND queried_at < NOW() - INTERVAL '30 minutes'
                    ORDER BY date DESC
                    LIMIT 20
                """, ())

                recent_finished = [row['fixture_id'] for row in cursor.fetchall()]

                return live_fixtures + recent_finished

        try:
            return self.safe_db_operation(get_fixtures_operation)
        except Exception as e:
            self.logger.error(f"Error getting fixtures needing updates: {str(e)}")
            return []

    def fetch_live_fixtures_update(self) -> Dict[str, Any]:
        """Specialized method to fetch updates for live and recently finished fixtures"""

        fixtures_to_update = self.get_fixtures_needing_updates()

        if not fixtures_to_update:
            self.logger.info("No fixtures need live updates")
            return {
                'success': True,
                'fixtures_processed': 0,
                'message': 'No fixtures requiring updates'
            }

        self.logger.info(f"Updating {len(fixtures_to_update)} live/recent fixtures")

        return self.fetch_and_store(fixture_ids=fixtures_to_update)

    def get_fixture_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics about stored fixtures"""

        def stats_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Overall stats
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_fixtures,
                        COUNT(CASE WHEN status IN ('SCHEDULED', 'TIMED') THEN 1 END) as upcoming,
                        COUNT(CASE WHEN status = 'LIVE' THEN 1 END) as live,
                        COUNT(CASE WHEN status = 'FT' THEN 1 END) as finished,
                        MIN(date) as earliest_fixture,
                        MAX(date) as latest_fixture,
                        MAX(queried_at) as last_updated
                    FROM fixtures_raw
                    WHERE league_id = %s
                """, (self.get_target_league_id(),))

                stats = cursor.fetchone()

                # Status breakdown
                cursor.execute("""
                    SELECT status, COUNT(*) as count
                    FROM fixtures_raw
                    WHERE league_id = %s
                    GROUP BY status
                    ORDER BY count DESC
                """, (self.get_target_league_id(),))

                status_breakdown = {row['status']: row['count'] for row in cursor.fetchall()}

                return {
                    'total_fixtures': stats['total_fixtures'],
                    'upcoming': stats['upcoming'],
                    'live': stats['live'],
                    'finished': stats['finished'],
                    'earliest_fixture': stats['earliest_fixture'].isoformat() if stats['earliest_fixture'] else None,
                    'latest_fixture': stats['latest_fixture'].isoformat() if stats['latest_fixture'] else None,
                    'last_updated': stats['last_updated'].isoformat() if stats['last_updated'] else None,
                    'status_breakdown': status_breakdown
                }

        try:
            return self.safe_db_operation(stats_operation)
        except Exception as e:
            self.logger.error(f"Error getting fixture stats: {str(e)}")
            return {'error': str(e)}
