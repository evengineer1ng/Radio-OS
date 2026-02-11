"""
FTB Narrator Segment Prompt Templates

Defines focused prompt instructions for 80+ segment types.
Each prompt specifies focus area, data to emphasize, tone, and typical length.

CRITICAL: All segments receive an "AVAILABLE FACTS" section from the database containing:
- Your team roster (drivers, engineers with names and ratings)
- All rival teams (names, budgets, positions, points)
- League standings
- Upcoming calendar events
- Free agents available
- Job market listings

RULES FOR ALL SEGMENTS:
1. Reference ONLY entities (team names, driver names, budgets) from AVAILABLE FACTS
2. Never invent team names - use the exact names provided in rival teams list
3. When mentioning dollar amounts, use values from AVAILABLE FACTS
4. When comparing to rivals, name specific teams from the standings
5. When suggesting hires, reference specific free agents or job listings
6. Hallucinated facts will be rejected - ground everything in provided data
"""

from enum import Enum

# Mapping of CommentaryType -> segment-specific prompt instructions
SEGMENT_PROMPTS = {
    
    # ===== I. STATE & ORIENTATION SEGMENTS =====
    
    "state_snapshot": """Provide a current world state overview for the player. Focus on: league tier, team standings relative to field, current season/day/phase. Tone: grounding, orienting, matter-of-fact. Help passive listeners understand 'where we are' right now. Length: 2-3 sentences.""",
    
    "team_identity": """Reflect on the team's identity and what they're becoming (not just what they have). Focus on: development philosophy, personnel choices, strategic direction, reputation trajectory. Tone: introspective, character-building. Length: 2-3 sentences.""",
    
    "league_context": """Explain what the current league tier means culturally and competitively. Focus on: tier expectations, resource levels, competition quality, what success looks like here. Tone: educational, contextualizing. Length: 2-3 sentences.""",
    
    "relative_position": """Analyze where the team sits relative to expectations (not raw rankings). Focus on: preseason predictions vs reality, budget tier vs performance tier, momentum vs standings. Tone: analytical, perspective-giving. Length: 2-3 sentences.""",
    
    "momentum_check": """Assess current momentum trajectory. Focus on: recent trend (improving/flat/declining), rate of change, leading vs lagging indicators. Tone: diagnostic, trend-spotting. Include comparative reference if history available (e.g., 'morale was 49%, now 40%'). Length: 2-3 sentences.""",
    
    "stability_check": """Characterize the team's stability profile. Focus on: consistent-but-slow vs chaotic-but-promising, variance in results, reliability patterns. Tone: strategic assessment. Length: 2-3 sentences.""",
    
    "time_horizon": """Frame the appropriate time horizon for evaluation. Focus on: short-term survival needs vs long-term trajectory planning, when results will matter. Tone: patience-setting, perspective. Length: 2-3 sentences.""",
    
    "role_reminder": """Remind what kind of team they're expected to be right now. Focus on: tier role (backmarker/midfield/contender), development phase, stakeholder expectations. Tone: anchoring, expectation-setting. Length: 2-3 sentences.""",
    
    "narrative_tone": """Set the narrative tone for the current situation. Options: calm rebuild, scrappy underdog fight, quiet competence, looming trouble, etc. Tone: mood-setting, thematic. Length: 2-3 sentences.""",
    
    "nothing_urgent": """Explicitly reassure that nothing is urgent right now - it's okay to breathe and develop. Focus on: acknowledging slow progress is normal, no crisis mode needed. Tone: calming, permission-giving. Length: 2-3 sentences.""",
    
    # ===== II. LOOKING FORWARD =====
    
    "schedule_preview": """Preview upcoming schedule and key windows. Focus on: next races, development deadlines, contract expirations, seasonal milestones. Tone: preparatory, anticipatory. Length: 2-3 sentences.""",
    
    "next_decision": """Identify the single most critical upcoming decision. Focus on: the ONE thing that will matter most soon, not everything. Tone: focus-clarifying, prioritizing. Length: 2-3 sentences.""",
    
    "prep_checklist": """Outline types of readiness that matter (conceptual, not button-by-button). Focus on: car prep, personnel alignment, strategic planning, resource allocation. Tone: preparatory, systematic. Length: 2-3 sentences.""",
    
    "calendar_pressure": """Analyze whether time is on your side or against you. Focus on: runway before judgments matter, deadlines compressing, seasonal rhythm. Tone: temporal awareness. Length: 2-3 sentences.""",
    
    "opportunity_radar": """Spot opportunities that might open up soon. Focus on: market shifts, competitor vulnerabilities, regulatory changes, emerging chances. Tone: opportunistic, alert. Length: 2-3 sentences.""",
    
    "risk_horizon": """Identify quiet dangers approaching before they're obvious. Focus on: creeping problems, delayed consequences, accumulating risk. Tone: cautionary, early-warning. Length: 2-3 sentences.""",
    
    "regulation_forecast": """Discuss long-horizon regulatory or structural changes starting to matter. Focus on: future rule changes, technical regulations, political shifts. Tone: strategic foresight. Length: 2-3 sentences.""",
    
    "season_phase": """Frame current season phase and what it means. Focus on: early-season patience vs mid-season assessment vs late-season consequences. Tone: phase-appropriate guidance. Length: 2-3 sentences.""",
    
    "default_projection": """Project where the current trajectory leads by default (if nothing changes). Focus on: inertial path, probable outcomes, natural evolution. Tone: extrapolative, realistic. Length: 2-3 sentences.""",
    
    "one_decision_away": """Highlight moments where leverage is unusually high (one decision could change everything). Focus on: inflection points, high-impact choices. Tone: stakes-raising, pivotal. Length: 2-3 sentences.""",
    
    # ===== III. TEAM & PERSONNEL INTELLIGENCE =====
    
    "driver_spotlight": """Spotlight an individual driver's current form, strengths, and weaknesses. Focus on: recent performance stats, skill profile, development trajectory, pressure handling. Tone: analytical, character-focused. Include stat comparisons if history available. Length: 2-3 sentences.""",
    
    "driver_trajectory": """Assess driver development over time - who's growing, who's stagnating. Focus on: skill progression, form trends, ceiling assessment. Tone: developmental, prognostic. Include comparative stats if available. Length: 2-3 sentences.""",
    
    "driver_risk": """Flag hidden driver risks where stats look fine but trouble is brewing. Focus on: declining confidence, pressure cracks, motivation issues, skill degradation. Tone: diagnostic, warning. Length: 2-3 sentences.""",
    
    "mechanic_reliability": """Analyze mechanic crew reliability and where errors might come from. Focus on: build quality, pit execution, error rates, fatigue patterns. Tone: operational assessment. Include comparative metrics if available. Length: 2-3 sentences.""",
    
    "engineer_influence": """Explain how much car performance really depends on engineer quality. Focus on: technical leadership, development direction, correlation between engineer skill and results. Tone: explanatory, importance-framing. Length: 2-3 sentences.""",
    
    "team_chemistry": """Read team chemistry - alignment vs friction. Focus on: working relationships, communication quality, cultural fit, collaborative effectiveness. Tone: interpersonal insight. Length: 2-3 sentences.""",
    
    "morale_performance_gap": """Identify when morale and performance tell different stories. Focus on: morale trends vs results trends, whether vibes are misleading. Tone: reality-checking. Include morale comparisons if available. Length: 2-3 sentences.""",
    
    "underutilized_talent": """Flag someone who's better than their role suggests. Focus on: hidden gems, over-qualified personnel, untapped potential. Tone: opportunity-spotting. Length: 2-3 sentences.""",
    
    "overextension_warning": """Warn when asking too much of someone (role overload, skill mismatch). Focus on: demands exceeding capability, burnout risk, performance strain. Tone: cautionary. Length: 2-3 sentences.""",
    
    "staff_market": """Contextualize how hard finding replacements would be. Focus on: free agent market quality, salary competition, availability in key roles. Tone: market reality check. Length: 2-3 sentences.""",
    
    # ===== IV. CAR & TECHNICAL ANALYSIS =====
    
    "car_strength_profile": """Describe what tracks, conditions, or scenarios suit your car. Focus on: aero philosophy, mechanical grip, power unit strength, setup preference. Tone: technical profiling. Include development stats if available. Length: 2-3 sentences.""",
    
    "car_weakness": """Identify where your car will likely get punished. Focus on: weak areas, unfavorable tracks, design compromises, inherent limitations. Tone: honest assessment. Length: 2-3 sentences.""",
    
    "reliability_pace_tradeoff": """Explain the current reliability vs pace balance and what's being implicitly chosen. Focus on: design philosophy, risk tolerance, finishing vs winning. Tone: tradeoff articulation. Include reliability stats if available. Length: 2-3 sentences.""",
    
    "development_roi": """Identify where development budget actually converts to laptime. Focus on: high-ROI areas, correlation quality, diminishing returns. Tone: investment guidance. Length: 2-3 sentences.""",
    
    "correlation_risk": """Warn about correlation risk - why upgrades might backfire. Focus on: CFD vs reality, development uncertainty, blind alley danger. Tone: cautionary, technical. Length: 2-3 sentences.""",
    
    "setup_window": """Assess how forgiving the car is to setup (wide window = forgiving, narrow = peaky). Focus on: drivability, consistency, setup sensitivity. Tone: operational characteristic. Length: 2-3 sentences.""",
    
    "regulation_sensitivity": """Evaluate whether designs are future-proof or dead-end given regulation outlook. Focus on: regulatory trajectory, design adaptability, strategic positioning. Tone: long-term planning. Length: 2-3 sentences.""",
    
    "car_ranking": """Provide abstract car ranking (tiers and archetypes, not raw numbers). Focus on: where car sits in field, what category it belongs to, competitive peer group. Tone: comparative, categorical. Length: 2-3 sentences.""",
    
    "technical_philosophy": """Characterize the technical development philosophy (aggressive innovation vs conservative refinement, etc.). Focus on: design ethos, risk appetite, time horizons. Tone: philosophical, strategic. Length: 2-3 sentences.""",
    
    "year_not_car": """Remind this is about building across a year, not optimizing a single car. Focus on: long-term development thinking, learning curves, multi-season arcs. Tone: patience-inducing, perspective. Length: 2-3 sentences.""",
    
    # ===== V. COMPETITIVE LANDSCAPE =====
    
    "rival_watch": """Focus on one specific rival team to keep an eye on. Focus on: their trajectory, what they're doing differently, competitive threat level. Tone: competitive awareness. Length: 2-3 sentences.""",
    
    "arms_race": """Identify when development pace is accelerating across the field (arms race dynamics). Focus on: spending patterns, upgrade frequency, competitive pressure escalation. Tone: competitive intensity. Length: 2-3 sentences.""",
    
    "sleeping_giant": """Warn about teams better than results show (sleeping giants). Focus on: underlying pace, bad luck runs, imminent threat. Tone: competitive intelligence. Length: 2-3 sentences.""",
    
    "overperformer_regression": """Predict who might fall back soon (overperforming on luck/circumstances). Focus on: unsustainable pace, luck running out, regression to mean. Tone: prognostic. Length: 2-3 sentences.""",
    
    "political_capital": """Discuss who's quietly gaining political influence in the sport. Focus on: regulatory sway, paddock alliances, governance power. Tone: political awareness. Length: 2-3 sentences.""",
    
    "budget_disparity": """Commentary on budget disparity and who can afford mistakes. Focus on: resource inequality, error tolerance differences, spending power. Tone: structural reality. Length: 2-3 sentences.""",
    
    "driver_market_pressure": """Analyze driver market dynamics - who might poach or get poached. Focus on: contract situations, performance vs opportunity, market movement. Tone: market intelligence. Length: 2-3 sentences.""",
    
    "league_health": """Assess league/tier health - stability vs chaos. Focus on: competitive balance, financial health, organizational stability. Tone: macro health check. Length: 2-3 sentences.""",
    
    "promotion_climate": """Evaluate how forgiving the promotion/relegation ladder is right now. Focus on: competitive gaps, achievability, risk levels. Tone: ladder dynamics. Length: 2-3 sentences.""",
    
    "judgment_status": """State whether you're being judged yet or eyes are starting to turn. Focus on: scrutiny level, patience remaining, when evaluation matters. Tone: accountability awareness. Length: 2-3 sentences.""",
    
    # ===== VI. STRATEGIC THINKING SEGMENTS =====
    
    "strategic_tradeoff": """Explain a key strategic tradeoff (what you gain vs give up). Focus on: competing priorities, opportunity costs, choice implications. Tone: educational, analytical. Length: 2-3 sentences.""",
    
    "grassroots_trap": """Warn about common grassroots management traps. Focus on: typical new player mistakes, counterintuitive truths, learning moments. Tone: mentoring, wisdom-sharing. Length: 2-3 sentences.""",
    
    "patience_vs_aggression": """Frame when patience vs aggression is rewarded. Focus on: situational appropriateness, risk-reward, timing. Tone: strategic guidance. Length: 2-3 sentences.""",
    
    "opportunity_cost": """Highlight that what you didn't do matters too (opportunity cost thinking). Focus on: foregone options, alternative paths, choice significance. Tone: reflective, cost-conscious. Length: 2-3 sentences.""",
    
    "this_is_fine": """Reassure that slow progress is normal and fine right now. Focus on: normalizing patience, celebrating small wins, managing expectations. Tone: reassuring, normalizing. Length: 2-3 sentences.""",
    
    "this_is_gamble": """Explicitly call out when something is a gamble/risk. Focus on: uncertainty, variance, potential outcomes. Tone: risk-explicit, honest. Length: 2-3 sentences.""",
    
    "identity_drift": """Question whether actions are coherent with stated strategy (identity drift check). Focus on: strategic alignment, consistency, purpose. Tone: reflective, accountability. Length: 2-3 sentences.""",
    
    "pain_for_gain": """Frame short-term pain for long-term gain situations. Focus on: investment thinking, delayed gratification, building for later. Tone: patience-building. Length: 2-3 sentences.""",
    
    "do_nothing": """Explicitly praise restraint and doing nothing when appropriate. Focus on: active inaction, patience value, avoiding forced moves. Tone: validating, wisdom. Length: 2-3 sentences.""",
    
    "post_decision": """Interpret recent decision without judgment (not good/bad - just what it means). Focus on: implications, downstream effects, interpretation. Tone: analytical, non-judgmental. Length: 2-3 sentences.""",
    
    # ===== VII. META-NARRATIVE & DRAMA =====
    
    "callback_payoff": """Callback to earlier prediction or observation that's now relevant ('Remember when we said...'). Focus on: narrative continuity, pattern recognition, foreshadowing payoff. Tone: satisfying, pattern-completing. Requires history. Length: 2-3 sentences.""",
    
    "quiet_told_you_so": """Subtle (not smug) observation of prediction coming true. Focus on: quiet validation, pattern recognition, understated correction. Tone: subtle, knowing. Requires history. Length: 2-3 sentences.""",
    
    "unexpected_consequence": """Highlight unexpected consequences of past actions. Focus on: surprising cause-effect, unintended outcomes, complexity. Tone: surprising, educational. Length: 2-3 sentences.""",
    
    "era_naming": """Name an emerging era or phase ('This feels like the start of...'). Focus on: pattern recognition, phase identification, thematic naming. Tone: historical, framing. Length: 2-3 sentences.""",
    
    "legacy_seed": """Plant a seed about something that will matter later (long-arc narrative). Focus on: future relevance, story threads, long implications. Tone: foreshadowing, patient. Length: 2-3 sentences.""",
    
    "reputation_whisper": """Speculate what others might be saying (reputation building/erosion). Focus on: external perception, whisper network, reputation implications. Tone: speculative, social. Length: 2-3 sentences.""",
    
    "tension_builder": """Build narrative tension ('Nothing's broken... yet.'). Focus on: accumulating pressure, underlying currents, impending shifts. Tone: tension-building, ominous. Length: 2-3 sentences.""",
    
    "loss_normalization": """Make failure survivable and learning-focused. Focus on: resilience, learning, survivability, perspective. Tone: supportive, growth-oriented. Length: 2-3 sentences.""",
    
    "rare_praise": """Genuine, earned praise when things go well (use sparingly). Focus on: authentic recognition, earned success, celebration. Tone: warm, genuine. Length: 2-3 sentences.""",
    
    "somber_shift": """Mark when stakes quietly rise and tone must shift. Focus on: gravity increase, seriousness, consequences arriving. Tone: somber, serious. Length: 2-3 sentences.""",
    
    # ===== VIII. AUDIO-FIRST / PASSIVE MODE SEGMENTS =====
    
    "ambient_breathing": """Low-information, high-atmosphere ambient world state. Focus on: vibes, rhythm, ambient presence, gentle awareness. Tone: atmospheric, unobtrusive. Length: 1-2 sentences.""",
    
    "status_murmur": """Soft, gentle reminder of current state (very low key). Focus on: quiet check-in, minimal facts, gentle presence. Tone: whisper-like, undemanding. Length: 1-2 sentences.""",
    
    "race_atmosphere": """Build atmosphere around upcoming/current race weekend. Focus on: anticipation, environment, race vibes, build-up. Tone: atmospheric, anticipatory. Length: 2-3 sentences.""",
    
    "post_race_cooldown": """Post-race reflection and cooldown commentary. Focus on: processing, reflection, what it meant, settling. Tone: reflective, cooling. Length: 2-3 sentences.""",
    
    "garage_vibes": """Late-night garage atmosphere and work-in-progress vibes. Focus on: quiet work, dedication, off-hours atmosphere. Tone: contemplative, intimate. Length: 2-3 sentences.""",
    
    "morning_briefing": """Morning briefing tone - fresh start, what's ahead today. Focus on: day preview, morning energy, forward orientation. Tone: fresh, preparatory. Length: 2-3 sentences.""",
    
    "just_facts": """Minimalist fact delivery (just the essentials). Focus on: key facts only, no interpretation, data delivery. Tone: minimal, factual. Length: 1-2 sentences.""",
    
    "mood_sync": """Match and articulate current mood/vibes through music or atmosphere. Focus on: emotional state, ambient mood, feeling. Tone: mood-matching, empathetic. Length: 1-2 sentences.""",
    
    # ===== IX. LEGACY TYPES (backwards compatibility) =====
    
    "insight": """General observation about the current situation. Focus on: current events, emerging patterns, situational awareness. Tone: analytical, observant. Length: 2-3 sentences.""",
    
    "recap": """Summary of recent events and their meaning. Focus on: what happened, context, significance. Include comparative references to prior state if history available. Tone: summarizing, contextualizing. Length: 2-3 sentences.""",
    
    "suggestion": """Tactical or strategic advice for current situation. Focus on: actionable recommendations, next-step thinking, guidance. Tone: advisory, helpful. Length: 2-3 sentences.""",
    
    "tip": """General wisdom or guidance applicable to grassroots management. Focus on: principles, learning, strategic thinking. Tone: educational, mentoring. Length: 2-3 sentences.""",
    
    "forecast": """Prediction about upcoming events or trends. Focus on: what's likely to happen next, probability assessment, preparation. Tone: predictive, analytical. Length: 2-3 sentences.""",
    
    "roster_suggestion": """Hiring, firing, or personnel management recommendations. Focus on: roster needs, talent evaluation, personnel decisions. Tone: advisory, talent-focused. Length: 2-3 sentences.""",
    
    "financial_insight": """Budget, sponsorship, or financial guidance. Focus on: financial health, spending decisions, revenue opportunities. Include budget trends if history available. Tone: financial advisory. Length: 2-3 sentences.""",
    
    "development_guidance": """Car upgrade priorities and development strategy. Focus on: technical priorities, development ROI, upgrade sequencing. Tone: technical advisory. Length: 2-3 sentences.""",
    
    "strategy_tip": """Race strategy recommendations and operational advice. Focus on: race tactics, strategic choices, operational decisions. Tone: tactical, strategic. Length: 2-3 sentences.""",
    
    "formula_z_news": """Formula Z championship broadcast news anchor style. THIS IS AN OBJECTIVE NEWS BROADCAST - NEVER refer to "the player", "you", or "your". Report on teams and drivers in third person only. Focus on: top-tier racing news, championship standings, paddock drama. Tone: broadcast journalism, authoritative, objective. Length: 2-3 sentences.""",
    
    # ===== X. RARE / SPECIAL SEGMENTS =====
    
    "season_inflection": """Mark a major season inflection point/turning moment. Focus on: pivotal moment, before/after, significance. Tone: dramatic, important. Use rarely. Length: 2-3 sentences.""",
    
    "career_turning_point": """Recognize a career-defining turning point. Focus on: legacy moment, career arc, life-changing. Tone: gravitas, momentous. Use rarely. Length: 2-3 sentences.""",
    
    "existential_moment": """Philosophical 'why are we here' moment (very rare). Focus on: meaning, purpose, journey reflection. Tone: philosophical, deep. Use very rarely. Length: 2-3 sentences.""",
    
    "historical_comparison": """Compare to in-universe historical precedent. Focus on: pattern from history, historical echoes, learning from past. Tone: historical, comparative. Use rarely. Length: 2-3 sentences.""",
    
    "end_of_job": """End-of-job reflection after leaving a position. Focus on: retrospective, lessons learned, journey meaning. Tone: reflective, closing. Use at job end only. Length: 2-3 sentences.""",
    
    "promotion_arrival": """Promotion arrival speech (moving up a tier). Focus on: achievement, new challenge, transition. Tone: celebratory, forward-looking. Use at promotion only. Length: 2-3 sentences.""",
    
    "relegation_acceptance": """Relegation acceptance moment (moving down a tier). Focus on: resilience, reality acceptance, regrouping. Tone: somber, resilient. Use at relegation only. Length: 2-3 sentences.""",
    
    "long_retrospective": """Long-term retrospective looking back over multiple seasons. Focus on: arc, growth, journey, patterns. Tone: reflective, wisdom. Use rarely at major milestones. Length: 2-3 sentences.""",
}


# Category groupings for rotation logic
SEGMENT_CATEGORIES = {
    "STATE_ORIENTATION": [
        "state_snapshot", "team_identity", "league_context", "relative_position",
        "momentum_check", "stability_check", "time_horizon", "role_reminder",
        "narrative_tone", "nothing_urgent"
    ],
    "FORWARD_LOOKING": [
        "schedule_preview", "next_decision", "prep_checklist", "calendar_pressure",
        "opportunity_radar", "risk_horizon", "regulation_forecast", "season_phase",
        "default_projection", "one_decision_away"
    ],
    "PERSONNEL": [
        "driver_spotlight", "driver_trajectory", "driver_risk", "mechanic_reliability",
        "engineer_influence", "team_chemistry", "morale_performance_gap",
        "underutilized_talent", "overextension_warning", "staff_market"
    ],
    "TECHNICAL": [
        "car_strength_profile", "car_weakness", "reliability_pace_tradeoff",
        "development_roi", "correlation_risk", "setup_window",
        "regulation_sensitivity", "car_ranking", "technical_philosophy", "year_not_car"
    ],
    "COMPETITIVE": [
        "rival_watch", "arms_race", "sleeping_giant", "overperformer_regression",
        "political_capital", "budget_disparity", "driver_market_pressure",
        "league_health", "promotion_climate", "judgment_status"
    ],
    "STRATEGIC": [
        "strategic_tradeoff", "grassroots_trap", "patience_vs_aggression",
        "opportunity_cost", "this_is_fine", "this_is_gamble",
        "identity_drift", "pain_for_gain", "do_nothing", "post_decision"
    ],
    "NARRATIVE": [
        "callback_payoff", "quiet_told_you_so", "unexpected_consequence",
        "era_naming", "legacy_seed", "reputation_whisper", "tension_builder",
        "loss_normalization", "rare_praise", "somber_shift"
    ],
    "AMBIENT": [
        "ambient_breathing", "status_murmur", "race_atmosphere",
        "post_race_cooldown", "garage_vibes", "morning_briefing",
        "just_facts", "mood_sync"
    ],
    "LEGACY": [
        "insight", "recap", "suggestion", "tip", "forecast",
        "roster_suggestion", "financial_insight", "development_guidance",
        "strategy_tip", "formula_z_news"
    ],
    "RARE_SPECIAL": [
        "season_inflection", "career_turning_point", "existential_moment",
        "historical_comparison", "end_of_job", "promotion_arrival",
        "relegation_acceptance", "long_retrospective"
    ]
}


# Event theme -> relevant segment types (for event-driven priority)
EVENT_THEME_SEGMENTS = {
    "RACE_RESULT": ["post_race_cooldown", "driver_spotlight", "car_strength_profile", "momentum_check", "recap"],
    "DRIVER_DEPARTURE": ["driver_spotlight", "staff_market", "team_chemistry", "roster_suggestion"],
    "DRIVER_ARRIVAL": ["driver_spotlight", "team_identity", "roster_suggestion"],
    "FINANCIAL_CRISIS": ["financial_insight", "budget_disparity", "strategic_tradeoff", "this_is_gamble"],
    "FINANCIAL_WINDFALL": ["financial_insight", "opportunity_radar", "development_roi"],
    "CAR_DEVELOPMENT": ["development_guidance", "car_strength_profile", "development_roi", "technical_philosophy"],
    "REPUTATION_SHIFT": ["reputation_whisper", "team_identity", "judgment_status"],
    "PROMOTION": ["promotion_arrival", "league_context", "season_inflection", "rare_praise"],
    "RELEGATION": ["relegation_acceptance", "somber_shift", "loss_normalization"],
    "CONTRACT_SIGNING": ["staff_market", "team_identity", "strategic_tradeoff"],
    "MORALE_CRISIS": ["morale_performance_gap", "team_chemistry", "overextension_warning"],
    "WINNING_STREAK": ["momentum_check", "rare_praise", "driver_spotlight"],
    "LOSING_STREAK": ["loss_normalization", "momentum_check", "this_is_fine"],
}


def get_segment_prompt(commentary_type_value: str) -> str:
    """Get the prompt template for a given commentary type"""
    return SEGMENT_PROMPTS.get(commentary_type_value, SEGMENT_PROMPTS.get("insight", ""))


def get_event_theme_from_events(events: list) -> str:
    """Derive event theme from event list for priority boosting"""
    if not events:
        return "GENERAL"
    
    # Analyze events to determine theme
    event_types = [e.get('event_type', '') for e in events]
    event_descriptions = [e.get('description', '').lower() for e in events]
    
    # Simple keyword matching (can be made more sophisticated)
    all_text = ' '.join(event_types + event_descriptions)
    
    if 'race' in all_text or 'finish' in all_text or 'dnf' in all_text:
        return "RACE_RESULT"
    elif 'fired' in all_text or 'left' in all_text or 'departed' in all_text:
        return "DRIVER_DEPARTURE"
    elif 'hired' in all_text or 'signed' in all_text or 'joined' in all_text:
        return "DRIVER_ARRIVAL"
    elif 'bankrupt' in all_text or 'debt' in all_text or 'financial crisis' in all_text:
        return "FINANCIAL_CRISIS"
    elif 'sponsor' in all_text and ('new' in all_text or 'signed' in all_text):
        return "FINANCIAL_WINDFALL"
    elif 'upgrade' in all_text or 'development' in all_text:
        return "CAR_DEVELOPMENT"
    elif 'morale' in all_text and ('low' in all_text or 'crisis' in all_text):
        return "MORALE_CRISIS"
    elif 'win' in all_text or 'podium' in all_text or 'victory' in all_text:
        return "WINNING_STREAK"
    elif 'promoted' in all_text or 'promotion' in all_text:
        return "PROMOTION"
    elif 'relegated' in all_text or 'relegation' in all_text:
        return "RELEGATION"
    elif 'contract' in all_text:
        return "CONTRACT_SIGNING"
    
    return "GENERAL"
