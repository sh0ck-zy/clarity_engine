from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from psycopg.rows import dict_row
import json
import time

from .base_fetcher import BaseFetcher
from fetchers.providers.base import DataProvider, ProviderResponse


class PredictionsFetcher(BaseFetcher):
    """Fetcher for predictions data from API-Football with comprehensive feature extraction"""

    def __init__(self, *, db_config: Dict[str, str], provider: DataProvider, sport: str = "football"):
        super().__init__(db_config=db_config, provider=provider, sport=sport)

    def fetch_and_store(self,
                       fixture_ids: List[int] = None,
                       days_ahead: int = 7,
                       force_refresh: bool = False,
                       league_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch predictions for fixtures and store comprehensive analysis data

        Args:
            fixture_ids: List of specific fixture IDs, or None for upcoming fixtures
            days_ahead: How many days ahead to fetch predictions for (if fixture_ids not specified)
            force_refresh: Whether to refresh existing predictions

        Returns:
            Dict with operation results and statistics
        """

        predictions_processed = 0
        predictions_new = 0
        predictions_updated = 0
        predictions_errors = 0
        api_calls_made = 0

        try:
            # Determine which fixtures to process
            target_league_id = league_id or self.get_target_league_id()

            if fixture_ids is None:
                fixture_ids = self._get_fixtures_for_predictions(days_ahead, force_refresh, target_league_id)

            if not fixture_ids:
                self.logger.info("No fixtures found for predictions fetch")
                return {
                    'success': True,
                    'message': 'No fixtures require predictions',
                    'predictions_processed': 0
                }

            self.logger.info(f"Processing predictions for {len(fixture_ids)} fixtures")

            # Process fixtures in batches to manage API rate limits
            def store_operation(conn):
                nonlocal predictions_processed, predictions_new, predictions_updated, predictions_errors, api_calls_made

                with conn.cursor(row_factory=dict_row) as cursor:
                    for fixture_id in fixture_ids:
                        try:
                            # Check if we should skip this fixture
                            if not force_refresh and self._should_skip_fixture(cursor, fixture_id):
                                continue

                            provider_response: ProviderResponse = self.provider.fetch_predictions(
                                fixture_ids=[fixture_id]
                            )
                            api_calls_made += provider_response.metadata.get("api_calls", 0)

                            for error in provider_response.errors:
                                self.logger.warning(
                                    f"Provider error while fetching predictions for fixture {fixture_id}: {error}"
                                )

                            if not provider_response.records:
                                self.logger.warning(
                                    f"No predictions data available for fixture {fixture_id}"
                                )
                                predictions_errors += 1
                                continue

                            # Process prediction data
                            prediction_record = provider_response.records[0]
                            prediction_data = prediction_record.payload
                            result = self._process_single_prediction(
                                cursor,
                                fixture_id,
                                prediction_data,
                                {"response": [prediction_data]},
                            )

                            if result['action'] == 'updated':
                                predictions_updated += 1
                            elif result['action'] == 'inserted':
                                predictions_new += 1

                            predictions_processed += 1

                            # Rate limiting between API calls
                            time.sleep(0.1)

                        except Exception as e:
                            self.logger.error(f"Error processing prediction for fixture {fixture_id}: {str(e)}")
                            predictions_errors += 1
                            continue

                return {
                    'processed': predictions_processed,
                    'new': predictions_new,
                    'updated': predictions_updated,
                    'errors': predictions_errors
                }

            # Execute database operation
            db_results = self.safe_db_operation(store_operation)

            # Compile results
            operation_results = {
                'success': True,
                'predictions_processed': db_results['processed'],
                'predictions_new': db_results['new'],
                'predictions_updated': db_results['updated'],
                'predictions_errors': db_results['errors'],
                'api_calls': api_calls_made,
                'fixtures_attempted': len(fixture_ids)
            }

            # Log summary
            self.log_fetch_summary("Predictions fetch", {
                'processed': db_results['processed'],
                'new': db_results['new'],
                'updated': db_results['updated'],
                'errors': db_results['errors'],
                'api_calls': api_calls_made
            })

            return operation_results

        except Exception as e:
            error_msg = f"Predictions fetch operation failed: {str(e)}"
            self.logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'predictions_processed': predictions_processed,
                'api_calls': api_calls_made
            }

    def _get_fixtures_for_predictions(self, days_ahead: int, force_refresh: bool, league_id: int) -> List[int]:
        """Get list of fixture IDs that need predictions"""

        def get_fixtures_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                if force_refresh:
                    # Get all upcoming fixtures regardless of existing predictions
                    cursor.execute(f"""
                        SELECT fixture_id
                        FROM fixtures_raw
                        WHERE date BETWEEN NOW() + INTERVAL '1 hour' AND NOW() + INTERVAL '{days_ahead} days'
                          AND status IN ('SCHEDULED', 'TIMED', 'NS')
                          AND league_id = %s
                        ORDER BY date ASC
                        LIMIT 50
                    """, (league_id,))
                else:
                    # Get fixtures without predictions or with old predictions
                    cursor.execute(f"""
                        SELECT fr.fixture_id
                        FROM fixtures_raw fr
                        LEFT JOIN predictions_raw pr ON fr.fixture_id = pr.fixture_id
                        WHERE fr.date BETWEEN NOW() + INTERVAL '1 hour' AND NOW() + INTERVAL '{days_ahead} days'
                          AND fr.status IN ('SCHEDULED', 'TIMED', 'NS')
                          AND fr.league_id = %s
                          AND (pr.fixture_id IS NULL OR pr.queried_at < NOW() - INTERVAL '24 hours')
                        ORDER BY fr.date ASC
                        LIMIT 50
                    """, (league_id,))

                return [row['fixture_id'] for row in cursor.fetchall()]

        try:
            return self.safe_db_operation(get_fixtures_operation)
        except Exception as e:
            self.logger.error(f"Error getting fixtures for predictions: {str(e)}")
            return []

    def _should_skip_fixture(self, cursor, fixture_id: int) -> bool:
        """Check if we should skip fetching prediction for this fixture"""

        # Check if prediction exists and is recent
        cursor.execute("""
            SELECT queried_at
            FROM predictions_raw
            WHERE fixture_id = %s
        """, (fixture_id,))

        result = cursor.fetchone()
        if result:
            last_fetch = result['queried_at']
            hours_since_fetch = (datetime.now() - last_fetch).total_seconds() / 3600

            # Skip if fetched within last 12 hours
            if hours_since_fetch < 12:
                self.logger.debug(f"Skipping fixture {fixture_id} - prediction fetched {hours_since_fetch:.1f}h ago")
                return True

        return False

    def _process_single_prediction(self, cursor, fixture_id: int,
                                  prediction_data: Dict[str, Any],
                                  full_api_response: Dict[str, Any]) -> Dict[str, str]:
        """Process and store a single prediction with rich feature extraction"""

        # Extract structured data from the prediction
        processed_data = self._extract_prediction_features(prediction_data)
        processed_data['fixture_id'] = fixture_id
        processed_data['sport'] = self.sport
        processed_data['raw_response'] = json.dumps(full_api_response)

        # Check if prediction already exists
        cursor.execute(
            "SELECT fixture_id FROM predictions_raw WHERE fixture_id = %s",
            (fixture_id,)
        )
        exists = cursor.fetchone()

        if exists:
            # Update existing prediction
            cursor.execute("""
                UPDATE predictions_raw SET
                    winner_data = %(winner_data)s,
                    win_or_draw = %(win_or_draw)s,
                    under_over = %(under_over)s,
                    goals_prediction = %(goals_prediction)s,
                    advice = %(advice)s,
                    percent_predictions = %(percent_predictions)s,
                    home_team_analysis = %(home_team_analysis)s,
                    away_team_analysis = %(away_team_analysis)s,
                    comparison_metrics = %(comparison_metrics)s,
                    h2h_matches = %(h2h_matches)s,
                    raw_response = %(raw_response)s,
                    sport = %(sport)s,
                    queried_at = NOW()
                WHERE fixture_id = %(fixture_id)s
            """, processed_data)

            self.logger.debug(f"Updated prediction for fixture {fixture_id}")
            return {'action': 'updated', 'fixture_id': fixture_id}

        else:
            # Insert new prediction
            cursor.execute("""
                INSERT INTO predictions_raw (
                    fixture_id, sport, winner_data, win_or_draw, under_over,
                    goals_prediction, advice, percent_predictions,
                    home_team_analysis, away_team_analysis,
                    comparison_metrics, h2h_matches, raw_response
                ) VALUES (
                    %(fixture_id)s, %(sport)s, %(winner_data)s, %(win_or_draw)s,
                    %(under_over)s, %(goals_prediction)s, %(advice)s,
                    %(percent_predictions)s, %(home_team_analysis)s,
                    %(away_team_analysis)s, %(comparison_metrics)s,
                    %(h2h_matches)s, %(raw_response)s
                )
            """, processed_data)

            self.logger.debug(f"Inserted new prediction for fixture {fixture_id}")
            return {'action': 'inserted', 'fixture_id': fixture_id}

    def _extract_prediction_features(self, prediction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and structure rich prediction features"""

        predictions = prediction_data.get('predictions', {})
        teams = prediction_data.get('teams', {})
        comparison = prediction_data.get('comparison', {})
        h2h = prediction_data.get('h2h', [])

        # Extract winner prediction with confidence and comment
        winner_data = predictions.get('winner', {})
        self.logger.debug(f"Winner prediction: {winner_data}")

        # Extract percentage predictions
        percent_data = predictions.get('percent', {})

        # Extract goals prediction
        goals_data = predictions.get('goals', {})

        # Extract advice
        advice = predictions.get('advice', '')

        # Extract comprehensive team analysis
        home_team_data = teams.get('home', {})
        away_team_data = teams.get('away', {})

        # Process home team analysis
        home_analysis = self._process_team_analysis(home_team_data, 'home')
        away_analysis = self._process_team_analysis(away_team_data, 'away')

        # Extract comparison metrics (crucial for feature engineering)
        comparison_metrics = self._process_comparison_metrics(comparison)

        # Process H2H data
        h2h_processed = self._process_h2h_data(h2h)

        return {
            'winner_data': json.dumps(winner_data),
            'win_or_draw': predictions.get('win_or_draw'),
            'under_over': predictions.get('under_over'),
            'goals_prediction': json.dumps(goals_data),
            'advice': advice,
            'percent_predictions': json.dumps(percent_data),
            'home_team_analysis': json.dumps(home_analysis),
            'away_team_analysis': json.dumps(away_analysis),
            'comparison_metrics': json.dumps(comparison_metrics),
            'h2h_matches': json.dumps(h2h_processed)
        }

    def _process_team_analysis(self, team_data: Dict[str, Any], team_side: str) -> Dict[str, Any]:
        """Process comprehensive team analysis data"""

        if not team_data:
            return {}

        # Extract team basic info
        team_info = {
            'id': team_data.get('id'),
            'name': team_data.get('name'),
            'logo': team_data.get('logo')
        }

        # Extract last 5 games analysis
        last_5 = team_data.get('last_5', {})
        last_5_processed = {
            'form': last_5.get('form', ''),
            'att': last_5.get('att', ''),
            'def': last_5.get('def', ''),
            'goals': {
                'for': {
                    'total': last_5.get('goals', {}).get('for', {}).get('total', 0),
                    'average': last_5.get('goals', {}).get('for', {}).get('average', '0.0')
                },
                'against': {
                    'total': last_5.get('goals', {}).get('against', {}).get('total', 0),
                    'average': last_5.get('goals', {}).get('against', {}).get('average', '0.0')
                }
            }
        }

        # Extract league statistics
        league_stats = team_data.get('league', {})
        league_processed = {
            'form': league_stats.get('form', ''),
            'fixtures': league_stats.get('fixtures', {}),
            'goals': league_stats.get('goals', {}),
            'biggest': league_stats.get('biggest', {}),
            'clean_sheet': league_stats.get('clean_sheet', {}),
            'failed_to_score': league_stats.get('failed_to_score', {}),
            'penalty': league_stats.get('penalty', {}),
            'lineups': league_stats.get('lineups', []),
            'cards': league_stats.get('cards', {})
        }

        return {
            'team_info': team_info,
            'last_5': last_5_processed,
            'league': league_processed
        }

    def _process_comparison_metrics(self, comparison: Dict[str, Any]) -> Dict[str, Any]:
        """Process comparison metrics between teams (crucial for ML features)"""

        if not comparison:
            return {}

        # These metrics are percentage-based comparisons between teams
        processed_comparison = {}

        # Form comparison
        if 'form' in comparison:
            processed_comparison['form'] = comparison['form']

        # Attack comparison
        if 'att' in comparison:
            processed_comparison['att'] = comparison['att']

        # Defense comparison
        if 'def' in comparison:
            processed_comparison['def'] = comparison['def']

        # Poisson distribution (very important for probability calculations)
        if 'poisson_distribution' in comparison:
            processed_comparison['poisson_distribution'] = comparison['poisson_distribution']

        # H2H comparison
        if 'h2h' in comparison:
            processed_comparison['h2h'] = comparison['h2h']

        # Goals comparison
        if 'goals' in comparison:
            processed_comparison['goals'] = comparison['goals']

        # Total comparison
        if 'total' in comparison:
            processed_comparison['total'] = comparison['total']

        return processed_comparison

    def _process_h2h_data(self, h2h_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process head-to-head historical data"""

        if not h2h_data:
            return []

        processed_h2h = []

        for match in h2h_data:
            if not match or 'fixture' not in match:
                continue

            processed_match = {
                'fixture_id': match['fixture'].get('id'),
                'date': match['fixture'].get('date'),
                'venue': match['fixture'].get('venue', {}),
                'status': match['fixture'].get('status', {}),
                'teams': match.get('teams', {}),
                'goals': match.get('goals', {}),
                'score': match.get('score', {})
            }

            # Only include matches with complete data
            if processed_match['fixture_id'] and processed_match['goals']:
                processed_h2h.append(processed_match)

        # Sort by date (most recent first)
        processed_h2h.sort(key=lambda x: x['date'] or '', reverse=True)

        return processed_h2h

    def get_predictions_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics about stored predictions"""

        def stats_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                # Overall prediction stats
                cursor.execute("""
                    SELECT
                        COUNT(*) as total_predictions,
                        COUNT(CASE WHEN advice IS NOT NULL AND advice != '' THEN 1 END) as with_advice,
                        COUNT(CASE WHEN h2h_matches != '[]' THEN 1 END) as with_h2h_data,
                        AVG(CASE
                            WHEN percent_predictions->>'home' ~ '^[0-9]+\.?[0-9]*%?$'
                            THEN CAST(TRIM(TRAILING '%' FROM percent_predictions->>'home') AS FLOAT)
                            ELSE NULL
                        END) as avg_home_win_probability,
                        MIN(queried_at) as earliest_prediction,
                        MAX(queried_at) as latest_prediction
                    FROM predictions_raw pr
                    JOIN fixtures_raw fr ON pr.fixture_id = fr.fixture_id
                    WHERE fr.league_id = %s
                """, (self.get_target_league_id(),))

                stats = cursor.fetchone()

                # Advice analysis
                cursor.execute("""
                    SELECT advice, COUNT(*) as count
                    FROM predictions_raw pr
                    JOIN fixtures_raw fr ON pr.fixture_id = fr.fixture_id
                    WHERE fr.league_id = %s
                      AND advice IS NOT NULL
                      AND advice != ''
                    GROUP BY advice
                    ORDER BY count DESC
                    LIMIT 10
                """, (self.get_target_league_id(),))

                advice_breakdown = {row['advice']: row['count'] for row in cursor.fetchall()}

                return {
                    'total_predictions': stats['total_predictions'],
                    'with_advice': stats['with_advice'],
                    'with_h2h_data': stats['with_h2h_data'],
                    'avg_home_win_probability': float(stats['avg_home_win_probability']) if stats['avg_home_win_probability'] else None,
                    'earliest_prediction': stats['earliest_prediction'].isoformat() if stats['earliest_prediction'] else None,
                    'latest_prediction': stats['latest_prediction'].isoformat() if stats['latest_prediction'] else None,
                    'top_advice': advice_breakdown
                }

        try:
            return self.safe_db_operation(stats_operation)
        except Exception as e:
            self.logger.error(f"Error getting predictions stats: {str(e)}")
            return {'error': str(e)}

    def validate_prediction_data_quality(self, fixture_id: int) -> Dict[str, Any]:
        """Validate the quality and completeness of prediction data for a fixture"""

        def validation_operation(conn):
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute("""
                    SELECT *
                    FROM predictions_raw
                    WHERE fixture_id = %s
                """, (fixture_id,))

                prediction = cursor.fetchone()

                if not prediction:
                    return {'valid': False, 'reason': 'No prediction data found'}

                quality_checks = {
                    'has_winner_data': bool(prediction['winner_data'] and prediction['winner_data'] != 'null'),
                    'has_percentages': bool(prediction['percent_predictions'] and prediction['percent_predictions'] != '{}'),
                    'has_advice': bool(prediction['advice'] and prediction['advice'].strip()),
                    'has_comparison_metrics': bool(prediction['comparison_metrics'] and prediction['comparison_metrics'] != '{}'),
                    'has_team_analysis': bool(prediction['home_team_analysis'] and prediction['away_team_analysis']),
                    'has_h2h_data': bool(prediction['h2h_matches'] and prediction['h2h_matches'] != '[]'),
                    'data_is_recent': (datetime.now() - prediction['queried_at']).total_seconds() < 24 * 3600
                }

                quality_score = sum(quality_checks.values()) / len(quality_checks)

                return {
                    'valid': quality_score >= 0.6,  # At least 60% of checks pass
                    'quality_score': quality_score,
                    'checks': quality_checks,
                    'last_updated': prediction['queried_at'].isoformat()
                }

        try:
            return self.safe_db_operation(validation_operation)
        except Exception as e:
            self.logger.error(f"Error validating prediction data for fixture {fixture_id}: {str(e)}")
            return {'valid': False, 'reason': f'Validation error: {str(e)}'}
