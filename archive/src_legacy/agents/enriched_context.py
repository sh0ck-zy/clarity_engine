"""
Enriched Context Builder - Merge Engine for Agent + DB Data

This module merges AI-extracted data with deterministic database data,
following the anti-hallucination principle:

1. DB data is ALWAYS the source of truth for structured metrics
2. Agent data ENRICHES but never REPLACES valid DB data
3. All agent data passes through validation before merge
4. Fallback: If agent fails, use DB data only (graceful degradation)

The result is a richer context that maintains data integrity.
"""

import sys
from pathlib import Path
from datetime import datetime, date
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
import logging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from src.analysis.context_builder_v2 import ContextBuilderV2
from src.analysis.context_schema import (
    MatchContext, TeamContext, TeamAbsences, PlayerAbsence,
    HeadToHead, TeamForm, LeaguePosition,
    validate_context, calculate_coverage_score
)
from .extraction_agent import ExtractionAgent
from .extraction_validator import ExtractionValidator, ValidationResult, validate_extraction
from .extraction_schemas import (
    InjuryExtraction, FormExtraction, TablePositionExtraction,
    HeadToHeadExtraction, TeamEnrichment, MatchEnrichment,
    dict_to_injury_extraction, dict_to_form_extraction,
    dict_to_table_extraction, dict_to_h2h_extraction
)

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentResult:
    """Result of enrichment process with metadata."""
    context: MatchContext
    enrichment_applied: bool
    enrichment_sources: List[str] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)
    agent_data_used: Dict[str, bool] = field(default_factory=dict)
    enrichment_timestamp: str = ""
    enrichment_quality: float = 0.0


class EnrichedContextBuilder:
    """
    Builds match context by merging DB data with AI-extracted enrichments.

    Architecture:
    ```
    DB Data (ContextBuilderV2)  +  Agent Data (ExtractionAgent)
              |                            |
              v                            v
         Base Context            Extracted Enrichment
              |                            |
              |                            v
              |                    Validation Layer
              |                            |
              v                            v
              +---------> Merge Engine <---+
                              |
                              v
                    Enriched MatchContext
    ```

    Key principles:
    - DB data is source of truth for xG, Elo, basic form
    - Agent data enriches injuries, news, H2H details
    - Validation MUST pass before merge
    - Graceful fallback to DB-only on agent failure
    """

    def __init__(
        self,
        use_agent: bool = True,
        provider: str = "claude",
        validate_strictly: bool = True
    ):
        """
        Initialize the enriched context builder.

        Args:
            use_agent: Whether to use AI agent for enrichment
            provider: LLM provider - "claude" (recommended), "gemini", or "openai"
            validate_strictly: Reject agent data that fails validation
        """
        self.use_agent = use_agent
        self.validate_strictly = validate_strictly

        # Initialize base builder (DB data)
        self.base_builder = ContextBuilderV2()

        # Initialize agent (if enabled)
        self.agent = ExtractionAgent(provider=provider) if use_agent else None

        # Validator
        self.validator = ExtractionValidator()

    def close(self):
        """Clean up resources."""
        self.base_builder.close()

    # ============================================================
    # MAIN ENTRY POINT
    # ============================================================

    def build_enriched_context(
        self,
        fixture_id: str,
        enrich_injuries: bool = True,
        enrich_h2h: bool = True,
        enrich_news: bool = False,
        force_agent: bool = False
    ) -> EnrichmentResult:
        """
        Build enriched match context.

        Args:
            fixture_id: Fixture ID (e.g., "2024-08-17_Arsenal_Wolves")
            enrich_injuries: Enrich with agent injury data
            enrich_h2h: Enrich with agent H2H data
            enrich_news: Enrich with agent news data
            force_agent: Force agent even if DB data is complete

        Returns:
            EnrichmentResult with context and metadata
        """
        # Step 1: Get base context from DB
        base_context = self.base_builder.build_context(fixture_id)

        if base_context is None:
            logger.error(f"Fixture not found: {fixture_id}")
            return EnrichmentResult(
                context=None,
                enrichment_applied=False,
                validation_errors=["Fixture not found"]
            )

        # Step 2: Decide if enrichment is needed/wanted
        if not self.use_agent and not force_agent:
            logger.info("Agent disabled, returning base context")
            return EnrichmentResult(
                context=base_context,
                enrichment_applied=False,
                enrichment_sources=["database"],
                enrichment_timestamp=datetime.now().isoformat()
            )

        # Step 3: Extract enrichment from agent
        result = EnrichmentResult(
            context=base_context,
            enrichment_applied=False,
            enrichment_sources=["database"],
            enrichment_timestamp=datetime.now().isoformat(),
            agent_data_used={
                "injuries_home": False,
                "injuries_away": False,
                "h2h": False,
                "news_home": False,
                "news_away": False
            }
        )

        try:
            # Get match details for agent
            home_team = base_context.home.identity.name
            away_team = base_context.away.identity.name
            league = base_context.league
            match_date = base_context.match_date

            # Update validator with match date
            self.validator.match_date = match_date

            # Enrich injuries
            if enrich_injuries:
                self._enrich_injuries(base_context, home_team, away_team, league, match_date, result)

            # Enrich H2H
            if enrich_h2h:
                self._enrich_h2h(base_context, home_team, away_team, league, match_date, result)

            # Enrich news (if enabled)
            if enrich_news:
                self._enrich_news(base_context, home_team, away_team, league, match_date, result)

            # Recalculate coverage score
            base_context.coverage_score = calculate_coverage_score(base_context)

            # Set enrichment quality
            used_count = sum(1 for v in result.agent_data_used.values() if v)
            total_count = len(result.agent_data_used)
            result.enrichment_quality = used_count / total_count if total_count > 0 else 0.0

            if used_count > 0:
                result.enrichment_applied = True
                result.enrichment_sources.append("agent")

        except Exception as e:
            logger.error(f"Enrichment failed, using base context: {e}")
            result.validation_errors.append(f"Enrichment error: {str(e)}")

        return result

    # ============================================================
    # INJURY ENRICHMENT
    # ============================================================

    def _enrich_injuries(
        self,
        context: MatchContext,
        home_team: str,
        away_team: str,
        league: str,
        match_date: date,
        result: EnrichmentResult
    ):
        """Enrich injury data from agent."""
        # Home team injuries
        try:
            home_injuries = self.agent.extract_injuries(home_team, league, match_date)
            home_validation = validate_extraction(
                home_injuries.get("injuries", []),
                "injuries",
                match_date
            )

            if home_validation.is_valid or not self.validate_strictly:
                merged_home = self._merge_injuries(
                    context.home.absences,
                    home_validation.data or home_injuries.get("injuries", [])
                )
                context.home.absences = merged_home
                result.agent_data_used["injuries_home"] = True
                logger.info(f"Enriched {home_team} injuries: {merged_home.total_missing} players")
            else:
                result.validation_errors.extend([f"Home injuries: {e}" for e in home_validation.errors])
                result.validation_warnings.extend(home_validation.warnings)

        except Exception as e:
            logger.warning(f"Failed to enrich home injuries: {e}")
            result.validation_errors.append(f"Home injuries extraction failed: {e}")

        # Away team injuries
        try:
            away_injuries = self.agent.extract_injuries(away_team, league, match_date)
            away_validation = validate_extraction(
                away_injuries.get("injuries", []),
                "injuries",
                match_date
            )

            if away_validation.is_valid or not self.validate_strictly:
                merged_away = self._merge_injuries(
                    context.away.absences,
                    away_validation.data or away_injuries.get("injuries", [])
                )
                context.away.absences = merged_away
                result.agent_data_used["injuries_away"] = True
                logger.info(f"Enriched {away_team} injuries: {merged_away.total_missing} players")
            else:
                result.validation_errors.extend([f"Away injuries: {e}" for e in away_validation.errors])
                result.validation_warnings.extend(away_validation.warnings)

        except Exception as e:
            logger.warning(f"Failed to enrich away injuries: {e}")
            result.validation_errors.append(f"Away injuries extraction failed: {e}")

    def _merge_injuries(
        self,
        db_absences: TeamAbsences,
        agent_injuries: List[Dict]
    ) -> TeamAbsences:
        """
        Merge DB injuries with agent-extracted injuries.

        Strategy:
        - Keep all DB injuries (source of truth)
        - Add agent injuries that aren't duplicates
        - Use agent data for additional context (is_key_player, expected_return)
        """
        # Start with existing DB injuries
        existing_names = {p.player_name.lower() for p in db_absences.players}
        merged_players = list(db_absences.players)

        attackers = db_absences.key_attackers_missing
        defenders = db_absences.key_defenders_missing

        for injury_dict in agent_injuries:
            player_name = injury_dict.get("player_name", "")

            # Skip duplicates
            if player_name.lower() in existing_names:
                continue

            # Determine position category
            position = injury_dict.get("position", "MID")

            # Create PlayerAbsence
            absence = PlayerAbsence(
                player_name=player_name,
                position=position,
                reason="injury",
                injury_type=injury_dict.get("injury_type"),
                impact_rating=None,
                xg_per90=None,
                xa_per90=None
            )

            merged_players.append(absence)
            existing_names.add(player_name.lower())

            # Update position counts
            if position == "FWD":
                attackers += 1
            elif position == "DEF":
                defenders += 1

        return TeamAbsences(
            total_missing=len(merged_players),
            key_attackers_missing=attackers,
            key_defenders_missing=defenders,
            total_offensive_impact=db_absences.total_offensive_impact,
            total_defensive_impact=db_absences.total_defensive_impact,
            players=merged_players
        )

    # ============================================================
    # H2H ENRICHMENT
    # ============================================================

    def _enrich_h2h(
        self,
        context: MatchContext,
        home_team: str,
        away_team: str,
        league: str,
        match_date: date,
        result: EnrichmentResult
    ):
        """Enrich head-to-head data from agent."""
        # Only enrich if DB H2H is weak
        if context.head_to_head.matches_played >= 3:
            logger.info("DB H2H sufficient, skipping agent enrichment")
            return

        try:
            h2h_data = self.agent.extract_head_to_head(home_team, away_team, league, match_date)
            h2h_dict = h2h_data.get("head_to_head")

            if not h2h_dict:
                return

            validation = validate_extraction(
                h2h_dict,
                "h2h",
                match_date,
                home_team=home_team,
                away_team=away_team
            )

            if validation.is_valid or not self.validate_strictly:
                merged_h2h = self._merge_h2h(context.head_to_head, h2h_dict)
                context.head_to_head = merged_h2h
                result.agent_data_used["h2h"] = True
                logger.info(f"Enriched H2H: {merged_h2h.matches_played} matches")
            else:
                result.validation_errors.extend([f"H2H: {e}" for e in validation.errors])
                result.validation_warnings.extend(validation.warnings)

        except Exception as e:
            logger.warning(f"Failed to enrich H2H: {e}")
            result.validation_errors.append(f"H2H extraction failed: {e}")

    def _merge_h2h(self, db_h2h: HeadToHead, agent_h2h: Dict) -> HeadToHead:
        """
        Merge DB H2H with agent-extracted H2H.

        Strategy:
        - If DB has more matches, keep DB
        - If agent has more matches, use agent (but verify)
        - Prefer agent for recent winner info
        """
        agent_matches = len(agent_h2h.get("last_5_meetings", []))
        db_matches = db_h2h.matches_played

        # If DB has good data, keep it
        if db_matches >= agent_matches and db_matches >= 3:
            return db_h2h

        # Use agent data
        return HeadToHead(
            home_wins=agent_h2h.get("home_team_wins", db_h2h.home_wins),
            draws=agent_h2h.get("draws", db_h2h.draws),
            away_wins=agent_h2h.get("away_team_wins", db_h2h.away_wins),
            avg_total_goals=agent_h2h.get("total_goals", 0) / max(agent_matches, 1) if agent_matches > 0 else db_h2h.avg_total_goals,
            home_avg_goals=db_h2h.home_avg_goals,  # Keep DB calculation
            away_avg_goals=db_h2h.away_avg_goals,
            matches_played=max(agent_matches, db_matches)
        )

    # ============================================================
    # NEWS ENRICHMENT
    # ============================================================

    def _enrich_news(
        self,
        context: MatchContext,
        home_team: str,
        away_team: str,
        league: str,
        match_date: date,
        result: EnrichmentResult
    ):
        """Enrich news/storyline data from agent."""
        # News is added to data_warnings as additional context
        try:
            home_news = self.agent.extract_team_news(home_team, league, match_date)
            news_data = home_news.get("news")

            if news_data:
                storylines = news_data.get("key_storylines", [])
                morale = news_data.get("morale_indicator")

                if morale and morale in ["low", "crisis"]:
                    context.data_warnings.append(f"[Agent] {home_team} morale: {morale}")

                for storyline in storylines[:2]:  # Max 2 storylines
                    context.data_warnings.append(f"[Agent] {home_team}: {storyline}")

                result.agent_data_used["news_home"] = True

        except Exception as e:
            logger.warning(f"Failed to enrich home news: {e}")

        try:
            away_news = self.agent.extract_team_news(away_team, league, match_date)
            news_data = away_news.get("news")

            if news_data:
                storylines = news_data.get("key_storylines", [])
                morale = news_data.get("morale_indicator")

                if morale and morale in ["low", "crisis"]:
                    context.data_warnings.append(f"[Agent] {away_team} morale: {morale}")

                for storyline in storylines[:2]:
                    context.data_warnings.append(f"[Agent] {away_team}: {storyline}")

                result.agent_data_used["news_away"] = True

        except Exception as e:
            logger.warning(f"Failed to enrich away news: {e}")


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def build_enriched_context(
    fixture_id: str,
    use_agent: bool = True,
    provider: str = "claude"
) -> EnrichmentResult:
    """
    Build enriched match context with one function call.

    Args:
        fixture_id: Fixture ID
        use_agent: Whether to use AI agent
        provider: LLM provider - "claude" (recommended), "gemini", or "openai"

    Returns:
        EnrichmentResult
    """
    builder = EnrichedContextBuilder(use_agent=use_agent, provider=provider)
    try:
        return builder.build_enriched_context(fixture_id)
    finally:
        builder.close()


def get_context_with_fallback(fixture_id: str) -> Optional[MatchContext]:
    """
    Get match context with graceful fallback.

    Tries enriched context first, falls back to base context on any error.

    Args:
        fixture_id: Fixture ID

    Returns:
        MatchContext or None
    """
    try:
        result = build_enriched_context(fixture_id)
        return result.context
    except Exception as e:
        logger.warning(f"Enriched context failed, trying base: {e}")

        # Fallback to base context
        from src.analysis.context_builder_v2 import build_match_context
        return build_match_context(fixture_id)


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Enriched Context Builder")
    parser.add_argument("fixture_id", help="Fixture ID to test")
    parser.add_argument("--no-agent", action="store_true", help="Disable agent enrichment")
    parser.add_argument("--provider", default="claude", choices=["claude", "gemini", "openai"],
                        help="LLM provider (default: claude)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    print(f"\nBuilding enriched context for: {args.fixture_id}")
    print(f"Provider: {args.provider}")
    print("=" * 60)

    builder = EnrichedContextBuilder(
        use_agent=not args.no_agent,
        provider=args.provider
    )

    try:
        result = builder.build_enriched_context(args.fixture_id)

        if result.context:
            ctx = result.context
            print(f"\n{ctx.home.identity.name} vs {ctx.away.identity.name}")
            print(f"Date: {ctx.match_date}")
            print(f"League: {ctx.league}")
            print(f"\nCoverage Score: {ctx.coverage_score}%")
            print(f"Enrichment Applied: {result.enrichment_applied}")
            print(f"Enrichment Quality: {result.enrichment_quality:.1%}")
            print(f"Sources: {result.enrichment_sources}")

            print(f"\nHome Injuries: {ctx.home.absences.total_missing}")
            for p in ctx.home.absences.players[:5]:
                print(f"  - {p.player_name} ({p.position}): {p.injury_type}")

            print(f"\nAway Injuries: {ctx.away.absences.total_missing}")
            for p in ctx.away.absences.players[:5]:
                print(f"  - {p.player_name} ({p.position}): {p.injury_type}")

            print(f"\nH2H Matches: {ctx.head_to_head.matches_played}")

            if result.validation_errors:
                print(f"\nValidation Errors: {len(result.validation_errors)}")
                for e in result.validation_errors[:5]:
                    print(f"  - {e}")

            if result.validation_warnings:
                print(f"\nValidation Warnings: {len(result.validation_warnings)}")
                for w in result.validation_warnings[:5]:
                    print(f"  - {w}")
        else:
            print("Failed to build context")
            print(f"Errors: {result.validation_errors}")

    finally:
        builder.close()
