import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from fetchers.providers.base import DataProvider
from config.config import get_enabled_league_ids, get_sport_settings


class BaseFetcher(ABC):
    """Base class for ingestion fetchers that operate on top of a data provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        db_config: Optional[Dict[str, str]] = None,
        *,
        provider: Optional[DataProvider] = None,
        sport: str = "football",
    ):
        if db_config is None:
            raise ValueError("db_config must be provided to BaseFetcher")

        if provider is None:
            if api_key is None:
                raise ValueError("Either provider or api_key must be supplied")
            from fetchers.providers.api_football import ApiFootballProvider

            provider = ApiFootballProvider(api_key, sport=sport)

        self.db_config = db_config
        self.provider = provider
        self.sport = sport

        # Ensure provider knows which sport it serves
        if hasattr(self.provider, "sport"):
            setattr(self.provider, "sport", sport)

        # Setup logging
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def get_db_connection(self):
        """Get database connection with connection pooling support."""
        try:
            return psycopg.connect(
                host=self.db_config["host"],
                dbname=self.db_config["database"],  # psycopg3 uses 'dbname'
                user=self.db_config["user"],
                password=self.db_config["password"],
                port=self.db_config.get("port", 5432),
                connect_timeout=30,
                options="-c statement_timeout=30000",
            )
        except psycopg.Error as exc:
            self.logger.error(f"Database connection failed: {exc}")
            raise

    def safe_db_operation(self, operation_func, *args, **kwargs):
        """Execute database operation with retry logic and error handling."""
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                with self.get_db_connection() as conn:
                    conn.autocommit = False
                    try:
                        result = operation_func(conn, *args, **kwargs)
                        conn.commit()
                        return result
                    except Exception:
                        conn.rollback()
                        raise
            except psycopg.OperationalError as exc:
                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Database operation failed (attempt {attempt + 1}/{max_retries}): {exc}. "
                        f"Retrying in {retry_delay}s..."
                    )
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                self.logger.error(
                    f"Database operation failed after {max_retries} attempts: {exc}"
                )
                raise
            except Exception as exc:
                self.logger.error(f"Database operation error: {exc}")
                raise

    def make_api_call(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Backward-compatible helper that delegates to the provider's raw fetch."""
        if hasattr(self.provider, "fetch_raw"):
            return self.provider.fetch_raw(endpoint, params or {})
        raise NotImplementedError(
            f"Provider {self.provider} does not support raw API access for endpoint '{endpoint}'"
        )

    @abstractmethod
    def fetch_and_store(self, **kwargs) -> Dict[str, Any]:
        """Fetch data from provider and persist it."""
        raise NotImplementedError

    def get_target_league_id(self) -> int:
        """Return default league ID for the configured sport."""
        league_ids = get_enabled_league_ids(self.sport)
        if league_ids:
            return league_ids[0]
        # Fallback to historical default if configuration missing
        return 94

    def get_current_season(self) -> int:
        """Get current season year based on football season cycle."""
        sport_settings = get_sport_settings(self.sport)
        return sport_settings.default_season

    def validate_fixture_data(self, fixture_data: Dict[str, Any]) -> bool:
        """Validate fixture data structure."""
        if not fixture_data:
            self.logger.warning("Empty fixture data received")
            return False

        fixture = fixture_data.get("fixture", {})
        if "id" not in fixture:
            self.logger.warning("Missing fixture ID")
            return False

        teams = fixture_data.get("teams", {})
        if "home" not in teams or "away" not in teams:
            self.logger.warning("Missing home or away team data")
            return False

        return True

    def log_fetch_summary(self, operation_name: str, results: Dict[str, Any]):
        """Log a summary of fetch operation results."""
        self.logger.info(
            f"{operation_name} completed - "
            f"Processed: {results.get('processed', 0)}, "
            f"New: {results.get('new', 0)}, "
            f"Updated: {results.get('updated', 0)}, "
            f"Errors: {results.get('errors', 0)}, "
            f"API calls: {results.get('api_calls', 0)}"
        )

    def get_upcoming_fixtures(self, conn, days_ahead: int = 7) -> List[int]:
        """Get list of upcoming fixture IDs for the target league."""
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT fixture_id
                FROM fixtures_raw
                WHERE date BETWEEN NOW() AND NOW() + INTERVAL '%s days'
                  AND status IN ('SCHEDULED', 'TIMED')
                  AND league_id = %s
                ORDER BY date ASC
            """,
                (days_ahead, self.get_target_league_id()),
            )

            return [row["fixture_id"] for row in cursor.fetchall()]

    def check_data_freshness(
        self, conn, table_name: str, hours_threshold: int = 24
    ) -> bool:
        """Check if data in table is fresh (updated within threshold)."""
        timestamp_column = {
            "fixtures_raw": "queried_at",
            "predictions_raw": "queried_at",
            "odds_raw": "queried_at",
            "match_features": "calculated_at",
        }.get(table_name, "queried_at")

        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT COUNT(*) as fresh_count
                FROM {table_name}
                WHERE {timestamp_column} > NOW() - INTERVAL '%s hours'
            """,
                (hours_threshold,),
            )

            result = cursor.fetchone()
            fresh_count = result[0] if result else 0

            self.logger.debug(
                f"Data freshness check for {table_name}: {fresh_count} records updated "
                f"in last {hours_threshold}h"
            )
            return fresh_count > 0
