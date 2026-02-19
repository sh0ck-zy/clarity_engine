"""
API-Football provider implementation for the generic ingestion adapters.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import requests

from .base import DataProvider, ProviderRecord, ProviderResponse


class ApiFootballProvider(DataProvider):
    """Adapter that wraps API-Football HTTP endpoints behind the generic provider interface."""

    name = "api_football"

    def __init__(
        self,
        api_key: str,
        *,
        sport: str = "football",
        host: str = "v3.football.api-sports.io",
        min_request_interval: float = 0.1,
        daily_request_limit: int = 900,
        session: Optional[requests.Session] = None,
        logger: Optional[logging.Logger] = None,
        bookmaker_config: Optional[Dict[str, Any]] = None,
    ):
        self.api_key = api_key
        self.host = host
        self.min_request_interval = min_request_interval
        self.daily_request_limit = daily_request_limit
        self.sport = sport
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": host,
            }
        )

        bookmaker_config = bookmaker_config or {}
        self.primary_bookmakers = bookmaker_config.get("primary", [])
        self.backup_bookmakers = bookmaker_config.get("backups", [])

        self.logger = logger or logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self._last_request_time = 0.0
        self._request_count = 0

    # --------------------------------------------------------------------- #
    # Provider interface implementations
    # --------------------------------------------------------------------- #

    def fetch_raw(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Expose raw endpoint access for legacy fetchers."""
        return self._request(endpoint, params)

    def fetch_fixtures(
        self,
        *,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        fixture_ids: Optional[List[int]] = None,
    ) -> ProviderResponse:
        response = ProviderResponse(metadata={"api_calls": 0, "provider": self.name, "sport": self.sport})

        if fixture_ids:
            batch_size = 20
            for idx in range(0, len(fixture_ids), batch_size):
                batch_ids = fixture_ids[idx : idx + batch_size]
                payload = self._request(
                    "fixtures", {"ids": "-".join(map(str, batch_ids))}
                )
                response.metadata["api_calls"] += 1
                response.records.extend(
                    [
                        ProviderRecord(
                            resource="fixtures",
                            payload=item,
                            source=self.name,
                            metadata={
                                "fixture_id": item.get("fixture", {}).get("id"),
                                "sport": self.sport,
                            },
                        )
                        for item in payload.get("response", [])
                    ]
                )
        else:
            params: Dict[str, Any] = {}
            if league_id is not None:
                params["league"] = league_id
            if season is not None:
                params["season"] = season
            if date_from:
                params["from"] = date_from
            if date_to:
                params["to"] = date_to

            payload = self._request("fixtures", params)
            response.metadata["api_calls"] += 1
            response.records.extend(
                [
                    ProviderRecord(
                        resource="fixtures",
                        payload=item,
                        source=self.name,
                        metadata={
                            "fixture_id": item.get("fixture", {}).get("id"),
                            "sport": self.sport,
                        },
                    )
                    for item in payload.get("response", [])
                ]
            )

        return response

    def fetch_predictions(self, *, fixture_ids: List[int]) -> ProviderResponse:
        response = ProviderResponse(metadata={"api_calls": 0, "provider": self.name, "sport": self.sport})

        for fixture_id in fixture_ids:
            payload = self._request("predictions", {"fixture": fixture_id})
            response.metadata["api_calls"] += 1

            predictions = payload.get("response", [])
            if not predictions:
                response.errors.append(f"No predictions for fixture {fixture_id}")
                continue

            response.records.extend(
                [
                    ProviderRecord(
                        resource="predictions",
                        payload=item,
                        source=self.name,
                        metadata={"fixture_id": fixture_id, "sport": self.sport},
                    )
                    for item in predictions
                ]
            )

        return response

    def fetch_odds(
        self,
        *,
        fixture_id: int,
        bookmaker_id: Optional[str] = None,
        market: Optional[str] = None,
    ) -> ProviderResponse:
        params: Dict[str, Any] = {"fixture": fixture_id}
        if bookmaker_id:
            params["bookmaker"] = bookmaker_id
        if market:
            params["bet"] = market

        payload = self._request("odds", params)

        return ProviderResponse(
            records=[
                ProviderRecord(
                    resource="odds",
                    payload=item,
                    source=self.name,
                    metadata={
                        "fixture_id": fixture_id,
                        "bookmaker_id": bookmaker_id,
                        "sport": self.sport,
                    },
                )
                for item in payload.get("response", [])
            ],
            metadata={"api_calls": 1, "provider": self.name, "sport": self.sport},
        )

    def fetch_injuries(
        self,
        *,
        fixture_ids: Optional[List[int]] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        team_id: Optional[int] = None,
    ) -> ProviderResponse:
        response = ProviderResponse(metadata={"api_calls": 0, "provider": self.name, "sport": self.sport})

        if fixture_ids:
            for fixture_id in fixture_ids:
                payload = self._request("injuries", {"fixture": fixture_id})
                response.metadata["api_calls"] += 1
                response.records.extend(
                    [
                        ProviderRecord(
                            resource="injuries",
                            payload=item,
                            source=self.name,
                            metadata={
                                "fixture_id": fixture_id,
                                "team_id": item.get("team", {}).get("id"),
                                "sport": self.sport,
                            },
                        )
                        for item in payload.get("response", [])
                    ]
                )
        elif league_id and season:
            payload = self._request("injuries", {"league": league_id, "season": season})
            response.metadata["api_calls"] += 1
            response.records.extend(
                [
                    ProviderRecord(
                            resource="injuries",
                            payload=item,
                            source=self.name,
                            metadata={
                                "fixture_id": item.get("fixture", {}).get("id"),
                                "team_id": item.get("team", {}).get("id"),
                                "sport": self.sport,
                            },
                        )
                        for item in payload.get("response", [])
                    ]
                )
        elif team_id:
            payload = self._request("injuries", {"team": team_id})
            response.metadata["api_calls"] += 1
            response.records.extend(
                [
                    ProviderRecord(
                            resource="injuries",
                            payload=item,
                            source=self.name,
                            metadata={
                                "fixture_id": item.get("fixture", {}).get("id"),
                                "team_id": team_id,
                                "sport": self.sport,
                            },
                        )
                        for item in payload.get("response", [])
                    ]
                )
        else:
            response.errors.append("No parameters supplied for injuries fetch")

        return response

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a raw API-Football request with retry, throttling, and logging."""

        if self._request_count >= self.daily_request_limit:
            raise RuntimeError(
                f"Daily API-Football request limit reached ({self.daily_request_limit})."
            )

        self._respect_rate_limit()

        url = f"https://{self.host}/{endpoint}"
        params = params or {}

        try:
            self.logger.info("API-Football request: %s %s", endpoint, params)
            response = self.session.get(url, params=params, timeout=30)
            self._last_request_time = time.time()
            self._request_count += 1
            response.raise_for_status()
            data = response.json()

            if not isinstance(data, dict):
                raise ValueError(f"Unexpected API response type: {type(data)}")

            if data.get("errors"):
                raise RuntimeError(f"API returned errors: {data['errors']}")

            return data

        except requests.exceptions.Timeout as exc:
            self.logger.error("API-Football timeout on %s: %s", endpoint, exc)
            raise
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response else "unknown"
            self.logger.error("HTTP error %s on %s: %s", status, endpoint, exc)
            if exc.response and exc.response.status_code == 429:
                retry_after = exc.response.headers.get("Retry-After", "unknown")
                raise RuntimeError(f"Rate limit exceeded. Retry after {retry_after}") from exc
            raise
        except requests.exceptions.RequestException as exc:
            self.logger.error("Request error on %s: %s", endpoint, exc)
            raise

    def _respect_rate_limit(self) -> None:
        """Sleep if needed to respect API-Football per-request minimum interval."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.min_request_interval:
            sleep_for = self.min_request_interval - elapsed
            time.sleep(sleep_for)
