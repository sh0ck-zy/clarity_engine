# Real-time Ingestion (Stubs)

This module provides placeholders for future real-time ingestion from paid APIs. The adapters are not functional until API keys and endpoints are configured.

## Configuration

Config lives in `config/realtime_ingestion.json` with placeholder API keys and rate limits.

```json
{
  "api_football": {
    "api_key": "REPLACE_ME",
    "base_url": "https://v3.football.api-sports.io",
    "rate_limit": {
      "requests_per_minute": 60,
      "burst": 10
    }
  },
  "odds_api": {
    "api_key": "REPLACE_ME",
    "base_url": "https://api.the-odds-api.com",
    "rate_limit": {
      "requests_per_minute": 60,
      "burst": 10
    }
  }
}
```

## Usage

```python
from src.ingestion.realtime_ingestion import build_realtime_adapters

adapters = build_realtime_adapters()
api_football = adapters["api_football"]
```

Each adapter exposes the following methods:

- `fetch_fixtures(since=None)`
- `fetch_lineups(fixture_id)`
- `fetch_odds(fixture_id)`

These methods currently raise `NotImplementedError` until real API access is available.
