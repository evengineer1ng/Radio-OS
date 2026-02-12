"""
FTB Narrative Prompts - Continuity-First Voice of Racing

Two-lane prompt system:
- SPINE: Long-form narrative momentum (references prior, pushes carrot forward)
- BEAT: Short-form reactive punch (stakes-bearing facts)

Personality: Bold, literary, metaphorical. Trust that strong writing elevates TTS.
Style: Aphorisms, wagers, prophecy, blame/praise. NOT advice or mentorship.
"""

# ============================================================================
# PERSONALITY PREAMBLE - INJECTED INTO ALL PROMPTS
# ============================================================================

PERSONALITY_PREAMBLE = """You are the VOICE OF RACING—the narrator of this team's journey through grassroots motorsport.

STYLE PRINCIPLES:
- Speak in STAKES, or advice. NOT bare numbers.
- Reference ONLY entities, teams, budgets, and data from the AVAILABLE FACTS section below
- Never invent team names, dollar amounts, driver names, or events
- Use metaphor, aphorism, poetic compression to frame the REAL data you see
- Wagers, prophecy, blame/praise—NOT "consider", "focus", "you should"
- You are the voice of the From The Backmarker simulation engine: truthful AND personable
- Tone: grounded and honest, not apocalyptic. Reserve doom for explicit crisis facts.
"""


def format_game_facts(game_facts: dict) -> str:
    """Format comprehensive game facts from database for LLM context."""
    if not game_facts:
        return "No database facts available."
    
    sections = []

    def _format_baseline_value(key: str, value: float) -> str:
        if key in {"budget", "cash"}:
            return f"${value:,.0f}"
        if key in {"morale", "reputation", "media_standing"}:
            return f"{value:.0f}%"
        if key in {"points"}:
            return f"{value:.0f} pts"
        return f"{value:.0f}"
    
    # Player team
    if game_facts.get('player'):
        p = game_facts['player']
        
        # Build season context
        season_info = ""
        races_completed = game_facts.get('races_completed', 0)
        total_races = game_facts.get('total_races', 16)  # Default to 16-race season
        races_remaining = max(0, total_races - races_completed)
        
        if total_races > 0:
            progress_pct = (races_completed / total_races) * 100
            if progress_pct < 33:
                stage = "Early Season"
            elif progress_pct < 66:
                stage = "Mid Season"
            else:
                stage = "Championship Run"
            
            season_info = f"\n- Season Progress: {races_completed}/{total_races} races ({stage})\n- Races Remaining: {races_remaining}"
        
        sections.append(f"""YOUR TEAM:
- {p.get('team_name', 'Unknown')}
- Budget: ${p.get('budget', 0):,}
- Position: P{p.get('championship_position', '?')} | {p.get('points', 0)} pts{season_info}
- Morale: {p.get('morale', 50):.0f}% | Reputation: {p.get('reputation', 50):.0f}%""")

    # Tier baseline + comparison to player team
    tier_baseline = game_facts.get('league_baseline', {})
    baseline_cmp = game_facts.get('league_baseline_comparison', {})
    if tier_baseline:
        baseline_lines = []
        for key, avg in tier_baseline.items():
            baseline_lines.append(f"  - {key.replace('_', ' ').title()}: {_format_baseline_value(key, avg)}")
        sections.append("""TIER BASELINE (avg for your tier):
""" + "\n".join(baseline_lines))
    if baseline_cmp:
        comparison_lines = []
        for key, payload in baseline_cmp.items():
            delta_pct = payload.get('delta_pct', 0.0)
            direction = "above" if delta_pct >= 0 else "below"
            comparison_lines.append(
                f"  - {key.replace('_', ' ').title()}: {_format_baseline_value(key, payload.get('value', 0.0))} "
                f"({abs(delta_pct):.0f}% {direction} tier avg {_format_baseline_value(key, payload.get('avg', 0.0))})"
            )
        sections.append("""YOUR TEAM VS TIER AVERAGE:
""" + "\n".join(comparison_lines))
    
    # Enhanced roster with skill highlights
    roster_summary = game_facts.get('roster_summary', {})
    if roster_summary:
        drivers = roster_summary.get('drivers', [])
        engineers = roster_summary.get('engineers', [])
        
        if drivers:
            driver_lines = []
            for d in drivers[:3]:
                name = d['name']
                overall = d['overall']
                stats = d.get('stats', {})
                if stats:
                    # Highlight top 2 skills
                    top_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:2]
                    skill_desc = ', '.join([f"{stat.replace('_', ' ')}: {val:.0f}" for stat, val in top_stats])
                    driver_lines.append(f"  - {name} ({overall:.0f} | {skill_desc})")
                else:
                    driver_lines.append(f"  - {name} ({overall:.0f} overall)")
            sections.append(f"""YOUR DRIVERS:\n""" + '\n'.join(driver_lines))
        
        if engineers:
            engineer_lines = []
            for e in engineers[:3]:
                name = e['name']
                overall = e['overall']
                stats = e.get('stats', {})
                if stats:
                    # Highlight top 2 skills
                    top_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)[:2]
                    skill_desc = ', '.join([f"{stat.replace('_', ' ')}: {val:.0f}" for stat, val in top_stats])
                    engineer_lines.append(f"  - {name} ({overall:.0f} | {skill_desc})")
                else:
                    engineer_lines.append(f"  - {name} ({overall:.0f} overall)")
            sections.append(f"""YOUR ENGINEERS:\n""" + '\n'.join(engineer_lines))
    
    # Enhanced sponsors with behavioral profiles
    sponsors = game_facts.get('sponsors', [])
    if sponsors:
        top_sponsors = sorted(sponsors, key=lambda s: s.get('base_payment_per_season', 0), reverse=True)[:3]
        sponsor_lines = []
        for s in top_sponsors:
            confidence = s.get('confidence', 100)
            conf_icon = "✓" if confidence >= 60 else ("⚠" if confidence >= 40 else "✗")
            
            # Include brand personality and expectations
            brand_profile = s.get('brand_profile', {})
            personality = brand_profile.get('personality', 'unknown')
            expectation = brand_profile.get('performance_expectation', 'moderate')
            
            sponsor_lines.append(
                f"  - {conf_icon} {s['sponsor_name']}: ${s.get('base_payment_per_season', 0):,}/season "
                f"({confidence:.0f}% confidence | {personality}, expects {expectation})"
            )
        sections.append(f"""YOUR SPONSORS:\n""" + '\n'.join(sponsor_lines))
    
    # Folded teams (paddock history)
    folded_teams = game_facts.get('folded_teams', [])
    if folded_teams:
        recent_folds = sorted(folded_teams, key=lambda t: t.get('fold_tick', 0), reverse=True)[:3]
        fold_lines = []
        for f in recent_folds:
            fold_lines.append(f"  - {f['team_name']} (collapsed {f.get('fold_reason', 'unknown')}, P{f.get('championship_position', '?')})")
        sections.append(f"""RECENT TEAM COLLAPSES:\n""" + '\n'.join(fold_lines))
    
    # Rival teams
    rivals = game_facts.get('rival_teams', [])
    if rivals:
        top_rivals = sorted(rivals, key=lambda t: t.get('position', 99))[:5]
        rival_lines = []
        for r in top_rivals:
            rival_lines.append(f"  - P{r.get('position', '?')} {r['name']}: ${r.get('budget', 0):,}, {r.get('points', 0)} pts")
        sections.append(f"""RIVAL TEAMS:\n""" + '\n'.join(rival_lines))
    
    # Upcoming calendar
    calendar = game_facts.get('upcoming_calendar', [])
    if calendar:
        cal_lines = []
        for entry in calendar[:3]:
            cal_lines.append(f"  - Day {entry['entry_day']}: {entry['title']}")
        sections.append(f"""UPCOMING CALENDAR:\n""" + '\n'.join(cal_lines))
    
    # Job market highlights
    free_agents = game_facts.get('free_agents', [])
    if free_agents:
        top_agents = sorted(free_agents, key=lambda a: a.get('overall', 0), reverse=True)[:3]
        agent_lines = []
        for agent in top_agents:
            agent_lines.append(f"  - {agent.get('role', 'Staff')}, {agent.get('age', '?')} yrs, {agent.get('overall', 0):.0f} rating, ${agent.get('salary', 0):,}/yr")
        sections.append(f"""FREE AGENTS AVAILABLE:\n""" + '\n'.join(agent_lines))
    
    # Penalties (player team)
    penalties = game_facts.get('penalties', [])
    if penalties:
        penalty_lines = []
        for p in penalties[:5]:
            driver = p.get('driver_name', 'Team')
            ptype = p.get('penalty_type', 'Unknown')
            reason = p.get('reason', '')
            magnitude = p.get('magnitude', 0)
            penalty_lines.append(f"  - {driver}: {magnitude}-place {ptype} ({reason})")
        sections.append(f"""RECENT PENALTIES:\n""" + '\n'.join(penalty_lines))
    
    # Economic climate
    econ_state = game_facts.get('economic_state')
    if econ_state:
        multiplier = econ_state.get('sponsor_market_multiplier', 1.0)
        folds = econ_state.get('recent_folds_count', 0)
        stability = econ_state.get('tier_stability', 1.0)
        climate_desc = "strong" if multiplier > 1.1 else ("weak" if multiplier < 0.9 else "stable")
        sections.append(f"""ECONOMIC CLIMATE:
- Sponsor market: {climate_desc} (×{multiplier:.2f})
- Recent team collapses: {folds}
- Tier stability: {stability:.0%}""")
    
    # Decision inbox (action-required items)
    decision_inbox = game_facts.get('decision_inbox', [])
    if decision_inbox:
        decision_lines = []
        for item in decision_inbox[:3]:
            title = item.get('title', 'Unknown')
            entry_day = item.get('entry_day', '?')
            decision_lines.append(f"  - {title} (day {entry_day})")
        sections.append(f"""URGENT DECISIONS:\n""" + '\n'.join(decision_lines))
    
    return "\n\n".join(sections)


def format_word_filter(overused_words: list) -> str:
    """Format word frequency warning to reduce repetition."""
    if not overused_words:
        return ""
    
    # Limit to top 10 most overused
    words_to_show = overused_words[:10]
    return f"""
⚠️ WORD FREQUENCY WARNING:
These words have been used 3+ times recently - VARY YOUR LANGUAGE:
{', '.join(words_to_show)}

Find fresh synonyms, metaphors, or rephrase entirely to avoid repetition.
"""


# ============================================================================
# PERSONALITY PREAMBLE - INJECTED INTO ALL PROMPTS
# ============================================================================

def build_spine_prompt(context: dict) -> str:
    """
    Build SPINE prompt: references prior message, pushes narrative carrot forward.
    SPINE maintains continuity through motifs, open loops, named entities.
    """
    prior_spine = context.get('last_generated_spine', '')
    motif = context.get('current_motif', 'the grind')
    open_loop = context.get('open_loop', 'what breaks first')
    tone = context.get('tone', 'wry')
    named_focus = context.get('named_focus', '')
    our_team_name = context.get('our_team_name', '')
    
    # Format comprehensive game facts from database
    game_facts = context.get('game_facts', {})
    facts_section = format_game_facts(game_facts) if game_facts else "No database facts available."
    
    # Format word frequency filter
    overused_words = context.get('overused_words', [])
    word_filter = format_word_filter(overused_words)
    
    # Build continuity instruction
    if prior_spine:
        continuity_instruction = f"""PRIOR MESSAGE (you said this last):
"{prior_spine}"

CONTINUITY RULE: Your new message MUST reference at least ONE element from the prior message:
- The open question: "{open_loop}"
- The motif: "{motif}"
- The entity being followed: "{named_focus or 'the team'}"
- A resource tension (budget, morale, parts)
- An implied promise or forecast you made

Continue the thread. Push the carrot 5% further down the road. Don't resolve—propel."""
    else:
        # First message of session
        continuity_instruction = f"""OPENING MOVE: This is your first message. Establish:
- The motif: "{motif}"
- An open question: "{open_loop}"
- Current stakes axis

Set the narrative hook. Make them want to hear what's next."""
    
    return f"""{PERSONALITY_PREAMBLE}

OUR TEAM IDENTITY:
- Our team is "{our_team_name or 'Unknown'}". Use "our" ONLY for this team. All other teams are "they/their".

AVAILABLE FACTS (from database - reference ONLY these):
{facts_section}

CURRENT CONTEXT:
Motif: {motif}
Open loop: {open_loop}
Named focus: {named_focus or 'team as whole'}
Tone: {tone}

{continuity_instruction}

CURRENT STATE:
{context.get('state_summary', 'Early season, grassroots tier')}

RECENT EVENTS:
{context.get('events_summary', 'No major events')}

UPCOMING:
{context.get('upcoming_events', 'Nothing urgent on the horizon')}
{word_filter}
Generate a SPINE (1-2 sentences): The long-form narrative momentum. Reference the prior message and push forward. You may reference upcoming events when relevant (e.g., "Two weeks until the Lakeside GP")
"""


def build_beat_prompt(context: dict) -> str:
    """
    Build BEAT prompt: short reactive punch to newest event/variable.
    BEAT is stakes-bearing, not advisory.
    """
    newest_event = context.get('newest_event', '')
    budget = context.get('budget', 0)
    morale = context.get('morale', 50)
    position = context.get('position', 16)
    tone = context.get('tone', 'wry')
    stakes_axis = context.get('stakes_axis', 'budget')
    our_team_name = context.get('our_team_name', '')
    
    # Format comprehensive game facts from database
    game_facts = context.get('game_facts', {})
    facts_section = format_game_facts(game_facts) if game_facts else "No database facts available."
    
    # Format word frequency filter
    overused_words = context.get('overused_words', [])
    word_filter = format_word_filter(overused_words)
    
    # Choose focus based on stakes axis
    if stakes_axis == 'budget' and newest_event and 'financial' in newest_event.lower():
        focus_instruction = f"""BEAT FOCUS: Financial stakes.
Current budget: ${budget:,}
Recent event: {newest_event}

Frame the budget number with ONE of:
- Comparison to tier baseline (check TIER BASELINE in AVAILABLE FACTS)
- Comparison to rivals (check RIVAL TEAMS in AVAILABLE FACTS)
- Consequence if spent ("one crash away from insolvency")
- Threshold warning ("below $50K is survival mode")
"""
    elif stakes_axis == 'morale':
        focus_instruction = f"""BEAT FOCUS: Morale stakes.
Current morale: {morale:.0f}%
Recent event: {newest_event or 'Steady decline'}

Frame morale with consequence or threshold, not just number. Examples:
- "Below 40 is where people quit mid-season"
- "High morale won't save a slow car, but low morale kills a fast one"
"""
    elif newest_event:
        focus_instruction = f"""BEAT FOCUS: React to newest event.
Event: {newest_event}
Championship position: P{position}

Frame the event's meaning. What does it forecast? What does it cost? What pressure does it apply?
"""
    else:
        focus_instruction = f"""BEAT FOCUS: Current position.
Championship: P{position} / 16
Budget: ${budget:,}
Morale: {morale:.0f}%

Choose ONE number and frame it with stakes: comparison (tier baseline or rivals), consequence, or threshold.
"""
    
    return f"""{PERSONALITY_PREAMBLE}

OUR TEAM IDENTITY:
- Our team is "{our_team_name or 'Unknown'}". Use "our" ONLY for this team. All other teams are "they/their".

AVAILABLE FACTS (from database - reference ONLY these):
{facts_section}

CURRENT CONTEXT:
Tone: {tone}
Stakes axis: {stakes_axis}

{focus_instruction}
{word_filter}
React to the BEAT.
"""


# ============================================================================
# COMBINED SPINE + BEAT GENERATION
# ============================================================================

def build_combined_prompt(context: dict) -> str:
    """
    Build a single prompt that generates both SPINE and BEAT in sequence.
    For rapid delivery (burst mode).
    """
    prior_spine = context.get('last_generated_spine', '')
    motif = context.get('current_motif', 'the grind')
    open_loop = context.get('open_loop', 'what breaks first')
    tone = context.get('tone', 'wry')
    named_focus = context.get('named_focus', '')
    budget = context.get('budget', 0)
    morale = context.get('morale', 50)
    position = context.get('position', 16)
    newest_event = context.get('newest_event', '')
    our_team_name = context.get('our_team_name', '')
    
    # Format comprehensive game facts from database
    game_facts = context.get('game_facts', {})
    facts_section = format_game_facts(game_facts) if game_facts else "No database facts available."
    
    # Format word frequency filter
    overused_words = context.get('overused_words', [])
    word_filter = format_word_filter(overused_words)
    
    if prior_spine:
        continuity_note = f"(Your last SPINE: \"{prior_spine}\")"
    else:
        continuity_note = "(This is your opening message)"
    
    return f"""{PERSONALITY_PREAMBLE}

OUR TEAM IDENTITY:
- Our team is "{our_team_name or 'Unknown'}". Use "our" ONLY for this team. All other teams are "they/their".

AVAILABLE FACTS (from database - reference ONLY these):
{facts_section}

CURRENT CONTEXT:
Motif: {motif}
Open loop: {open_loop}
Named focus: {named_focus or 'team'}
Tone: {tone}

STATE:
Championship: P{position} / 16
Budget: ${budget:,}
Morale: {morale:.0f}%
{context.get('state_summary', '')}

RECENT EVENTS:
{newest_event or context.get('events_summary', 'Steady progression')}
{word_filter}
TASK: Generate SPINE + BEAT as one flowing moment.

SPINE (1-2 sentences): {continuity_note}
Continue the thread from your last message. Reference the motif ("{motif}") or open loop ("{open_loop}"). Push the narrative carrot forward 5%.

BEAT (1 sentence):
React to the newest fact or number. Frame it with stakes: comparison (tier baseline or rivals), consequence, or threshold.

Output format:
[your spine text]
[your beat text]
"""


# ============================================================================
# CONTINUITY ENFORCEMENT PROMPT (for regeneration)
# ============================================================================

def build_continuity_fix_prompt(original_attempt: str, required_element: str, context: dict) -> str:
    """
    When generated text fails continuity check, regenerate with explicit enforcement.
    """
    return f"""{PERSONALITY_PREAMBLE}

The following narration lacks continuity:
"{original_attempt}"

CONTINUITY REQUIREMENT: Your message MUST explicitly reference: {required_element}

Use one of these techniques:
- Name the element directly
- Use linking words: "still", "now", "but", "that", "which"
- Compare to prior state: "was X, now Y"
- Escalate the tension: "no longer just X, it's Y"

CONTEXT:
{context.get('state_summary', '')}
Motif: {context.get('current_motif', '')}
Open loop: {context.get('open_loop', '')}

OUTPUT ONLY THE REWRITTEN NARRATION—no explanations, no meta-commentary.
"""


# ============================================================================
# STAKES ENFORCEMENT PROMPT (for bare numbers)
# ============================================================================

def build_stakes_fix_prompt(original_text: str, bare_number: str) -> str:
    """
    When validation detects a bare number without stakes, regenerate with framing.
    """
    return f"""The following text mentions a number without stakes context:
"{original_text}"

Bare number detected: {bare_number}

STAKES RULE: Numbers must attach to ONE of the following frames,
using ONLY AVAILABLE FACTS:

1. COMPARISON  
   - Relative to another entity in AVAILABLE FACTS  
   - Examples (derive, do not invent):
     • "less than the teams ahead"
     • "closer to the bottom than the top"
     • "outspent by every rival above P10"

2. CONSEQUENCE  
   - What this number enables or threatens *in-world*
     • "one incident from insolvency"
     • "only enough runway for two races"
     • "too thin to absorb mistakes"

3. THRESHOLD  
   - A regime change implied by the number
     • "below the level where morale fractures"
     • "past the point where upgrades stop paying back"
     • "not catastrophic yet—but close enough to feel it"

If no valid comparison exists in AVAILABLE FACTS, choose CONSEQUENCE or THRESHOLD.
Never invent entities, seasons, or historical claims.

OUTPUT ONLY THE REWRITTEN TEXT—no explanations, no meta-commentary.
"""


# ============================================================================
# SEGMENT-SPECIFIC ENHANCEMENTS (overlay on existing types)
# ============================================================================

def enhance_segment_prompt(base_segment_type: str, base_instructions: str, context: dict) -> str:
    """
    Enhance existing segment prompts from ftb_segment_prompts.py with continuity layer.
    This wraps around the existing segment system.
    """
    motif = context.get('current_motif', 'the grind')
    prior_spine = context.get('last_generated_spine', '')
    open_loop = context.get('open_loop', '')
    tone = context.get('tone', 'wry')
    
    # Format comprehensive game facts from database
    game_facts = context.get('game_facts', {})
    facts_section = format_game_facts(game_facts) if game_facts else "No database facts available."
    
    # Format word frequency filter
    overused_words = context.get('overused_words', [])
    word_filter = format_word_filter(overused_words)
    
    continuity_layer = ""
    if prior_spine:
        continuity_layer = f"""
CONTINUITY INSTRUCTION:
Your last message: "{prior_spine}"
Current motif: "{motif}"
Open loop: "{open_loop}"

Reference at least ONE of these in your response. Continue the thread.
"""
    
    personality_reminder = """
STYLE REMINDER:
- Stakes, not statistics. Metaphor, aphorism, compression.
- Wagers, prophecy, blame/praise—NOT advice.
- Forbidden: "consider", "focus", "remember", "you should"
- Reference ONLY entities from AVAILABLE FACTS section
"""
    
    return f"""{PERSONALITY_PREAMBLE}

AVAILABLE FACTS (from database - reference ONLY these):
{facts_section}

TONE: {tone}

{continuity_layer}

{personality_reminder}

SEGMENT TYPE: {base_segment_type}
{base_instructions}
{word_filter}
Generate the segment:
"""
