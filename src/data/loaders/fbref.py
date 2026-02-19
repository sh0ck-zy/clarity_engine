#!/usr/bin/env python3
"""
FBref Data Loader
Downloads and processes squad statistics from fbref.com
Calculates PPDA (Passes Allowed Per Defensive Action) and Field Tilt
"""

import requests
import pandas as pd
from io import StringIO
import logging
from typing import Dict, Optional
from datetime import datetime
import os
import json

logger = logging.getLogger(__name__)


class FBrefLoader:
    """
    Load and process FBref.com Premier League squad statistics
    """
    
    # FBref Premier League URLs
    PREMIER_LEAGUE_BASE = "https://fbref.com/en/comps/9"
    PREMIER_LEAGUE_SQUAD_STATS = "https://fbref.com/en/comps/9/Premier-League-Stats"
    
    def __init__(self, cache_dir: str = "data/fbref_cache"):
        """
        Initialize FBref loader
        
        Args:
            cache_dir: Directory to cache downloaded CSVs
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
    
    def load_squad_stats_csv(self, season: int = 2025) -> Optional[pd.DataFrame]:
        """
        Load Premier League squad statistics CSV from cache or manual download
        
        Args:
            season: Season year (e.g., 2025 for 2024-25 season)
        
        Returns:
            DataFrame with squad statistics or None if not found
        """
        cache_file = os.path.join(self.cache_dir, f"pl_squad_stats_{season}.csv")
        
        # Check cache first
        if os.path.exists(cache_file):
            logger.info(f"Loading squad stats from {cache_file}")
            try:
                # FBref CSVs often have multi-level headers, try different approaches
                df = pd.read_csv(cache_file, skiprows=1)  # Skip header row if needed
                
                # Clean column names (remove extra spaces, normalize)
                df.columns = df.columns.str.strip()
                
                # If first column is unnamed or index, use it as team name
                if df.columns[0] in ['Unnamed: 0', ''] or 'Squad' not in df.columns[0]:
                    # Try to find squad column
                    for col in df.columns:
                        if 'Squad' in str(col) or 'Team' in str(col):
                            df = df.rename(columns={col: 'Squad'})
                            break
                
                logger.info(f"Loaded {len(df)} teams from CSV")
                return df
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                # Try alternative parsing
                try:
                    df = pd.read_csv(cache_file)
                    logger.info(f"Loaded {len(df)} teams (alternative parsing)")
                    return df
                except Exception as e2:
                    logger.error(f"Alternative parsing also failed: {e2}")
        
        logger.warning(f"CSV file not found: {cache_file}")
        logger.info("Please download manually from:")
        logger.info("  1. Visit: https://fbref.com/en/comps/9/Premier-League-Stats")
        logger.info("  2. Click 'Squad Stats' tab")
        logger.info("  3. Scroll to bottom and click 'Share & Export'")
        logger.info(f"  4. Select 'Get table as CSV' and save to: {cache_file}")
        
        return None
    
    def calculate_ppda(self, df: pd.DataFrame, team_name: str) -> Optional[float]:
        """
        Calculate PPDA (Passes Allowed Per Defensive Action) for a team
        
        PPDA = Opponent Passes / (Tackles + Interceptions + Fouls)
        
        Args:
            df: DataFrame with squad statistics
            team_name: Team name to match (fuzzy matching)
        
        Returns:
            PPDA value or None if not found
        """
        if df is None or df.empty:
            return None
        
        # Find team row (fuzzy match)
        team_row = self._find_team_row(df, team_name)
        if team_row is None:
            logger.warning(f"Team '{team_name}' not found in FBref data")
            return None
        
        # FBref column names - check actual column names in the data
        # PPDA formula: Opponent Passes / (Tackles + Interceptions + Fouls)
        
        # Try to find PPDA directly (FBref sometimes has it pre-calculated)
        ppda_columns = [
            'PPDA', 'PPDA_Opp', 'Opp_PPDA', 'Passes_Allowed_Per_Def_Action',
            'PPDA Opp', 'Opp PPDA', 'PPDA_opp', 'opp_PPDA'
        ]
        for col in ppda_columns:
            if col in team_row.index:
                try:
                    value = team_row[col]
                    if pd.notna(value):
                        return round(float(value), 2)
                except:
                    continue
        
        # Calculate PPDA from components
        # PPDA = Opponent Passes / (Tackles + Interceptions + Fouls)
        
        # Find opponent passes (passes against/opponent passes)
        opp_passes_cols = [
            'Opp_Passes', 'Opp Passes', 'Opp_Pass', 'Passes_Against',
            'Opp_Pass_Attempted', 'Opp Pass', 'Opp_Pass_Total',
            'Opponent Passes', 'Opponent_Passes', 'Passes Opp'
        ]
        opp_passes = self._get_value(team_row, opp_passes_cols)
        
        # Find defensive actions
        tackles_cols = [
            'Tackles', 'Tkl', 'Tackles_Won', 'Tackles Def 3rd',
            'Tackles Mid 3rd', 'Tackles Att 3rd', 'Tkl_Def', 'Tkl_Mid', 'Tkl_Att'
        ]
        interceptions_cols = [
            'Interceptions', 'Int', 'Inter', 'Interceptions_Total',
            'Inter_Total', 'Int_Total'
        ]
        fouls_cols = [
            'Fouls', 'Fls', 'Fouls_Committed', 'Fouls_Total',
            'Fls_Total', 'Fouls Committed'
        ]
        
        tackles = self._get_value(team_row, tackles_cols)
        interceptions = self._get_value(team_row, interceptions_cols)
        fouls = self._get_value(team_row, fouls_cols)
        
        # If we have individual tackle columns, sum them
        if tackles is None:
            tackle_sum = 0
            for col in tackles_cols:
                val = self._get_value(team_row, [col])
                if val is not None:
                    tackle_sum += val
            if tackle_sum > 0:
                tackles = tackle_sum
        
        if opp_passes is not None and tackles is not None and interceptions is not None and fouls is not None:
            defensive_actions = tackles + interceptions + fouls
            if defensive_actions > 0:
                ppda = opp_passes / defensive_actions
                return round(ppda, 2)
        
        logger.warning(f"Could not calculate PPDA for {team_name} - missing data")
        logger.debug(f"Available columns: {list(team_row.index)[:20]}")
        return None
    
    def calculate_field_tilt(self, df: pd.DataFrame, team_name: str) -> Optional[float]:
        """
        Calculate Field Tilt for a team
        
        Field Tilt = (Attacking Third Passes / Total Passes) * 100
        
        Args:
            df: DataFrame with squad statistics
            team_name: Team name to match
        
        Returns:
            Field Tilt percentage or None if not found
        """
        if df is None or df.empty:
            return None
        
        team_row = self._find_team_row(df, team_name)
        if team_row is None:
            logger.warning(f"Team '{team_name}' not found in FBref data")
            return None
        
        # Field Tilt = (Attacking Third Passes / Total Passes) * 100
        # Or: (Attacking Third Passes / (Attacking Third Passes + Defending Third Passes)) * 100
        
        # Try to find Field Tilt directly
        tilt_columns = [
            'Field_Tilt', 'Tilt', 'Att_3rd_Pass_Pct', 'Attacking_Third_Pass_Pct',
            'Field Tilt', 'Att 3rd Pass %', 'Att_3rd_Pass%', 'Attacking_3rd_Pass_Pct',
            'Att 3rd Pass Pct', 'Attacking Third Pass %'
        ]
        for col in tilt_columns:
            if col in team_row.index:
                try:
                    value = team_row[col]
                    if pd.notna(value):
                        value = float(value)
                        # If it's already a percentage (0-100), return as is
                        # If it's a ratio (0-1), multiply by 100
                        if value <= 1.0:
                            return round(value * 100, 1)
                        return round(value, 1)
                except:
                    continue
        
        # Calculate from components
        # Field Tilt = (Attacking Third Passes / Total Passes) * 100
        
        att_third_cols = [
            'Att_3rd_Passes', 'Attacking_Third_Passes', 'Passes_Att_3rd', 'Pass_Att_3rd',
            'Att 3rd Passes', 'Attacking 3rd Passes', 'Passes Att 3rd',
            'Passes_Attacking_Third', 'Att_3rd', 'Attacking_3rd'
        ]
        total_passes_cols = [
            'Passes', 'Total_Passes', 'Pass_Attempted', 'Passes_Attempted',
            'Total Passes', 'Pass Attempted', 'Passes Attempted',
            'Passes_Total', 'Pass_Total', 'Total_Pass'
        ]
        
        att_third_passes = self._get_value(team_row, att_third_cols)
        total_passes = self._get_value(team_row, total_passes_cols)
        
        # Alternative: Use attacking third + defending third if total not available
        if total_passes is None:
            def_third_cols = [
                'Def_3rd_Passes', 'Defending_Third_Passes', 'Passes_Def_3rd',
                'Def 3rd Passes', 'Defending 3rd Passes', 'Passes Def 3rd'
            ]
            def_third_passes = self._get_value(team_row, def_third_cols)
            if att_third_passes is not None and def_third_passes is not None:
                total_passes = att_third_passes + def_third_passes
        
        if att_third_passes is not None and total_passes is not None and total_passes > 0:
            tilt = (att_third_passes / total_passes) * 100
            return round(tilt, 1)
        
        logger.warning(f"Could not calculate Field Tilt for {team_name} - missing data")
        logger.debug(f"Available columns: {list(team_row.index)[:20]}")
        return None
    
    def _find_team_row(self, df: pd.DataFrame, team_name: str) -> Optional[pd.Series]:
        """Find team row in DataFrame using fuzzy matching"""
        if df is None or df.empty:
            return None
        
        # Try exact match first
        squad_col = None
        for col in df.columns:
            if 'Squad' in str(col) or 'Team' in str(col):
                squad_col = col
                break
        
        if squad_col is None:
            # Try first column
            squad_col = df.columns[0]
        
        # Exact match
        mask = df[squad_col].str.contains(team_name, case=False, na=False)
        matches = df[mask]
        
        if not matches.empty:
            return matches.iloc[0]
        
        # Try partial match (e.g., "Man City" vs "Manchester City")
        team_lower = team_name.lower()
        for idx, row in df.iterrows():
            team_val = str(row[squad_col]).lower()
            if team_lower in team_val or team_val in team_lower:
                return row
        
        return None
    
    def _get_value(self, row: pd.Series, column_names: list) -> Optional[float]:
        """Get value from row trying multiple column names"""
        for col in column_names:
            if col in row.index:
                try:
                    value = row[col]
                    if pd.isna(value):
                        continue
                    return float(value)
                except:
                    continue
        return None
    
    def get_team_metrics(self, season: int, team_name: str) -> Dict[str, Optional[float]]:
        """
        Get PPDA and Field Tilt for a team
        
        Args:
            season: Season year
            team_name: Team name
        
        Returns:
            Dict with 'ppda' and 'field_tilt' values
        """
        df = self.load_squad_stats_csv(season)
        
        if df is None:
            logger.error("Failed to load FBref data")
            return {'ppda': None, 'field_tilt': None}
        
        ppda = self.calculate_ppda(df, team_name)
        field_tilt = self.calculate_field_tilt(df, team_name)
        
        return {
            'ppda': ppda,
            'field_tilt': field_tilt
        }


if __name__ == "__main__":
    # Test the loader
    logging.basicConfig(level=logging.INFO)
    
    loader = FBrefLoader()
    
    # Test with a team
    print("Testing FBref loader...")
    metrics = loader.get_team_metrics(season=2025, team_name="Chelsea")
    print(f"Chelsea metrics: {metrics}")

