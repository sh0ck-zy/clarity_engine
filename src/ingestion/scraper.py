import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
import time
import sys
from io import StringIO
from pathlib import Path

# Silence webdriver_manager logs
os.environ.setdefault("WDM_LOG", "0")

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.database.config import get_connection
# Ensure operations.py is updated to accept the 'round' parameter in save_fixture
from src.database.operations import save_fixture, save_team_stats

FBREF_URL = "https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures"
SEASON = "2025-2026"

def get_html_with_selenium(url):
    print("   🕵️  Launching Headless Chrome...")
    
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # This User-Agent is crucial
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        driver.get(url)
        # Wait a bit for Cloudflare checks or JS to load
        time.sleep(5) 
        html = driver.page_source
        return html
    finally:
        driver.quit()

def run_scraper():
    print(f"🚛 Starting Selenium Ingestion for {SEASON}...")
    
    conn = get_connection()
    if not conn:
        return

    # 1. GET THE HTML
    html_content = get_html_with_selenium(FBREF_URL)
    
    if "403 Forbidden" in html_content:
        print("❌ Still blocked (403). Try running without --headless mode to solve captcha manually.")
        return

    # 2. EXTRACT THE TABLE
    print("   📄 Parsing HTML tables...")
    try:
        # Pandas does the heavy lifting here
        tables = pd.read_html(StringIO(html_content))
        
        # Find the schedule table. We look for 'Score' AND 'Wk' to be sure
        df = None
        for t in tables:
            if 'Score' in t.columns and 'Wk' in t.columns:
                df = t
                break
        
        # Fallback if we only found one with Score (sometimes headers vary)
        if df is None:
            for t in tables:
                if 'Score' in t.columns:
                    df = t
                    break
        
        if df is None:
            print("❌ Could not find Schedule table in HTML.")
            return
            
    except Exception as e:
        print(f"❌ Error parsing HTML: {e}")
        return

    # 3. PROCESS AND SAVE
    # Clean up the dataframe (FBref repeats headers)
    df = df[df['Date'] != 'Date'].dropna(subset=['Date'])
    
    print(f"   📋 Found {len(df)} matches. Saving to DB...")
    
    matches_saved = 0
    upcoming_saved = 0
    
    for _, row in df.iterrows():
        try:
            date = row['Date']
            home_team = row['Home']
            away_team = row['Away']
            
            # --- NEW: EXTRACT ROUND (WK) ---
            # We treat 'Wk' carefully because it might be empty or formatted weirdly
            game_round = None
            if 'Wk' in row and pd.notna(row['Wk']):
                try:
                    game_round = int(row['Wk'])
                except ValueError:
                    game_round = None # If it's not a clean number, leave it null
            
            if pd.isna(home_team) or pd.isna(away_team):
                continue

            clean_home = home_team.replace(" ", "_")
            clean_away = away_team.replace(" ", "_")
            fixture_id = f"{date}_{clean_home}_{clean_away}"

            score = row['Score']
            status = 'SCHEDULED'
            home_goals, away_goals = None, None

            if pd.notna(score):
                parts = score.replace('–', '-').split('-')
                if len(parts) == 2:
                    home_goals = int(parts[0])
                    away_goals = int(parts[1])
                    status = 'FINISHED'

            # --- UPDATED SAVE CALL ---
            # We are now sending 9 items instead of 8
            save_fixture(conn, (
                fixture_id, date, SEASON, 
                home_team, away_team, 
                home_goals, away_goals, status,
                game_round # <--- Added this newly extracted variable
            ))

            # Save Stats (xG)
            if status == 'FINISHED':
                # Handle potential missing xG columns
                home_xg = float(row['xG']) if 'xG' in row and pd.notna(row['xG']) else None
                away_xg = float(row['xG.1']) if 'xG.1' in row and pd.notna(row['xG.1']) else None

                stats_rows = [
                    (fixture_id, home_team, True, home_xg, away_xg, None, None),
                    (fixture_id, away_team, False, away_xg, home_xg, None, None)
                ]
                save_team_stats(conn, stats_rows)
                matches_saved += 1
            else:
                upcoming_saved += 1

        except Exception as e:
            # print(f"Skipping row: {e}") # Uncomment for debugging
            continue

    print(f"✅ Success!")
    print(f"   - {matches_saved} Finished matches")
    print(f"   - {upcoming_saved} Scheduled matches")
    
    conn.close()

if __name__ == "__main__":
    run_scraper()
