from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import pandas as pd
from io import StringIO
import time

URL = "https://fbref.com/en/comps/9/schedule/Premier-League-Scores-and-Fixtures"

def spy_on_columns():
    print(f"🕵️  Spying on FBref columns...")
    
    # Setup Headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    try:
        driver.get(URL)
        time.sleep(5)
        html = driver.page_source
        
        # Read the table
        dfs = pd.read_html(StringIO(html))
        
        # Find the main schedule table
        df = None
        for t in dfs:
            if 'Score' in t.columns:
                df = t
                break
        
        if df is None:
            print("❌ Could not find table.")
            return

        print("\n📋 AVAILABLE COLUMNS ON THIS PAGE:")
        print("-----------------------------------")
        for col in df.columns:
            print(f" - {col}")
            
        print("\n🧐 VERDICT:")
        if 'xG' in df.columns:
            print("✅ xG is here.")
        else:
            print("❌ xG is MISSING.")
            
        if 'PPDA' in df.columns:
            print("✅ PPDA is here.")
        else:
            print("❌ PPDA is MISSING (We need to scrape Match Reports or Understat for this).")

    finally:
        driver.quit()

if __name__ == "__main__":
    spy_on_columns()