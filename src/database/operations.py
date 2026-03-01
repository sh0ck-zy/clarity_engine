from psycopg2.extras import execute_values

def save_fixture(conn, fixture_data):
    """
    Saves a single fixture to the database.
    fixture_data: tuple(id, date, season, home_team, away_team, home_score, away_score, status, round)
    """
    # Note the addition of "round" in the columns and EXCLUDED updates
    sql = """
    INSERT INTO fixtures (
        id, date, season, home_team, away_team, 
        home_score, away_score, status, "round"
    )
    VALUES %s
    ON CONFLICT (id) DO UPDATE SET
        date = EXCLUDED.date,
        home_score = EXCLUDED.home_score,
        away_score = EXCLUDED.away_score,
        status = EXCLUDED.status,
        "round" = EXCLUDED."round";
    """
    try:
        cur = conn.cursor()
        # execute_values expects a list of tuples, so we wrap fixture_data in []
        execute_values(cur, sql, [fixture_data])
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"❌ Error saving fixture {fixture_data[0]}: {e}")

def save_team_stats(conn, stats_list):
    """
    Saves a list of team stats (usually 2 rows per match).
    stats_list: list of tuples(fixture_id, team_name, is_home, xg, xga, ppda, field_tilt, elo)
    Note: elo should be None when inserting; existing elo values are preserved on conflict.
    """
    sql = """
    INSERT INTO team_stats (fixture_id, team_name, is_home, xg, xga, ppda, field_tilt, elo)
    VALUES %s
    ON CONFLICT (fixture_id, team_name) DO UPDATE SET
        xg = EXCLUDED.xg,
        xga = EXCLUDED.xga,
        ppda = EXCLUDED.ppda,
        field_tilt = EXCLUDED.field_tilt,
        elo = COALESCE(team_stats.elo, EXCLUDED.elo);
    """
    try:
        cur = conn.cursor()
        execute_values(cur, sql, stats_list)
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"❌ Error saving stats: {e}")