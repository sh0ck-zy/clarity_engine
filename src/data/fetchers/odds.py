from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from psycopg.rows import dict_row
import json
import time

from .base_fetcher import BaseFetcher
from fetchers.providers.base import DataProvider, ProviderResponse


class OddsFetcher(BaseFetcher):
    """Fetcher for odds data with multi-timestamp tracking and market analysis"""

    def __init__(self, *, db_config: Dict[str, str], provider: DataProvider, sport: str = "football"):
        super().__init__(db_config=db_config, provider=provider, sport=sport)

        # Default bookmakers to track (prioritize config → fall back to common IDs)
        try:
            primary = getattr(self.provider, 'primary_bookmakers', []) or []
            backups = getattr(self.provider, 'backup_bookmakers', []) or []
            self.logger.debug(f"OddsFetcher: Found bookmakers from provider - primary: {primary}, backups: {backups}")
        except Exception as e:
            self.logger.warning(f"OddsFetcher: Could not get bookmakers from provider: {e}")
            primary, backups = [], []

        configured = [str(b) for b in (primary + backups) if b is not None]
        self.default_bookmakers = configured or [
            '8',   # Bet365 (API-Football ID: 8)
            '4',   # Pinnacle (sharp)
            '3',   # Betfair
        ]
        self.logger.debug(f"OddsFetcher: Using bookmakers: {self.default_bookmakers}")

        # Markets to track for MVP v1
        self.target_markets = ['1X2']  # Start with 1X2, expand later

    def fetch_and_store(self,
                       fixture_ids: List[int] = None,
                       markets: List[str] = None,
                       bookmakers: List[str] = None,
                       days_ahead: int = 7) -> Dict[str, Any]:
        """
        Fetch odds for fixtures with multi-timestamp strategy

        Args:
            fixture_ids: List of fixture IDs (if None, get upcoming fixtures)
            markets: List of markets to fetch (defaults to ['1X2'])
            bookmakers: List of bookmaker IDs (defaults to major bookmakers)
            days_ahead: How many days ahead to fetch for (if fixture_ids not specified)

        Returns:
            Dict with operation results and statistics
        """

        markets = markets or self.target_markets
        bookmakers = bookmakers or self.default_bookmakers[:2]  # Limit to 2 for MVP

        odds_processed = 0
        odds_entries_stored = 0
        fixtures_processed = 0
        api_calls_made = 0
        errors = 0

        try:
            # Get fixtures to process
            if fixture_ids is None:
                fixture_ids = self._get_fixtures_for_odds(days_ahead)

            if not fixture_ids:
                self.logger.info("No fixtures found for odds fetch")
                return {
                    'success': True,
                    'message': 'No fixtures require odds',
                    'odds_processed': 0
                }

            self.logger.info(f"Processing odds for {len(fixture_ids)} fixtures, {len(bookmakers)} bookmakers")

            # Process odds with database transaction
            def store_operation(conn):
                nonlocal odds_processed, odds_entries_stored, fixtures_processed, api_calls_made, errors

                # Convert bookmaker IDs to strings for comparison
                target_bookmaker_ids = set(str(bm_id) for bm_id in bookmakers)

                with conn.cursor(row_factory=dict_row) as cursor:
                    for fixture_id in fixture_ids:
                        try:
                            # Fetch ALL odds for this fixture in one API call (more efficient)
                            # Then filter by bookmaker in code
                            provider_response: ProviderResponse = self.provider.fetch_odds(
                                fixture_id=fixture_id,
                                bookmaker_id=None  # Don't filter by bookmaker - get all
                            )
                            api_calls_made += provider_response.metadata.get("api_calls", 0)

                            for error in provider_response.errors:
                                self.logger.warning(
                                    f"Provider error fetching odds for fixture {fixture_id}: {error}"
                                )

                            fixture_odds_stored = 0

                            if provider_response.records:
                                self.logger.debug(
                                    f"Fixture {fixture_id}: Received {len(provider_response.records)} records, "
                                    f"targeting bookmakers {list(target_bookmaker_ids)}"
                                )
                                
                                # Filter records by target bookmakers
                                filtered_records = []
                                for record in provider_response.records:
                                    # Each record.payload should be a fixture odds object with bookmakers array
                                    payload = record.payload
                                    if isinstance(payload, dict) and 'bookmakers' in payload:
                                        all_bookmakers = payload.get('bookmakers', [])
                                        self.logger.debug(
                                            f"Fixture {fixture_id}: Found {len(all_bookmakers)} bookmakers in payload"
                                        )
                                        
                                        # Filter bookmakers to only include target ones
                                        filtered_bookmakers = [
                                            bm for bm in all_bookmakers
                                            if str(bm.get('id', '')) in target_bookmaker_ids
                                        ]
                                        
                                        if filtered_bookmakers:
                                            self.logger.debug(
                                                f"Fixture {fixture_id}: Filtered to {len(filtered_bookmakers)} target bookmakers: "
                                                f"{[bm.get('name', 'N/A') for bm in filtered_bookmakers]}"
                                            )
                                            # Create a new payload with only target bookmakers
                                            filtered_payload = payload.copy()
                                            filtered_payload['bookmakers'] = filtered_bookmakers
                                            filtered_records.append(filtered_payload)
                                        else:
                                            available_bm_ids = [str(bm.get('id', '')) for bm in all_bookmakers]
                                            self.logger.debug(
                                                f"Fixture {fixture_id}: No target bookmakers found. "
                                                f"Available: {available_bm_ids}, Target: {list(target_bookmaker_ids)}"
                                            )
                                    
                                    # If payload doesn't have bookmakers structure, it might be the old format
                                    # In that case, check if metadata has bookmaker_id
                                    elif record.metadata.get('bookmaker_id') and str(record.metadata['bookmaker_id']) in target_bookmaker_ids:
                                        filtered_records.append(payload)

                                if filtered_records:
                                    self.logger.info(
                                        f"Fixture {fixture_id}: Processing {len(filtered_records)} filtered records"
                                    )
                                    stored_count = self._process_odds_response(
                                        cursor,
                                        fixture_id,
                                        {"response": filtered_records},
                                        markets
                                    )
                                    fixture_odds_stored += stored_count
                                    self.logger.info(
                                        f"Fixture {fixture_id}: Stored {stored_count} odds entries "
                                        f"(from {len(provider_response.records)} records)"
                                    )
                                else:
                                    self.logger.warning(
                                        f"Fixture {fixture_id}: No odds after filtering for bookmakers {list(target_bookmaker_ids)}"
                                    )
                            else:
                                self.logger.debug(f"Fixture {fixture_id}: No records in API response")

                            # Update odds analysis after processing all bookmakers for this fixture
                            if fixture_odds_stored > 0:
                                self._update_odds_analysis(cursor, fixture_id, markets)
                                fixtures_processed += 1
                                odds_entries_stored += fixture_odds_stored

                            odds_processed += fixture_odds_stored

                            # Rate limiting between fixture calls
                            time.sleep(0.2)

                        except Exception as e:
                            self.logger.error(f"Error processing fixture {fixture_id}: {str(e)}")
                            errors += 1
                            continue

                return {
                    'odds_processed': odds_processed,
                    'odds_entries_stored': odds_entries_stored,
                    'fixtures_processed': fixtures_processed,
                    'errors': errors
                }

            # Execute database operation
            db_results = self.safe_db_operation(store_operation)

            # Compile results
            operation_results = {
                'success': True,
                'odds_processed': db_results['odds_processed'],
                'odds_entries_stored': db_results['odds_entries_stored'],
                'fixtures_processed': db_results['fixtures_processed'],
                'fixtures_attempted': len(fixture_ids),
                'api_calls': api_calls_made,
                'errors': db_results['errors'],
                'bookmakers_tracked': len(bookmakers),
                'markets_tracked': len(markets)
            }

            # Log summary
            self.log_fetch_summary("Odds fetch", {
                'processed': db_results['odds_processed'],
                'new': db_results['odds_entries_stored'],
                'updated': 0,  # Odds are always inserted as new records
                'errors': db_results['errors'],
                'api_calls': api_calls_made
            })

            return operation_results

        except Exception as e:
            error_msg = f"Odds fetch operation failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'odds_processed': odds_processed,
                'api_calls': api_calls_made
            }

    def _get_fixtures_for_odds(self, days_ahead: int) -> List[int]:
        """Get list of fixture IDs that need odds tracking"""

        def get_fixtures_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Get upcoming fixtures that don't have recent odds or need updates
                cursor.execute(f"""
                    SELECT DISTINCT fr.fixture_id, fr.date
                    FROM fixtures_raw fr
                    LEFT JOIN odds_raw ods ON fr.fixture_id = ods.fixture_id
                        AND ods.queried_at > NOW() - INTERVAL '2 hours'
                    WHERE fr.date BETWEEN NOW() + INTERVAL '1 hour' AND NOW() + INTERVAL '{days_ahead} days'
                      AND fr.status IN ('SCHEDULED', 'TIMED', 'NS')
                      AND fr.league_id = %s
                      AND (ods.fixture_id IS NULL OR fr.date < NOW() + INTERVAL '24 hours')
                    ORDER BY fr.date ASC
                    LIMIT 30
                """, (self.get_target_league_id(),))

                return [row['fixture_id'] for row in cursor.fetchall()]

        try:
            return self.safe_db_operation(get_fixtures_operation)
        except Exception as e:
            self.logger.error(f"Error getting fixtures for odds: {str(e)}")
            return []

    def _process_odds_response(self, cursor, fixture_id: int, api_data: Dict[str, Any],
                              target_markets: List[str]) -> int:
        """Process odds response and store individual odds entries"""

        stored_count = 0
        current_timestamp = datetime.now()
        
        # Market name mapping: API-Football uses different names than our internal names
        market_mapping = {
            'Match Winner': '1X2',
            '1X2': '1X2',
            'Home/Away': '1X2',
        }

        response_items = api_data.get('response', [])
        
        if not response_items:
            self.logger.warning(f"No response items in api_data for fixture {fixture_id}")
            return 0

        for odds_data in response_items:
            bookmakers = odds_data.get('bookmakers', [])

            if not bookmakers:
                self.logger.debug(f"No bookmakers in odds_data for fixture {fixture_id}")
                continue

            for bookmaker in bookmakers:
                bookmaker_name = bookmaker.get('name', 'Unknown')
                bets = bookmaker.get('bets', [])

                for market_data in bets:
                    market = market_data.get('name', '')
                    mapped_market = market_mapping.get(market, market)

                    # Only process target markets (check both original and mapped name)
                    if market not in target_markets and mapped_market not in target_markets:
                        continue

                    # Use mapped market name for storage
                    market_to_store = mapped_market if mapped_market in target_markets else market
                    values = market_data.get('values', [])

                    for value in values:
                        try:
                            # Store individual odds entry
                            odds_entry = {
                                'fixture_id': fixture_id,
                                'sport': self.sport,
                                'bookmaker': bookmaker_name,
                                'market': market_to_store,
                                'selection': value.get('value', ''),
                                'odd': float(value.get('odd', 0)),
                                'timestamp': current_timestamp,
                                'raw_response': json.dumps(api_data)
                            }

                            cursor.execute("""
                                INSERT INTO odds_raw (
                                    fixture_id, sport, bookmaker, market, selection,
                                    odd, timestamp, raw_response
                                ) VALUES (
                                    %(fixture_id)s, %(sport)s, %(bookmaker)s, %(market)s,
                                    %(selection)s, %(odd)s, %(timestamp)s, %(raw_response)s
                                )
                                ON CONFLICT (fixture_id, bookmaker, market, selection, timestamp)
                                DO UPDATE SET
                                    odd = EXCLUDED.odd,
                                    raw_response = EXCLUDED.raw_response,
                                    sport = EXCLUDED.sport
                            """, odds_entry)

                            stored_count += 1

                        except Exception as e:
                            self.logger.error(f"Error storing odds entry for fixture {fixture_id}, market {market_to_store}: {str(e)}")
                            continue

        if stored_count > 0:
            self.logger.debug(f"Stored {stored_count} odds entries for fixture {fixture_id}")
        return stored_count

    def _update_odds_analysis(self, cursor, fixture_id: int, markets: List[str]):
        """Update odds analysis table with multi-timestamp data and market analysis"""

        for market in markets:
            try:
                # Get odds summary for this fixture and market
                cursor.execute("""
                    SELECT
                        selection,
                        MIN(timestamp) as first_tracked,
                        MAX(timestamp) as last_tracked,
                        FIRST_VALUE(odd) OVER (
                            PARTITION BY selection ORDER BY timestamp ASC
                        ) as initial_odd,
                        LAST_VALUE(odd) OVER (
                            PARTITION BY selection ORDER BY timestamp ASC
                            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                        ) as current_odd,
                        AVG(odd) as avg_odd,
                        COUNT(*) as data_points
                    FROM odds_raw
                    WHERE fixture_id = %s AND market = %s AND sport = %s
                    GROUP BY fixture_id, market, selection, odd, timestamp
                    ORDER BY selection
                """, (fixture_id, market, self.sport))

                odds_summary = cursor.fetchall()

                for odds_row in odds_summary:
                    selection = odds_row['selection']
                    initial_odd = odds_row['initial_odd']
                    current_odd = odds_row['current_odd']
                    avg_odd = odds_row['avg_odd']
                    first_tracked = odds_row['first_tracked']

                    # Calculate market movement
                    market_movement = 0
                    if initial_odd and current_odd and initial_odd != current_odd:
                        market_movement = ((current_odd - initial_odd) / initial_odd) * 100

                    # Detect sharp money (significant line movement)
                    sharp_money_indicator = abs(market_movement) > 10  # 10% movement threshold

                    # Determine timestamp-specific odds
                    odds_24h = self._get_odds_at_timestamp(cursor, fixture_id, market, selection, hours_before=24)
                    odds_1h = self._get_odds_at_timestamp(cursor, fixture_id, market, selection, hours_before=1)

                    # Update or insert odds analysis
                    cursor.execute("""
                        INSERT INTO odds_analysis (
                            fixture_id, sport, market, selection, odds_initial, odds_24h,
                            odds_1h, odds_current, market_movement, sharp_money_indicator,
                            bookmaker_consensus, first_tracked, last_updated
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                        )
                        ON CONFLICT (fixture_id, market, selection)
                        DO UPDATE SET
                            odds_24h = EXCLUDED.odds_24h,
                            odds_1h = EXCLUDED.odds_1h,
                            odds_current = EXCLUDED.odds_current,
                            market_movement = EXCLUDED.market_movement,
                            sharp_money_indicator = EXCLUDED.sharp_money_indicator,
                            bookmaker_consensus = EXCLUDED.bookmaker_consensus,
                            sport = EXCLUDED.sport,
                            last_updated = NOW()
                    """, (
                        fixture_id, self.sport, market, selection, initial_odd,
                        odds_24h, odds_1h, current_odd, market_movement,
                        sharp_money_indicator, avg_odd, first_tracked
                    ))

            except Exception as e:
                self.logger.error(f"Error updating odds analysis for fixture {fixture_id}, market {market}: {str(e)}")

    def _get_odds_at_timestamp(self, cursor, fixture_id: int, market: str,
                              selection: str, hours_before: int) -> Optional[float]:
        """Get odds value closest to a specific time before kickoff"""

        cursor.execute("""
            SELECT fr.date as kickoff_date
            FROM fixtures_raw fr
            WHERE fr.fixture_id = %s AND fr.sport = %s
        """, (fixture_id, self.sport))

        fixture_result = cursor.fetchone()
        if not fixture_result:
            return None

        kickoff_date = fixture_result['kickoff_date']
        target_timestamp = kickoff_date - timedelta(hours=hours_before)

        # Find odds closest to target timestamp
        cursor.execute("""
            SELECT odd
            FROM odds_raw
            WHERE fixture_id = %s AND market = %s AND selection = %s AND sport = %s
            ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
            LIMIT 1
        """, (fixture_id, market, selection, self.sport, target_timestamp))

        result = cursor.fetchone()
        return float(result['odd']) if result else None

    def get_odds_movement_alerts(self, movement_threshold: float = 10.0) -> List[Dict[str, Any]]:
        """Get fixtures with significant odds movements for alerting"""

        def alerts_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    SELECT
                        oa.fixture_id,
                        oa.market,
                        oa.selection,
                        oa.odds_initial,
                        oa.odds_current,
                        oa.market_movement,
                        oa.last_updated,
                        fr.teams->>'home'->>'name' as home_team,
                        fr.teams->>'away'->>'name' as away_team,
                        fr.date as kickoff_date
                    FROM odds_analysis oa
                    JOIN fixtures_raw fr ON oa.fixture_id = fr.fixture_id
                    WHERE ABS(oa.market_movement) > %s
                      AND fr.date > NOW()
                      AND fr.league_id = %s
                      AND oa.sport = %s
                      AND oa.last_updated > NOW() - INTERVAL '6 hours'
                    ORDER BY ABS(oa.market_movement) DESC
                    LIMIT 20
                """, (movement_threshold, self.get_target_league_id(), self.sport))

                alerts = []
                for row in cursor.fetchall():
                    alerts.append({
                        'fixture_id': row['fixture_id'],
                        'match': f"{row['home_team']} vs {row['away_team']}",
                        'kickoff': row['kickoff_date'].isoformat(),
                        'market': row['market'],
                        'selection': row['selection'],
                        'initial_odds': float(row['odds_initial']) if row['odds_initial'] else None,
                        'current_odds': float(row['odds_current']) if row['odds_current'] else None,
                        'movement_percent': float(row['market_movement']) if row['market_movement'] else 0,
                        'last_updated': row['last_updated'].isoformat()
                    })

                return alerts

        try:
            return self.safe_db_operation(alerts_operation)
        except Exception as e:
            self.logger.error(f"Error getting odds movement alerts: {str(e)}")
            return []

    def get_odds_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics about stored odds"""

        def stats_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Overall odds stats
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_odds_entries,
                        COUNT(DISTINCT fixture_id) as fixtures_with_odds,
                        COUNT(DISTINCT bookmaker) as bookmakers_tracked,
                        COUNT(DISTINCT market) as markets_tracked,
                        MIN(queried_at) as earliest_odds,
                        MAX(queried_at) as latest_odds
                    FROM odds_raw or_raw
                    JOIN fixtures_raw fr ON or_raw.fixture_id = fr.fixture_id
                    WHERE fr.league_id = %s
                """, (self.get_target_league_id(),))

                overall_stats = cursor.fetchone()

                # Market breakdown
                cursor.execute("""
                    SELECT market, COUNT(*) as entries, COUNT(DISTINCT fixture_id) as fixtures
                    FROM odds_raw or_raw
                    JOIN fixtures_raw fr ON or_raw.fixture_id = fr.fixture_id
                    WHERE fr.league_id = %s
                    GROUP BY market
                    ORDER BY entries DESC
                """, (self.get_target_league_id(),))

                market_breakdown = [
                    {
                        'market': row['market'],
                        'entries': row['entries'],
                        'fixtures': row['fixtures']
                    }
                    for row in cursor.fetchall()
                ]

                # Recent market movements
                cursor.execute("""
                    SELECT COUNT(*) as sharp_movements
                    FROM odds_analysis oa
                    JOIN fixtures_raw fr ON oa.fixture_id = fr.fixture_id
                    WHERE oa.sharp_money_indicator = true
                      AND fr.league_id = %s
                      AND oa.last_updated > NOW() - INTERVAL '24 hours'
                """, (self.get_target_league_id(),))

                sharp_movements = cursor.fetchone()

                return {
                    'total_odds_entries': overall_stats['total_odds_entries'],
                    'fixtures_with_odds': overall_stats['fixtures_with_odds'],
                    'bookmakers_tracked': overall_stats['bookmakers_tracked'],
                    'markets_tracked': overall_stats['markets_tracked'],
                    'earliest_odds': overall_stats['earliest_odds'].isoformat() if overall_stats['earliest_odds'] else None,
                    'latest_odds': overall_stats['latest_odds'].isoformat() if overall_stats['latest_odds'] else None,
                    'market_breakdown': market_breakdown,
                    'sharp_movements_24h': sharp_movements['sharp_movements']
                }

        try:
            return self.safe_db_operation(stats_operation)
        except Exception as e:
            self.logger.error(f"Error getting odds stats: {str(e)}")
            return {'error': str(e)}

    def fetch_pre_match_odds_intensive(self, hours_before_kickoff: int = 2) -> Dict[str, Any]:
        """Intensive odds fetching for matches starting soon"""

        def get_pre_match_fixtures(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(f"""
                    SELECT fixture_id
                    FROM fixtures_raw
                    WHERE date BETWEEN NOW() AND NOW() + INTERVAL '{hours_before_kickoff} hours'
                      AND status IN ('SCHEDULED', 'TIMED', 'NS')
                      AND league_id = %s
                    ORDER BY date ASC
                """, (self.get_target_league_id(),))

                return [row['fixture_id'] for row in cursor.fetchall()]

        try:
            pre_match_fixtures = self.safe_db_operation(get_pre_match_fixtures)

            if not pre_match_fixtures:
                return {
                    'success': True,
                    'message': 'No fixtures require pre-match odds intensive tracking',
                    'fixtures_processed': 0
                }

            self.logger.info(f"Performing intensive odds tracking for {len(pre_match_fixtures)} pre-match fixtures")

            # Use all bookmakers for pre-match intensive tracking
            result = self.fetch_and_store(
                fixture_ids=pre_match_fixtures,
                bookmakers=self.default_bookmakers
            )

            result['operation_type'] = 'pre_match_intensive'
            return result

        except Exception as e:
            self.logger.error(f"Error in pre-match odds intensive: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'operation_type': 'pre_match_intensive'
            }
