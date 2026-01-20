import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "realtime_ingestion.json"


@dataclass(frozen=True)
class RateLimitConfig:
    requests_per_minute: int
    burst: int


@dataclass(frozen=True)
class APIConfig:
    api_key: str
    base_url: str
    rate_limit: RateLimitConfig


@dataclass(frozen=True)
class RealtimeIngestionConfig:
    api_football: APIConfig
    odds_api: APIConfig


def _parse_api_config(payload: dict) -> APIConfig:
    rate_limit = payload.get("rate_limit", {})
    return APIConfig(
        api_key=payload.get("api_key", ""),
        base_url=payload.get("base_url", ""),
        rate_limit=RateLimitConfig(
            requests_per_minute=int(rate_limit.get("requests_per_minute", 60)),
            burst=int(rate_limit.get("burst", 10)),
        ),
    )


def load_realtime_config(path: Optional[Path] = None) -> RealtimeIngestionConfig:
    config_path = path or DEFAULT_CONFIG_PATH
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return RealtimeIngestionConfig(
        api_football=_parse_api_config(data.get("api_football", {})),
        odds_api=_parse_api_config(data.get("odds_api", {})),
    )


class APIAdapter(ABC):
    def __init__(self, config: APIConfig) -> None:
        self.config = config

    @abstractmethod
    def fetch_fixtures(self, since: Optional[datetime] = None) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_lineups(self, fixture_id: str) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def fetch_odds(self, fixture_id: str) -> list[dict]:
        raise NotImplementedError


class APIFootballAdapter(APIAdapter):
    def fetch_fixtures(self, since: Optional[datetime] = None) -> list[dict]:
        raise NotImplementedError("APIFootballAdapter is a placeholder for future API keys.")

    def fetch_lineups(self, fixture_id: str) -> list[dict]:
        raise NotImplementedError("APIFootballAdapter is a placeholder for future API keys.")

    def fetch_odds(self, fixture_id: str) -> list[dict]:
        raise NotImplementedError("APIFootballAdapter is a placeholder for future API keys.")


class OddsAPIAdapter(APIAdapter):
    def fetch_fixtures(self, since: Optional[datetime] = None) -> list[dict]:
        raise NotImplementedError("OddsAPIAdapter is a placeholder for future API keys.")

    def fetch_lineups(self, fixture_id: str) -> list[dict]:
        raise NotImplementedError("OddsAPIAdapter is a placeholder for future API keys.")

    def fetch_odds(self, fixture_id: str) -> list[dict]:
        raise NotImplementedError("OddsAPIAdapter is a placeholder for future API keys.")


def build_realtime_adapters(
    config: Optional[RealtimeIngestionConfig] = None,
) -> dict[str, APIAdapter]:
    resolved = config or load_realtime_config()
    return {
        "api_football": APIFootballAdapter(resolved.api_football),
        "odds_api": OddsAPIAdapter(resolved.odds_api),
    }
