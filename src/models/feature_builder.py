"""
Feature builder for probabilistic model.

Extracts feature vectors from team_states + fotmob_matches.
All features are pre-match (temporal correctness enforced via round_number - 1).
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_PATH = _PROJECT_ROOT / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from database.config import get_connection
from models.elo_cache import bulk_fetch, get_team_elo, report_coverage

# Feature columns used by the model (9 deltas + 2 absolutes)
FEATURE_COLS = [
    "xg_diff_last5_delta",
    "xg_for_last5_delta",
    "xg_against_last5_delta",
    "form_points_delta",
    "goal_diff_season_delta",
    "position_delta",
    "home_strength_delta",
    "league_rest_days_delta",
    "elo_delta",
    "home_venue_points",
    "away_venue_points",
]

# Metadata columns (not used as features)
METADATA_COLS = [
    "elo_missing_home",
    "elo_missing_away",
    "elo_missing_any",
]

_MATCHES_WITH_STATES_SQL = """
SELECT
    m.fotmob_match_id,
    m.round_number,
    m.match_date,
    m.home_team_id,
    m.away_team_id,
    m.home_team_name,
    m.away_team_name,
    m.home_score,
    m.away_score,
    h.position          AS home_position,
    h.goal_difference   AS home_goal_diff,
    h.form_points       AS home_form_points,
    h.xg_for_last5      AS home_xg_for_last5,
    h.xg_against_last5  AS home_xg_against_last5,
    h.xg_diff_last5     AS home_xg_diff_last5,
    h.home_points       AS home_venue_points,
    a.position          AS away_position,
    a.goal_difference   AS away_goal_diff,
    a.form_points       AS away_form_points,
    a.xg_for_last5      AS away_xg_for_last5,
    a.xg_against_last5  AS away_xg_against_last5,
    a.xg_diff_last5     AS away_xg_diff_last5,
    a.away_points       AS away_venue_points
FROM fotmob_matches m
JOIN team_states h
    ON h.team_id = m.home_team_id
    AND h.round_number = m.round_number - 1
JOIN team_states a
    ON a.team_id = m.away_team_id
    AND a.round_number = m.round_number - 1
WHERE m.home_score IS NOT NULL
    AND m.round_number > 1
ORDER BY m.round_number, m.match_date
"""

_REST_DAYS_SQL = """
WITH team_dates AS (
    SELECT home_team_id AS team_id, match_date, round_number
    FROM fotmob_matches WHERE home_score IS NOT NULL
    UNION ALL
    SELECT away_team_id AS team_id, match_date, round_number
    FROM fotmob_matches WHERE home_score IS NOT NULL
),
with_prev AS (
    SELECT
        curr.team_id,
        curr.round_number,
        curr.match_date AS curr_date,
        (
            SELECT match_date
            FROM team_dates prev
            WHERE prev.team_id = curr.team_id
                AND prev.match_date < curr.match_date
            ORDER BY prev.match_date DESC
            LIMIT 1
        ) AS prev_date
    FROM team_dates curr
)
SELECT
    team_id,
    round_number,
    CASE
        WHEN prev_date IS NOT NULL
        THEN EXTRACT(DAY FROM (curr_date::timestamp - prev_date::timestamp))::int
        ELSE NULL
    END AS rest_days
FROM with_prev
"""


def _load_matches_with_states(conn) -> pd.DataFrame:
    """Load matches joined with pre-match team_states (round N-1)."""
    return pd.read_sql(_MATCHES_WITH_STATES_SQL, conn)


def _compute_rest_days(conn) -> pd.DataFrame:
    """Compute league rest days per team per round."""
    return pd.read_sql(_REST_DAYS_SQL, conn)


def _merge_rest_days(df: pd.DataFrame, rest_df: pd.DataFrame) -> pd.DataFrame:
    """Merge rest days for home and away teams."""
    home_rest = rest_df.rename(
        columns={"team_id": "home_team_id", "rest_days": "home_rest_days"}
    )
    away_rest = rest_df.rename(
        columns={"team_id": "away_team_id", "rest_days": "away_rest_days"}
    )

    df = df.merge(
        home_rest[["home_team_id", "round_number", "home_rest_days"]],
        on=["home_team_id", "round_number"],
        how="left",
    )
    df = df.merge(
        away_rest[["away_team_id", "round_number", "away_rest_days"]],
        on=["away_team_id", "round_number"],
        how="left",
    )
    return df


def _merge_elo(df: pd.DataFrame) -> pd.DataFrame:
    """Add ELO ratings and missing flags."""
    home_elos = []
    away_elos = []
    missing_home = []
    missing_away = []

    for _, row in df.iterrows():
        match_date = row["match_date"]
        if isinstance(match_date, pd.Timestamp):
            match_date = match_date.date()
        elif isinstance(match_date, datetime):
            match_date = match_date.date()

        h_elo = get_team_elo(row["home_team_name"], match_date)
        a_elo = get_team_elo(row["away_team_name"], match_date)

        home_elos.append(h_elo)
        away_elos.append(a_elo)
        missing_home.append(1 if h_elo is None else 0)
        missing_away.append(1 if a_elo is None else 0)

    df["home_elo"] = home_elos
    df["away_elo"] = away_elos
    df["elo_missing_home"] = missing_home
    df["elo_missing_away"] = missing_away
    df["elo_missing_any"] = [
        1 if h or a else 0 for h, a in zip(missing_home, missing_away)
    ]

    return df


def _compute_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all delta features."""
    df["xg_diff_last5_delta"] = df["home_xg_diff_last5"] - df["away_xg_diff_last5"]
    df["xg_for_last5_delta"] = df["home_xg_for_last5"] - df["away_xg_for_last5"]
    df["xg_against_last5_delta"] = (
        df["home_xg_against_last5"] - df["away_xg_against_last5"]
    )
    df["form_points_delta"] = df["home_form_points"] - df["away_form_points"]
    df["goal_diff_season_delta"] = df["home_goal_diff"] - df["away_goal_diff"]
    # Inverted: positive = home team is better ranked (lower position number)
    df["position_delta"] = df["away_position"] - df["home_position"]
    df["home_strength_delta"] = df["home_venue_points"] - df["away_venue_points"]

    # League rest days delta (NULL -> 0.0 for delta)
    df["league_rest_days_delta"] = (
        df["home_rest_days"].fillna(0) - df["away_rest_days"].fillna(0)
    )

    # ELO delta (None -> 0.0 for delta, tracked by flags)
    df["elo_delta"] = df["home_elo"].fillna(0) - df["away_elo"].fillna(0)

    return df


def _derive_result(row: pd.Series) -> str:
    """Derive match result from scores."""
    if row["home_score"] > row["away_score"]:
        return "H"
    if row["away_score"] > row["home_score"]:
        return "A"
    return "D"


def _check_postponements(df: pd.DataFrame) -> None:
    """Warn about matches where round ordering != date ordering."""
    issues = []
    for round_num in df["round_number"].unique():
        round_matches = df[df["round_number"] == round_num]
        max_date_this = round_matches["match_date"].max()

        later_rounds = df[df["round_number"] > round_num]
        if later_rounds.empty:
            continue
        min_date_later = later_rounds["match_date"].min()

        if max_date_this > min_date_later:
            offending = round_matches[round_matches["match_date"] > min_date_later]
            for _, row in offending.iterrows():
                issues.append(
                    f"  R{row['round_number']} {row['home_team_name']} vs "
                    f"{row['away_team_name']} ({row['match_date']}) played after "
                    f"R{round_num + 1}+ started ({min_date_later})"
                )

    if issues:
        print(f"\nWARNING: {len(issues)} postponed fixture(s) detected:")
        for issue in issues:
            print(issue)
        print(
            "Round-based walk-forward may have minor temporal leakage for these.\n"
        )


def build_feature_dataset(
    conn=None, allow_missing_elo: bool = False
) -> pd.DataFrame:
    """
    Build the full feature dataset for probabilistic model training.

    Returns DataFrame with columns:
        - Identifiers: fotmob_match_id, round_number, match_date,
          home_team_name, away_team_name
        - Features: FEATURE_COLS (11 columns)
        - Metadata: METADATA_COLS (3 columns)
        - Target: result (H/D/A)
    """
    managed_conn = False
    if conn is None:
        conn = get_connection()
        managed_conn = True

    try:
        print("Loading matches with pre-match team_states...")
        df = _load_matches_with_states(conn)
        print(f"  {len(df)} matches loaded (R2-R26)")

        print("Computing league rest days...")
        rest_df = _compute_rest_days(conn)
        df = _merge_rest_days(df, rest_df)
    finally:
        if managed_conn and conn:
            conn.close()

    # Pre-fetch ELO for all match dates
    match_dates = []
    for d in df["match_date"]:
        if isinstance(d, pd.Timestamp):
            match_dates.append(d.date())
        elif isinstance(d, datetime):
            match_dates.append(d.date())
        else:
            match_dates.append(d)

    print("Fetching ELO ratings...")
    bulk_fetch(match_dates)
    df = _merge_elo(df)

    # Check ELO coverage
    all_teams = list(df["home_team_name"]) + list(df["away_team_name"])
    all_dates = match_dates + match_dates
    coverage = report_coverage(all_teams, all_dates)
    missing_rate = coverage["missing_rate"]
    print(
        f"ELO coverage: {coverage['found']}/{coverage['total']} "
        f"({1 - missing_rate:.1%} found)"
    )
    if coverage["missing_teams"]:
        print(f"  Missing teams: {coverage['missing_teams']}")

    if missing_rate > 0.05 and not allow_missing_elo:
        raise RuntimeError(
            f"ELO missing rate {missing_rate:.1%} > 5%. "
            "Use --allow-missing-elo to proceed."
        )

    # Compute deltas
    df = _compute_deltas(df)

    # Derive target
    df["result"] = df.apply(_derive_result, axis=1)

    # Check postponements
    _check_postponements(df)

    # Select output columns
    id_cols = [
        "fotmob_match_id",
        "round_number",
        "match_date",
        "home_team_name",
        "away_team_name",
    ]
    output_cols = id_cols + FEATURE_COLS + METADATA_COLS + ["result"]
    df = df[output_cols].copy()

    # Print distribution
    dist = df["result"].value_counts()
    print(f"\nResult distribution: H={dist.get('H', 0)} D={dist.get('D', 0)} A={dist.get('A', 0)}")
    print(f"Total rows: {len(df)}")

    return df


def compute_dataset_hash(df: pd.DataFrame) -> str:
    """Compute SHA256 hash of the feature dataset for reproducibility."""
    cols = sorted(FEATURE_COLS + ["result", "fotmob_match_id", "round_number"])
    subset = df[cols].sort_values(["fotmob_match_id"]).reset_index(drop=True)
    content = subset.to_csv(index=False)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def save_dataset_artifact(
    df: pd.DataFrame, output_dir: Optional[Path] = None
) -> None:
    """Save feature dataset as Parquet + metadata JSON."""
    if output_dir is None:
        output_dir = _PROJECT_ROOT / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    parquet_path = output_dir / "probabilistic_dataset_v1.parquet"
    metadata_path = output_dir / "probabilistic_dataset_v1_metadata.json"

    df.to_parquet(parquet_path, index=False)

    n_rows_by_round = (
        df.groupby("round_number").size().to_dict()
    )
    missing_counts = {}
    for col in FEATURE_COLS:
        n_missing = int(df[col].isna().sum())
        if n_missing > 0:
            missing_counts[col] = n_missing

    metadata = {
        "feature_version": "v1",
        "dataset_hash": compute_dataset_hash(df),
        "n_rows": len(df),
        "n_rows_by_round": {str(k): v for k, v in sorted(n_rows_by_round.items())},
        "missing_counts_by_feature": missing_counts,
        "feature_columns": FEATURE_COLS,
        "created_at": datetime.now().isoformat(),
    }

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nDataset saved: {parquet_path} ({len(df)} rows)")
    print(f"Metadata saved: {metadata_path}")
