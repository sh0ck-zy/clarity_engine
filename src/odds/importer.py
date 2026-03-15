"""Parse football-data.co.uk CSVs → standardized DataFrame → parquet."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from odds.normalizer import normalize_team_name

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

LEAGUE_CONFIG = {
    47: {"code": "E0", "format": "standard"},     # Premier League
    57: {"code": "N1", "format": "standard"},     # Eredivisie
    61: {"code": "P1", "format": "standard"},     # Liga Portugal
    53: {"code": "F1", "format": "standard"},     # Ligue 1
    54: {"code": "D1", "format": "standard"},     # Bundesliga
    55: {"code": "I1", "format": "standard"},     # Serie A
    87: {"code": "SP1", "format": "standard"},    # La Liga
    268: {"code": "BRA", "format": "extra"},      # Brasileirão
}

SEASONS = ["1819", "1920", "2021", "2122", "2223", "2324", "2425", "2526"]

_BASE_URL = "https://www.football-data.co.uk/mmz4281"


def download_csv(league_id: int, season: str, output_dir: Optional[Path] = None) -> Path:
    """Download from football-data.co.uk. Skips if file exists."""
    config = LEAGUE_CONFIG[league_id]
    code = config["code"]
    if output_dir is None:
        output_dir = _PROJECT_ROOT / "data" / "football_data" / "odds"
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{code}_{season}.csv"
    out_path = output_dir / filename

    if out_path.exists():
        logger.info("Already exists: %s", out_path)
        return out_path

    url = f"{_BASE_URL}/{season}/{code}.csv"
    logger.info("Downloading %s → %s", url, out_path)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    out_path.write_bytes(resp.content)
    return out_path


def parse_csv(csv_path: Path, league_id: int, season: str) -> pd.DataFrame:
    """Parse football-data CSV into canonical wide DataFrame.

    Output columns:
        league_id, season, match_date, home_team, away_team,
        bookmaker, source,
        odds_H_open, odds_D_open, odds_A_open,
        odds_H_close, odds_D_close, odds_A_close,
        prob_H_open, prob_D_open, prob_A_open,
        prob_H_close, prob_D_close, prob_A_close,
        source_match_key, matched_fixture_key
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    config = LEAGUE_CONFIG.get(league_id, {"format": "standard"})
    fmt = config.get("format", "standard")

    if fmt == "extra":
        return _parse_extra(df, league_id, season)
    return _parse_standard(df, league_id, season)


def _parse_standard(df: pd.DataFrame, league_id: int, season: str) -> pd.DataFrame:
    """Parse standard format (HomeTeam/AwayTeam, B365H/D/A)."""
    if "HomeTeam" not in df.columns:
        raise ValueError(f"Missing HomeTeam column. Columns: {list(df.columns)}")

    # Opening odds
    open_cols = {"B365H": "odds_H_open", "B365D": "odds_D_open", "B365A": "odds_A_open"}
    # Closing odds
    close_cols = {"B365CH": "odds_H_close", "B365CD": "odds_D_close", "B365CA": "odds_A_close"}

    rows = []
    for _, row in df.iterrows():
        home_csv = str(row["HomeTeam"])
        away_csv = str(row["AwayTeam"])
        home = normalize_team_name(home_csv)
        away = normalize_team_name(away_csv)

        # Parse date
        date_str = str(row.get("Date", ""))
        match_date = _parse_date(date_str)

        code = LEAGUE_CONFIG.get(league_id, {}).get("code", "??")
        source_key = f"{code}|{season}|{home_csv}|{away_csv}|{match_date}"

        rec = {
            "league_id": league_id,
            "season": season,
            "match_date": match_date,
            "home_team": home,
            "away_team": away,
            "bookmaker": "Bet365",
            "source": "football-data.co.uk",
            "source_match_key": source_key,
            "matched_fixture_key": None,
        }

        # Opening odds
        for csv_col, out_col in open_cols.items():
            val = row.get(csv_col)
            rec[out_col] = float(val) if pd.notna(val) else None

        # Closing odds
        for csv_col, out_col in close_cols.items():
            val = row.get(csv_col)
            rec[out_col] = float(val) if pd.notna(val) else None

        rows.append(rec)

    result = pd.DataFrame(rows)
    result = _add_probabilities(result)
    return result


def _parse_extra(df: pd.DataFrame, league_id: int, season: str) -> pd.DataFrame:
    """Parse extra format (Home/Away, PSCH/D/A or B365CH/CD/CA)."""
    if "Home" not in df.columns:
        raise ValueError(f"Missing Home column. Columns: {list(df.columns)}")

    # Detect available odds columns
    if all(c in df.columns for c in ["PSCH", "PSCD", "PSCA"]):
        h_col, d_col, a_col = "PSCH", "PSCD", "PSCA"
        bookmaker = "Pinnacle"
    elif all(c in df.columns for c in ["B365CH", "B365CD", "B365CA"]):
        h_col, d_col, a_col = "B365CH", "B365CD", "B365CA"
        bookmaker = "Bet365"
    else:
        raise ValueError("No recognizable odds columns in extra-format CSV")

    rows = []
    for _, row in df.iterrows():
        # Season filter handled at caller level if needed
        home_csv = str(row["Home"])
        away_csv = str(row["Away"])
        home = normalize_team_name(home_csv)
        away = normalize_team_name(away_csv)

        date_str = str(row.get("Date", ""))
        match_date = _parse_date(date_str)

        code = LEAGUE_CONFIG.get(league_id, {}).get("code", "??")
        source_key = f"{code}|{season}|{home_csv}|{away_csv}|{match_date}"

        rec = {
            "league_id": league_id,
            "season": season,
            "match_date": match_date,
            "home_team": home,
            "away_team": away,
            "bookmaker": bookmaker,
            "source": "football-data.co.uk",
            # Extra format only has closing-style odds
            "odds_H_open": None,
            "odds_D_open": None,
            "odds_A_open": None,
            "odds_H_close": float(row[h_col]) if pd.notna(row[h_col]) else None,
            "odds_D_close": float(row[d_col]) if pd.notna(row[d_col]) else None,
            "odds_A_close": float(row[a_col]) if pd.notna(row[a_col]) else None,
            "source_match_key": source_key,
            "matched_fixture_key": None,
        }
        rows.append(rec)

    result = pd.DataFrame(rows)
    result = _add_probabilities(result)
    return result


def _parse_date(date_str: str) -> str:
    """Parse date from football-data format (DD/MM/YYYY or DD/MM/YY)."""
    if not date_str or date_str == "nan":
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def _remove_vig(odds_h: float, odds_d: float, odds_a: float) -> tuple[float, float, float]:
    """Remove vig from 1X2 odds, return fair probabilities."""
    impl_h = 1.0 / odds_h
    impl_d = 1.0 / odds_d
    impl_a = 1.0 / odds_a
    total = impl_h + impl_d + impl_a
    return impl_h / total, impl_d / total, impl_a / total


def _add_probabilities(df: pd.DataFrame) -> pd.DataFrame:
    """Add vig-removed probability columns for opening and closing odds."""
    for suffix in ("open", "close"):
        h_col = f"odds_H_{suffix}"
        d_col = f"odds_D_{suffix}"
        a_col = f"odds_A_{suffix}"
        p_h = f"prob_H_{suffix}"
        p_d = f"prob_D_{suffix}"
        p_a = f"prob_A_{suffix}"

        probs_h, probs_d, probs_a = [], [], []
        for _, row in df.iterrows():
            if pd.notna(row.get(h_col)) and pd.notna(row.get(d_col)) and pd.notna(row.get(a_col)):
                ph, pd_, pa = _remove_vig(row[h_col], row[d_col], row[a_col])
                probs_h.append(ph)
                probs_d.append(pd_)
                probs_a.append(pa)
            else:
                probs_h.append(None)
                probs_d.append(None)
                probs_a.append(None)

        df[p_h] = probs_h
        df[p_d] = probs_d
        df[p_a] = probs_a

    return df


def save_parquet(df: pd.DataFrame, output_dir: Optional[Path] = None) -> Path:
    """Write parsed odds to parquet. One file per league_id+season."""
    if output_dir is None:
        output_dir = _PROJECT_ROOT / "data" / "odds_clean"
    output_dir.mkdir(parents=True, exist_ok=True)

    league_id = df["league_id"].iloc[0]
    season = df["season"].iloc[0]
    out_path = output_dir / f"{league_id}_{season}.parquet"
    df.to_parquet(out_path, index=False)
    logger.info("Saved %d rows → %s", len(df), out_path)
    return out_path
