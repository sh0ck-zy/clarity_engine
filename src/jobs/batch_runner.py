from typing import Iterable

import pandas as pd

from src.analysis.predictor import ClarityEngine
from src.database.config import get_connection


class BatchRunner:
    """Runs model inference across a set of fixtures for a given round."""

    def __init__(self) -> None:
        self.conn = get_connection()

    def _fetch_fixture_ids(self, season: str, round_id: str | int) -> Iterable[str]:
        if not self.conn:
            return []
        query = "SELECT id FROM fixtures WHERE season = %s"
        params = [season]
        if round_id != "all":
            query += " AND round = %s"
            params.append(round_id)
        df = pd.read_sql(query, self.conn, params=tuple(params))
        return df["id"].tolist()

    def run_round(self, season: str, round_id: str | int, prompt: str, force: bool = False) -> None:
        fixtures = self._fetch_fixture_ids(season, round_id)
        if not fixtures:
            print(f"⚠️  No fixtures found for season={season}, round={round_id}.")
            return

        engine = ClarityEngine()
        try:
            for fx_id in fixtures:
                print(f"🧠 Running batch analysis for {fx_id} with prompt '{prompt}'")
                try:
                    engine.run_analysis(fx_id, prompt, force_refresh=force)
                except Exception as exc:  # pragma: no cover - defensive logging
                    print(f"❌ Error analyzing {fx_id}: {exc}")
        finally:
            engine.close()
            if self.conn:
                self.conn.close()
