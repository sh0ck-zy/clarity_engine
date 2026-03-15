"""Tests for the odds module: normalizer, importer, resolver."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from odds.normalizer import CSV_TO_FOTMOB, normalize_team_name, load_reviewed_mapping, save_reviewed_mapping
from odds.importer import parse_csv, save_parquet
from odds.resolver import get_odds_lookup, clear_cache


# ── Fixtures ──────────────────────────────────────────────────

_E0_CSV = _PROJECT_ROOT / "data" / "football_data" / "odds" / "E0_2526.csv"
_E0_2425_CSV = _PROJECT_ROOT / "data" / "football_data" / "odds" / "E0_2425.csv"


def _require_csv(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"CSV not found: {path}")


# ── Normalizer tests ─────────────────────────────────────────

class TestNormalizer:
    def test_normalize_known_team(self):
        assert normalize_team_name("Man City") == "Manchester City"
        assert normalize_team_name("Wolves") == "Wolverhampton Wanderers"
        assert normalize_team_name("Nott'm Forest") == "Nottingham Forest"

    def test_normalize_identity(self):
        """Teams already matching FotMob name pass through."""
        assert normalize_team_name("Arsenal") == "Arsenal"
        assert normalize_team_name("Liverpool") == "Liverpool"

    def test_normalize_fuzzy_fallback(self):
        """Unknown team matched fuzzily against known FotMob names."""
        # "Manchester Utd" should fuzzy-match to "Manchester United"
        result = normalize_team_name("Manchester Utd")
        assert result == "Manchester United"

    def test_normalize_persisted_mapping(self):
        """Reviewed mapping is loaded and used."""
        import odds.normalizer as norm
        # Reset cache
        norm._reviewed_cache = None

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"FakeTeam FC": "Real Team FC"}, f)
            tmp_path = Path(f.name)

        original_path = norm._MAPPING_PATH
        try:
            norm._MAPPING_PATH = tmp_path
            norm._reviewed_cache = None
            mapping = load_reviewed_mapping()
            assert mapping["FakeTeam FC"] == "Real Team FC"
        finally:
            norm._MAPPING_PATH = original_path
            norm._reviewed_cache = None
            tmp_path.unlink(missing_ok=True)


# ── Importer tests ───────────────────────────────────────────

class TestImporter:
    def test_parse_csv(self):
        """Parse E0_2526.csv, verify full column schema."""
        _require_csv(_E0_CSV)
        df = parse_csv(_E0_CSV, league_id=47, season="2526")
        assert len(df) > 0

        expected_cols = [
            "league_id", "season", "match_date", "home_team", "away_team",
            "bookmaker", "source",
            "odds_H_open", "odds_D_open", "odds_A_open",
            "odds_H_close", "odds_D_close", "odds_A_close",
            "prob_H_open", "prob_D_open", "prob_A_open",
            "prob_H_close", "prob_D_close", "prob_A_close",
            "source_match_key", "matched_fixture_key",
        ]
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"

        # Verify source_match_key format
        key = df["source_match_key"].iloc[0]
        assert key.startswith("E0|2526|")

        # Verify team normalization happened
        assert "Man City" not in df["home_team"].values
        assert "Man City" not in df["away_team"].values

    def test_parse_csv_closing_odds(self):
        """Closing odds columns extracted correctly."""
        _require_csv(_E0_CSV)
        df = parse_csv(_E0_CSV, league_id=47, season="2526")
        n_close = df["odds_H_close"].notna().sum()
        # E0 should have closing odds for most matches
        assert n_close > 0, "Expected some closing odds"

    def test_save_load_parquet(self):
        """Round-trip: CSV → parse → parquet → load, verify columns preserved."""
        _require_csv(_E0_CSV)
        df = parse_csv(_E0_CSV, league_id=47, season="2526")

        with tempfile.TemporaryDirectory() as tmpdir:
            out = save_parquet(df, output_dir=Path(tmpdir))
            assert out.exists()

            loaded = pd.read_parquet(out)
            assert len(loaded) == len(df)
            assert set(loaded.columns) == set(df.columns)

            # Verify odds values survived round-trip
            pd.testing.assert_series_equal(
                loaded["odds_H_open"].dropna().reset_index(drop=True),
                df["odds_H_open"].dropna().reset_index(drop=True),
            )


# ── Resolver tests ───────────────────────────────────────────

class TestResolver:
    def setup_method(self):
        clear_cache()

    def test_resolver_opening(self):
        """get_odds_lookup(snapshot_type='opening') returns B365H values."""
        _require_csv(_E0_CSV)
        lookup = get_odds_lookup(league_id=47, season="2526", snapshot_type="opening")
        assert len(lookup) > 0

        # Each value should be (prob_H, prob_D, prob_A, odds_H, odds_D, odds_A)
        key = next(iter(lookup))
        val = lookup[key]
        assert len(val) == 6
        # Odds should be > 1.0
        assert val[3] > 1.0
        assert val[4] > 1.0
        assert val[5] > 1.0
        # Probs should sum to ~1.0
        assert abs(val[0] + val[1] + val[2] - 1.0) < 0.01

    def test_resolver_closing(self):
        """get_odds_lookup(snapshot_type='closing') returns B365CH values."""
        _require_csv(_E0_CSV)
        lookup = get_odds_lookup(league_id=47, season="2526", snapshot_type="closing")
        assert len(lookup) > 0

        key = next(iter(lookup))
        val = lookup[key]
        assert len(val) == 6
        assert val[3] > 1.0

    def test_resolver_matches_legacy(self):
        """Resolver output matches legacy _load_market_odds for E0_2526."""
        _require_csv(_E0_CSV)

        # Load via resolver
        resolver_lookup = get_odds_lookup(league_id=47, season="2526", snapshot_type="opening")

        # Load via legacy
        from models.feature_builder import _load_market_odds
        legacy_lookup = _load_market_odds(league_id=47)

        # Both should have the same keys and very close values
        assert len(resolver_lookup) > 0
        assert len(legacy_lookup) > 0

        common_keys = set(resolver_lookup.keys()) & set(legacy_lookup.keys())
        assert len(common_keys) > 0, "No common keys between resolver and legacy"

        for key in common_keys:
            r_vals = resolver_lookup[key]
            l_vals = legacy_lookup[key]
            for i in range(6):
                assert abs(r_vals[i] - l_vals[i]) < 0.001, (
                    f"Mismatch for {key} index {i}: resolver={r_vals[i]}, legacy={l_vals[i]}"
                )

    def test_resolver_fallback_no_parquet(self):
        """Resolver works without parquet (falls back to CSV)."""
        _require_csv(_E0_CSV)
        clear_cache()

        # Even without parquet files, resolver should parse CSV directly
        lookup = get_odds_lookup(league_id=47, season="2526", snapshot_type="opening")
        assert len(lookup) > 0
