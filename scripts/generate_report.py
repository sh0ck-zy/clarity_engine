import sys
import os
import pandas as pd
import warnings

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from database.config import get_connection

# Silence the pesky Pandas/SQLAlchemy warning
warnings.filterwarnings('ignore')

def generate_html_report():
    print("🎨 Generating Clarity HQ Dashboard...")
    conn = get_connection()
    if not conn:
        return

    # 0. INVENTORY STATS
    sql_inventory = """
        SELECT season, status, COUNT(*) as count
        FROM fixtures
        GROUP BY season, status
        ORDER BY season DESC, status
    """
    df_inventory = pd.read_sql(sql_inventory, conn)

    # 1. MATCH ANALYSIS (The Core Data)
    # We calculate xG Diff here so it's ready for the view
    sql_results = """
        SELECT 
            f.date,
            f.home_team, 
            f.home_score || ' - ' || f.away_score as result,
            f.away_team,
            -- TACTICAL PROFILE (Identity)
            ts_home.elo as "H Elo",
            ts_away.elo as "A Elo",
            ts_home.ppda as "H PPDA",
            ts_away.ppda as "A PPDA",
            ts_home.field_tilt as "H Tilt",
            ts_away.field_tilt as "A Tilt",
            -- PERFORMANCE (The Truth)
            ts_home.xg as "H xG",
            ts_away.xg as "A xG",
            ROUND(ts_home.xg - ts_away.xg, 2) as "xG Diff"
        FROM fixtures f
        LEFT JOIN team_stats ts_home ON f.id = ts_home.fixture_id AND ts_home.is_home = TRUE
        LEFT JOIN team_stats ts_away ON f.id = ts_away.fixture_id AND ts_away.is_home = FALSE
        WHERE f.status = 'FINISHED'
        ORDER BY f.date DESC
    """
    df_results = pd.read_sql(sql_results, conn)

    # 2. UPCOMING FIXTURES (Next 15)
    sql_schedule = """
        SELECT date, home_team, 'vs' as vs, away_team 
        FROM fixtures 
        WHERE status = 'SCHEDULED' AND date >= CURRENT_DATE 
        ORDER BY date ASC 
        LIMIT 15
    """
    df_schedule = pd.read_sql(sql_schedule, conn)

    # 3. GENERATE HTML DASHBOARD
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Clarity HQ | Football Intelligence</title>
        <style>
            :root {{
                --bg-color: #f4f6f9;
                --card-bg: #ffffff;
                --text-primary: #2c3e50;
                --text-secondary: #7f8c8d;
                --accent-blue: #3498db;
                --border-color: #ecf0f1;
            }}
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                background-color: var(--bg-color); 
                margin: 0; 
                padding: 40px; 
                color: var(--text-primary);
            }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            
            /* Header */
            .header {{ margin-bottom: 30px; border-bottom: 3px solid var(--accent-blue); padding-bottom: 20px; }}
            h1 {{ margin: 0; font-size: 32px; color: var(--text-primary); }}
            .subtitle {{ color: var(--text-secondary); font-size: 16px; margin-top: 5px; font-weight: 400; }}

            /* Cards */
            .card {{ 
                background: var(--card-bg); 
                border-radius: 12px; 
                box-shadow: 0 4px 6px rgba(0,0,0,0.04); 
                padding: 25px; 
                margin-bottom: 30px; 
            }}
            h2 {{ 
                font-size: 18px; 
                margin-top: 0; 
                margin-bottom: 20px; 
                color: var(--accent-blue);
                text-transform: uppercase;
                letter-spacing: 1px;
                font-weight: 700;
            }}

            /* Tables */
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            th {{ 
                background-color: #f8f9fa; 
                color: var(--text-secondary); 
                font-weight: 700; 
                text-align: left; 
                padding: 15px 12px; 
                text-transform: uppercase; 
                font-size: 11px;
                letter-spacing: 0.5px;
                border-bottom: 2px solid var(--border-color);
            }}
            td {{ padding: 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }}
            tr:last-child td {{ border-bottom: none; }}
            tr:hover {{ background-color: #f8fbff; }}

            /* Data Columns Styling */
            
            /* Teams & Result */
            td:nth-child(2), td:nth-child(4) {{ font-weight: 600; font-size: 14px; }}
            td:nth-child(3) {{ font-weight: 800; text-align: center; background: #f1f3f5; border-radius: 4px; color: #2c3e50; }} /* Score */
            
            /* Elo (Purple) */
            td:nth-child(5), td:nth-child(6) {{ font-family: "Menlo", monospace; color: #6f42c1; }}
            
            /* Tactics (Pink/Red) */
            td:nth-child(7), td:nth-child(8), td:nth-child(9), td:nth-child(10) {{ color: #e83e8c; font-weight: 500; }}
            
            /* xG (Green) */
            td:nth-child(11), td:nth-child(12) {{ color: #28a745; font-family: "Menlo", monospace; }}
            
            /* xG Diff (Bold Green) */
            td:nth-child(13) {{ font-weight: 800; color: #218838; background: #e6fffa; }} 

        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>⚽ Clarity Engine HQ</h1>
                <div class="subtitle">Premier League Intelligence Dashboard</div>
            </div>

            <div class="card">
                <h2>📦 Warehouse Inventory</h2>
                {df_inventory.to_html(index=False, classes='table', border=0)}
            </div>

            <div class="card">
                <h2>✅ Match Analysis (Deep Dive)</h2>
                <p style="font-size: 13px; color: #666; margin-bottom: 20px; line-height: 1.6;">
                    <strong>Legend:</strong><br>
                    <span style="color: #6f42c1;">● Elo Rating</span> (Team Strength) &nbsp;|&nbsp; 
                    <span style="color: #e83e8c;">● PPDA / Tilt</span> (Tactical Style) &nbsp;|&nbsp; 
                    <span style="color: #28a745;">● xG / xG Diff</span> (Performance Quality)
                </p>
                {df_results.to_html(index=False, classes='table', border=0)}
            </div>

            <div class="card">
                <h2>📅 Upcoming Schedule</h2>
                {df_schedule.to_html(index=False, classes='table', border=0)}
            </div>
        </div>
    </body>
    </html>
    """

    output_path = os.path.join(os.path.dirname(__file__), '../data/audit_report.html')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✨ HQ Dashboard generated: {os.path.abspath(output_path)}")
    conn.close()

if __name__ == "__main__":
    generate_html_report()