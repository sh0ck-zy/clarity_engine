from flask import Flask, jsonify, render_template, request
import ast
import json
import sys
import threading
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Setup Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.analysis.builder import MatchContextBuilder
from src.analysis.copilot import ClarityCopilot
from src.analysis.judge import ClarityJudge
from src.analysis.predictor import ClarityEngine
from src.analysis.prompts import PROMPTS
from src.database.config import get_connection
from src.jobs.batch_runner import BatchRunner

load_dotenv()
warnings.filterwarnings("ignore")

app = Flask(__name__, template_folder="templates")


# --- HELPERS ---
def safe_parse_json(data):
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        data = data.strip()
        try:
            return json.loads(data)
        except Exception:
            try:
                return ast.literal_eval(data)
            except Exception:
                return {}
    return {}


# --- ROUTES ---
@app.route("/")
def index():
    return render_template("index.html", prompts=PROMPTS)


@app.route("/api/rounds/<season>")
def get_rounds(season):
    conn = get_connection()
    df = pd.read_sql(
        "SELECT DISTINCT round FROM fixtures WHERE season=%s AND round IS NOT NULL ORDER BY round DESC",
        conn,
        params=(season,),
    )
    conn.close()
    return jsonify(df["round"].tolist())


@app.route("/api/matches/<season>/<round_val>")
def get_matches(season, round_val):
    conn = get_connection()

    query = """
        SELECT f.id, f.date, f.home_team, f.away_team, f.status, f.round,
               f.home_score, f.away_score,
               ts_h.xg as h_xg, ts_a.xg as a_xg
        FROM fixtures f
        LEFT JOIN team_stats ts_h ON f.id = ts_h.fixture_id AND ts_h.is_home = TRUE
        LEFT JOIN team_stats ts_a ON f.id = ts_a.fixture_id AND ts_a.is_home = FALSE
        WHERE f.season = %s
    """
    params = [season]

    if round_val != "all":
        query += " AND f.round = %s"
        params.append(round_val)

    query += " ORDER BY f.round DESC, f.date DESC"
    df = pd.read_sql(query, conn, params=tuple(params))

    df["date"] = df["date"].astype(str)
    df = df.replace({np.nan: None})

    conn.close()
    return jsonify(df.to_dict("records"))


@app.route("/api/context/<fixture_id>")
def get_match_context(fixture_id):
    builder = MatchContextBuilder()
    try:
        ctx = builder.build_context(fixture_id)
        return jsonify(ctx)
    except Exception as e:
        return jsonify({"error": str(e)})
    finally:
        builder.close()


@app.route("/api/fixture/<fixture_id>/history")
def get_fixture_history(fixture_id):
    conn = get_connection()
    query = "SELECT id, prompt_version, model_name, created_at, headline FROM analysis_reports WHERE fixture_id = %s ORDER BY created_at DESC"
    df = pd.read_sql(query, conn, params=(fixture_id,))
    conn.close()
    df["created_at"] = df["created_at"].astype(str)
    return jsonify(df.to_dict("records"))


@app.route("/api/report/<analysis_id>")
def get_specific_report(analysis_id):
    conn = get_connection()
    query = "SELECT full_json, fixture_id FROM analysis_reports WHERE id = %s"
    row = pd.read_sql(query, conn, params=(analysis_id,))

    try:
        audit_row = pd.read_sql(
            "SELECT rating, failure_reason, notes FROM analysis_audits WHERE analysis_id = %s",
            conn,
            params=(analysis_id,),
        )
    except Exception:
        audit_row = pd.DataFrame()

    try:
        ai_row = pd.read_sql(
            "SELECT score, verdict, reasoning FROM ai_evaluations WHERE analysis_id = %s",
            conn,
            params=(analysis_id,),
        )
    except Exception:
        ai_row = pd.DataFrame()

    conn.close()

    if not row.empty:
        raw_data = row.iloc[0]["full_json"]
        payload = safe_parse_json(raw_data)
        audit_data = audit_row.iloc[0].to_dict() if not audit_row.empty else None
        ai_data = ai_row.iloc[0].to_dict() if not ai_row.empty else None
        return jsonify(
            {
                "exists": True,
                "payload": payload,
                "audit": audit_data,
                "ai_eval": ai_data,
                "fixture_id": row.iloc[0]["fixture_id"],
            }
        )

    return jsonify({"exists": False})


@app.route("/api/analyze/<fixture_id>")
def run_analysis_route(fixture_id):
    prompt_key = request.args.get("prompt", "hybrid")
    force = request.args.get("force") == "true"
    engine = ClarityEngine()
    try:
        result = engine.run_analysis(fixture_id, prompt_key, force_refresh=force)
        return jsonify({"response": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        engine.close()


@app.route("/api/batch/run", methods=["POST"])
def run_batch():
    data = request.json
    season = data.get("season")
    round_id = data.get("round")
    prompt = data.get("prompt", "hybrid")

    def run_background():
        runner = BatchRunner()
        runner.run_round(season, round_id, prompt, force=False)
        print(f"✅ Batch para ronda {round_id} concluído.")

    thread = threading.Thread(target=run_background)
    thread.start()
    return jsonify({"status": "started", "message": f"Batch iniciado para Ronda {round_id}."})


@app.route("/api/judge/run", methods=["POST"])
def run_judge():
    data = request.json
    analysis_id = data.get("analysis_id")
    fixture_id = data.get("fixture_id")

    conn = get_connection()
    try:
        an_row = pd.read_sql(
            "SELECT full_json FROM analysis_reports WHERE id = %s",
            conn,
            params=(analysis_id,),
        )
        if an_row.empty:
            return jsonify({"error": "analysis not found"}), 404
        prediction = safe_parse_json(an_row.iloc[0]["full_json"])

        match_query = "SELECT home_score, away_score, status FROM fixtures WHERE id = %s"
        match_row = pd.read_sql(match_query, conn, params=(fixture_id,))
        stats_query = "SELECT team_name, xg, is_home FROM team_stats WHERE fixture_id = %s"
        stats_df = pd.read_sql(stats_query, conn, params=(fixture_id,))

        if match_row.empty:
            return jsonify({"error": "fixture not found"}), 404

        actual_data = {
            "score": f"{match_row.iloc[0]['home_score']} - {match_row.iloc[0]['away_score']}",
            "status": match_row.iloc[0]["status"],
            "stats": stats_df.to_dict("records"),
        }

        judge = ClarityJudge()
        verdict = judge.evaluate(prediction, actual_data)

        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_evaluations WHERE analysis_id = %s", (analysis_id,))
        cursor.execute(
            """
            INSERT INTO ai_evaluations (analysis_id, fixture_id, score, verdict, reasoning)
            VALUES (%s, %s, %s, %s, %s)
        """,
            (analysis_id, fixture_id, verdict.get("score"), verdict.get("verdict"), verdict.get("reasoning")),
        )
        conn.commit()

        return jsonify({"status": "success", "verdict": verdict})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/copilot/chat", methods=["POST"])
def chat_copilot():
    data = request.json
    messages = data.get("messages", [])
    context = data.get("context", {})  # Contains analysis_a, analysis_b, match_info

    copilot = ClarityCopilot()
    response = copilot.chat(messages, context)

    return jsonify({"role": "assistant", "content": response})


@app.route("/api/audit", methods=["POST"])
def save_audit_route():
    data = request.json
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT 1 FROM analysis_audits LIMIT 1")
    except Exception:
        conn.close()
        return jsonify({"error": "audit table missing"}), 500

    analysis_id = data.get("analysis_id")
    if analysis_id:
        cursor.execute("SELECT audit_id FROM analysis_audits WHERE analysis_id = %s", (analysis_id,))
        exists = cursor.fetchone()

        if exists:
            cursor.execute(
                "UPDATE analysis_audits SET rating=%s, failure_reason=%s, notes=%s WHERE analysis_id=%s",
                (data["rating"], data["reason"], data["notes"], analysis_id),
            )
        else:
            cursor.execute(
                "INSERT INTO analysis_audits (analysis_id, fixture_id, rating, failure_reason, notes) VALUES (%s, %s, %s, %s, %s)",
                (analysis_id, data["fixture_id"], data["rating"], data["reason"], data["notes"]),
            )
        conn.commit()
        conn.close()
        return jsonify({"status": "saved"})
    conn.close()
    return jsonify({"error": "No ID"}), 400


if __name__ == "__main__":
    print("🚀 Clarity Lab v4.2 (Comparator + CoPilot) is live at http://127.0.0.1:5001")
    app.run(debug=True, port=5001)
