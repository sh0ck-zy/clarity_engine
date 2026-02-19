import pandas as pd
import io
import requests
from datetime import datetime

def check_names():
    print("🕵️  Fetching ClubElo Team Names...")
    url = "http://api.clubelo.com/" + datetime.now().strftime("%Y-%m-%d")
    s = requests.get(url).content
    df = pd.read_csv(io.StringIO(s.decode('utf-8')))
    
    eng = df[df['Country'] == 'ENG']
    print("\n📋 English Teams in ClubElo:")
    print(sorted(eng['Club'].unique()))

if __name__ == "__main__":
    check_names()