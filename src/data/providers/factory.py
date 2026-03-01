"""
Provider factory utilities to instantiate data providers from configuration.
"""

from __future__ import annotations

import os
from typing import Optional

from config.config import ProviderConfig
from .api_football import ApiFootballProvider
from .zerozero import ZeroZeroProvider


def create_provider(
    provider_config: ProviderConfig,
    sport: str,
    api_key_override: Optional[str] = None,
):
    """
    Instantiate a configured provider for the given sport.

    Currently supports API-Football (football) but is designed to be extended
    for other sports and provider types (scrapers, partner feeds, etc.).
    """

    provider_type = provider_config.type
    config = provider_config.config or {}

    if provider_type in {"api_football", "api"}:
        env_key = config.get("env_api_key", "API_FOOTBALL_KEY")
        api_key: Optional[str] = api_key_override or os.getenv(env_key)

        if not api_key:
            raise ValueError(
                f"API key environment variable '{env_key}' is not set for provider '{provider_config.key}'"
            )

        rate_limits = config.get("rate_limits", {})
        bookmakers = config.get("bookmakers", {})

        return ApiFootballProvider(
            api_key=api_key,
            sport=sport,
            min_request_interval=rate_limits.get("delay_between_calls", 0.1),
            daily_request_limit=rate_limits.get("max_calls_per_hour", 900),
            bookmaker_config=bookmakers,
        )

    elif provider_type == "zerozero":
        # ZeroZero scraper doesn't need API key
        rate_limits = config.get("rate_limits", {})
        
        return ZeroZeroProvider(
            min_request_interval=rate_limits.get("delay_between_calls", 1.0),
            base_url=config.get("base_url", "https://www.zerozero.pt"),
        )

    raise ValueError(f"Unsupported provider type '{provider_type}' for provider '{provider_config.key}'")
