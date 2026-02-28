"""
Round-based I/O utilities for the Clarity Engine pipeline.

Handles folder creation, JSON schemas, and status management for
the output/rounds/ structure.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ROUNDS_DIR = _PROJECT_ROOT / "output" / "rounds"

# Team name shortening (same as match_renderer.py)
_SHORT_NAMES = {
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Crystal Palace": "C Palace",
    "Leicester City": "Leicester",
    "Manchester City": "Man City",
    "Manchester United": "Man Utd",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nottm Forest",
    "Tottenham Hotspur": "Spurs",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    "Ipswich Town": "Ipswich",
    "Leeds United": "Leeds",
    "Luton Town": "Luton",
    "Aston Villa": "Aston Villa",
    "Burnley": "Burnley",
    "Brentford": "Brentford",
    "Fulham": "Fulham",
    "Arsenal": "Arsenal",
    "Chelsea": "Chelsea",
    "Liverpool": "Liverpool",
    "Everton": "Everton",
    "Sunderland": "Sunderland",
}


def _shorten(name: str) -> str:
    return _SHORT_NAMES.get(name, name)


def _sanitize(s: str) -> str:
    """Make a string filesystem-safe."""
    s = s.replace(" ", "_").replace("&", "and")
    s = re.sub(r"[^A-Za-z0-9_\-]", "", s)
    return s


def match_folder_name(home_team: str, away_team: str) -> str:
    """Create folder name from team names, e.g. 'Wolves_vs_Aston_Villa'."""
    return f"{_sanitize(_shorten(home_team))}_vs_{_sanitize(_shorten(away_team))}"


def round_dir(league: str, round_number: int) -> Path:
    """Get the round directory path, e.g. output/rounds/PL_R28/."""
    return _ROUNDS_DIR / f"{league}_R{round_number}"


def write_round_config(
    path: Path,
    league: str,
    league_id: int,
    round_number: int,
    season: str,
    model_version: str,
    match_count: int,
) -> None:
    """Write round_config.json."""
    config = {
        "league": league,
        "league_id": league_id,
        "round_number": round_number,
        "season": season,
        "model_version": model_version,
        "match_count": match_count,
        "created_at": datetime.now().isoformat(),
    }
    with open(path / "round_config.json", "w") as f:
        json.dump(config, f, indent=2)


def write_round_status(path: Path, status: str = "draft") -> None:
    """Write round_status.json."""
    data = {
        "status": status,
        "created_at": datetime.now().isoformat(),
        "approved_at": None,
        "published_at": None,
        "approved_by": None,
        "notes": None,
    }
    with open(path / "round_status.json", "w") as f:
        json.dump(data, f, indent=2)


def read_round_status(path: Path) -> Dict:
    """Read round_status.json."""
    with open(path / "round_status.json") as f:
        return json.load(f)


def update_round_status(path: Path, **kwargs) -> None:
    """Update fields in round_status.json."""
    status = read_round_status(path)
    status.update(kwargs)
    with open(path / "round_status.json", "w") as f:
        json.dump(status, f, indent=2)


def write_review(match_dir: Path, status: str = "pending", **kwargs) -> None:
    """Write or update review.json for a match."""
    review = {
        "status": status,
        "reviewer": kwargs.get("reviewer"),
        "reviewed_at": kwargs.get("reviewed_at"),
        "notes": kwargs.get("notes", ""),
        "override_editorial": kwargs.get("override_editorial"),
    }
    with open(match_dir / "review.json", "w") as f:
        json.dump(review, f, indent=2)


def read_review(match_dir: Path) -> Dict:
    """Read review.json for a match."""
    review_path = match_dir / "review.json"
    if review_path.exists():
        with open(review_path) as f:
            return json.load(f)
    return {"status": "pending"}
