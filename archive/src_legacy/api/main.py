"""
FastAPI Backend for Match Intelligence Backtesting Platform

Wraps existing Python modules to provide a REST API for the frontend.

Run with:
    uvicorn src.api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional, List, Dict, Any
import json
import numpy as np

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Import existing modules
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.config import get_connection
from src.analysis.context_builder_v2 import ContextBuilderV2
from src.analysis.context_schema import context_to_dict, MatchContext
from src.analysis.predictor import ClarityEngine
from src.analysis.evaluator import AnalysisEvaluator
from src.analysis.data_validator import DataValidator


def convert_numpy_types(obj):
    """Recursively convert numpy types to Python native types for JSON serialization."""
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (date, datetime)):
        return obj.isoformat()
    else:
        return obj


# ============================================================
# Pydantic Models
# ============================================================


class FixtureSummary(BaseModel):
    fixture_id: str
    home_team: str
    away_team: str
    date: date
    round: Optional[int]
    home_score: Optional[int]
    away_score: Optional[int]
    status: Optional[str]


class RoundSummary(BaseModel):
    round: int
    fixtures_total: int
    analyses_total: int
    evaluations_total: int
    accuracy: Optional[float]


class ContextSchemaConfig(BaseModel):
    """Configuration for which fields to include in context."""
    name: str
    include_identity: bool = True
    include_form: bool = True
    include_absences: bool = True
    include_head_to_head: bool = True
    include_schedule: bool = True
    include_league_position: bool = True
    include_odds: bool = True


class AnalysisRequest(BaseModel):
    fixture_id: str
    prompt_version: str
    schema_config: Optional[ContextSchemaConfig] = None
    force_refresh: bool = False


class BacktestRequest(BaseModel):
    fixture_ids: List[str]
    prompt_version: str
    schema_config: Optional[ContextSchemaConfig] = None
    experiment_name: Optional[str] = None


class AnalysisResult(BaseModel):
    fixture_id: str
    predicted_score: Optional[str]
    confidence: Optional[int]
    betting_recommendation: Optional[str]
    is_correct: Optional[bool]
    full_json: Optional[Dict[str, Any]]


class EvaluationResult(BaseModel):
    report_id: int
    narrative_score: Optional[int]
    score_accuracy: Optional[bool]
    tip_accuracy: Optional[bool]
    critical_flags: List[str]


class FailureDetail(BaseModel):
    fixture_id: str
    home_team: str
    away_team: str
    predicted_score: str
    actual_score: str
    confidence: int
    prompt_version: str
    reasoning: Optional[str]
    context_used: Optional[Dict[str, Any]]
    reality_narrative: Optional[str]


# ============================================================
# App Setup
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Match Intelligence API...")
    yield
    # Shutdown
    print("👋 Shutting down...")


app = FastAPI(
    title="Match Intelligence API",
    description="Backtesting platform for Match Intelligence model",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Fixtures Endpoints
# ============================================================

@app.get("/api/fixtures", response_model=List[FixtureSummary])
def get_fixtures(
    season: str = "2025-2026",
    round: Optional[int] = None,
    limit: int = Query(default=100, le=500)
):
    """Get fixtures with optional round filter."""
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()
        if round:
            cur.execute("""
                SELECT id, home_team, away_team, date, round, home_score, away_score, status
                FROM fixtures
                WHERE season = %s AND round = %s
                ORDER BY date, home_team
                LIMIT %s
            """, (season, round, limit))
        else:
            cur.execute("""
                SELECT id, home_team, away_team, date, round, home_score, away_score, status
                FROM fixtures
                WHERE season = %s
                ORDER BY date DESC, home_team
                LIMIT %s
            """, (season, limit))

        fixtures = []
        for row in cur.fetchall():
            fixtures.append(FixtureSummary(
                fixture_id=row[0],
                home_team=row[1],
                away_team=row[2],
                date=row[3],
                round=row[4],
                home_score=row[5],
                away_score=row[6],
                status=row[7]
            ))
        return fixtures
    finally:
        conn.close()


@app.get("/api/rounds", response_model=List[RoundSummary])
def get_rounds(season: str = "2025-2026", league: str = "Premier League"):
    """Get round-level summary stats."""
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        query = """
            SELECT
                f.round,
                COUNT(DISTINCT f.id) AS fixtures_total,
                COUNT(DISTINCT ar.id) AS analyses_total,
                COUNT(DISTINCT ae.id) AS evaluations_total,
                AVG(CASE WHEN ar.is_correct THEN 1 ELSE 0 END) * 100 AS accuracy
            FROM fixtures f
            LEFT JOIN analysis_reports ar ON ar.fixture_id = f.id
            LEFT JOIN analysis_evaluations ae ON ae.fixture_id = f.id
            WHERE f.season = %s AND f.league = %s AND f.round IS NOT NULL
            GROUP BY f.round
            ORDER BY f.round DESC
        """
        cur = conn.cursor()
        cur.execute(query, (season, league))

        rounds = []
        for row in cur.fetchall():
            rounds.append(RoundSummary(
                round=row[0],
                fixtures_total=row[1],
                analyses_total=row[2],
                evaluations_total=row[3],
                accuracy=float(row[4]) if row[4] else None
            ))
        return rounds
    finally:
        conn.close()


# ============================================================
# Context Endpoints
# ============================================================

@app.get("/api/context/{fixture_id}")
def get_context(fixture_id: str):
    """Get full match context for a fixture."""
    builder = ContextBuilderV2()
    try:
        context = builder.build_context(fixture_id)
        if not context:
            raise HTTPException(status_code=404, detail=f"Fixture not found: {fixture_id}")
        # Use JSONResponse to bypass FastAPI's jsonable_encoder which fails on numpy types
        return JSONResponse(content=convert_numpy_types(context_to_dict(context)))
    finally:
        builder.close()


@app.get("/api/context/{fixture_id}/coverage")
def get_context_coverage(fixture_id: str):
    """Get data coverage score for a fixture."""
    validator = DataValidator()
    try:
        coverage = validator.check_data_coverage(fixture_id)
        if not coverage:
            raise HTTPException(status_code=404, detail=f"Fixture not found: {fixture_id}")
        return {
            "fixture_id": fixture_id,
            "overall_score": coverage.overall_score,
            "sources": [{"name": s.name, "status": s.status, "details": s.details} for s in coverage.sources]
        }
    finally:
        validator.close()


@app.get("/api/context/{fixture_id}/time-travel")
def check_time_travel(fixture_id: str):
    """Check time-travel safety for a fixture."""
    validator = DataValidator()
    try:
        report = validator.check_time_travel_safety(fixture_id)
        if not report:
            raise HTTPException(status_code=404, detail=f"Fixture not found: {fixture_id}")
        return {
            "fixture_id": fixture_id,
            "is_safe": report.is_safe,
            "match_date": report.match_date.isoformat() if report.match_date else None,
            "warnings": [{"severity": w.severity, "message": w.message} for w in report.warnings]
        }
    finally:
        validator.close()


# ============================================================
# Analysis Endpoints
# ============================================================

@app.post("/api/analyze", response_model=AnalysisResult)
def run_analysis(request: AnalysisRequest):
    """Run analysis for a single fixture."""
    engine = ClarityEngine()
    try:
        result = engine.run_analysis(
            request.fixture_id,
            request.prompt_version,
            force_refresh=request.force_refresh
        )
        if not result or "error" in result:
            error_msg = result.get("error", "Analysis failed") if result else "No result"
            raise HTTPException(status_code=500, detail=error_msg)

        return AnalysisResult(
            fixture_id=request.fixture_id,
            predicted_score=result.get("predicted_score"),
            confidence=result.get("confidence"),
            betting_recommendation=result.get("betting_recommendation"),
            is_correct=result.get("is_correct"),
            full_json=result
        )
    finally:
        engine.close()


@app.get("/api/analyses/{fixture_id}")
def get_analyses(fixture_id: str):
    """Get all analyses for a fixture."""
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                ar.id, ar.prompt_version, ar.predicted_score, ar.confidence,
                ar.betting_recommendation, ar.is_correct, ar.full_json, ar.created_at
            FROM analysis_reports ar
            WHERE ar.fixture_id = %s
            ORDER BY ar.created_at DESC
        """, (fixture_id,))

        analyses = []
        for row in cur.fetchall():
            full_json = row[6]
            if isinstance(full_json, str):
                try:
                    full_json = json.loads(full_json)
                except:
                    full_json = {}

            analyses.append({
                "id": row[0],
                "prompt_version": row[1],
                "predicted_score": row[2],
                "confidence": row[3],
                "betting_recommendation": row[4],
                "is_correct": row[5],
                "full_json": full_json,
                "created_at": row[7].isoformat() if row[7] else None
            })
        return {"analyses": analyses}
    finally:
        conn.close()


# ============================================================
# Evaluation Endpoints
# ============================================================

@app.post("/api/evaluate/{report_id}")
def run_evaluation(report_id: int, force_refresh: bool = False):
    """Run evaluation for an analysis report."""
    evaluator = AnalysisEvaluator()
    try:
        result = evaluator.evaluate_analysis(report_id, force_refresh=force_refresh)
        if not result:
            raise HTTPException(status_code=404, detail=f"Report not found or no reality data: {report_id}")
        return result
    finally:
        evaluator.close()


@app.get("/api/evaluations/{fixture_id}")
def get_evaluations(fixture_id: str):
    """Get evaluations for a fixture."""
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                ae.report_id, ae.narrative_score, ae.score_accuracy, ae.tip_accuracy,
                ae.narrative_feedback, ae.narrative_critical_flags
            FROM analysis_evaluations ae
            WHERE ae.fixture_id = %s
        """, (fixture_id,))

        evaluations = []
        for row in cur.fetchall():
            critical_flags = row[5]
            if isinstance(critical_flags, str):
                try:
                    critical_flags = json.loads(critical_flags)
                except:
                    critical_flags = []

            evaluations.append({
                "report_id": row[0],
                "narrative_score": row[1],
                "score_accuracy": row[2],
                "tip_accuracy": row[3],
                "feedback": row[4],
                "critical_flags": critical_flags or []
            })
        return {"evaluations": evaluations}
    finally:
        conn.close()


# ============================================================
# Failures Endpoint
# ============================================================

@app.get("/api/failures", response_model=List[FailureDetail])
def get_failures(
    season: str = "2025-2026",
    prompt_version: Optional[str] = None,
    limit: int = Query(default=50, le=200)
):
    """Get failed predictions with details for deep dive."""
    conn = get_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    try:
        cur = conn.cursor()
        prompt_filter = "AND ar.prompt_version = %s" if prompt_version else ""
        params = [season, limit] if not prompt_version else [season, prompt_version, limit]

        query = f"""
            SELECT
                f.id, f.home_team, f.away_team,
                ar.predicted_score, f.home_score, f.away_score,
                ar.confidence, ar.prompt_version, ar.full_json,
                mr.narrative_summary
            FROM analysis_reports ar
            JOIN fixtures f ON ar.fixture_id = f.id
            LEFT JOIN match_reality mr ON f.id = mr.fixture_id
            WHERE f.season = %s
              AND ar.is_correct = FALSE
              AND f.home_score IS NOT NULL
              {prompt_filter}
            ORDER BY f.date DESC
            LIMIT %s
        """
        cur.execute(query, params)

        failures = []
        for row in cur.fetchall():
            full_json = row[8]
            if isinstance(full_json, str):
                try:
                    full_json = json.loads(full_json)
                except:
                    full_json = {}

            reasoning = None
            if full_json:
                glass_box = full_json.get("glass_box_logic", {})
                reasoning = glass_box.get("reasoning")

            failures.append(FailureDetail(
                fixture_id=row[0],
                home_team=row[1],
                away_team=row[2],
                predicted_score=row[3] or "?",
                actual_score=f"{row[4]}-{row[5]}" if row[4] is not None else "?",
                confidence=row[6] or 0,
                prompt_version=row[7],
                reasoning=reasoning,
                context_used=full_json.get("context_snapshot") if full_json else None,
                reality_narrative=row[9]
            ))
        return failures
    finally:
        conn.close()


# ============================================================
# Prompts Endpoint
# ============================================================

@app.get("/api/prompts")
def get_prompts():
    """Get available prompt versions."""
    from src.analysis.prompts import PROMPTS
    return {
        "prompts": [
            {"key": k, "name": v["name"]}
            for k, v in PROMPTS.items()
        ]
    }


# ============================================================
# Health Check
# ============================================================

@app.get("/api/health")
def health_check():
    """Health check endpoint."""
    conn = get_connection()
    db_status = "ok" if conn else "error"
    if conn:
        conn.close()
    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status
    }
