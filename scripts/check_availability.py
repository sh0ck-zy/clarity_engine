import soccerdata as sd
import sys

def check_providers():
    print("🕵️  CHECKING DATA AVAILABILITY")
    print("============================")

    # 1. CHECK UNDERSTAT
    print("\n1. UNDERSTAT (The Specialist)")
    try:
        ws = sd.Understat(leagues="ENG-Premier League", seasons="2024")
        leagues = ws.available_leagues()
        print(f"   ✅ Available Leagues ({len(leagues)}):")
        print(f"      {leagues}")
            
    except Exception as e:
        print(f"   ⚠️ Error checking Understat: {e}")

    # 2. CHECK WHOSCORED (The Generalist)
    print("\n2. WHOSCORED (The Global Giant)")
    try:
        # Instead of trying to connect to a specific league immediately,
        # We try to see what the library thinks is valid.
        # Note: WhoScored scraping is notoriously hard due to blocking.
        
        # We use a dummy init to check available leagues if possible, 
        # or rely on the error message which lists them.
        print("   Attempting to connect to WhoScored...")
        ws = sd.WhoScored(leagues="ENG-Premier League", seasons="2024")
        
        print("   ✅ Connection Successful. Listing valid leagues...")
        print(f"      {ws.available_leagues()}")

    except Exception as e:
        print(f"   ⚠️ WhoScored Blocked/Unavailable: {e}")
        print("   (This usually means WhoScored has detected the script and blocked the request)")

if __name__ == "__main__":
    check_providers()