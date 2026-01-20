#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import importlib.util

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection  # type: ignore[import-not-found]

load_dotenv()

SPLIT_RANGES = {
    "train": ("1900-01-01", "2024-05-01"),
    "val": ("2024-05-01", "2024-08-01"),
    "test": ("2024-08-01", "2100-01-01"),
}


def _load_fixture_base(conn) -> pd.DataFrame:
    query = """
        SELECT f.fixture_id,
               f.date,
               f.season,
               f.league_id,
               f.home_team_id,
               f.away_team_id,
               COALESCE(m.home_score, f.home_score) AS home_score,
               COALESCE(m.away_score, f.away_score) AS away_score,
               m.home_xg,
               m.away_xg,
               m.result
        FROM fixtures_historical f
        LEFT JOIN match_outcomes m
          ON m.fixture_id = f.fixture_id
        WHERE COALESCE(m.home_score, f.home_score) IS NOT NULL
          AND COALESCE(m.away_score, f.away_score) IS NOT NULL
    """
    return pd.read_sql(query, conn)


def _load_features(conn) -> pd.DataFrame:
    query = """
        SELECT fixture_id, feature_key, feature_value
        FROM match_features
    """
    features = pd.read_sql(query, conn)
    if features.empty:
        raise RuntimeError("No match_features found; cannot export dataset.")
    return features


def _pivot_features(features: pd.DataFrame) -> pd.DataFrame:
    wide = features.pivot_table(
        index="fixture_id",
        columns="feature_key",
        values="feature_value",
        aggfunc="first",
    )
    wide.reset_index(inplace=True)
    return wide


def _ensure_result_column(df: pd.DataFrame) -> pd.DataFrame:
    def _derive_result(row: pd.Series) -> str:
        existing = row.get("result")
        if isinstance(existing, str) and existing.strip():
            return existing
        home_score = row.get("home_score")
        away_score = row.get("away_score")
        if home_score is None or away_score is None:
            return ""
        if bool(pd.isna(home_score)) or bool(pd.isna(away_score)):
            return ""
        home_score_value = float(home_score)
        away_score_value = float(away_score)
        home_score = int(home_score_value)
        away_score = int(away_score_value)
        if home_score > away_score:
            return "HOME"
        if away_score > home_score:
            return "AWAY"
        return "DRAW"

    df["result"] = df.apply(_derive_result, axis=1)
    return df


def _filter_missing_features(df: pd.DataFrame, feature_columns: list[str]) -> pd.DataFrame:
    if not feature_columns:
        raise RuntimeError("No feature columns available after pivot.")
    missing_ratio = df[feature_columns].isna().mean(axis=1)
    return df.loc[missing_ratio <= 0.2].copy()


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    if importlib.util.find_spec("pyarrow") is not None:
        df.to_parquet(path, index=False)
        return
    if importlib.util.find_spec("fastparquet") is not None:
        df.to_parquet(path, index=False, engine="fastparquet")
        return
    raise RuntimeError(
        "Parquet export requires pyarrow or fastparquet. "
        "Install one of them and re-run."
    )


def _export_split(df: pd.DataFrame, split: str, output_dir: Path) -> None:
    start, end = SPLIT_RANGES[split]
    start_date = pd.Timestamp(start)
    end_date = pd.Timestamp(end)
    mask = (df["date"] >= start_date) & (df["date"] < end_date)
    split_df = df.loc[mask].copy()
    split_df["date"] = split_df["date"].dt.strftime("%Y-%m-%d")
    base_name = f"clarity_engine_{split}"
    csv_path = output_dir / f"{base_name}.csv"
    parquet_path = output_dir / f"{base_name}.parquet"
    split_df.to_csv(csv_path, index=False)
    _write_parquet(split_df, parquet_path)
    print(f"✅ {split}: {len(split_df)} rows -> {csv_path}, {parquet_path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export ML-ready dataset with temporal splits.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT,
        help="Output directory for CSV/Parquet exports (default: project root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return 1

    try:
        base = _load_fixture_base(conn)
        features = _load_features(conn)
    finally:
        conn.close()

    wide_features = _pivot_features(features)
    dataset = base.merge(wide_features, on="fixture_id", how="left")
    dataset["date"] = pd.to_datetime(dataset["date"])
    dataset = _ensure_result_column(dataset)

    feature_columns = [
        column
        for column in dataset.columns
        if column
        not in {
            "fixture_id",
            "date",
            "season",
            "league_id",
            "home_team_id",
            "away_team_id",
            "home_score",
            "away_score",
            "home_xg",
            "away_xg",
            "result",
        }
    ]
    pre_filter_count = len(dataset)
    dataset = _filter_missing_features(dataset, feature_columns)
    print(
        "Filtered fixtures for missing features: "
        f"{pre_filter_count} -> {len(dataset)}"
    )

    for split in ("train", "val", "test"):
        _export_split(dataset, split, output_dir)

    print("✅ ML dataset export complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
