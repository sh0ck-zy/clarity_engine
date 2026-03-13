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

# Feature columns used by the model (9 deltas + 2 absolutes + 3 convergence + 6 market)
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
    # Convergence features (draw signals)
    "strength_convergence",
    "form_convergence",
    "clean_sheets_delta",
    # Market odds features
    "market_prob_H",
    "market_prob_D",
    "market_prob_A",
    "market_draw_signal",
    "market_home_edge",
    "market_entropy",
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
    h.draws             AS home_draws,
    h.played            AS home_played,
    h.clean_sheets_last5 AS home_clean_sheets_last5,
    h.goals_conceded_last5 AS home_goals_conceded_last5,
    a.position          AS away_position,
    a.goal_difference   AS away_goal_diff,
    a.form_points       AS away_form_points,
    a.xg_for_last5      AS away_xg_for_last5,
    a.xg_against_last5  AS away_xg_against_last5,
    a.xg_diff_last5     AS away_xg_diff_last5,
    a.away_points       AS away_venue_points,
    a.draws             AS away_draws,
    a.played            AS away_played,
    a.clean_sheets_last5 AS away_clean_sheets_last5,
    a.goals_conceded_last5 AS away_goals_conceded_last5
FROM fotmob_matches m
JOIN team_states h
    ON h.team_id = m.home_team_id
    AND h.round_number = m.round_number - 1
JOIN team_states a
    ON a.team_id = m.away_team_id
    AND a.round_number = m.round_number - 1
WHERE m.round_number > 1
ORDER BY m.round_number, m.match_date
"""

_REST_DAYS_SQL = """
WITH team_dates AS (
    SELECT home_team_id AS team_id, match_date, round_number
    FROM fotmob_matches
    UNION ALL
    SELECT away_team_id AS team_id, match_date, round_number
    FROM fotmob_matches
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


def _load_matches_with_states(conn, league_id: Optional[int] = None) -> pd.DataFrame:
    """Load matches joined with pre-match team_states (round N-1)."""
    sql = _MATCHES_WITH_STATES_SQL
    if league_id is not None:
        sql = sql.replace(
            "WHERE m.round_number > 1",
            f"WHERE m.round_number > 1\n    AND m.league_id = {league_id}\n    AND h.league_id = {league_id}\n    AND a.league_id = {league_id}",
        )
    return pd.read_sql(sql, conn)


def _compute_rest_days(conn, league_id: Optional[int] = None) -> pd.DataFrame:
    """Compute league rest days per team per round."""
    sql = _REST_DAYS_SQL
    if league_id is not None:
        sql = sql.replace(
            "FROM fotmob_matches\n",
            f"FROM fotmob_matches WHERE league_id = {league_id}\n",
        )
    return pd.read_sql(sql, conn)


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


def _merge_elo(df: pd.DataFrame, countries: Optional[List[str]] = None) -> pd.DataFrame:
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

        h_elo = get_team_elo(row["home_team_name"], match_date, countries=countries)
        a_elo = get_team_elo(row["away_team_name"], match_date, countries=countries)

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


# Football-data.co.uk -> FotMob team name mapping
_CSV_TO_FOTMOB = {
    "Arsenal": "Arsenal",
    "Aston Villa": "Aston Villa",
    "Bournemouth": "AFC Bournemouth",
    "Brentford": "Brentford",
    "Brighton": "Brighton & Hove Albion",
    "Burnley": "Burnley",
    "Chelsea": "Chelsea",
    "Crystal Palace": "Crystal Palace",
    "Everton": "Everton",
    "Fulham": "Fulham",
    "Leeds": "Leeds United",
    "Leicester": "Leicester City",
    "Liverpool": "Liverpool",
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Newcastle": "Newcastle United",
    "Nott'm Forest": "Nottingham Forest",
    "Southampton": "Southampton",
    "Sunderland": "Sunderland",
    "Spurs": "Tottenham Hotspur",
    "Tottenham": "Tottenham Hotspur",
    "West Ham": "West Ham United",
    "Wolves": "Wolverhampton Wanderers",
    "Ipswich": "Ipswich Town",
    "Luton": "Luton Town",
    # Portuguese teams (football-data.co.uk name -> FotMob name)
    # These will be populated once we see the actual FotMob names after backfill
    "Sp Lisbon": "Sporting CP",
    "Sporting": "Sporting CP",
    "Benfica": "SL Benfica",
    "Porto": "FC Porto",
    "Braga": "SC Braga",
    "Guimaraes": "Vitória SC",
    "Famalicao": "FC Famalicão",
    "Gil Vicente": "Gil Vicente FC",
    "Moreirense": "Moreirense FC",
    "Rio Ave": "Rio Ave FC",
    "Santa Clara": "Santa Clara",
    "Casa Pia": "Casa Pia AC",
    "Estrela Amadora": "CF Estrela da Amadora",
    "Estoril": "GD Estoril Praia",
    "Arouca": "FC Arouca",
    "Boavista": "Boavista FC",
    "Nacional": "CD Nacional",
    "AVS": "AVS",
}

# League ID -> odds CSV config
_LEAGUE_ODDS_CONFIG = {
    47: {  # Premier League
        "csv": "E0_2526.csv",
        "format": "standard",  # HomeTeam, AwayTeam, B365H/D/A columns
    },
    57: {  # Eredivisie
        "csv": "N1_2526.csv",
        "format": "standard",
    },
    61: {  # Liga Portugal
        "csv": "P1_2526.csv",
        "format": "standard",
    },
    268: {  # Brasileirão
        "csv": "BRA_2025.csv",
        "format": "extra",  # Home, Away, PSCH/D/A columns, multi-season file
        "season_filter": "2025",
    },
}

# League ID -> ELO country codes
_LEAGUE_COUNTRIES = {
    47: ["ENG"],
    57: ["NED"],
    61: ["POR"],
    268: [],  # ClubELO doesn't cover Brazil
}


def _load_market_odds(league_id: int = 47, csv_path: Optional[Path] = None) -> Dict[tuple, tuple]:
    """Load market odds from football-data.co.uk CSV. Returns lookup dict.

    Handles two CSV formats:
    - 'standard' (E0, P1): HomeTeam, AwayTeam, B365H/D/A
    - 'extra' (BRA): Home, Away, PSCH/D/A (Pinnacle closing only)
    """
    config = _LEAGUE_ODDS_CONFIG.get(league_id, {})

    if csv_path is None:
        csv_name = config.get("csv")
        if not csv_name:
            return {}
        csv_path = _PROJECT_ROOT / "data" / "football_data" / "odds" / csv_name

    if not csv_path.exists():
        return {}

    odds_df = pd.read_csv(csv_path)
    fmt = config.get("format", "standard")

    if fmt == "extra":
        # Brazilian/extra format: Country, League, Season, Date, Time, Home, Away, HG, AG, Res, PSCH, PSCD, PSCA, ...
        season_filter = config.get("season_filter")
        if season_filter:
            odds_df = odds_df[odds_df["Season"].astype(str) == season_filter]

        required = ["Home", "Away", "PSCH", "PSCD", "PSCA"]
        if not all(c in odds_df.columns for c in required):
            # Try closing B365 columns as fallback
            required = ["Home", "Away", "B365CH", "B365CD", "B365CA"]
            if not all(c in odds_df.columns for c in required):
                return {}
            h_col, d_col, a_col = "B365CH", "B365CD", "B365CA"
        else:
            h_col, d_col, a_col = "PSCH", "PSCD", "PSCA"

        home_col, away_col = "Home", "Away"
    else:
        # Standard format: HomeTeam, AwayTeam, B365H, B365D, B365A
        required = ["HomeTeam", "AwayTeam", "B365H", "B365D", "B365A"]
        if not all(c in odds_df.columns for c in required):
            return {}
        h_col, d_col, a_col = "B365H", "B365D", "B365A"
        home_col, away_col = "HomeTeam", "AwayTeam"

    # Drop rows with missing odds
    odds_df = odds_df.dropna(subset=[h_col, d_col, a_col])

    # Build implied probabilities (normalized after vig removal)
    odds_df["impl_H"] = 1.0 / odds_df[h_col].astype(float)
    odds_df["impl_D"] = 1.0 / odds_df[d_col].astype(float)
    odds_df["impl_A"] = 1.0 / odds_df[a_col].astype(float)
    total_impl = odds_df["impl_H"] + odds_df["impl_D"] + odds_df["impl_A"]
    odds_df["prob_H"] = odds_df["impl_H"] / total_impl
    odds_df["prob_D"] = odds_df["impl_D"] / total_impl
    odds_df["prob_A"] = odds_df["impl_A"] / total_impl

    lookup: Dict[tuple, tuple] = {}
    for _, row in odds_df.iterrows():
        csv_home = str(row[home_col])
        csv_away = str(row[away_col])
        fotmob_home = _CSV_TO_FOTMOB.get(csv_home, csv_home)
        fotmob_away = _CSV_TO_FOTMOB.get(csv_away, csv_away)
        lookup[(fotmob_home, fotmob_away)] = (
            float(row["prob_H"]),
            float(row["prob_D"]),
            float(row["prob_A"]),
        )

    return lookup


def _merge_market_odds(df: pd.DataFrame, odds_lookup: Dict[tuple, tuple]) -> pd.DataFrame:
    """Merge market implied probabilities into feature dataset."""
    market_h = []
    market_d = []
    market_a = []

    for _, row in df.iterrows():
        key = (row["home_team_name"], row["away_team_name"])
        if key in odds_lookup:
            prob_h, prob_d, prob_a = odds_lookup[key]
            market_h.append(prob_h)
            market_d.append(prob_d)
            market_a.append(prob_a)
        else:
            market_h.append(np.nan)
            market_d.append(np.nan)
            market_a.append(np.nan)

    df["market_prob_H"] = market_h
    df["market_prob_D"] = market_d
    df["market_prob_A"] = market_a

    matched = df["market_prob_H"].notna().sum()
    total = len(df)
    print(f"Market odds: {matched}/{total} matches matched ({matched/total:.1%})")

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

    # Convergence features: measure how CLOSE teams are (draw signals)
    df["strength_convergence"] = 1.0 / (1.0 + df["elo_delta"].abs())
    df["form_convergence"] = 1.0 / (1.0 + df["form_points_delta"].abs())
    df["clean_sheets_delta"] = (
        df["home_clean_sheets_last5"].fillna(0) - df["away_clean_sheets_last5"].fillna(0)
    )

    # Market-derived features (NaN if odds unavailable)
    if "market_prob_H" in df.columns:
        df["market_draw_signal"] = df["market_prob_D"]
        df["market_home_edge"] = df["market_prob_H"] - df["market_prob_A"]
        # Market entropy: how uncertain the market is (high = draw-likely)
        # -sum(p * log(p)) / log(3), normalized to [0,1]
        import math
        def _market_entropy(row):
            probs = [row["market_prob_H"], row["market_prob_D"], row["market_prob_A"]]
            if any(pd.isna(p) for p in probs):
                return np.nan
            entropy = -sum(p * math.log(p) if p > 0 else 0.0 for p in probs)
            return entropy / math.log(3)
        df["market_entropy"] = df.apply(_market_entropy, axis=1)

    return df


def _derive_result(row: pd.Series) -> str:
    """Derive match result from scores. Returns NaN for scheduled matches."""
    if pd.isna(row["home_score"]) or pd.isna(row["away_score"]):
        return np.nan
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
    conn=None, allow_missing_elo: bool = False, league_id: Optional[int] = None,
) -> pd.DataFrame:
    """
    Build the full feature dataset for probabilistic model training.

    Args:
        conn: Database connection (auto-created if None)
        allow_missing_elo: Allow > 5% ELO missing rate
        league_id: FotMob league ID to filter by (None = all leagues, 47 = PL, 61 = Portugal, 268 = Brazil)

    Returns DataFrame with columns:
        - Identifiers: fotmob_match_id, round_number, match_date,
          home_team_name, away_team_name
        - Features: FEATURE_COLS
        - Metadata: METADATA_COLS
        - Target: result (H/D/A)
    """
    managed_conn = False
    if conn is None:
        conn = get_connection()
        managed_conn = True

    try:
        league_label = f"league_id={league_id}" if league_id is not None else "all leagues"
        print(f"Loading matches with pre-match team_states ({league_label})...")
        df = _load_matches_with_states(conn, league_id=league_id)
        min_r = df["round_number"].min() if len(df) > 0 else "?"
        max_r = df["round_number"].max() if len(df) > 0 else "?"
        print(f"  {len(df)} matches loaded (R{min_r}-R{max_r})")

        print("Computing league rest days...")
        rest_df = _compute_rest_days(conn, league_id=league_id)
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

    # Determine ELO countries for this league (or all if multi-league)
    if league_id is not None:
        elo_countries = _LEAGUE_COUNTRIES.get(league_id, ["ENG"])
    else:
        # Combine all country codes for multi-league
        all_countries = set()
        for countries in _LEAGUE_COUNTRIES.values():
            all_countries.update(countries)
        elo_countries = sorted(all_countries) if all_countries else ["ENG"]

    print("Fetching ELO ratings...")
    if elo_countries:
        bulk_fetch(match_dates, countries=elo_countries)
    else:
        print("  No ELO coverage for this league (will be marked as missing)")
    df = _merge_elo(df, countries=elo_countries if elo_countries else None)

    # Load and merge market odds
    print("Loading market odds...")
    if league_id is not None:
        odds_lookup = _load_market_odds(league_id=league_id)
    else:
        # Load odds for all configured leagues
        odds_lookup: Dict[str, Dict[str, float]] = {}
        for lid in _LEAGUE_ODDS_CONFIG:
            league_odds = _load_market_odds(league_id=lid)
            if league_odds:
                odds_lookup.update(league_odds)
    if odds_lookup:
        df = _merge_market_odds(df, odds_lookup)
    else:
        print("  No market odds data found, filling NaN")
        for col in ["market_prob_H", "market_prob_D", "market_prob_A"]:
            df[col] = np.nan

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

    # For leagues without ELO coverage (e.g., Brazil), skip the check
    if missing_rate > 0.05 and not allow_missing_elo and elo_countries:
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
