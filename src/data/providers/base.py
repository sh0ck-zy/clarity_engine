"""
Generic data provider interfaces for ingesting football data from multiple sources.

These abstractions allow the ingestion layer to work with APIs, scrapers, or partner
feeds interchangeably by returning normalized provider records plus lightweight metadata.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProviderRecord:
    """Single data item returned by a provider."""

    resource: str
    payload: Dict[str, Any]
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Batch of provider records plus contextual metadata."""

    records: List[ProviderRecord] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def extend(self, other: "ProviderResponse") -> None:
        """Merge another provider response into this one."""
        self.records.extend(other.records)
        self.errors.extend(other.errors)
        self.metadata.update(other.metadata)


class DataProvider(ABC):
    """Abstract provider interface that supports multiple ingestion back-ends."""

    name: str = "unknown"

    # --- Raw access -----------------------------------------------------------

    def fetch_raw(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Optional raw fetch; providers can override when direct access is available."""
        raise NotImplementedError("Raw fetch not implemented for this provider")

    # --- Generic resource access -------------------------------------------------

    @abstractmethod
    def fetch_fixtures(
        self,
        *,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        fixture_ids: Optional[List[int]] = None,
    ) -> ProviderResponse:
        """Fetch fixtures matching the supplied criteria."""

    @abstractmethod
    def fetch_predictions(
        self,
        *,
        fixture_ids: List[int],
    ) -> ProviderResponse:
        """Fetch model predictions for the given fixtures."""

    @abstractmethod
    def fetch_odds(
        self,
        *,
        fixture_id: int,
        bookmaker_id: Optional[str] = None,
        market: Optional[str] = None,
    ) -> ProviderResponse:
        """Fetch odds for a single fixture (optionally filtered by bookmaker/market)."""

    @abstractmethod
    def fetch_injuries(
        self,
        *,
        fixture_ids: Optional[List[int]] = None,
        league_id: Optional[int] = None,
        season: Optional[int] = None,
        team_id: Optional[int] = None,
    ) -> ProviderResponse:
        """Fetch injury reports using any supported lookup options."""

    # --- Utility -----------------------------------------------------------------

    def supports(self, resource: str) -> bool:
        """Return True if the provider implements a given resource."""
        supported = {
            "fixtures": self.fetch_fixtures,
            "predictions": self.fetch_predictions,
            "odds": self.fetch_odds,
            "injuries": self.fetch_injuries,
        }
        return resource in supported and callable(supported[resource])
