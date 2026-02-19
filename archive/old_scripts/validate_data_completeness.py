#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from database.config import get_connection
from validation.data_completeness import build_report

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate historical data completeness.")
    parser.add_argument("--season", type=int, required=True, help="Season year (e.g. 2023).")
    parser.add_argument("--league-id", type=int, default=1, help="League ID (default: 1).")
    parser.add_argument("--detailed", action="store_true", help="Include missing samples.")
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "data_completeness_report.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    conn = get_connection()
    if conn is None:
        print("❌ Could not connect to the database.")
        return 1

    try:
        report = build_report(
            conn,
            season=args.season,
            league_id=args.league_id,
            detailed=args.detailed,
        )
    finally:
        conn.close()

    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("✅ Data completeness report generated.")
    print(f"   - {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
