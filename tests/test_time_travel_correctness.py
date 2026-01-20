import inspect

import pytest

from src.data import feature_engineering
from src.database.config import get_connection


def _get_connection_or_skip():
    conn = get_connection()
    if conn is None:
        pytest.skip("Database connection unavailable; cannot validate time-travel invariants.")
    return conn


def _fetch_count(conn, query: str, params: tuple = ()) -> int:
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _fetch_sample(conn, query: str, params: tuple = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def test_injuries_valid_at_precedes_fixture_date():
    conn = _get_connection_or_skip()
    try:
        count_query = """
            SELECT COUNT(*)
            FROM injuries_historical i
            JOIN fixtures_historical f ON f.fixture_id = i.fixture_id
            WHERE i.valid_at >= f.date
        """
        sample_query = """
            SELECT i.fixture_id, i.player_id, i.valid_at, f.date
            FROM injuries_historical i
            JOIN fixtures_historical f ON f.fixture_id = i.fixture_id
            WHERE i.valid_at >= f.date
            ORDER BY i.valid_at DESC
            LIMIT 5
        """
        violations = _fetch_count(conn, count_query)
        if violations:
            sample = _fetch_sample(conn, sample_query)
            assert (
                violations == 0
            ), f"TIME TRAVEL VIOLATION: {violations} injuries have valid_at >= fixture date. Sample: {sample}"
    finally:
        conn.close()


def test_odds_snapshots_captured_before_fixture_date():
    conn = _get_connection_or_skip()
    try:
        count_query = """
            SELECT COUNT(*)
            FROM odds_snapshots o
            JOIN fixtures_historical f ON f.fixture_id = o.fixture_id
            WHERE o.captured_at >= f.date
        """
        sample_query = """
            SELECT o.fixture_id, o.captured_at, f.date
            FROM odds_snapshots o
            JOIN fixtures_historical f ON f.fixture_id = o.fixture_id
            WHERE o.captured_at >= f.date
            ORDER BY o.captured_at DESC
            LIMIT 5
        """
        violations = _fetch_count(conn, count_query)
        if violations:
            sample = _fetch_sample(conn, sample_query)
            assert (
                violations == 0
            ), f"TIME TRAVEL VIOLATION: {violations} odds snapshots captured after kickoff. Sample: {sample}"
    finally:
        conn.close()


def test_form_feature_queries_use_only_prior_matches():
    recent_matches_source = inspect.getsource(feature_engineering._fetch_recent_team_matches)
    h2h_source = inspect.getsource(feature_engineering._fetch_h2h_matches)
    league_source = inspect.getsource(feature_engineering._fetch_league_positions)

    assert "date < %s" in recent_matches_source, (
        "Form feature query must filter matches strictly before fixture date."
    )
    assert "date < %s" in h2h_source, (
        "H2H query must filter matches strictly before fixture date."
    )
    assert "date < %s" in league_source, (
        "League position query must filter matches strictly before fixture date."
    )

    default_limit = feature_engineering._fetch_recent_team_matches.__defaults__[0]
    assert default_limit == 5, "Form features must use exactly 5 previous matches by default."

    derive_source = inspect.getsource(feature_engineering.derive_form_features)
    assert derive_source.count("limit=5") >= 2, (
        "derive_form_features should request the last 5 matches for both home and away teams."
    )


def test_feature_engineering_avoids_match_outcomes_table():
    module_source = inspect.getsource(feature_engineering)
    assert "match_outcomes" not in module_source, (
        "Feature engineering must not use match_outcomes (post-match data)."
    )
