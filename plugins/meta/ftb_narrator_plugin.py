"""
FTB Narrator Meta Plugin (Universal Contract v2.0)

Provides continuous Jarvis-style narrator for From The Backmarker.
Implements the universal meta plugin contract with streaming capability.

Architecture:
- Reads game state from ftb_state_db.py (SQLite) asynchronously
- Generates player-focused commentary via LLM
- Frames events in relation to player journey
- Calm, analytical tone (not frantic play-by-play)
- Completely decoupled from game simulation
"""

import threading
import time
import random
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import sys
import faulthandler
import traceback
from collections import deque

# Keep last N debug breadcrumbs in memory
FTB_NARRATOR_BREADCRUMBS = deque(maxlen=500)

def _crumb(msg: str):
    ts = time.strftime("%H:%M:%S")
    FTB_NARRATOR_BREADCRUMBS.append(f"[{ts}] {msg}")

def _dump_breadcrumbs(prefix="[FTB Narrator]"):
    try:
        print(f"{prefix} --- LAST {len(FTB_NARRATOR_BREADCRUMBS)} BREADCRUMBS ---")
        for line in list(FTB_NARRATOR_BREADCRUMBS):
            print(f"{prefix} {line}")
    except Exception:
        pass

# Dump Python tracebacks on fatal errors (segfaults, aborts)
try:
    faulthandler.enable(all_threads=True)
    # Optional: periodically dump stack traces to help catch hangs
    # faulthandler.dump_traceback_later(30, repeat=True)
except Exception:
    pass

# Main thread exceptions
def _sys_excepthook(exc_type, exc, tb):
    print("[FTB Narrator] UNCAUGHT EXCEPTION (sys.excepthook):", exc)
    traceback.print_exception(exc_type, exc, tb)
    _dump_breadcrumbs()
sys.excepthook = _sys_excepthook

# Thread exceptions (Python 3.8+)
if hasattr(threading, "excepthook"):
    _orig = threading.excepthook
    def _thread_excepthook(args):
        print(f"[FTB Narrator] UNCAUGHT THREAD EXCEPTION in {args.thread.name}: {args.exc_value}")
        traceback.print_exception(args.exc_type, args.exc_value, args.exc_traceback)
        _dump_breadcrumbs()
        _orig(args)
    threading.excepthook = _thread_excepthook

try:
    from bookmark import MetaPluginBase
except ImportError:
    from abc import ABC, abstractmethod
    class MetaPluginBase(ABC):
        @abstractmethod
        def initialize(self, runtime_context, cfg, mem): pass
        @abstractmethod
        def shutdown(self): pass
        def process_input(self, input_data): return []
        def supports_streaming(self): return False
        def get_streaming_handle(self): return None
        def supports_delegation(self): return False

# Import state database
try:
    from plugins import ftb_state_db
except ImportError:
    print("[FTB Narrator] Warning: Could not import ftb_state_db")
    ftb_state_db = None

# Import segment prompts
try:
    from plugins.meta import ftb_segment_prompts
except ImportError:
    print("[FTB Narrator] Warning: Could not import ftb_segment_prompts")
    ftb_segment_prompts = None

# Import broadcast commentary generator
try:
    from plugins import ftb_broadcast_commentary
except ImportError:
    print("[FTB Narrator] Warning: Could not import ftb_broadcast_commentary")
    ftb_broadcast_commentary = None

# Import race day module
try:
    from plugins import ftb_race_day
except ImportError:
    print("[FTB Narrator] Warning: Could not import ftb_race_day")
    ftb_race_day = None


# ============================================================================
# NARRATOR TYPES
# ============================================================================

class CommentaryType(Enum):
    """Types of narrator commentary - 80+ segment types for variety"""
    
    # ===== I. STATE & ORIENTATION SEGMENTS =====
    STATE_SNAPSHOT = "state_snapshot"                     # Current world state overview
    TEAM_IDENTITY = "team_identity"                       # Who you are becoming
    LEAGUE_CONTEXT = "league_context"                     # What tier means culturally
    RELATIVE_POSITION = "relative_position"               # Where you sit vs expectations
    MOMENTUM_CHECK = "momentum_check"                     # Trending up/flat/down
    STABILITY_CHECK = "stability_check"                   # Stable-but-slow vs chaotic-but-promising
    TIME_HORIZON = "time_horizon"                         # Short-term vs long-term framing
    ROLE_REMINDER = "role_reminder"                       # What kind of team you're expected to be
    NARRATIVE_TONE = "narrative_tone"                     # Calm rebuild, scrappy fight, etc.
    NOTHING_URGENT = "nothing_urgent"                     # Explicitly okay to breathe
    
    # ===== BROADCAST COMMENTARY (NEW) =====
    BROADCAST_RACE_START = "broadcast_race_start"         # Race start commentary
    BROADCAST_OVERTAKE = "broadcast_overtake"             # Overtake commentary
    BROADCAST_CRASH = "broadcast_crash"                   # Incident commentary
    BROADCAST_DNF = "broadcast_dnf"                       # Retirement commentary
    BROADCAST_FASTEST_LAP = "broadcast_fastest_lap"       # Fastest lap commentary
    BROADCAST_FINAL_LAP = "broadcast_final_lap"           # Race finish commentary
    BROADCAST_LAP_UPDATE = "broadcast_lap_update"         # Periodic lap update
    
    # ===== II. LOOKING FORWARD =====
    SCHEDULE_PREVIEW = "schedule_preview"                 # Races, development windows
    NEXT_DECISION = "next_decision"                       # The thing that will matter
    PREP_CHECKLIST = "prep_checklist"                     # Types of readiness that matter
    CALENDAR_PRESSURE = "calendar_pressure"               # Time on your side or against you
    OPPORTUNITY_RADAR = "opportunity_radar"               # Things that might open up
    RISK_HORIZON = "risk_horizon"                         # Quiet dangers approaching
    REGULATION_FORECAST = "regulation_forecast"           # Long-horizon structural stuff
    SEASON_PHASE = "season_phase"                         # Early patience vs late consequences
    DEFAULT_PROJECTION = "default_projection"             # Where trajectory leads by default
    ONE_DECISION_AWAY = "one_decision_away"               # Where leverage is unusually high
    
    # ===== III. TEAM & PERSONNEL INTELLIGENCE =====
    DRIVER_SPOTLIGHT = "driver_spotlight"                 # Individual driver strengths/flaws
    DRIVER_TRAJECTORY = "driver_trajectory"               # Who's growing, stagnating
    DRIVER_RISK = "driver_risk"                           # Stats look fine but imply trouble
    MECHANIC_RELIABILITY = "mechanic_reliability"         # Where errors might come from
    ENGINEER_INFLUENCE = "engineer_influence"             # How much car depends on them
    TEAM_CHEMISTRY = "team_chemistry"                     # Alignment vs friction
    MORALE_PERFORMANCE_GAP = "morale_performance_gap"     # Are vibes lying to you
    UNDERUTILIZED_TALENT = "underutilized_talent"         # Someone better than their role
    OVEREXTENSION_WARNING = "overextension_warning"       # Asking too much of someone
    STAFF_MARKET = "staff_market"                         # How hard replacements are to find
    
    # ===== IV. CAR & TECHNICAL ANALYSIS =====
    CAR_STRENGTH_PROFILE = "car_strength_profile"         # What tracks/conditions suit you
    CAR_WEAKNESS = "car_weakness"                         # Where you'll get punished
    RELIABILITY_PACE_TRADEOFF = "reliability_pace_tradeoff"  # What you're implicitly choosing
    DEVELOPMENT_ROI = "development_roi"                   # Where money converts to performance
    CORRELATION_RISK = "correlation_risk"                 # Why upgrades might backfire
    SETUP_WINDOW = "setup_window"                         # How forgiving your car is
    REGULATION_SENSITIVITY = "regulation_sensitivity"     # Future-proof vs dead-end designs
    CAR_RANKING = "car_ranking"                           # Tiers and archetypes
    TECHNICAL_PHILOSOPHY = "technical_philosophy"         # What kind of car you're building
    YEAR_NOT_CAR = "year_not_car"                         # Long-term thinking cue
    
    # ===== V. COMPETITIVE LANDSCAPE =====
    RIVAL_WATCH = "rival_watch"                           # One specific team to watch
    ARMS_RACE = "arms_race"                               # Development pace accelerating
    SLEEPING_GIANT = "sleeping_giant"                     # Teams better than results show
    OVERPERFORMER_REGRESSION = "overperformer_regression" # Who might fall back soon
    POLITICAL_CAPITAL = "political_capital"               # Who's gaining influence quietly
    BUDGET_DISPARITY = "budget_disparity"                 # Who can afford mistakes
    DRIVER_MARKET_PRESSURE = "driver_market_pressure"     # Who might poach or get poached
    LEAGUE_HEALTH = "league_health"                       # Stability vs chaos in tier
    PROMOTION_CLIMATE = "promotion_climate"               # How forgiving the ladder is
    JUDGMENT_STATUS = "judgment_status"                   # Not being judged yet / eyes turning
    
    # ===== VI. STRATEGIC THINKING SEGMENTS =====
    STRATEGIC_TRADEOFF = "strategic_tradeoff"             # What you gain vs give up
    GRASSROOTS_TRAP = "grassroots_trap"                   # Patterns new players fall into
    PATIENCE_VS_AGGRESSION = "patience_vs_aggression"     # When each is rewarded
    OPPORTUNITY_COST = "opportunity_cost"                 # What you didn't do matters too
    THIS_IS_FINE = "this_is_fine"                         # Normalize slow progress
    THIS_IS_GAMBLE = "this_is_gamble"                     # Make risk explicit
    IDENTITY_DRIFT = "identity_drift"                     # Are your actions coherent
    PAIN_FOR_GAIN = "pain_for_gain"                       # Short-term pain/long-term gain
    DO_NOTHING = "do_nothing"                             # Explicitly praise restraint
    POST_DECISION = "post_decision"                       # Not judgment - interpretation
    
    # ===== VII. META-NARRATIVE & DRAMA =====
    CALLBACK_PAYOFF = "callback_payoff"                   # Remember when we said...
    QUIET_TOLD_YOU_SO = "quiet_told_you_so"               # Subtle, not smug
    UNEXPECTED_CONSEQUENCE = "unexpected_consequence"     # Things went sideways
    ERA_NAMING = "era_naming"                             # This feels like the start of...
    LEGACY_SEED = "legacy_seed"                           # Things that matter later
    REPUTATION_WHISPER = "reputation_whisper"             # What people might be saying
    TENSION_BUILDER = "tension_builder"                   # Nothing's broken... yet
    LOSS_NORMALIZATION = "loss_normalization"             # Make failure survivable
    RARE_PRAISE = "rare_praise"                           # When things genuinely go well
    SOMBER_SHIFT = "somber_shift"                         # When stakes quietly rise
    
    # ===== VIII. AUDIO-FIRST / PASSIVE MODE SEGMENTS =====
    AMBIENT_BREATHING = "ambient_breathing"               # Low-info, high-vibe filler
    STATUS_MURMUR = "status_murmur"                       # Soft state reminders
    RACE_ATMOSPHERE = "race_atmosphere"                   # Race weekend atmosphere build
    POST_RACE_COOLDOWN = "post_race_cooldown"             # Post-race reflection
    GARAGE_VIBES = "garage_vibes"                         # Late-night garage vibes
    MORNING_BRIEFING = "morning_briefing"                 # Morning briefing tone
    JUST_FACTS = "just_facts"                             # Minimalist facts segment
    MOOD_SYNC = "mood_sync"                               # Music-driven mood sync
    
    # ===== IX. LEGACY TYPES (backwards compat) =====
    INSIGHT = "insight"                                   # General observation
    RECAP = "recap"                                       # Summary of recent events
    SUGGESTION = "suggestion"                             # Tactical/strategic advice
    TIP = "tip"                                           # General wisdom/guidance
    FORECAST = "forecast"                                 # Prediction about upcoming
    ROSTER_SUGGESTION = "roster_suggestion"               # Hiring/firing recommendations
    FINANCIAL_INSIGHT = "financial_insight"               # Budget/sponsorship guidance
    DEVELOPMENT_GUIDANCE = "development_guidance"         # Car upgrade priorities
    STRATEGY_TIP = "strategy_tip"                         # Race strategy recommendations
    FORMULA_Z_NEWS = "formula_z_news"                     # Formula Z championship broadcast
    
    # ===== X. RARE / SPECIAL SEGMENTS =====
    SEASON_INFLECTION = "season_inflection"               # Season turning point
    CAREER_TURNING_POINT = "career_turning_point"         # Career recognition
    EXISTENTIAL_MOMENT = "existential_moment"             # Why are we here
    HISTORICAL_COMPARISON = "historical_comparison"       # In-universe history
    END_OF_JOB = "end_of_job"                             # End-of-job reflection
    PROMOTION_ARRIVAL = "promotion_arrival"               # Promotion speech
    RELEGATION_ACCEPTANCE = "relegation_acceptance"       # Relegation moment
    LONG_RETROSPECTIVE = "long_retrospective"             # Long-term retrospective


@dataclass
class SegmentHistoryEntry:
    """Tracks when a segment type was last used and comparative state"""
    last_used_tick: int = 0
    last_game_day: int = 0
    use_count: int = 0
    last_state_snapshot: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NarratorContext:
    """Persistent context the narrator maintains"""
    player_team: str
    current_day: int = 0
    current_season: int = 1
    current_tick: int = 0
    active_tab: Optional[str] = None
    
    # Recent narrative threads
    last_topics_discussed: deque = field(default_factory=lambda: deque(maxlen=20))
    recent_events_seen: deque = field(default_factory=lambda: deque(maxlen=50))
    
    # NEW: Word frequency tracking for avoiding repetition
    recent_generated_texts: deque = field(default_factory=lambda: deque(maxlen=10))  # Last 10 generated texts
    
    # Player state snapshot
    player_budget: int = 0
    player_championship_position: int = 0
    player_points: int = 0
    player_morale: float = 50.0
    player_reputation: float = 0.0
    player_tier: int = 1
    
    # Streak tracking
    races_since_points: int = 0
    consecutive_dnfs: int = 0
    races_since_win: int = 0
    
    # Thematic threads
    active_themes: List[str] = field(default_factory=list)
    open_story_loops: List[str] = field(default_factory=list)
    
    # NEW: Segment variety & history tracking
    segment_history: Dict[str, Any] = field(default_factory=dict)  # CommentaryType.value -> SegmentHistoryEntry dict
    
    # NEW: Event-driven priority
    urgent_event_pending: bool = False
    event_theme: Optional[str] = None  # E.g., 'FINANCIAL_CRISIS', 'DRIVER_DEPARTURE', 'RACE_RESULT'
    urgent_segments_generated: int = 0
    
    # CONTINUITY-FIRST: Show Bible fields
    current_motif: str = "quiet climb"  # Persistent motif rotated every 5-7 segments
    open_loop: str = ""  # Unresolved tension or question
    named_focus: str = ""  # Entity being followed (driver, rival, sponsor, engineer)
    stakes_axis: str = "budget"  # One of: budget, morale, pace, reliability, politics
    tone: str = "wry"  # One of: wry, hungry, grim, electric
    last_generated_spine: str = ""  # Full text of last Spine message
    last_generated_beat: str = ""  # Full text of last Beat message
    claim_tags: deque = field(default_factory=lambda: deque(maxlen=20))  # Semantic claims made recently
    segments_since_motif_change: int = 0  # Track when to rotate motif


@dataclass
class EventObservation:
    """Filtered view of events since last narrator cycle"""
    high_priority_events: List[Any]
    medium_priority_events: List[Any]
    low_priority_events: List[Any]
    player_team_events: List[Any]
    world_events: List[Any]
    
    def has_significant_events(self) -> bool:
        return len(self.high_priority_events) > 0 or len(self.player_team_events) > 0


# ============================================================================
# CLAIM TRACKER - "SAID-IT TAX" SYSTEM
# ============================================================================

class ClaimTracker:
    """
    Tracks semantic claims the narrator has made recently.
    Enforces the "said-it tax": repetition requires escalation, resolution, or new metaphor.
    """
    
    def __init__(self, context: NarratorContext):
        self.context = context
        
        # Keywords that signal escalation/resolution (stakes-bearing language)
        self.escalation_words = {
            'now', 'still', 'worse', 'better', 'more', 'less', 'half', 'double',
            'threshold', 'breaking point', 'tipping point', 'critical',
            'consequence', 'result', 'outcome', 'lead to', 'means',
            'comparison', 'versus', 'than', 'compared to',
            'if', 'unless', 'when', 'until', 'before'
        }
    
    def extract_claims(self, text: str) -> List[str]:
        """Extract semantic claim tags from generated text"""
        tags = []
        text_lower = text.lower()
        
        # Financial claims
        if 'budget' in text_lower or '$' in text or 'money' in text_lower or 'spend' in text_lower:
            if 'tight' in text_lower or 'strain' in text_lower or 'low' in text_lower or 'critical' in text_lower:
                tags.append('budget_tight')
            elif 'healthy' in text_lower or 'comfortable' in text_lower:
                tags.append('budget_healthy')
            else:
                tags.append('budget_mentioned')
        
        # Morale claims
        if 'morale' in text_lower:
            if 'low' in text_lower or 'fragile' in text_lower or 'drop' in text_lower:
                tags.append('morale_low')
            elif 'high' in text_lower or 'strong' in text_lower:
                tags.append('morale_high')
            else:
                tags.append('morale_mentioned')
        
        # Performance claims
        if any(word in text_lower for word in ['pace', 'speed', 'lap time', 'performance']):
            tags.append('performance_check')
        
        if any(word in text_lower for word in ['position', 'standing', 'championship']):
            tags.append('standings_check')
        
        # Temporal/patience claims
        if any(word in text_lower for word in ['early', 'patience', 'long term', 'season']):
            tags.append('patience_early_season')
        
        # Risk/caution claims
        if any(word in text_lower for word in ['careful', 'cautious', 'risk', 'avoid', 'careful']):
            tags.append('caution_advised')
        
        # Parts/reliability
        if any(word in text_lower for word in ['parts', 'reliability', 'dnf', 'crash']):
            tags.append('reliability_concern')
        
        return tags
    
    def has_claimed_recently(self, tag: str) -> bool:
        """Check if narrator has made this claim in last 20 segments"""
        return tag in self.context.claim_tags
    
    def escalates_or_resolves(self, tag: str, new_text: str) -> bool:
        """Check if new text escalates or resolves a prior claim"""
        text_lower = new_text.lower()
        
        # Look for escalation keywords
        has_escalation = any(word in text_lower for word in self.escalation_words)
        
        # Look for comparison language (numbers with context)
        has_comparison = any(phrase in text_lower for phrase in [
            'was', 'now', 'from', 'to', 'half of', 'twice', 'more than', 'less than'
        ])
        
        # Look for consequence/threshold language
        has_stakes = any(phrase in text_lower for phrase in [
            'means', 'consequence', 'result', 'lead to', 'risk of', 
            'threshold', 'breaking point', 'where', 'is where'
        ])
        
        return has_escalation or has_comparison or has_stakes
    
    def validate_repetition(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validate that text doesn't repeat claims without escalation.
        Returns (is_valid, list_of_violations)
        """
        new_tags = self.extract_claims(text)
        violations = []
        
        for tag in new_tags:
            if self.has_claimed_recently(tag):
                # Tag was used recently - check for escalation
                if not self.escalates_or_resolves(tag, text):
                    violations.append(f"Repeated claim without escalation: {tag}")
        
        return (len(violations) == 0, violations)
    
    def record_claims(self, text: str):
        """Record claims from finalized segment"""
        tags = self.extract_claims(text)
        for tag in tags:
            if tag not in self.context.claim_tags:
                self.context.claim_tags.append(tag)


# ============================================================================
# SHOW BIBLE MANAGER - MOTIF / LOOP / FOCUS ROTATION
# ============================================================================

class ShowBibleManager:
    """
    Manages the narrator's "show bible": motifs, open loops, named focus, stakes axis, tone.
    Rotates these elements to maintain freshness while preserving continuity.
    """
    
    MOTIF_POOL = [
        "survival era",
        "thin ice",
        "one crash away",
        "quiet climb",
        "the grind",
        "proving ground",
        "uphill battle",
        "margin game",
        "patience test",
        "grassroots gambit"
    ]
    
    TONE_POOL = ["wry", "hungry", "grim", "electric"]
    STAKES_POOL = ["budget", "morale", "pace", "reliability", "politics"]
    
    def __init__(self, context: NarratorContext):
        self.context = context
    
    def should_rotate_motif(self) -> bool:
        """Check if it's time to rotate motif (every 5-7 segments)"""
        return self.context.segments_since_motif_change >= random.randint(5, 7)
    
    def rotate_motif(self):
        """Choose new motif different from current"""
        available = [m for m in self.MOTIF_POOL if m != self.context.current_motif]
        if available:
            self.context.current_motif = random.choice(available)
            self.context.segments_since_motif_change = 0
    
    def update_open_loop(self, events: List[Dict[str, Any]], state_snapshot: Dict[str, Any]):
        """Update open loop based on current events and state"""
        # Priority: unresolved high-stakes situations
        
        # Financial pressure
        if state_snapshot.get('budget', 0) < 50000:
            self.context.open_loop = "how long the money lasts"
            return
        
        # Morale crisis
        if state_snapshot.get('morale', 50) < 40:
            self.context.open_loop = "if the team holds together"
            return
        
        # Contract expiries (if we have that data)
        # Championship position battle
        if state_snapshot.get('position', 16) <= 8:
            self.context.open_loop = "whether this pace holds"
            return
        
        # Default: generic momentum question
        self.context.open_loop = "what breaks first—patience or progress"
    
    def choose_named_focus(self, entities: List[Dict[str, Any]], upcoming_calendar: List[Dict[str, Any]] = None):
        """Choose an entity to follow (driver, mechanic, etc.) - prefers calendar entities"""
        # CALENDAR INTEGRATION: Prefer entities from upcoming events (contracts, decisions)
        if upcoming_calendar:
            for event in upcoming_calendar[:3]:  # Check top 3 upcoming
                if event.get('category') == 'personnel':
                    entity_name = event.get('metadata', {}).get('entity_name')
                    if entity_name:
                        self.context.named_focus = entity_name
                        return
        
        # Fallback: prefer drivers on player team
        player_drivers = [e for e in entities if e.get('entity_type') == 'driver' and e.get('is_player_team')]
        if player_drivers:
            self.context.named_focus = random.choice(player_drivers).get('name', '')
        elif entities:
            self.context.named_focus = entities[0].get('name', '')
    
    def choose_stakes_axis(self, state_snapshot: Dict[str, Any]):
        """Choose primary stakes axis based on current pressure points"""
        budget = state_snapshot.get('budget', 0)
        morale = state_snapshot.get('morale', 50)
        position = state_snapshot.get('position', 16)
        
        # Prioritize most critical axis
        if budget < 50000:
            self.context.stakes_axis = "budget"
        elif morale < 40:
            self.context.stakes_axis = "morale"
        elif position <= 5:
            self.context.stakes_axis = "pace"
        else:
            # Rotate between reliability and budget
            self.context.stakes_axis = random.choice(["budget", "reliability"])
    
    def choose_tone(self, state_snapshot: Dict[str, Any]):
        """Choose tone based on current situation"""
        budget = state_snapshot.get('budget', 0)
        morale = state_snapshot.get('morale', 50)
        position = state_snapshot.get('position', 16)
        
        # Crisis = grim
        if budget < 30000 or morale < 35:
            self.context.tone = "grim"
        # Fighting for top positions = electric
        elif position <= 5:
            self.context.tone = "electric"
        # Midfield grind = wry
        elif position > 8:
            self.context.tone = "wry"
        # Default = hungry
        else:
            self.context.tone = "hungry"
    
    def finalize_segment_update(self, events: List[Dict[str, Any]], state_snapshot: Dict[str, Any], entities: List[Dict[str, Any]], upcoming_calendar: List[Dict[str, Any]] = None):
        """Called after each segment generation to update show bible"""
        self.context.segments_since_motif_change += 1
        
        # Rotate motif if stale
        if self.should_rotate_motif():
            self.rotate_motif()
        
        # Update other elements
        self.update_open_loop(events, state_snapshot)
        self.choose_stakes_axis(state_snapshot)
        self.choose_tone(state_snapshot)
        
        # Update named focus occasionally (prefer calendar entities)
        if random.random() < 0.3 and entities:
            self.choose_named_focus(entities, upcoming_calendar)


# ============================================================================
# SIGNIFICANCE / HEAT CALCULATOR
# ============================================================================

class SignificanceCalculator:
    """
    Calculates "heat" score for events and state changes.
    Only narrate when heat crosses threshold - prevents forced talking.
    """
    
    # Heat thresholds
    SPEAK_THRESHOLD = 18.0  # Minimum heat to trigger narration
    URGENT_THRESHOLD = 100.0  # Auto-speak regardless of cooldown
    
    def __init__(self, context: NarratorContext):
        self.context = context
        self.upcoming_calendar = []  # Cache for calendar entries
    
    def set_upcoming_calendar(self, upcoming: List[Dict[str, Any]]):
        """Set cached upcoming calendar entries for heat calculation"""
        self.upcoming_calendar = upcoming
    
    def calculate_heat(self, observations: EventObservation, state_changes: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        """Calculate significance heat from events and state changes. Returns (total_heat, breakdown_dict)"""
        breakdown = {}
        
        # Baseline ambient heat - "everything gives off value for simply existing"
        # This ensures the narrator always has something to observe and comment on
        ambient_heat = 20.0  # Base heat for having an active game state
        breakdown['ambient'] = ambient_heat
        
        # Event-based heat
        event_heat = (
            len(observations.high_priority_events) * 40.0 +
            len(observations.player_team_events) * 25.0 +
            len(observations.medium_priority_events) * 10.0
        )
        breakdown['events'] = event_heat
        
        # State change heat (only if changes are meaningful)
        budget_delta = abs(state_changes.get('budget_delta', 0))
        budget_heat = 0.0
        if budget_delta > 5000:  # Only care about 5K+ changes
            budget_heat = min(budget_delta / 500, 40.0)  # Cap at 40
        breakdown['budget'] = budget_heat
        
        morale_delta = abs(state_changes.get('morale_delta', 0))
        morale_heat = 0.0
        if morale_delta > 3:  # Only care about 3+ point changes
            morale_heat = morale_delta * 5.0
        breakdown['morale'] = morale_heat
        
        position_delta = abs(state_changes.get('position_delta', 0))
        position_heat = 0.0
        if position_delta > 0:  # Any position change is significant
            position_heat = position_delta * 20.0
        breakdown['position'] = position_heat
        
        points_delta = state_changes.get('points_delta', 0)
        points_heat = 0.0
        if points_delta > 0:  # Gaining points is always significant
            points_heat = points_delta * 10.0
        breakdown['points'] = points_heat
        
        # Critical threshold states add heat
        threshold_heat = 0.0
        if self.context.player_budget < 30000:
            threshold_heat += 25.0
        if self.context.player_morale < 35:
            threshold_heat += 25.0
        if self.context.consecutive_dnfs >= 2:
            threshold_heat += 30.0
        breakdown['threshold'] = threshold_heat
        
        # CALENDAR INTEGRATION: Add urgency heat for approaching deadlines
        deadline_heat = 0.0
        for entry in self.upcoming_calendar[:5]:  # Top 5 soonest
            days_until = entry['entry_day'] - self.context.current_day
            priority = entry.get('priority', 50)
            
            if days_until <= 3:  # Within 3 days
                deadline_heat += 20.0 if entry.get('action_required', False) else 10.0
            elif days_until <= 7:  # Within 1 week
                deadline_heat += 10.0 if entry.get('action_required', False) else 5.0
        
        deadline_heat = min(deadline_heat, 40.0)  # Cap at 40
        breakdown['deadline'] = deadline_heat
        
        # Sum base heat (includes ambient heat for simply existing)
        base_heat = ambient_heat + event_heat + budget_heat + morale_heat + position_heat + points_heat + threshold_heat + deadline_heat
        
        # Time-based cooling (reduce heat if spoke recently)
        time_since_last = time.time() - self.context.last_topics_discussed[-1] if self.context.last_topics_discussed else 999999
        cool_factor = 1.0
        if time_since_last < 180:  # Less than 3 minutes
            cool_factor = time_since_last / 180.0  # 0.0 at 0s, 1.0 at 180s
        breakdown['cooldown'] = cool_factor
        
        final_heat = base_heat * cool_factor
        
        return final_heat, breakdown


# ============================================================================
# TRUTH VALIDATOR - REJECT HALLUCINATIONS
# ============================================================================

class TruthValidator:
    """
    Validates narrator text for truthiness (fuzzy/lenient fact-checking).
    Allows contextually reasonable content - only rejects clear fabrications.
    """
    
    def __init__(self, context: NarratorContext, db_path: str):
        self.context = context
        self.db_path = db_path
    
    def validate_truth(self, text: str, game_state: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Fuzzy truth check - allows mostly-true content.
        Returns (is_valid, list_of_violations)
        """
        violations = []
        text_lower = text.lower()
        
        # Ban only obvious speculation/invention
        speculation_markers = [
            'rumor has it', 'sources say', 'reportedly',
            'insider claims', 'allegedly'
        ]
        for marker in speculation_markers:
            if marker in text_lower:
                violations.append(f"Speculative language: '{marker}'")
        
        # Extract and verify team names (FUZZY - allow common words and database entities)
        mentioned_teams = self._extract_team_names(text)
        known_teams = game_state.get('known_teams', [])
        entity_allowlist = game_state.get('entity_allowlist', set())
        
        # Minimal generic racing terms only (no specific names)
        common_words = [
            'Day', 'Season', 'Formula', 'Morale', 'Budget', 'Championship', 'The',
            'Racing', 'Performance', 'Team', 'Division', 'Grand', 'Prix',
            'Motorsport', 'Driver', 'Engineer', 'Manager', 'Rival', 'Contender',
            'Community', 'Motorsports', 'Local', 'City', 'Finding', 'Their',
            'Will', 'As', 'With', 'How', 'Without', 'In', 'Patience'
        ]
        
        for team in mentioned_teams:
            if team != self.context.player_team and team not in known_teams:
                # Check both generic common words AND database entity allowlist
                if team not in common_words and team not in entity_allowlist:
                    violations.append(f"Unknown entity: {team}")
        
        # Verify dollar amounts (FUZZY - 50% tolerance)
        amounts = self._extract_dollar_amounts(text)
        for amount in amounts:
            if not self._verify_dollar_amount(amount, game_state):
                violations.append(f"Unverified amount: ${amount:,}")
        
        # Verify percentages (FUZZY - 20 point tolerance)
        percentages = self._extract_percentages(text)
        for pct in percentages:
            if not self._verify_percentage(pct, game_state):
                violations.append(f"Unverified percentage: {pct}%")
        
        return (len(violations) == 0, violations)
    
    def _extract_team_names(self, text: str) -> List[str]:
        """Extract capitalized words that might be team names"""
        import re
        potential_teams = re.findall(r'\b[A-Z][a-z]+(?:\'s)?\b', text)
        return list(set(potential_teams))
    
    def _extract_dollar_amounts(self, text: str) -> List[int]:
        """Extract dollar amounts from text"""
        import re
        amounts = []
        
        # Match $XXK, $XXM, $XX,XXX
        k_matches = re.findall(r'\$(\d+)K', text, re.IGNORECASE)
        for match in k_matches:
            amounts.append(int(match) * 1000)
        
        m_matches = re.findall(r'\$(\d+)M', text, re.IGNORECASE)
        for match in m_matches:
            amounts.append(int(match) * 1000000)
        
        comma_matches = re.findall(r'\$(\d{1,3}(?:,\d{3})+)', text)
        for match in comma_matches:
            amounts.append(int(match.replace(',', '')))
        
        return amounts
    
    def _extract_percentages(self, text: str) -> List[float]:
        """Extract percentage values from text"""
        import re
        matches = re.findall(r'(\d+(?:\.\d+)?)%', text)
        return [float(m) for m in matches]
    
    def _verify_dollar_amount(self, amount: int, game_state: Dict[str, Any]) -> bool:
        """Fuzzy check - allow if within 50% of known values"""
        player_budget = game_state.get('budget', 0)
        
        # Allow if within 50% of player budget (fuzzy match)
        if player_budget > 0:
            tolerance = player_budget * 0.5
            if abs(amount - player_budget) <= tolerance:
                return True
        
        # Check against known team budgets
        team_budgets = game_state.get('team_budgets', {})
        for team_budget in team_budgets.values():
            if team_budget > 0:
                tolerance = team_budget * 0.5
                if abs(amount - team_budget) <= tolerance:
                    return True
        
        return False
    
    def _verify_percentage(self, pct: float, game_state: Dict[str, Any]) -> bool:
        """Fuzzy check - allow if within 20 points of known values"""
        morale = game_state.get('morale', 50.0)
        
        # Allow if within 20 points of player morale (fuzzy match)
        if abs(pct - morale) <= 20.0:
            return True
        
        return False


# ============================================================================
# CONTINUOUS NARRATOR THREAD
# ============================================================================

class ContinuousNarrator:
    """
    Independent thread that observes ftb_state_db and generates Jarvis-style commentary.
    Implements streaming narration capability.
    Completely decoupled from game simulation.
    """
    
    def __init__(self, db_path: str, player_team: str, runtime_context: Dict[str, Any], cfg: Dict[str, Any], game_id: str = ''):
        self.db_path = db_path
        self.game_id = game_id  # Unique identifier for current game session
        station_dir = runtime_context.get('STATION_DIR', '.')
        print(f"[FTB Narrator] init: STATION_DIR={station_dir} db_path={self.db_path}")
        print(f"[FTB Narrator] init: game_id={self.game_id}")
        print(f"[FTB Narrator] init: ftb_state_db={'OK' if ftb_state_db else 'MISSING'}")
        print(f"[FTB Narrator] init: runtime has call_llm={bool(runtime_context.get('call_llm'))} db_enqueue={bool(runtime_context.get('db_enqueue_segment'))} log={bool(runtime_context.get('log'))}")

        # Ensure player_team is a string (extract name if Team object)
        self.player_team = player_team.name if hasattr(player_team, 'name') else str(player_team)
        self.runtime = runtime_context
        self.cfg = cfg
        
        # Extract narrator config
        narrator_cfg = cfg.get("ftb", {}).get("narrator", {})
        self.enabled = narrator_cfg.get("enabled", True)
        self.cadence_range = narrator_cfg.get("cadence_seconds", [10, 20])
        self.max_segments_per_hour = narrator_cfg.get("max_segments_per_hour", 180)  # Increased from 60 for omnipresent narrator
        
        # State
        self.context = NarratorContext(player_team=player_team)
        self.running = False
        self.suspended = False  # True during PBP mode – narrator sleeps
        self.thread = None
        self.last_segment_time = 0
        self.last_news_broadcast_time = 0  # Track Formula Z news broadcasts separately
        self.segments_this_hour = 0
        self.hour_start_time = time.time()
        self.startup_time = time.time()  # Track when narrator started for event filtering
        
        # CONTINUITY-FIRST: Initialize claim tracker and show bible manager
        self.claim_tracker = ClaimTracker(self.context)
        self.show_bible_manager = ShowBibleManager(self.context)
        self.burst_sequence = []  # Queue of (text, priority) for burst delivery
        self.in_burst_mode = False
        
        # HEAT/TRUTH SYSTEMS: Initialize significance calculator and truth validator
        self.significance_calc = SignificanceCalculator(self.context)
        self.truth_validator = TruthValidator(self.context, db_path)
        
        # State tracking for heat calculation (initialized with dummy values, updated on first poll)
        self.last_state_snapshot = {
            'budget': 0,
            'morale': 50.0,
            'position': 16,
            'points': 0
        }
        self._snapshot_initialized = False  # Flag to detect first state load
        
        # ENTITY ALLOWLIST: Database-driven truth validation cache
        self._entity_allowlist = set()  # Set of all known entity names from DB
        self._allowlist_last_updated = 0  # Timestamp of last cache refresh
        self._allowlist_ttl = 300  # Cache TTL in seconds (5 minutes)
        
        # Voice configuration
        self.voice_path = cfg.get("voices", {}).get("narrator", 
                                                     cfg.get("audio", {}).get("voices", {}).get("narrator"))
        
        # Formula Z news anchor voice (with multiple fallback paths)
        self.news_anchor_voice_path = (
            cfg.get("audio", {}).get("voices", {}).get("formula_z_news_anchor")  # Primary
            or cfg.get("audio", {}).get("voices", {}).get("formula_z_news")      # Alternate key
            or cfg.get("audio", {}).get("voices", {}).get("news_anchor")         # Generic news
            or cfg.get("voices", {}).get("formula_z_news_anchor")                # Legacy location
            or self.voice_path  # Final fallback to narrator
        )
        
        # Broadcast commentary voices (play-by-play and color commentator)
        self.pbp_voice_path = cfg.get("voices", {}).get("play_by_play", self.voice_path)
        self.color_voice_path = cfg.get("voices", {}).get("color_commentator", self.news_anchor_voice_path)
        
        # Broadcast commentary generator
        self.broadcast_generator = None
        if ftb_broadcast_commentary:
            # Will be initialized when we know league tier
            self.broadcast_generator_tier = None
        
        # LLM model
        self.model_name = cfg.get("models", {}).get("narrator", "qwen3:8b")
        
        # Get runtime functions
        self.log = runtime_context.get('log', print)
        self.call_llm = runtime_context.get('call_llm')
        self.db_enqueue = runtime_context.get('db_enqueue_segment')
        self.db_connect = runtime_context.get('db_connect')
        
        # Validate critical functions
        if not self.call_llm:
            self.log("ftb_narrator", "WARNING: call_llm not available in runtime_context - narrator cannot generate commentary")
        if not self.db_enqueue or not self.db_connect:
            self.log("ftb_narrator", "WARNING: db functions not available in runtime_context - narrator cannot enqueue audio")
        if self.call_llm and self.db_enqueue and self.db_connect:
            self.log("ftb_narrator", "Runtime functions validated: narrator audio enabled")
        
        # Clean up old events and context on startup
        self._startup_cleanup()
        
        # Initialize entity allowlist cache
        self._get_entity_allowlist()
    
    def start(self):
        """Start the narrator thread"""
        if not self.enabled:
            self.log("ftb_narrator", "Disabled in config, not starting")
            return
        
        if self.running:
            self.log("ftb_narrator", "Already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="FTB-Narrator")
        self.thread.start()
        self.log("ftb_narrator", f"Started continuous narrator for {self.player_team}")
    
    def stop(self):
        """Stop the narrator thread"""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5.0)
        self.log("ftb_narrator", "Stopped narrator thread")
    
    def _migrate_narrator_context_schema(self, cursor):
        """
        CONTINUITY-FIRST: Migrate narrator_context table to add Show Bible columns if missing.
        SQLite doesn't support ALTER TABLE ADD COLUMN with defaults in all cases, so we check first.
        """
        try:
            # Get current columns
            cursor.execute("PRAGMA table_info(narrator_context)")
            columns = {row[1] for row in cursor.fetchall()}
            
            # Add missing columns one by one
            new_columns = {
                'player_team': "TEXT",
                'save_timestamp': "REAL",
                'current_motif': "TEXT DEFAULT 'quiet climb'",
                'open_loop': "TEXT DEFAULT ''",
                'named_focus': "TEXT DEFAULT ''",
                'stakes_axis': "TEXT DEFAULT 'budget'",
                'tone': "TEXT DEFAULT 'wry'",
                'last_generated_spine': "TEXT DEFAULT ''",
                'last_generated_beat': "TEXT DEFAULT ''",
                'claim_tags_json': "TEXT DEFAULT '[]'",
                'segments_since_motif_change': "INTEGER DEFAULT 0"
            }
            
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    try:
                        cursor.execute(f"ALTER TABLE narrator_context ADD COLUMN {col_name} {col_type}")
                        self.log("ftb_narrator", f"MIGRATION: Added column '{col_name}' to narrator_context")
                    except Exception as e:
                        # Column might already exist or other error
                        self.log("ftb_narrator", f"MIGRATION: Could not add column '{col_name}': {e}")
            
        except Exception as e:
            self.log("ftb_narrator", f"Schema migration error (non-fatal): {e}")
    
    def _startup_cleanup(self):
        """Clear ALL pre-existing events on startup to ensure clean slate"""
        if not ftb_state_db:
            self.log("ftb_narrator", "WARNING: ftb_state_db not available, cannot perform startup cleanup")
            return
        
        if not self.db_path:
            self.log("ftb_narrator", "WARNING: db_path not set, cannot perform startup cleanup")
            return
        
        # Ensure the state DB schema exists before cleanup.
        import os
        import sqlite3
        if not os.path.exists(self.db_path):
            self.log("ftb_narrator", f"Database does not exist yet at {self.db_path}, initializing")
            ftb_state_db.init_db(self.db_path)
        else:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                    existing_tables = {row[0] for row in cursor.fetchall()}
                required_tables = {"events_buffer", "teams", "player_state", "league_standings"}
                if not required_tables.issubset(existing_tables):
                    self.log("ftb_narrator", "Database schema incomplete, initializing")
                    ftb_state_db.init_db(self.db_path)
            except Exception as e:
                self.log("ftb_narrator", f"Database schema check failed, reinitializing: {e}")
                ftb_state_db.init_db(self.db_path)
        
        try:
            self.log("ftb_narrator", f"Starting cleanup for database: {self.db_path}")
            
            # AGGRESSIVE CLEANUP: Always mark ALL existing events as seen on startup
            # This ensures we ONLY process events that happen AFTER narrator starts
            with ftb_state_db.get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count and clear ALL unseen events
                cursor.execute("SELECT COUNT(*) FROM events_buffer WHERE emitted_to_narrator = 0")
                unseen_count = cursor.fetchone()[0]
                
                if unseen_count > 0:
                    # Mark ALL unseen events as emitted (ignore everything from before startup)
                    cursor.execute("UPDATE events_buffer SET emitted_to_narrator = 1")
                    self.log("ftb_narrator", f"STARTUP CLEANUP: Cleared {unseen_count} pre-existing events from queue")
                else:
                    self.log("ftb_narrator", "STARTUP CLEANUP: No pre-existing events found (clean start)")
                
                # CONTINUITY-FIRST: Migrate schema if needed (add Show Bible columns)
                self._migrate_narrator_context_schema(cursor)
                
                # Check if we need to reset context
                should_reset = False
                stored_team = None
                
                try:
                    cursor.execute("SELECT player_team, save_timestamp FROM narrator_context WHERE id = 1")
                    row = cursor.fetchone()
                    
                    if row:
                        stored_team = row[0] if len(row) > 0 else None
                        
                        # Different team = different save
                        if stored_team and stored_team != self.player_team:
                            should_reset = True
                            self.log("ftb_narrator", f"Team change detected: {stored_team} -> {self.player_team}")
                    else:
                        # No context exists
                        should_reset = True
                        
                except Exception as e:
                    # Unexpected error after migration
                    self.log("ftb_narrator", f"Context check error after migration: {e}")
                    should_reset = True
                
                # Reset or update context
                if should_reset:
                    cursor.execute("DELETE FROM narrator_context")
                    cursor.execute("""
                        INSERT INTO narrator_context (id, last_commentary_time, player_team, save_timestamp)
                        VALUES (1, 0, ?, ?)
                    """, (self.player_team, time.time()))
                    self.log("ftb_narrator", f"Context reset for team: {self.player_team}")
                else:
                    cursor.execute("""
                        UPDATE narrator_context 
                        SET save_timestamp = ?, player_team = ?
                        WHERE id = 1
                    """, (time.time(), self.player_team))
                    self.log("ftb_narrator", f"Context updated for continued session: {self.player_team}")
                
                conn.commit()
            
            # Force close all database connections to ensure clean state
            # This prevents cached connection from reading stale data
            if hasattr(ftb_state_db, '_thread_local'):
                if hasattr(ftb_state_db._thread_local, 'connections'):
                    if self.db_path in ftb_state_db._thread_local.connections:
                        try:
                            ftb_state_db._thread_local.connections[self.db_path].close()
                            del ftb_state_db._thread_local.connections[self.db_path]
                            self.log("ftb_narrator", "Closed and cleared database connection cache")
                        except:
                            pass
            
            # Clear queued audio segments from bookmark database
            segments_cleared = 0
            if self.db_connect:
                try:
                    audio_conn = self.db_connect()
                    cursor = audio_conn.cursor()
                    
                    # Count narrator segments before deletion
                    cursor.execute("""
                        SELECT COUNT(*) FROM segments 
                        WHERE status='queued' AND source='ftb_narrator'
                    """)
                    segments_cleared = cursor.fetchone()[0]
                    
                    # Delete all queued narrator audio segments
                    cursor.execute("""
                        DELETE FROM segments 
                        WHERE status='queued' AND source='ftb_narrator'
                    """)
                    audio_conn.commit()
                    audio_conn.close()
                    
                    if segments_cleared > 0:
                        self.log("ftb_narrator", f"AUDIO CLEANUP: Cleared {segments_cleared} queued audio segments")
                    else:
                        self.log("ftb_narrator", "AUDIO CLEANUP: No queued audio segments found")
                        
                except Exception as e:
                    self.log("ftb_narrator", f"Error clearing audio segments: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                self.log("ftb_narrator", "WARNING: db_connect not available, cannot clear audio segments")
            
            self.log("ftb_narrator", f"============================================")
            self.log("ftb_narrator", f"STARTUP CLEANUP COMPLETE")
            self.log("ftb_narrator", f"- Team: {self.player_team}")
            self.log("ftb_narrator", f"- Events cleared: {unseen_count if unseen_count > 0 else 0}")
            self.log("ftb_narrator", f"- Audio segments cleared: {segments_cleared}")
            self.log("ftb_narrator", f"- Ready for fresh events only")
            self.log("ftb_narrator", f"============================================")
            
        except Exception as e:
            self.log("ftb_narrator", f"Error during startup cleanup: {e}")
            import traceback
            traceback.print_exc()
    
    def _run_loop(self):
        """Main narrator observation loop"""
        self.log("ftb_narrator", "Narrator loop started")
        
        while self.running:
            try:
                # ---- PBP suspension gate ----
                if self.suspended:
                    time.sleep(1.0)
                    continue
                
                # TICK ALIGNMENT: Sync narrator tick with game simulation tick
                self._sync_current_tick()
                
                # Reset hourly counter
                if time.time() - self.hour_start_time > 3600:
                    self.segments_this_hour = 0
                    self.hour_start_time = time.time()
                
                # Check rate limit (increased for omnipresent narrator)
                if self.segments_this_hour >= self.max_segments_per_hour:
                    time.sleep(30)  # Reduced from 60
                    continue
                
                # Check minimum interval with 90-second cooldown after regular segments
                elapsed_since_last = time.time() - self.last_segment_time
                if elapsed_since_last < 90:  # 90-second cooldown after each segment
                    time.sleep(min(10, 90 - elapsed_since_last))  # Sleep in chunks to be responsive
                    continue
                
                # Observe event pool
                observations = self._observe_events()
                
                # Update context with current player state
                self._update_player_context()
                
                # Initialize state snapshot on first run (prevents phantom heat spike)
                if not self._snapshot_initialized:
                    self.last_state_snapshot = {
                        'budget': self.context.player_budget,
                        'morale': self.context.player_morale,
                        'position': self.context.player_championship_position,
                        'points': self.context.player_points
                    }
                    self._snapshot_initialized = True
                    self.log("ftb_narrator", f"Initialized heat snapshot: budget=${self.last_state_snapshot['budget']:,}, morale={self.last_state_snapshot['morale']:.1f}")
                
                # Decide if we should speak
                should_speak, commentary_type = self._should_generate_commentary(observations)
                
                if should_speak:
                    # ---- Re-check suspension BEFORE expensive LLM call ----
                    if self.suspended:
                        self.log("ftb_narrator", "Suspended before LLM call – skipping")
                        continue

                    # Generate commentary
                    segment_text = self._generate_commentary(observations, commentary_type)
                    
                    # ---- Re-check suspension AFTER LLM call (may have taken 10-30s) ----
                    if self.suspended:
                        self.log("ftb_narrator", "Suspended after LLM call – discarding generated text")
                        self.burst_sequence = []
                        self.in_burst_mode = False
                        continue

                    if segment_text:
                        # CONTINUITY-FIRST: Validate and enforce continuity
                        validated_text = self._validate_and_enforce_continuity(segment_text, commentary_type, observations)
                        
                        # ---- Re-check suspension AFTER validation (more LLM calls) ----
                        if self.suspended:
                            self.log("ftb_narrator", "Suspended after validation – discarding")
                            self.burst_sequence = []
                            self.in_burst_mode = False
                            continue

                        if validated_text:
                            # CONTINUITY-FIRST: Trigger burst mode (rapid multi-part delivery)
                            self._trigger_burst_mode(validated_text, commentary_type, observations)
                            
                            # ---- Final suspension gate before enqueue ----
                            if self.suspended:
                                self.log("ftb_narrator", "Suspended before enqueue – discarding burst")
                                self.burst_sequence = []
                                self.in_burst_mode = False
                                continue

                            # Enqueue burst sequence or single segment
                            if self.burst_sequence:
                                self._enqueue_burst_sequence()
                            else:
                                self._enqueue_audio(validated_text, commentary_type)
                            
                            # Update show bible after successful generation
                            try:
                                # Get recent events and entities for show bible
                                recent_events = observations.high_priority_events + observations.player_team_events
                                state_snapshot = {
                                    'budget': self.context.player_budget,
                                    'morale': self.context.player_morale,
                                    'position': self.context.player_championship_position
                                }
                                
                                # Query entities from DB
                                entities = []
                                try:
                                    if ftb_state_db and self.db_path:
                                        entities = ftb_state_db.query_entities(self.db_path, team_name=self.player_team)
                                except:
                                    pass
                                
                                # CALENDAR INTEGRATION: Pass upcoming calendar to show bible manager
                                upcoming = self._query_upcoming_calendar(days_ahead=14)
                                self.show_bible_manager.finalize_segment_update(recent_events, state_snapshot, entities, upcoming)
                            except Exception as e:
                                self.log("ftb_narrator", f"Error updating show bible: {e}")
                            
                            self.last_segment_time = time.time()
                            self.segments_this_hour += 1
                
                # Check for Formula Z news broadcast
                if self._should_broadcast_news():
                    news_text = self._generate_news_broadcast()
                    if news_text:
                        # Validate news broadcast for hallucinations
                        is_valid, violations = self._validate_news_broadcast(news_text)
                        if is_valid:
                            self._enqueue_audio(news_text, CommentaryType.FORMULA_Z_NEWS)
                            self.last_news_broadcast_time = time.time()
                            self.log("ftb_narrator", "Formula Z news broadcast delivered")
                        else:
                            self.log("ftb_narrator", f"News broadcast rejected (hallucinations detected): {violations}")
                            # Still update last broadcast time to avoid spam retries
                            self.last_news_broadcast_time = time.time()
                
                # Check for live race broadcast commentary
                self._check_live_race_broadcast()
                
                # Random sleep for natural pacing (reduced for omnipresent narrator)
                sleep_duration = random.uniform(2, 5)  # Changed from self.cadence_range (10-20)
                time.sleep(sleep_duration)
                
            except Exception as e:
                self.log("ftb_narrator", f"Error in narrator loop: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)
    
    def _observe_events(self) -> EventObservation:
        """Read state DB and filter for relevant unseen events (with smart batch aggregation)"""
        if not ftb_state_db or not self.db_path:
            return EventObservation([], [], [], [], [])
        
        # Check if DB file exists
        if not os.path.exists(self.db_path):
            return EventObservation([], [], [], [], [])
        
        # Log first observation for debugging
        if not hasattr(self, '_first_observation_logged'):
            self.log("ftb_narrator", f"First event observation cycle starting (startup was at {self.startup_time:.2f})")
            self._first_observation_logged = True
        
        # BATCH INTELLIGENCE: Peek at first event to detect batch mode WITHOUT marking seen
        try:
            peek_events = ftb_state_db.query_unseen_events(self.db_path, mark_seen=False, limit=5)
        except Exception as e:
            self.log("ftb_narrator", f"Error peeking at events: {e}")
            return EventObservation([], [], [], [], [])
        
        if not peek_events:
            return EventObservation([], [], [], [], [])
        
        # Check for batch mode markers
        is_batch_mode = False
        batch_start_tick = None
        batch_end_tick = None
        
        for event in peek_events:
            event_data = event.get('data', {})
            if event_data.get('_batch_mode'):
                is_batch_mode = True
                batch_start_tick = event_data.get('_batch_start_tick')
                batch_end_tick = event_data.get('_batch_end_tick')
                break
        
        # BATCH MODE: Aggregate all events in range intelligently
        if is_batch_mode:
            self.log("ftb_narrator", f"Batch mode detected: ticks {batch_start_tick} to {batch_end_tick}")
            try:
                # Query ALL unseen events (higher limit for batch processing)
                all_events = ftb_state_db.query_unseen_events(self.db_path, mark_seen=False, limit=500)
                
                # Filter to only FTB events in this batch
                batch_events = []
                for event in all_events:
                    event_data = event.get('data', {})
                    if not event_data.get('_ftb'):
                        continue
                    if event_data.get('_batch_mode') and \
                       event_data.get('_batch_start_tick') == batch_start_tick and \
                       event_data.get('_batch_end_tick') == batch_end_tick:
                        batch_events.append(event)
                
                self.log("ftb_narrator", f"Batch aggregation: {len(batch_events)} events found")
                
                # INTELLIGENT PRUNING: Keep only significant events
                high_priority = []
                medium_priority = []
                player_team_events = []
                world_events = []
                
                for event in batch_events:
                    event_team = event.get('team', '')
                    is_player_event = event_team == self.player_team
                    priority = event.get('priority', 50.0)
                    severity = event.get('severity', 'info')
                    
                    # For batch mode: only keep HIGH priority or player events
                    if priority >= 80 or severity in ["critical", "major"]:
                        high_priority.append(event)
                        if is_player_event:
                            player_team_events.append(event)
                    elif is_player_event and priority >= 60:  # Player medium-high events
                        medium_priority.append(event)
                        player_team_events.append(event)
                    elif not is_player_event and priority >= 75:  # Only very significant world events
                        world_events.append(event)
                
                # Further pruning: if too many events, keep only top 20%
                total_kept = len(high_priority) + len(medium_priority) + len(world_events)
                if total_kept > 20:
                    self.log("ftb_narrator", f"Pruning batch: {total_kept} -> top 20%")
                    # Sort by priority and keep top 20%
                    all_kept = high_priority + medium_priority + world_events
                    all_kept.sort(key=lambda e: e.get('priority', 50.0), reverse=True)
                    pruned = all_kept[:max(5, len(all_kept) // 5)]  # Top 20%, minimum 5
                    
                    # Rebuild lists
                    high_priority = [e for e in pruned if e.get('priority', 50) >= 80]
                    medium_priority = [e for e in pruned if 60 <= e.get('priority', 50) < 80]
                    player_team_events = [e for e in pruned if e.get('team') == self.player_team]
                    world_events = [e for e in pruned if e.get('team') != self.player_team]
                
                # Mark ALL batch events as seen atomically (not just the ones we kept)
                ftb_state_db.query_unseen_events(self.db_path, mark_seen=True, limit=500)
                
                self.log("ftb_narrator", f"Batch result: {len(high_priority)} high, {len(player_team_events)} player, {len(world_events)} world")
                
                return EventObservation(
                    high_priority_events=high_priority,
                    medium_priority_events=medium_priority,
                    low_priority_events=[],  # Excluded in batch mode
                    player_team_events=player_team_events,
                    world_events=world_events
                )
                
            except Exception as e:
                self.log("ftb_narrator", f"Error in batch aggregation: {e}")
                import traceback
                traceback.print_exc()
                return EventObservation([], [], [], [], [])
        
        # NORMAL MODE: Process events normally
        try:
            unseen_events = ftb_state_db.query_unseen_events(self.db_path, mark_seen=True, limit=100)
            
            # Safety check: log if we're getting events immediately after startup
            if unseen_events and hasattr(self, 'startup_time'):
                if time.time() - self.startup_time < 10:  # Within 10 seconds of startup
                    self.log("ftb_narrator", f"WARNING: Got {len(unseen_events)} events within {time.time() - self.startup_time:.1f}s of startup - should have been cleaned up!")
        except Exception as e:
            self.log("ftb_narrator", f"Error reading state DB: {e}")
            return EventObservation([], [], [], [], [])
        
        # Filter and categorize - ONLY process FTB game events
        high_priority = []
        medium_priority = []
        low_priority = []
        player_team_events = []
        world_events = []
        
        for event in unseen_events:
            # Only process events that are actually from FTB game
            # Skip events from other plugins (e.g., futuresight, markets, etc.)
            event_data = event.get('data', {})
            if not event_data.get('_ftb'):
                continue  # Skip non-FTB events
            
            event_team = event.get('team', '')
            is_player_event = event_team == self.player_team
            
            if is_player_event:
                player_team_events.append(event)
            else:
                world_events.append(event)
            
            priority = event.get('priority', 50.0)
            severity = event.get('severity', 'info')
            
            if priority >= 80 or severity in ["critical", "major"]:
                high_priority.append(event)
            elif priority >= 50:
                medium_priority.append(event)
            else:
                low_priority.append(event)
        
        # NEW: Queue purging (ruthless 2-day cutoff)
        self._purge_old_events(self.context.current_day)
        
        # NEW: Detect urgent events and set event-driven priority
        if high_priority and player_team_events:
            # High-priority player events trigger urgent mode
            if not self.context.urgent_event_pending:
                # Derive event theme
                if ftb_segment_prompts:
                    event_theme = ftb_segment_prompts.get_event_theme_from_events(high_priority)
                    self.context.event_theme = event_theme
                    self.context.urgent_event_pending = True
                    self.context.urgent_segments_generated = 0
                    self.log("ftb_narrator", f"URGENT EVENT DETECTED: theme={event_theme}")
        
        return EventObservation(
            high_priority_events=high_priority,
            medium_priority_events=medium_priority,
            low_priority_events=low_priority,
            player_team_events=player_team_events,
            world_events=world_events
        )
    
    def _sync_current_tick(self):
        """TICK ALIGNMENT: Sync narrator's tick counter with game simulation tick from database"""
        if not ftb_state_db or not self.db_path:
            # Fallback: increment manually if DB unavailable
            self.context.current_tick += 1
            return
        
        try:
            game_state = ftb_state_db.query_game_state(self.db_path)
            if game_state:
                db_tick = game_state.get("tick", 0)
                if db_tick != self.context.current_tick:
                    old_tick = self.context.current_tick
                    self.context.current_tick = db_tick
                    # Log only on significant jumps (batch mode or startup)
                    if abs(db_tick - old_tick) > 1:
                        self.log("ftb_narrator", f"Tick sync: {old_tick} -> {db_tick} (jump of {db_tick - old_tick})")
        except Exception as e:
            self.log("ftb_narrator", f"Error syncing tick: {e}")
            # Fallback: increment manually on error
            self.context.current_tick += 1
    
    def _update_player_context(self):
        """Update narrator's understanding of current player state from DB"""
        if not ftb_state_db or not self.db_path:
            return
        
        try:
            player_state = ftb_state_db.query_player_state(self.db_path)
            if player_state:
                self.context.player_budget = int(player_state.get("budget", 0))
                self.context.player_championship_position = player_state.get("championship_position", 0)
                self.context.player_points = player_state.get("points", 0)
                self.context.player_morale = player_state.get("morale", 50.0)
                self.context.player_reputation = player_state.get("reputation", 0.0)
                self.context.player_tier = player_state.get("tier", 1)
                
                # Query game state for tick/day info
                game_state = ftb_state_db.query_game_state(self.db_path)
                if game_state:
                    self.context.current_day = game_state.get("day", 0)
                    self.context.current_season = game_state.get("season", 1)
                
                # Query UI context for active tab
                ui_context = ftb_state_db.query_ui_context(self.db_path)
                if ui_context:
                    self.context.active_tab = ui_context.get("active_tab")
        except Exception as e:
            self.log("ftb_narrator", f"Error updating player context: {e}")
    
    def _purge_old_events(self, current_day: int):
        """TICK ALIGNMENT: Ruthlessly purge events older than 10 ticks from queue"""
        if not ftb_state_db or not self.db_path:
            return 0
        
        current_tick = self.context.current_tick
        if current_tick == 0:
            return 0
        
        try:
            # Mark old events as emitted directly via SQL
            with ftb_state_db.get_connection(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Count events to be purged (>10 ticks old)
                cursor.execute("""
                    SELECT COUNT(*) FROM events_buffer 
                    WHERE emitted_to_narrator = 0 AND tick < ?
                """, (current_tick - 10,))
                old_count = cursor.fetchone()[0]
                
                if old_count > 0:
                    # Mark old events as emitted
                    cursor.execute("""
                        UPDATE events_buffer 
                        SET emitted_to_narrator = 1 
                        WHERE emitted_to_narrator = 0 AND tick < ?
                    """, (current_tick - 10,))
                    
                    conn.commit()
                    self.log("ftb_narrator", f"Purged {old_count} events older than 10 ticks (current tick: {current_tick})")
                    return old_count
            
            return 0
        except Exception as e:
            self.log("ftb_narrator", f"Error purging old events: {e}")
            return 0
    
    def _build_entity_allowlist(self) -> set:
        """Build comprehensive set of all valid entity names from database"""
        allowlist = {self.context.player_team}
        
        if not ftb_state_db or not self.db_path:
            self.log("ftb_narrator", "Cannot build entity allowlist: db not available")
            return allowlist
        
        try:
            # All team names
            teams = ftb_state_db.query_all_teams(self.db_path)
            if teams:
                # Add team names
                allowlist.update(t['name'] for t in teams if t['name'])
                
                # Add team principals
                allowlist.update(t['principal'] for t in teams if t.get('principal'))
                
                # Query rosters for each team to get all entity names
                for team in teams:
                    try:
                        roster = ftb_state_db.query_entities_by_team(self.db_path, team['name'])
                        if roster:
                            allowlist.update(e['name'] for e in roster if e.get('name'))
                    except Exception as e:
                        self.log("ftb_narrator", f"Error querying roster for {team['name']}: {e}")
                        continue
            
            self.log("ftb_narrator", f"Built entity allowlist with {len(allowlist)} names")
            
        except Exception as e:
            self.log("ftb_narrator", f"Error building entity allowlist: {e}")
        
        return allowlist
    
    def _get_entity_allowlist(self) -> set:
        """Get cached entity allowlist, rebuild if stale"""
        now = time.time()
        if now - self._allowlist_last_updated > self._allowlist_ttl:
            self._entity_allowlist = self._build_entity_allowlist()
            self._allowlist_last_updated = now
        return self._entity_allowlist
    
    def _choose_segment_type(self, observations: EventObservation) -> CommentaryType:
        """Choose segment type using cooldown-weighted selection with event-driven priority"""
        
        # Import for type checking
        if not ftb_segment_prompts:
            # Fallback to legacy behavior
            return CommentaryType.RECAP
        
        # Get current tick for cooldown calculations
        current_tick = self.context.current_tick
        
        # RECENCY BOOST: Check for very recent high-priority events (especially race results)
        has_fresh_race_result = False
        if observations.high_priority_events:
            for event in observations.high_priority_events:
                event_data = event.get('data', {})
                event_tick = event.get('tick', 0)
                tick_age = current_tick - event_tick
                
                # Race result within 3 ticks gets massive boost
                if event_data.get('category') in ['race_result', 'race_finish'] and tick_age <= 3:
                    has_fresh_race_result = True
                    self.log("ftb_narrator", f"RACE RESULT DOMINANCE: race_result at tick {event_tick} (age: {tick_age}) triggers focused coverage")
                    break
        
        # RACE RESULT DOMINANCE: Force race-specific segment types if fresh result exists
        if has_fresh_race_result:
            race_segments = [
                CommentaryType.POST_RACE_COOLDOWN,
                CommentaryType.RACE_ATMOSPHERE,
                CommentaryType.DRIVER_SPOTLIGHT,  # Focus on driver performance
                CommentaryType.DRIVER_TRAJECTORY,  # How driver/team trend looks
                CommentaryType.RECAP,  # Race recap
                CommentaryType.MOMENTUM_CHECK,  # Post-race momentum assessment
            ]
            
            # All these types exist, pick one randomly
            chosen = random.choice(race_segments)
            self.log("ftb_narrator", f"Race result dominance: forcing {chosen.value}")
            return chosen
        
        # Check if urgent event mode is active
        if self.context.urgent_event_pending and self.context.event_theme:
            # Filter to event-relevant segments
            relevant_segments = ftb_segment_prompts.EVENT_THEME_SEGMENTS.get(
                self.context.event_theme, []
            )
            
            if relevant_segments:
                # Boost relevant segments massively
                segment_weights = {}
                for seg_value in relevant_segments:
                    try:
                        seg_type = CommentaryType(seg_value)
                        segment_weights[seg_type] = 100.0  # Huge boost for relevant segments
                    except ValueError:
                        continue
                
                if segment_weights:
                    chosen = random.choices(
                        list(segment_weights.keys()),
                        weights=list(segment_weights.values()),
                        k=1
                    )[0]
                    
                    # Increment urgent segments counter
                    self.context.urgent_segments_generated += 1
                    
                    # Clear urgent mode after 2-3 segments
                    if self.context.urgent_segments_generated >= random.randint(2, 3):
                        self.context.urgent_event_pending = False
                        self.context.event_theme = None
                        self.context.urgent_segments_generated = 0
                        self.log("ftb_narrator", f"Cleared urgent event mode after {self.context.urgent_segments_generated} segments")
                    
                    return chosen
        
        # Normal mode: cooldown-weighted selection across all segments
        segment_weights = {}
        
        # Build weights for all segment types
        for commentary_type in CommentaryType:
            # Skip rare/special segments in normal rotation (require specific triggers)
            if commentary_type.value in ftb_segment_prompts.SEGMENT_CATEGORIES.get("RARE_SPECIAL", []):
                continue
            
            base_weight = 1.0
            
            # Get segment history
            history_entry = self.context.segment_history.get(commentary_type.value)
            
            if history_entry:
                # Calculate cooldown penalty (exponential decay)
                ticks_since_use = current_tick - history_entry.get('last_used_tick', 0)
                
                # Half-life of ~50 ticks for cooldown decay
                cooldown_factor = pow(0.5, ticks_since_use / 50.0) if ticks_since_use < 200 else 0.0
                
                # Reduce weight based on recency
                base_weight *= (1.0 - cooldown_factor * 0.9)  # Up to 90% reduction if very recent
            
            # Boost weight if matches active tab
            if self.context.active_tab:
                tab_boost_map = {
                    "Team": ["roster_suggestion", "driver_spotlight", "team_chemistry", "driver_trajectory"],
                    "Finance": ["financial_insight", "budget_disparity", "opportunity_cost"],
                    "Development": ["development_guidance", "car_strength_profile", "development_roi", "technical_philosophy"],
                    "Race Operations": ["strategy_tip", "car_strength_profile", "setup_window"]
                }
                
                if commentary_type.value in tab_boost_map.get(self.context.active_tab, []):
                    base_weight *= 2.5
            
            # Category balance boost (slight preference for under-represented categories)
            category_usage = {}
            for cat_name, cat_segments in ftb_segment_prompts.SEGMENT_CATEGORIES.items():
                cat_count = sum(1 for s in cat_segments if self.context.segment_history.get(s, {}).get('use_count', 0) > 0)
                category_usage[cat_name] = cat_count
            
            # Find which category this segment belongs to
            for cat_name, cat_segments in ftb_segment_prompts.SEGMENT_CATEGORIES.items():
                if commentary_type.value in cat_segments:
                    # Slight boost for under-used categories
                    if category_usage.get(cat_name, 0) < 3:
                        base_weight *= 1.3
                    break
            
            segment_weights[commentary_type] = max(0.01, base_weight)  # Minimum weight
        
        # Log top weighted segments for debugging
        top_5 = sorted(segment_weights.items(), key=lambda x: x[1], reverse=True)[:5]
        self.log("ftb_narrator", f"Top segment weights: {[(t.value, f'{w:.2f}') for t, w in top_5]}")
        
        # Choose weighted random segment
        if segment_weights:
            chosen = random.choices(
                list(segment_weights.keys()),
                weights=list(segment_weights.values()),
                k=1
            )[0]
            return chosen
        
        # Fallback
        return CommentaryType.RECAP
    
    def _get_comparative_context(self, commentary_type: CommentaryType) -> str:
        """Build comparative context showing changes since last time this segment was used"""
        if not ftb_state_db or not self.db_path:
            return ""
        
        # Get history for this segment type
        history_entry = self.context.segment_history.get(commentary_type.value)
        if not history_entry or not history_entry.get('last_state_snapshot'):
            return ""
        
        try:
            last_snapshot = history_entry['last_state_snapshot']
            comparisons = []
            
            # Compare morale
            if 'morale' in last_snapshot:
                morale_delta = self.context.player_morale - last_snapshot['morale']
                if abs(morale_delta) >= 5.0:
                    direction = "up" if morale_delta > 0 else "down"
                    comparisons.append(f"Morale has moved {direction} from {last_snapshot['morale']:.0f}% to {self.context.player_morale:.0f}%")
            
            # Compare budget
            if 'budget' in last_snapshot:
                budget_delta = self.context.player_budget - last_snapshot['budget']
                if abs(budget_delta) >= last_snapshot['budget'] * 0.1:  # 10% change
                    direction = "increased" if budget_delta > 0 else "decreased"
                    comparisons.append(f"Budget has {direction} from ${last_snapshot['budget']:,} to ${self.context.player_budget:,}")
            
            # Compare standings
            if 'position' in last_snapshot:
                pos_delta = last_snapshot['position'] - self.context.player_championship_position  # Note: lower is better
                if pos_delta != 0:
                    direction = "up" if pos_delta > 0 else "down"
                    comparisons.append(f"Championship position moved {direction} from P{last_snapshot['position']} to P{self.context.player_championship_position}")
            
            # Compare points
            if 'points' in last_snapshot:
                points_delta = self.context.player_points - last_snapshot['points']
                if points_delta > 0:
                    comparisons.append(f"Gained {points_delta} points (now {self.context.player_points} total)")
            
            # Compare day progression
            if 'day' in last_snapshot:
                day_delta = self.context.current_day - last_snapshot['day']
                if day_delta > 0:
                    comparisons.append(f"{day_delta} days have passed since last time (now day {self.context.current_day})")
            
            if comparisons:
                return "\n\nCOMPARATIVE CONTEXT (since last similar segment):\n" + "\n".join(f"- {c}" for c in comparisons) + "\n"
            
            return ""
            
        except Exception as e:
            self.log("ftb_narrator", f"Error building comparative context: {e}")
            return ""
    
    def _update_segment_history(self, commentary_type: CommentaryType):
        """Update segment history after successful generation"""
        # Create snapshot of current state
        state_snapshot = {
            'morale': self.context.player_morale,
            'budget': self.context.player_budget,
            'position': self.context.player_championship_position,
            'points': self.context.player_points,
            'day': self.context.current_day,
            'season': self.context.current_season
        }
        
        # Get or create history entry
        if commentary_type.value not in self.context.segment_history:
            self.context.segment_history[commentary_type.value] = {
                'last_used_tick': self.context.current_tick,
                'last_game_day': self.context.current_day,
                'use_count': 1,
                'last_state_snapshot': state_snapshot
            }
        else:
            entry = self.context.segment_history[commentary_type.value]
            entry['last_used_tick'] = self.context.current_tick
            entry['last_game_day'] = self.context.current_day
            entry['use_count'] = entry.get('use_count', 0) + 1
            entry['last_state_snapshot'] = state_snapshot
    
    def _should_generate_commentary(self, observations: EventObservation) -> tuple:
        """Decide if narrator should speak (cooldown removed - always ready)"""
        # Don't speak if game hasn't started yet (day 0)
        if self.context.current_day == 0:
            return (False, CommentaryType.INSIGHT)
        
        # NO COOLDOWN - always ready to speak
        chosen_type = self._choose_segment_type(observations)
        self.log("ftb_narrator", f"Ready to speak - generating {chosen_type.value} commentary")
        return (True, chosen_type)
    
    def _generate_commentary(self, observations: EventObservation, commentary_type: CommentaryType) -> Optional[str]:
        """Generate narrator commentary using LLM"""
        prompt = self._build_prompt(observations, commentary_type)
        
        if not prompt or not self.call_llm:
            return None
        
        try:
            response = self.call_llm(
                model=self.model_name,
                prompt=prompt,
                max_tokens=200,
                temperature=0.7,
                timeout=30  # Increased timeout for narrator (runs async)
            )
            
            # ---- Bail out immediately if suspended during LLM call ----
            if self.suspended:
                self.log("ftb_narrator", "Suspended during LLM call – discarding response")
                return None
            
            # Extract text
            if isinstance(response, dict):
                text = response.get("response", "") or response.get("text", "")
            else:
                text = str(response)
            
            text = text.strip()
            
            # Debug logging for empty responses
            if len(text) == 0:
                self.log("ftb_narrator", f"WARNING: LLM returned empty text. Response type: {type(response)}, Response: {response}")
                return None
            
            if len(text) < 20:
                self.log("ftb_narrator", f"WARNING: LLM text too short ({len(text)} chars): {text[:50]}")
                return None
            
            # Remove JSON formatting if present
            if text.startswith('{'):
                import json
                try:
                    parsed = json.loads(text)
                    text = parsed.get("text", text)
                except:
                    pass
            
            # Update segment history after successful generation
            self._update_segment_history(commentary_type)
            self.log("ftb_narrator", f"Generated {commentary_type.value} segment (use count: {self.context.segment_history.get(commentary_type.value, {}).get('use_count', 1)})")
            
            return text
            
        except Exception as e:
            self.log("ftb_narrator", f"LLM generation error: {e}")
            return None
    
    def _build_prompt(self, observations: EventObservation, commentary_type: CommentaryType) -> str:
        """Build LLM prompt for commentary generation - CONTINUITY-FIRST enhanced"""
        
        # Try to import narrative prompts
        try:
            from plugins import ftb_narrative_prompts
            use_narrative_prompts = True
        except ImportError:
            self.log("ftb_narrator", "WARNING: Could not import ftb_narrative_prompts, using legacy prompts")
            use_narrative_prompts = False
        
        # Check if this is batch mode (multi-day advance)
        is_batch = False
        batch_start_tick = None
        batch_end_tick = None
        if observations.high_priority_events or observations.player_team_events:
            first_event = (observations.high_priority_events + observations.player_team_events)[0]
            event_data = first_event.get('data', {})
            if event_data.get('_batch_mode'):
                is_batch = True
                batch_start_tick = event_data.get('_batch_start_tick')
                batch_end_tick = event_data.get('_batch_end_tick')
        
        # CONTINUITY-FIRST: Use narrative prompts if available
        if use_narrative_prompts:
            # Build context dict for narrative prompts
            ctx = self._build_context_dict(observations)
            
            # Get segment-specific prompt from original templates
            segment_specific_instruction = ""
            if ftb_segment_prompts:
                segment_specific_instruction = ftb_segment_prompts.get_segment_prompt(commentary_type.value)
            
            # Enhance with continuity layer
            if segment_specific_instruction:
                return ftb_narrative_prompts.enhance_segment_prompt(
                    commentary_type.value,
                    segment_specific_instruction,
                    ctx
                )
            else:
                # Use combined SPINE + BEAT prompt
                return ftb_narrative_prompts.build_combined_prompt(ctx)
        
        # FALLBACK: Legacy prompt system (if ftb_narrative_prompts not available)
        # Adjust system prompt for batch mode
        if is_batch:
            days_elapsed = batch_end_tick - batch_start_tick if batch_start_tick and batch_end_tick else 7
            system_prompt = f"""You are Jarvis, the AI companion to a racing team principal navigating the motorsport world.

The player just advanced {days_elapsed} days in a single batch. Your role:
- Provide a cohesive narrative summary of the period
- Synthesize multiple events into a compelling arc ("Over the past week..." or "This month saw...")
- Focus on key trends, major results, and strategic implications
- Tone: calm, analytical, storytelling
- Length: 3-4 sentences covering the full period

Create one unified commentary covering all events, not individual reactions."""
        else:
            system_prompt = """You are Jarvis, the AI companion to a racing team principal navigating the motorsport world.

Your role:
- Provide steady, insightful commentary on their journey
- Frame events in relation to player goals and challenges
- Offer perspective, not play-by-play
- Tone: calm, analytical, supportive, occasionally witty
- Length: 2-3 sentences maximum

You observe their world and offer guidance, recaps, insights, and strategic suggestions."""
        
        # Build context summary
        tier_names = {1: "Grassroots", 2: "Formula V", 3: "Formula X", 4: "Formula Y", 5: "Formula Z"}
        tier_name = tier_names.get(self.context.player_tier, f"Tier {self.context.player_tier}")
        
        context_str = f"""PLAYER CONTEXT:
Team: {self.context.player_team}
Tier: {tier_name}
Season: {self.context.current_season}, Day: {self.context.current_day}
Championship Position: {self.context.player_championship_position} | Points: {self.context.player_points}
Budget: ${self.context.player_budget:,}
Morale: {self.context.player_morale:.1f}/100 | Reputation: {self.context.player_reputation:.1f}/100
"""
        
        # Add active tab context
        if self.context.active_tab:
            context_str += f"\nCurrent View: {self.context.active_tab} tab\n"
        
        # RECENCY BOOST: Apply multipliers and sort by boosted priority
        events_str = ""
        if observations.has_significant_events():
            event_limit = 15 if is_batch else 5  # More events for batch summaries
            
            # Apply recency boost to get freshest events first
            boosted_events = self._apply_recency_boost_to_events(observations.player_team_events)
            boosted_events.sort(key=lambda e: e.get('priority', 50.0), reverse=True)
            
            events_str = f"\nRECENT EVENTS{' (BATCH)' if is_batch else ''}:\n"
            for event in boosted_events[:event_limit]:
                category = event.get('category', 'event')
                data = event.get('data', {})
                summary = data.get('summary', data.get('reason', 'Event occurred'))
                
                # Show recency indicator for debugging
                multiplier = event.get('_recency_multiplier', 1.0)
                freshness_marker = "🔥" if multiplier >= 1.5 else "⚡" if multiplier > 1.0 else ""
                
                events_str += f"- {freshness_marker}{category}: {summary}\n"
        
        # Add tab-specific data and instructions
        tab_specific_context = ""
        tab_specific_instruction = ""
        
        if commentary_type == CommentaryType.ROSTER_SUGGESTION:
            tab_specific_context = self._get_roster_context()
            tab_specific_instruction = "The player is viewing their team roster. Offer a specific recommendation about hiring, firing, or roster management. Reference actual available candidates or current team members if relevant."
        
        elif commentary_type == CommentaryType.FINANCIAL_INSIGHT:
            tab_specific_instruction = f"The player is reviewing finances. With a budget of ${self.context.player_budget:,}, offer insight on budget management, sponsorship opportunities, or financial strategy."
        
        elif commentary_type == CommentaryType.DEVELOPMENT_GUIDANCE:
            tab_specific_instruction = "The player is in the development screen. Offer guidance on car development priorities, infrastructure investment, or technical strategy for this tier."
        
        elif commentary_type == CommentaryType.STRATEGY_TIP:
            tab_specific_instruction = "The player is viewing race operations. Offer strategic advice about upcoming races, calendar management, or race weekend preparation."
        
        # Get segment-specific prompt from templates
        if ftb_segment_prompts:
            segment_prompt = ftb_segment_prompts.get_segment_prompt(commentary_type.value)
            if segment_prompt:
                tab_specific_instruction = segment_prompt
        
        # Fallback to legacy type instructions if no segment prompt
        if not tab_specific_instruction:
            type_instructions = {
                CommentaryType.INSIGHT: "Provide an insightful observation about the current situation. What pattern or opportunity do you notice?",
                CommentaryType.RECAP: "Provide a brief recap of where things stand. Summarize the current state and trajectory.",
                CommentaryType.SUGGESTION: "Offer a tactical or strategic suggestion. What should the player consider doing?",
                CommentaryType.TIP: "Share a piece of wisdom or general guidance about racing management.",
                CommentaryType.FORECAST: "Look ahead to upcoming events or challenges. What should the player prepare for?",
            }
            tab_specific_instruction = type_instructions.get(commentary_type, "Provide commentary.")
        
        instruction = tab_specific_instruction
        
        # Get comparative context (shows changes since last time this segment was used)
        comparative_context = self._get_comparative_context(commentary_type)
        
        return f"""{system_prompt}

{context_str}
{events_str}
{tab_specific_context}
{comparative_context}

SEGMENT TYPE: {commentary_type.value}
INSTRUCTION: {instruction}

Reply with ONLY the commentary text (2-3 sentences). Do not include labels, JSON, or metadata."""
    
    def _get_roster_context(self) -> str:
        """Query job board and free agents for roster suggestions"""
        if not ftb_state_db or not self.db_path:
            return ""
        
        try:
            # Query current roster
            roster = ftb_state_db.query_entities_by_team(self.db_path, self.context.player_team)
            
            # Query job board for visible opportunities
            job_listings = ftb_state_db.query_job_board(self.db_path, tier=self.context.player_tier)
            
            # Query top free agents in our tier
            free_agents = ftb_state_db.query_free_agents(self.db_path, tier=self.context.player_tier, limit=5)
            
            context = "\nROSTER CONTEXT:\n"
            
            # Summarize roster
            driver_count = len([e for e in roster if e['type'] == 'Driver'])
            engineer_count = len([e for e in roster if e['type'] == 'Engineer'])
            context += f"Current Roster: {driver_count} drivers, {engineer_count} engineers\n"
            
            # Highlight underperforming entities
            underperformers = [e for e in roster if e['overall'] < 45]
            if underperformers:
                context += f"Underperformers: "
                for entity in underperformers[:2]:
                    context += f"{entity['name']} ({entity['type']}, {entity['overall']:.0f} rating), "
                context = context.rstrip(', ') + "\n"
            
            # List top free agents
            if free_agents:
                context += "\nTOP FREE AGENTS:\n"
                for agent in free_agents[:3]:
                    affordable = "affordable" if agent['salary'] < self.context.player_budget * 0.1 else "expensive"
                    context += f"- {agent['role']}, age {agent['age']}, {agent['overall']:.0f} rating, ${agent['salary']:,}/yr ({affordable})\n"
            
            return context
            
        except Exception as e:
            self.log("ftb_narrator", f"Error fetching roster context: {e}")
            return ""
    
    def _should_broadcast_news(self) -> bool:
        """Check if it's time for a Formula Z news broadcast"""
        # Only broadcast Formula Z news if player is NOT in Formula Z (tier 5)
        if self.context.player_tier == 5:
            return False
        
        # Check timing (15-30 minutes since last broadcast for frequent news breaks)
        elapsed_minutes = (time.time() - self.last_news_broadcast_time) / 60
        if elapsed_minutes < 15:
            return False
        
        # Check if there's Formula Z race activity
        try:
            fz_leagues = ftb_state_db.query_league_standings(self.db_path, tier=5)
            if not fz_leagues:
                return False

            fz_standings = fz_leagues[0].get('standings', [])
            if len(fz_standings) < 3:
                return False
            
            # Broadcast on random intervals between 15-30 minutes
            if elapsed_minutes >= 30:
                return True
            
            # Probability increases with elapsed time
            probability = (elapsed_minutes - 15) / 15  # 0 at 15 minutes, 1 at 30 minutes
            return random.random() < probability * 0.4  # 40% chance in window
            
        except Exception as e:
            self.log("ftb_narrator", f"Error checking Formula Z data: {e}")
            return False
    
    def _generate_news_broadcast(self) -> Optional[str]:
        """Generate Formula Z championship news broadcast with dedicated news anchor personality
        
        CRITICAL: This method queries ONLY Formula Z (tier 5) data and NO player context.
        """
        try:
            # Query Formula Z standings ONLY (tier 5)
            fz_leagues = ftb_state_db.query_league_standings(self.db_path, tier=5)
            if not fz_leagues:
                return None

            fz_league = fz_leagues[0]
            fz_standings = fz_league.get('standings', [])
            if not fz_standings:
                return None
            
            league_id = fz_league.get('league_id')
            
            # ===== Query ONLY Formula Z data (NO player context) =====
            
            # 1. Get season/day from Formula Z race results (NOT from general game state)
            current_season = 1
            current_day = 0
            try:
                # Get most recent Formula Z race to determine current season
                recent_fz_race = ftb_state_db.query_race_results(
                    self.db_path,
                    league_ids=[league_id] if league_id else None,
                    limit=1
                )
                if recent_fz_race:
                    current_season = recent_fz_race[0].get('season', 1)
                    # Approximate day from round number (rough estimate)
                    round_num = recent_fz_race[0].get('round_number', 0)
                    current_day = round_num * 14  # Rough approximation
            except Exception:
                pass  # Use defaults if query fails
            
            # 2. Get all Formula Z teams with full details (tier 5 ONLY)
            fz_teams = []
            budget_map = {}
            try:
                teams = ftb_state_db.query_all_teams(self.db_path, league_id=league_id) if league_id else ftb_state_db.query_all_teams(self.db_path)
                # Filter to tier 5 teams only
                fz_teams = [t for t in teams if t.get('tier') == 5]
                budget_map = {t.get('name'): t.get('budget', 0) for t in fz_teams}
            except Exception as query_err:
                self.log("ftb_narrator", f"Error querying FZ teams: {query_err}")
            
            # 3. Get all drivers for each Formula Z team (ONLY tier 5 teams)
            driver_roster_map = {}  # team_name -> list of driver dicts
            all_fz_drivers = []
            for team_name in [team.get('team') or team.get('name') for team in fz_standings[:12]]:
                try:
                    entities = ftb_state_db.query_entities_by_team(self.db_path, team_name)
                    drivers = [e for e in entities if e.get('type') == 'driver']
                    driver_roster_map[team_name] = drivers
                    all_fz_drivers.extend(drivers)
                except Exception as driver_err:
                    self.log("ftb_narrator", f"Error querying drivers for {team_name}: {driver_err}")
                    driver_roster_map[team_name] = []
            
            # 4. Query recent Formula Z race results (tier 5 ONLY, last 3 races)
            race_results = []
            try:
                race_results = ftb_state_db.query_race_results(
                    self.db_path,
                    seasons=[current_season],
                    league_ids=[league_id] if league_id else None,
                    limit=3
                )
            except Exception as race_err:
                self.log("ftb_narrator", f"Error querying FZ race results: {race_err}")
            
            # 5. Query recent Formula Z events for additional context (tier 5 ONLY)
            recent_events = []
            try:
                recent_events = ftb_state_db.query_tier_events(self.db_path, tier=5, limit=10)
            except Exception:
                recent_events = []
            
            # ===== Build enriched prompt with real data =====
            
            # Standings with driver names
            standings_text = "FORMULA Z CHAMPIONSHIP STANDINGS:\n"
            for i, team in enumerate(fz_standings[:8]):
                team_name = team.get('team', 'Unknown')
                points = team.get('points', 0)
                budget = budget_map.get(team_name, 0)
                drivers = driver_roster_map.get(team_name, [])
                driver_names = [d.get('name', 'Unknown') for d in drivers[:2]]  # Top 2 drivers
                
                standings_text += f"{i+1}. {team_name}: {points} pts"
                if driver_names:
                    standings_text += f" (Drivers: {', '.join(driver_names)})"
                if budget > 0:
                    standings_text += f" [${budget:,.0f}]"
                standings_text += "\n"
            
            # Recent race results with driver names and positions
            race_text = ""
            if race_results:
                race_text = "\nRECENT RACE RESULTS:\n"
                for race in race_results[:2]:  # Last 2 races
                    track = race.get('track_name', 'Unknown')
                    round_num = race.get('round_number', '?')
                    finish_positions = race.get('finish_positions', [])
                    
                    race_text += f"Round {round_num} ({track}):\n"
                    for pos in finish_positions[:5]:  # Top 5 finishers
                        driver_name = pos.get('driver', 'Unknown')
                        team_name = pos.get('team', 'Unknown')
                        position = pos.get('position', '?')
                        race_text += f"  P{position}: {driver_name} ({team_name})\n"
                    
                    # Add fastest lap holder if available
                    fastest_lap = race.get('fastest_lap_holder')
                    if fastest_lap:
                        race_text += f"  Fastest Lap: {fastest_lap}\n"
            
            # Driver spotlight (top performers from race data)
            driver_spotlight = ""
            if race_results:
                # Collect podium finishers
                podium_drivers = set()
                for race in race_results:
                    for pos in race.get('finish_positions', [])[:3]:
                        driver_name = pos.get('driver')
                        if driver_name:
                            podium_drivers.add(driver_name)
                
                if podium_drivers:
                    driver_spotlight = f"\nRECENT PODIUM DRIVERS: {', '.join(list(podium_drivers)[:6])}\n"
            
            # Add recent events context
            events_text = ""
            if recent_events:
                events_text = "\nRECENT FORMULA Z ACTIVITY:\n"
                for event in recent_events[:4]:
                    evt_data = event.get('data', {})
                    summary = evt_data.get('summary', '')
                    if summary:
                        events_text += f"- {summary}\n"
            
            prompt = f"""You are the Formula Z News Anchor - a dedicated motorsport journalist covering the elite Formula Z championship. 
Your personality: Sharp, enthusiastic, plugged into the paddock gossip, and passionate about the sport's biggest stories.

Your style:
- Jump right into the juicy scoop
- Use punchy, energetic language
- Reference specific teams AND DRIVERS by name (they are real - use them!)
- Hint at drama and intrigue when present
- Professional but with personality

CRITICAL RESTRICTIONS:
- NEVER refer to "the player", "you", "your", or address the listener directly
- This is an OBJECTIVE news broadcast about Formula Z, NOT commentary about anyone's personal journey
- Report on teams and drivers in third person only (e.g., "Red Bull Racing is...", "Hamilton has...", etc.)
- You are a journalist reporting NEWS, not a companion or advisor

CHAMPIONSHIP STATUS:
Season {current_season}, Day {current_day}

{standings_text}
{race_text}
{driver_spotlight}
{events_text}

CRITICAL: ALL driver names and team names above are REAL entities from the database. Reference them directly - do NOT make up names.

TASK: Deliver a breaking Formula Z news update (2-3 sentences, 50-80 words). 

Pick ONE hot storyline from the REAL data above:
- Specific driver's recent race performance (podium, win, crash)
- Championship battle between specific teams
- Driver lineup changes or team struggles
- Race result implications for standings
- Budget disparities affecting competition

Open with energy ("Breaking from Formula Z...", "Hot news from the top tier...", etc.) then reference SPECIFIC driver/team names from the data.

Reply with ONLY the news update text."""

            response = self.call_llm(
                model=self.model_name,
                prompt=prompt,
                max_tokens=150,
                temperature=0.75  # Slightly lower to stay grounded in facts
            )
            
            # Extract text
            if isinstance(response, dict):
                text = response.get("response", "") or response.get("text", "")
            else:
                text = str(response)
            
            text = text.strip()
            if len(text) < 30:
                return None
            
            # Remove JSON formatting if present
            if text.startswith('{'):
                import json
                try:
                    parsed = json.loads(text)
                    text = parsed.get("text", text)
                except:
                    pass
            
            # Log enriched data for debugging
            self.log("ftb_narrator", f"Formula Z broadcast generated with {len(all_fz_drivers)} drivers across {len(driver_roster_map)} teams, {len(race_results)} recent races")
            
            return text
            
        except Exception as e:
            self.log("ftb_narrator", f"Error generating news broadcast: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _validate_news_broadcast(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validate news broadcast for hallucinated driver/team names.
        Returns (is_valid, list_of_violations)
        """
        violations = []
        text_lower = text.lower()
        
        # CHECK 1: Reject player references or second-person language
        player_reference_patterns = [
            r'\bplayer\b',
            r'\byou\b',
            r'\byour\b',
            r'\byou\'re\b',
            r'\byou\'ve\b',
            r'\byou\'ll\b'
        ]
        
        for pattern in player_reference_patterns:
            if re.search(pattern, text_lower):
                violations.append(f"News anchor must not refer to player/listener (found pattern: {pattern})")
        
        # CHECK 2: Get entity allowlist (all known teams and drivers)
        entity_allowlist = self._get_entity_allowlist()
        
        # Extract capitalized words that look like proper nouns (potential names)
        # More aggressive pattern to catch first+last names
        potential_names = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        
        # Filter out common words and known acceptable terms
        common_racing_terms = {
            'Formula', 'Championship', 'Breaking', 'Hot', 'News', 'Season', 'Day',
            'Budget', 'Points', 'Team', 'Driver', 'Race', 'Podium', 'Grand', 'Prix',
            'Motorsport', 'Tier', 'League', 'Circuit', 'Track', 'Lap', 'Standings',
            'Performance', 'Victory', 'Win', 'Battle', 'Championship', 'Manager',
            'Fastest', 'Position', 'P1', 'P2', 'P3', 'Round', 'Paddock', 'Elite',
            'Top', 'Point', 'Gap', 'Lead', 'Contender', 'Rival', 'Pace',
            'Meanwhile', 'However', 'Despite', 'After', 'During', 'Before',
            'The', 'A', 'An', 'In', 'On', 'At', 'With', 'From', 'To', 'For'
        }
        
        for name in potential_names:
            # Skip common terms
            if name in common_racing_terms:
                continue
            
            # Split multi-word names and check each part
            name_parts = name.split()
            for part in name_parts:
                if part in common_racing_terms:
                    continue
                
                # Check if this name part exists in entity allowlist
                # Case-insensitive partial match (accounts for team suffixes like "Racing")
                found = False
                for entity in entity_allowlist:
                    if part.lower() in entity.lower() or entity.lower() in part.lower():
                        found = True
                        break
                
                if not found:
                    # Potential hallucination - unknown name
                    violations.append(f"Unknown entity mentioned: '{name}' (part: '{part}')")
        
        # Additional check: flag generic driver placeholders
        placeholder_patterns = [
            r'\bdriver\s+\w+\b',  # "driver X"
            r'\bteam\s+\w+\b',    # "team X"
            r'\b[A-Z]\.\s*[A-Z]\.\b'  # Initials like "J.S."
        ]
        
        for pattern in placeholder_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                matches = re.findall(pattern, text, re.IGNORECASE)
                violations.append(f"Generic placeholder detected: {matches}")
        
        # Fuzzy mode: Allow up to 1 minor violation (e.g., one uncommon surname)
        # This prevents false positives from legitimate but unusual names
        # BUT: Player reference violations are ALWAYS rejected (checked first)
        if len(violations) <= 1 and not any('player/listener' in v for v in violations):
            return (True, [])
        
        return (len(violations) == 0, violations)
    
    def _calculate_state_changes(self) -> Dict[str, Any]:
        """Calculate state changes since last snapshot for heat calculation"""
        current = {
            'budget': self.context.player_budget,
            'morale': self.context.player_morale,
            'position': self.context.player_championship_position,
            'points': self.context.player_points
        }
        
        changes = {
            'budget_delta': current['budget'] - self.last_state_snapshot['budget'],
            'morale_delta': current['morale'] - self.last_state_snapshot['morale'],
            'position_delta': self.last_state_snapshot['position'] - current['position'],  # Lower is better
            'points_delta': current['points'] - self.last_state_snapshot['points']
        }
        
        # Update snapshot
        self.last_state_snapshot = current
        
        return changes
    
    def _gather_game_state(self) -> Dict[str, Any]:
        """Gather verified game state for truth validation"""
        game_state = {
            'budget': self.context.player_budget,
            'morale': self.context.player_morale,
            'position': self.context.player_championship_position,
            'points': self.context.player_points,
            'day': self.context.current_day,
            'season': self.context.current_season,
            'known_teams': [self.context.player_team],
            'team_budgets': {},
            'entity_allowlist': self._get_entity_allowlist()  # Database-driven entity names
        }
        
        # Try to get other teams for validation
        if ftb_state_db and self.db_path:
            try:
                teams = ftb_state_db.query_all_teams(self.db_path)
                if teams:
                    game_state['known_teams'].extend([t['name'] for t in teams if t['name'] != self.context.player_team])
                    game_state['team_budgets'] = {t['name']: t['budget'] for t in teams}
            except Exception as e:
                self.log("ftb_narrator", f"Error gathering team data for truth validation: {e}")
        
        return game_state
    
    def _validate_and_enforce_continuity(self, text: str, commentary_type: CommentaryType, observations: EventObservation, max_retries: int = 2) -> Optional[str]:
        """
        CONTINUITY-FIRST: Validate text for continuity, claims, stakes, and advisory language.
        TRUTH-FIRST: Reject any hallucinations or invented facts.
        Regenerate if needed.
        """
        # ---- Bail immediately if suspended ----
        if self.suspended:
            return None
        
        # Import narrative prompts
        try:
            from plugins import ftb_narrative_prompts
        except ImportError:
            self.log("ftb_narrator", "WARNING: Could not import ftb_narrative_prompts, skipping continuity enforcement")
            return text
        
        # REMOVED: Truth validation - it was too aggressive and rejected valid driver names
        # The LLM now receives comprehensive database facts and should stay grounded naturally
        
        # 1. Check for banned advisory language (HARD BAN)
        advisory_violations = self._detect_advisory_language(text)
        if advisory_violations and max_retries > 0:
            self.log("ftb_narrator", f"REGENERATE: Advisory language detected: {advisory_violations}")
            # Regenerate with explicit ban
            advisory_prompt = f"""The following narration contains BANNED advisory language:
"{text}"

Violations: {', '.join(advisory_violations)}

BANNED PHRASES: "consider", "focus", "remember", "you should", "make sure", "be sure to", "it's essential", "it's important"

REWRITE without advisory language. Use stakes language instead:
- Wagers ("if you push, someone snaps")
- Aphorisms ("this is where seasons die quietly")
- Prophecy ("the bill arrives later")
- Blame/praise ("that was brave; it was expensive")

OUTPUT ONLY THE REWRITTEN NARRATION—no explanations, no meta-commentary.
"""
            try:
                response = self.call_llm(
                    model=self.model_name,
                    prompt=advisory_prompt + "\n\n" + self._build_context_for_regeneration(observations),
                    max_tokens=200,
                    temperature=0.75,
                    timeout=30
                )
                if isinstance(response, dict):
                    text = response.get("response", "") or response.get("text", "")
                else:
                    text = str(response).strip()
                
                # Strip meta-commentary patterns
                text = self._strip_meta_commentary(text)
                
                # Retry validation
                return self._validate_and_enforce_continuity(text, commentary_type, observations, max_retries - 1)
            except Exception as e:
                self.log("ftb_narrator", f"Advisory language regeneration failed: {e}")
                # Fall through with cleaned text
                text = self._strip_advisory_language(text)
        
        # 2. Check for bare numbers without stakes
        bare_numbers = self._detect_bare_numbers(text)
        if bare_numbers and max_retries > 0:
            self.log("ftb_narrator", f"REGENERATE: Bare numbers without stakes: {bare_numbers}")
            # Regenerate with stakes instruction
            stakes_prompt = f"""The following narration contains numbers without stakes context:
"{text}"

Problematic numbers: {', '.join(bare_numbers)}

REWRITE INSTRUCTIONS:
Every number must carry stakes by functioning as COMPARISON, CONSEQUENCE, or THRESHOLD.

- COMPARISON: relative position ("less than rivals", "closer to the bottom")
- CONSEQUENCE: risk/pressure ("one incident from insolvency", "too thin to absorb mistakes")  
- THRESHOLD: regime change ("below where morale fractures", "past the point upgrades pay back")

OUTPUT ONLY THE REWRITTEN NARRATION. Do NOT include:
- "Based on our discussion" or "I see what's happening"
- "Let me rewrite" or explanations of your changes
- Meta-commentary about the task or rules

Example:
Bad: "I'll rewrite this to add stakes. The team has $50K..."
Good: "With $50K left—barely enough runway for two races—the pressure mounts."

OUTPUT ONLY THE NARRATION:
"""
            try:
                response = self.call_llm(
                    model=self.model_name,
                    prompt=stakes_prompt + "\n\n" + self._build_context_for_regeneration(observations),
                    max_tokens=200,
                    temperature=0.75,
                    timeout=30
                )
                if isinstance(response, dict):
                    text = response.get("response", "") or response.get("text", "")
                else:
                    text = str(response).strip()
                
                # Strip meta-commentary patterns
                text = self._strip_meta_commentary(text)
                
                # Retry validation (but don't recurse on bare numbers again to avoid infinite loop)
                return self._validate_and_enforce_continuity(text, commentary_type, observations, max_retries - 1)
            except Exception as e:
                self.log("ftb_narrator", f"Stakes regeneration failed: {e}")
                # Fall through with original text
        
        # 3. Check claim repetition (Said-It Tax)
        is_valid, claim_violations = self.claim_tracker.validate_repetition(text)
        if not is_valid and max_retries > 0:
            self.log("ftb_narrator", f"REGENERATE: Claim repetition detected: {claim_violations}")
            # Regenerate with escalation instruction
            escalation_prompt = f"""The following narration repeats prior claims without escalation:
"{text}"

Repetitions: {', '.join(claim_violations)}

REWRITE to escalate using comparison (was/now), consequence (means/leads to), or threshold language.

OUTPUT ONLY THE REWRITTEN NARRATION—no explanations, no meta-commentary.
"""
            try:
                response = self.call_llm(
                    model=self.model_name,
                    prompt=escalation_prompt + "\n\n" + self._build_context_for_regeneration(observations),
                    max_tokens=200,
                    temperature=0.75,
                    timeout=30
                )
                if isinstance(response, dict):
                    text = response.get("response", "") or response.get("text", "")
                else:
                    text = str(response).strip()
                
                # Strip meta-commentary patterns
                text = self._strip_meta_commentary(text)
                
                # Retry validation
                return self._validate_and_enforce_continuity(text, commentary_type, observations, max_retries - 1)
            except Exception as e:
                self.log("ftb_narrator", f"Regeneration failed: {e}")
                # Fall through with original text
        
        # 3. Check continuity (must reference prior message)
        if self.context.last_generated_spine and max_retries > 0:
            # Simple heuristic: check if text shares entity name, or uses linking words
            has_continuity = self._check_continuity(text, self.context.last_generated_spine)
            if not has_continuity:
                self.log("ftb_narrator", f"REGENERATE: No continuity with prior message")
                required_element = self.context.open_loop or self.context.current_motif or "the team's current situation"
                
                try:
                    regen_prompt = ftb_narrative_prompts.build_continuity_fix_prompt(
                        text,
                        required_element,
                        self._build_context_dict(observations)
                    )
                    response = self.call_llm(
                        model=self.model_name,
                        prompt=regen_prompt,
                        max_tokens=200,
                        temperature=0.75,
                        timeout=30
                    )
                    if isinstance(response, dict):
                        text = response.get("response", "") or response.get("text", "")
                    else:
                        text = str(response).strip()
                    
                    # Strip meta-commentary patterns
                    text = self._strip_meta_commentary(text)
                    
                    # Retry validation
                    return self._validate_and_enforce_continuity(text, commentary_type, observations, max_retries - 1)
                except Exception as e:
                    self.log("ftb_narrator", f"Continuity regeneration failed: {e}")
        
        # 4. Record claims from valid text
        self.claim_tracker.record_claims(text)
        
        return text
    
    def _check_continuity(self, new_text: str, prior_text: str) -> bool:
        """Simple heuristic to check if new text has continuity with prior"""
        new_lower = new_text.lower()
        prior_lower = prior_text.lower()
        
        # Check for linking words
        linking_words = ['still', 'now', 'but', 'that', 'which', 'this', 'it', 'continues', 'remains']
        has_linking = any(word in new_lower for word in linking_words)
        
        # Check for shared entity names (extract capitalized words)
        import re
        prior_entities = set(re.findall(r'\b[A-Z][a-z]+\b', prior_text))
        new_entities = set(re.findall(r'\b[A-Z][a-z]+\b', new_text))
        has_shared_entity = len(prior_entities & new_entities) > 0
        
        # Check for motif/open loop reference
        has_motif = self.context.current_motif.lower() in new_lower
        has_loop = self.context.open_loop and self.context.open_loop.lower() in new_lower
        
        return has_linking or has_shared_entity or has_motif or has_loop
    
    def _gather_game_facts(self) -> Dict[str, Any]:
        """Query comprehensive game state from database for fact-based narration.
        
        Returns dict with all available game data to ground LLM generations in truth.
        """
        if not ftb_state_db or not self.db_path:
            return {}
        
        facts = {}
        
        try:
            # Player state
            player_state = ftb_state_db.query_player_state(self.db_path)
            facts['player'] = player_state or {}
            
            # Game state for season context
            try:
                game_state = ftb_state_db.query_game_state(self.db_path)
                if game_state:
                    facts['current_season'] = game_state.get('season', 1)
                    facts['current_day'] = game_state.get('day', 0)
                    races_completed = game_state.get('races_completed_this_season', 0)
                else:
                    races_completed = 0
                    facts['current_season'] = 1
                    facts['current_day'] = 0
            except Exception as e:
                self.log("ftb_narrator", f"Error querying game state: {e}")
                races_completed = 0
                facts['current_season'] = 1
                facts['current_day'] = 0

            # Prefer player league race count for season progress
            try:
                player_league_id = None
                player_tier = None
                if player_state:
                    player_league_id = player_state.get('league_id')
                    player_tier = player_state.get('tier')

                if player_league_id:
                    results = ftb_state_db.query_race_results(
                        self.db_path,
                        seasons=[facts['current_season']],
                        league_ids=[player_league_id]
                    )
                    races_completed = len(results)

                facts['races_completed'] = races_completed

                # Set tier-based season length (10/14/24)
                if player_tier == 5:
                    facts['total_races'] = 24
                elif player_tier == 4:
                    facts['total_races'] = 14
                else:
                    facts['total_races'] = 10
            except Exception as e:
                self.log("ftb_narrator", f"Error determining season progress: {e}")
                facts['races_completed'] = races_completed
                facts['total_races'] = 16
            
            # total_races is set from tier-based season length above
            
            # Player roster
            try:
                roster = ftb_state_db.query_entities_by_team(self.db_path, self.context.player_team)
                facts['roster'] = roster
                facts['roster_summary'] = {
                    'drivers': [e for e in roster if e['type'] == 'Driver'],
                    'engineers': [e for e in roster if e['type'] == 'Engineer'],
                    'mechanics': [e for e in roster if e['type'] == 'Mechanic']
                }
            except Exception as e:
                self.log("ftb_narrator", f"Error querying roster: {e}")
                facts['roster'] = []
                facts['roster_summary'] = {'drivers': [], 'engineers': [], 'mechanics': []}
            
            # All teams (league-scoped for fair comparisons)
            try:
                # First, get player's team to find their league_id
                all_teams_global = ftb_state_db.query_all_teams(self.db_path)
                player_team_data = next((t for t in all_teams_global if t['name'] == self.context.player_team), None)
                
                if player_team_data and player_team_data.get('league_id'):
                    # Query teams in player's league only
                    league_teams = ftb_state_db.query_all_teams(self.db_path, league_id=player_team_data['league_id'])
                    facts['all_teams'] = league_teams
                    facts['rival_teams'] = [t for t in league_teams if t['name'] != self.context.player_team]
                else:
                    # Fallback: use all teams if player's league can't be determined
                    facts['all_teams'] = all_teams_global
                    facts['rival_teams'] = [t for t in all_teams_global if t['name'] != self.context.player_team]

                # Tier baseline (tier-weighted average using teams in player's tier)
                player_tier = None
                if player_team_data:
                    player_tier = player_team_data.get('tier') or player_team_data.get('tier_number')
                if player_tier is None:
                    player_tier = self.context.player_tier

                tier_teams = [
                    t for t in all_teams_global
                    if (t.get('tier') or t.get('tier_number')) == player_tier
                ]
                if not tier_teams:
                    tier_teams = facts.get('all_teams', [])

                baseline_keys = ["budget", "points", "morale", "reputation", "media_standing"]
                baseline = {}
                for key in baseline_keys:
                    values = [t.get(key) for t in tier_teams if isinstance(t.get(key), (int, float))]
                    if values:
                        baseline[key] = sum(values) / len(values)

                facts['league_baseline'] = baseline

                comparison = {}
                if player_team_data:
                    for key, avg in baseline.items():
                        value = player_team_data.get(key)
                        if isinstance(value, (int, float)) and avg:
                            delta_pct = ((value - avg) / avg) * 100.0
                            comparison[key] = {
                                'value': value,
                                'avg': avg,
                                'delta_pct': delta_pct
                            }
                facts['league_baseline_comparison'] = comparison
            except Exception as e:
                self.log("ftb_narrator", f"Error querying teams: {e}")
                facts['all_teams'] = []
                facts['rival_teams'] = []
                facts['league_baseline'] = {}
                facts['league_baseline_comparison'] = {}
            
            # League standings
            try:
                standings = ftb_state_db.query_league_standings(self.db_path)
                facts['standings'] = standings
            except Exception as e:
                self.log("ftb_narrator", f"Error querying standings: {e}")
                facts['standings'] = []
            
            # Upcoming calendar
            try:
                current_day = self.context.current_day
                calendar = ftb_state_db.query_calendar_window(self.db_path, current_day, current_day + 7)
                facts['upcoming_calendar'] = calendar[:5]  # Top 5 soonest
            except Exception as e:
                self.log("ftb_narrator", f"Error querying calendar: {e}")
                facts['upcoming_calendar'] = []
            
            # Job market
            try:
                job_board = ftb_state_db.query_job_board(self.db_path, tier=self.context.player_tier)
                facts['job_board'] = job_board[:10]  # Top 10 listings
            except Exception as e:
                self.log("ftb_narrator", f"Error querying job board: {e}")
                facts['job_board'] = []
            
            # Free agents
            try:
                free_agents = ftb_state_db.query_free_agents(self.db_path, tier=self.context.player_tier, limit=10)
                facts['free_agents'] = free_agents
            except Exception as e:
                self.log("ftb_narrator", f"Error querying free agents: {e}")
                facts['free_agents'] = []
            
            # Sponsorships (with behavioral profiles)
            try:
                sponsors = ftb_state_db.query_sponsorships(self.db_path, team_name=self.context.player_team)
                facts['sponsors'] = sponsors
            except Exception as e:
                self.log("ftb_narrator", f"Error querying sponsorships: {e}")
                facts['sponsors'] = []
            
            # Folded teams (paddock graveyard)
            try:
                folded = ftb_state_db.query_folded_teams(self.db_path, limit=5)
                facts['folded_teams'] = folded
            except Exception as e:
                self.log("ftb_narrator", f"Error querying folded teams: {e}")
                facts['folded_teams'] = []
            
            # Penalties (player team)
            try:
                penalties = ftb_state_db.query_penalties(self.db_path, team_name=self.context.player_team, limit=5)
                facts['penalties'] = penalties
            except Exception as e:
                self.log("ftb_narrator", f"Error querying penalties: {e}")
                facts['penalties'] = []
            
            # League economic state (sponsor market health)
            try:
                econ_state = ftb_state_db.query_league_economic_state(self.db_path)
                facts['economic_state'] = econ_state
            except Exception as e:
                self.log("ftb_narrator", f"Error querying economic state: {e}")
                facts['economic_state'] = None
            
            # Action-required calendar items (decision inbox)
            try:
                decision_items = ftb_state_db.query_decision_inbox(self.db_path)
                filtered = []
                for item in decision_items:
                    if item.get('category') != 'personnel':
                        filtered.append(item)
                        continue
                    metadata = item.get('metadata', {})
                    team = metadata.get('team') or metadata.get('team_name')
                    if team and team == self.context.player_team:
                        filtered.append(item)
                facts['decision_inbox'] = filtered
            except Exception as e:
                self.log("ftb_narrator", f"Error querying decision inbox: {e}")
                facts['decision_inbox'] = []
            
        except Exception as e:
            self.log("ftb_narrator", f"Error in _gather_game_facts: {e}")
        
        return facts
    
    def _calculate_event_recency_multiplier(self, event: dict) -> float:
        """
        RECENCY BOOST: Calculate priority multiplier based on event tick age
        
        Multipliers:
        - tick_age = 0 (this tick): 2.0x
        - tick_age ≤ 2: 1.5x
        - tick_age ≤ 5: 1.2x
        - tick_age ≤ 10: 1.0x (baseline)
        - tick_age > 10: 0.5x (should be purged, but handle gracefully)
        """
        event_tick = event.get('tick', 0)
        current_tick = self.context.current_tick
        tick_age = current_tick - event_tick
        
        if tick_age == 0:
            return 2.0
        elif tick_age <= 2:
            return 1.5
        elif tick_age <= 5:
            return 1.2
        elif tick_age <= 10:
            return 1.0
        else:
            return 0.5  # Stale event
    
    def _apply_recency_boost_to_events(self, events: List[dict]) -> List[dict]:
        """Apply recency multipliers to event priorities (creates augmented copies)"""
        boosted_events = []
        
        for event in events:
            # Create shallow copy to avoid mutating original
            boosted = event.copy()
            
            # Calculate recency multiplier
            multiplier = self._calculate_event_recency_multiplier(event)
            
            # Apply to priority
            base_priority = event.get('priority', 50.0)
            boosted['priority'] = base_priority * multiplier
            boosted['_recency_multiplier'] = multiplier  # Track for debugging
            
            boosted_events.append(boosted)
        
        return boosted_events
    
    def _build_context_dict(self, observations: EventObservation) -> dict:
        """Build context dictionary for narrative prompts"""
        # RECENCY BOOST: Apply multipliers to all events before building context
        high_priority_boosted = self._apply_recency_boost_to_events(observations.high_priority_events)
        player_team_boosted = self._apply_recency_boost_to_events(observations.player_team_events)
        
        # Sort by boosted priority to get freshest/most important events first
        high_priority_boosted.sort(key=lambda e: e.get('priority', 50.0), reverse=True)
        player_team_boosted.sort(key=lambda e: e.get('priority', 50.0), reverse=True)
        
        newest_event = ""
        if high_priority_boosted:
            evt = high_priority_boosted[0]
            newest_event = evt.get('event_type', '') + ": " + str(evt.get('data', {}))
        elif player_team_boosted:
            evt = player_team_boosted[0]
            newest_event = evt.get('event_type', '') + ": " + str(evt.get('data', {}))
        
        # CALENDAR INTEGRATION: Query upcoming events for time-aware commentary
        upcoming_events = self._query_upcoming_calendar(days_ahead=7)
        upcoming_summary = self._format_upcoming_events(upcoming_events)
        
        # DATABASE-DRIVEN: Gather comprehensive game facts for grounded generation
        game_facts = self._gather_game_facts()
        
        return {
            'last_generated_spine': self.context.last_generated_spine,
            'current_motif': self.context.current_motif,
            'open_loop': self.context.open_loop,
            'tone': self.context.tone,
            'named_focus': self.context.named_focus,
            'our_team_name': self.context.player_team,
            'budget': self.context.player_budget,
            'morale': self.context.player_morale,
            'position': self.context.player_championship_position,
            'stakes_axis': self.context.stakes_axis,
            'newest_event': newest_event,
            'upcoming_events': upcoming_summary,
            'state_summary': f"Day {self.context.current_day}, Season {self.context.current_season}, P{self.context.player_championship_position}/16, ${self.context.player_budget:,}, Morale {self.context.player_morale:.0f}%",
            'game_facts': game_facts  # Add comprehensive DB query results
        }
    
    def _build_context_for_regeneration(self, observations: EventObservation) -> str:
        """Build context string for regeneration prompts"""
        ctx = self._build_context_dict(observations)
        return f"""
Current state: {ctx['state_summary']}
Motif: {ctx['current_motif']}
Open loop: {ctx['open_loop']}
Tone: {ctx['tone']}
Recent event: {ctx['newest_event']}
"""
    
    def _query_upcoming_calendar(self, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """Query upcoming calendar events for narrative context"""
        if not ftb_state_db or not self.db_path:
            return []
        
        try:
            current_day = self.context.current_day
            entries = ftb_state_db.query_calendar_window(
                self.db_path,
                current_day,
                current_day + days_ahead
            )
            filtered = []
            for entry in entries:
                if entry.get('category') != 'personnel':
                    filtered.append(entry)
                    continue
                metadata = entry.get('metadata', {})
                team = metadata.get('team') or metadata.get('team_name')
                if team and team == self.context.player_team:
                    filtered.append(entry)
            entries = filtered
            # Return top 5 by priority
            entries.sort(key=lambda e: e.get('priority', 50), reverse=True)
            return entries[:5]
        except Exception as e:
            self.log("ftb_narrator", f"Error querying calendar: {e}")
            return []
    
    def _format_upcoming_events(self, events: List[Dict[str, Any]]) -> str:
        """Format upcoming events for inclusion in narrative prompts"""
        if not events:
            return "Nothing urgent on the horizon."
        
        current_day = self.context.current_day
        lines = []
        
        for event in events:
            days_until = event['entry_day'] - current_day
            if days_until == 0:
                when = "today"
            elif days_until == 1:
                when = "tomorrow"
            else:
                when = f"in {days_until} days"
            
            lines.append(f"- {event['title']} ({when})")
        
        return "Upcoming:\n" + "\n".join(lines)
    
    def _detect_advisory_language(self, text: str) -> List[str]:
        """Detect banned advisory language in text"""
        forbidden_phrases = [
            "you should", "you need to", "you must", "make sure", "be sure to",
            "consider", "focus on", "focus", "remember to", "remember",
            "it's essential", "it's important", "the optimal", "i recommend",
            "you'll want to"
        ]
        
        violations = []
        text_lower = text.lower()
        
        for phrase in forbidden_phrases:
            if phrase in text_lower:
                violations.append(phrase)
        
        return violations
    
    def _strip_advisory_language(self, text: str) -> str:
        """Remove advisory language from text (fallback cleanup)"""
        replacements = {
            "You should": "",
            "You need to": "",
            "Make sure": "",
            "Consider": "",
            "Focus on": "",
            "Remember to": "",
            "It's essential": "",
            "It's important": ""
        }
        
        cleaned = text
        for phrase, replacement in replacements.items():
            cleaned = cleaned.replace(phrase, replacement)
        
        return cleaned.strip()
    
    def _strip_meta_commentary(self, text: str) -> str:
        """
        Remove meta-commentary and LLM reasoning artifacts from regenerated text.
        The LLM sometimes outputs its thinking process instead of just the narration.
        """
        import re
        
        # Patterns that indicate meta-commentary (case-insensitive)
        meta_patterns = [
            r"(?i)^(Based on our discussion|I see what's happening|I didn't write this|Let me rewrite|I'll rewrite|I've identified that|To fix this|In this revised)",
            r"(?i)^(This text|The text|The following|In this rewritten version)",
            r"(?i)^(I understand|I can help|I will|I should|I need to)",
            r"(?i)^(Here's the|Here is the)",
            r"(?i)STAKES RULE|Bare Numbers? Detected|CONSEQUENCE|THRESHOLD|COMPARISON",
            r"(?i)\(revised\)|\(rewritten\)|\\n\\nExplanation:",
        ]
        
        cleaned = text
        
        # Remove lines that match meta-commentary patterns
        lines = cleaned.split('\n')
        filtered_lines = []
        skip_rest = False
        
        for line in lines:
            # Check if line is meta-commentary
            is_meta = any(re.match(pattern, line.strip()) for pattern in meta_patterns)
            
            # Skip lines that contain explanation markers
            if 'explanation:' in line.lower() or 'note:' in line.lower():
                skip_rest = True
                continue
            
            if skip_rest:
                continue
                
            if not is_meta and line.strip():
                filtered_lines.append(line)
        
        cleaned = '\n'.join(filtered_lines).strip()
        
        # Remove any remaining meta-commentary phrases mid-sentence
        for pattern in meta_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up resulting whitespace issues
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'\s+([.,;:])', r'\1', cleaned)
        
        return cleaned.strip()
    
    def _detect_bare_numbers(self, text: str) -> List[str]:
        """
        Detect numbers mentioned without stakes context.
        A number is "bare" if it appears without nearby comparison/consequence/threshold language.
        """
        import re
        
        bare_numbers = []
        
        # Stakes keywords that should be near numbers
        stakes_keywords = [
            'half of', 'twice', 'double', 'triple',  # Comparison multipliers
            'more than', 'less than', 'compared to', 'versus', 'than',  # Comparison
            'if', 'unless', 'when', 'until', 'away from', 'from',  # Consequence
            'below', 'above', 'under', 'over', 'threshold', 'breaking point',  # Threshold
            'enough for', 'covers', 'means', 'buys', 'costs',  # Consequence
            'was', 'now', 'up from', 'down from', 'changed',  # Temporal comparison
        ]
        
        # Find budget mentions: $XXX or $XX,XXX or $XXK or $XXM
        budget_pattern = r'\$\d+(?:,\d+)*(?:[KM])?'
        budget_matches = re.finditer(budget_pattern, text)
        
        for match in budget_matches:
            num_str = match.group()
            start = max(0, match.start() - 50)  # Look 50 chars before
            end = min(len(text), match.end() + 50)  # Look 50 chars after
            context_window = text[start:end].lower()
            
            # Check if stakes keywords are nearby
            has_stakes = any(keyword in context_window for keyword in stakes_keywords)
            
            if not has_stakes:
                bare_numbers.append(num_str)
        
        # Find percentage mentions: XX%
        percent_pattern = r'\d+(?:\.\d+)?%'
        percent_matches = re.finditer(percent_pattern, text)
        
        for match in percent_matches:
            num_str = match.group()
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context_window = text[start:end].lower()
            
            has_stakes = any(keyword in context_window for keyword in stakes_keywords)
            
            if not has_stakes:
                bare_numbers.append(num_str)
        
        return bare_numbers
    
    def _trigger_burst_mode(self, primary_text: str, commentary_type: CommentaryType, observations: EventObservation):
        """
        CONTINUITY-FIRST: Enter burst mode to generate 2-4 related segments rapidly.
        """
        self.in_burst_mode = True
        self.burst_sequence = [(primary_text, 85.0, commentary_type)]  # Primary segment at base priority
        
        # ---- Don't generate follow-ups if already suspended ----
        if self.suspended:
            return
        
        # Decide if we should generate follow-ups (every 3rd generation, or high-priority events)
        should_burst = (
            len(observations.high_priority_events) > 0 or
            random.random() < 0.33  # 33% chance on normal segments
        )
        
        if not should_burst:
            return
        
        # Generate 1-2 follow-up segments
        num_follow_ups = random.randint(1, 2)
        
        for i in range(num_follow_ups):
            # ---- Check suspension before each follow-up LLM call ----
            if self.suspended:
                self.log("ftb_narrator", f"Burst generation aborted (suspended) after {i} follow-ups")
                break

            try:
                # Build context for follow-up
                ctx = self._build_context_dict(observations)
                ctx['last_generated_spine'] = primary_text if i == 0 else self.burst_sequence[-1][0]
                
                # Import narrative prompts
                from plugins import ftb_narrative_prompts
                
                # Generate follow-up using combined prompt
                follow_up_prompt = ftb_narrative_prompts.build_combined_prompt(ctx)
                
                response = self.call_llm(
                    model=self.model_name,
                    prompt=follow_up_prompt,
                    max_tokens=200,
                    temperature=0.75,
                    timeout=30
                )
                
                # ---- Check suspension after LLM call returns ----
                if self.suspended:
                    self.log("ftb_narrator", f"Burst follow-up {i+1} discarded (suspended after LLM)")
                    break
                
                if isinstance(response, dict):
                    follow_up_text = response.get("response", "") or response.get("text", "")
                else:
                    follow_up_text = str(response).strip()
                
                # Parse SPINE: / BEAT: format if present
                if "SPINE:" in follow_up_text and "BEAT:" in follow_up_text:
                    import re
                    spine_match = re.search(r'SPINE:\s*(.+?)(?=BEAT:)', follow_up_text, re.DOTALL)
                    beat_match = re.search(r'BEAT:\s*(.+?)$', follow_up_text, re.DOTALL)
                    if spine_match and beat_match:
                        spine_text = spine_match.group(1).strip()
                        beat_text = beat_match.group(1).strip()
                        combined_text = f"{spine_text} {beat_text}"
                        follow_up_text = combined_text
                
                if len(follow_up_text) > 20:
                    # Validate follow-up
                    validated_text = self._validate_and_enforce_continuity(follow_up_text, commentary_type, observations, max_retries=1)
                    if validated_text:
                        # Add to burst sequence with incrementing priority (ensures ordering)
                        priority = 85.0 + (i + 1)
                        self.burst_sequence.append((validated_text, priority, commentary_type))
                        self.log("ftb_narrator", f"Burst follow-up {i+1}: {validated_text[:50]}...")
            
            except Exception as e:
                self.log("ftb_narrator", f"Burst follow-up {i+1} failed: {e}")
    
    def _enqueue_burst_sequence(self):
        """Enqueue all segments in burst sequence with proper priorities"""
        if not self.burst_sequence:
            return
        
        # ---- HARD GATE: discard burst if suspended during generation ----
        if self.suspended:
            self.log("ftb_narrator", f"BLOCKED burst enqueue of {len(self.burst_sequence)} segments (suspended/PBP)")
            self.burst_sequence = []
            self.in_burst_mode = False
            return
        
        self.log("ftb_narrator", f"Enqueueing burst sequence of {len(self.burst_sequence)} segments")
        
        for text, priority, commentary_type in self.burst_sequence:
            self._enqueue_audio_with_priority(text, commentary_type, priority)
        
        # Update show bible after burst
        if self.burst_sequence:
            last_text = self.burst_sequence[-1][0]
            self.context.last_generated_spine = last_text
        
        # Clear burst mode
        self.burst_sequence = []
        self.in_burst_mode = False
    
    def _enqueue_audio_with_priority(self, text: str, commentary_type: CommentaryType, priority: float = 85.0):
        """Enqueue commentary with custom priority"""
        # ---- HARD GATE: never enqueue while suspended (PBP mode) ----
        if self.suspended:
            self.log("ftb_narrator", f"BLOCKED enqueue (suspended/PBP): {commentary_type.value}")
            return

        if not self.db_enqueue or not self.db_connect or not self.voice_path:
            self.log("ftb_narrator", f"Would speak ({commentary_type.value}): {text}")
            return
        
        try:
            # Record topic to avoid repetition
            topic_hash = hash(text[:50])
            self.context.last_topics_discussed.append(topic_hash)
            
            # Choose voice based on commentary type
            voice_path = self.voice_path
            voice_name = "narrator"
            sfx_files = []
            
            # News broadcasts use different voice and newsflash sound effect
            if commentary_type == CommentaryType.FORMULA_Z_NEWS:
                # Use dedicated Formula Z news anchor voice with proper fallback chain
                news_voice_path = (
                    self.cfg.get("audio", {}).get("voices", {}).get("formula_z_news_anchor")
                    or self.cfg.get("audio", {}).get("voices", {}).get("formula_z_news")
                    or self.cfg.get("audio", {}).get("voices", {}).get("news_anchor")
                    or self.cfg.get("voices", {}).get("formula_z_news_anchor")
                    or self.news_anchor_voice_path
                    or self.voice_path  # Final fallback to narrator voice
                )
                voice_path = news_voice_path
                voice_name = "formula_z_news"
                
                self.log("ftb_narrator", f"Formula Z news using voice: {voice_path} (via {voice_name})")
                
                # Add newsflash sound effect (relative to station directory)
                station_dir = self.runtime.get('STATION_DIR', '.')
                newsflash_sfx = os.path.join(station_dir, 'audio', 'ui', 'newsflash.wav')
                if os.path.exists(newsflash_sfx):
                    sfx_files.append(newsflash_sfx)
                    self.log("ftb_narrator", f"Adding newsflash SFX: {newsflash_sfx}")
            
            # Build segment for audio system (matching db_enqueue_segment format)
            import time
            import hashlib
            
            seg_id = hashlib.sha1(f"ftb_narrator|{time.time()}|{text[:50]}".encode()).hexdigest()
            post_id = hashlib.sha1(f"ftb_narrator|{commentary_type.value}|{self.context.current_day}".encode()).hexdigest()
            
            segment = {
                "id": seg_id,
                "post_id": post_id,
                "source": "narrator",  # Changed from 'ftb_narrator' to avoid spoken prefix
                "event_type": f"narrator_{commentary_type.value}",
                "title": "",  # Empty - narration text is in body
                "body": text,  # The actual narration text
                "comments": [],
                "angle": "",  # Empty - not needed for literal segments
                "why": "",  # Empty - not needed for literal segments
                "key_points": [],  # Empty to avoid metadata being spoken
                "priority": priority,  # Custom priority for burst sequencing
                "host_hint": "announce",
                # Additional metadata for audio system
                "lead_voice": voice_name,
                "_voice": voice_name,
                "_voice_path": voice_path,
                "_literal": True,  # This is final narration text, don't reprocess
                "_sfx_files": sfx_files,  # Sound effects to play before narration
                "_metadata": {
                    "commentary_type": commentary_type.value,
                    "team": str(self.player_team),
                    "day": self.context.current_day
                }
            }
            
            # Open connection and enqueue
            conn = self.db_connect()
            try:
                self.db_enqueue(conn, segment)
                conn.close()
                self.log("ftb_narrator", f"Enqueued {commentary_type.value} [p={priority:.0f}]: {text[:60]}...")
            except Exception as e:
                conn.close()
                raise e
            
        except Exception as e:
            self.log("ftb_narrator", f"Error enqueueing audio: {e}")
            import traceback
            traceback.print_exc()
    
    
    def _check_live_race_broadcast(self):
        """
        Check if live race is streaming and generate broadcast commentary.
        This runs on a separate cadence from regular narrator commentary.
        """
        if not ftb_race_day or not ftb_broadcast_commentary:
            return
        
        try:
            # Get game state from DB
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if there's an active live race
            cursor.execute("""
                SELECT value FROM game_state 
                WHERE key = 'race_day_phase' AND game_id = ?
            """, (self.game_id,))
            phase_row = cursor.fetchone()
            
            if not phase_row:
                conn.close()
                return
            
            phase_str = phase_row[0]
            
            # Check if we're in RACE_RUNNING phase
            if 'RACE_RUNNING' not in phase_str:
                conn.close()
                return
            
            # Get current lap and recent events
            cursor.execute("""
                SELECT value FROM game_state 
                WHERE key = 'race_day_current_lap' AND game_id = ?
            """, (self.game_id,))
            lap_row = cursor.fetchone()
            current_lap = int(lap_row[0]) if lap_row else 0
            
            cursor.execute("""
                SELECT value FROM game_state 
                WHERE key = 'race_day_total_laps' AND game_id = ?
            """, (self.game_id,))
            total_lap_row = cursor.fetchone()
            total_laps = int(total_lap_row[0]) if total_lap_row else 0
            
            # Get league tier for audio params
            cursor.execute("""
                SELECT value FROM game_state 
                WHERE key = 'player_league_tier' AND game_id = ?
            """, (self.game_id,))
            tier_row = cursor.fetchone()
            league_tier = int(tier_row[0]) if tier_row else 3
            
            conn.close()
            
            # Initialize broadcast generator if needed
            if not self.broadcast_generator or self.broadcast_generator_tier != league_tier:
                self.broadcast_generator = ftb_broadcast_commentary.BroadcastCommentaryGenerator(
                    league_tier=league_tier,
                    player_team_name=self.player_team
                )
                self.broadcast_generator_tier = league_tier
                self.log("ftb_narrator", f"Initialized broadcast generator for tier {league_tier}")
            
            # Check for new events to commentate on
            self._generate_broadcast_commentary_for_lap(current_lap, total_laps)
            
        except Exception as e:
            self.log("ftb_narrator", f"Error checking live race broadcast: {e}")
    
    def _generate_broadcast_commentary_for_lap(self, current_lap: int, total_laps: int):
        """
        Generate broadcast commentary for the current lap.
        Reads race events from DB and generates appropriate commentary.
        """
        if not self.broadcast_generator:
            return
        
        try:
            # Track last commentated lap to avoid repeats
            if not hasattr(self, '_last_broadcast_lap'):
                self._last_broadcast_lap = 0
            
            # Only commentate if lap advanced
            if current_lap <= self._last_broadcast_lap:
                return
            
            self._last_broadcast_lap = current_lap
            
            # Get race events for this lap from DB
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT event_type, data FROM sim_events
                WHERE category IN ('overtake', 'crash', 'mechanical_dnf', 'fastest_lap')
                AND json_extract(data, '$.lap_number') = ?
                AND game_id = ?
                ORDER BY event_id DESC
                LIMIT 10
            """, (current_lap, self.game_id))
            
            events = cursor.fetchall()
            conn.close()
            
            # Generate commentary for each event
            commentary_lines = []
            
            for event_type, data_json in events:
                import json
                data = json.loads(data_json) if data_json else {}
                
                if event_type == 'overtake':
                    driver = data.get('driver', 'Unknown')
                    position = data.get('position', 0)
                    is_player = data.get('team', '') == self.player_team
                    lines = self.broadcast_generator.generate_overtake_commentary(driver, position, current_lap, is_player)
                    commentary_lines.extend(lines)
                
                elif event_type == 'crash':
                    driver = data.get('driver', 'Unknown')
                    team = data.get('team', 'Unknown')
                    is_player = team == self.player_team
                    lines = self.broadcast_generator.generate_crash_commentary(driver, team, current_lap, is_player)
                    commentary_lines.extend(lines)
                
                elif event_type == 'mechanical_dnf':
                    driver = data.get('driver', 'Unknown')
                    team = data.get('team', 'Unknown')
                    is_player = team == self.player_team
                    lines = self.broadcast_generator.generate_dnf_commentary(driver, team, current_lap, is_player)
                    commentary_lines.extend(lines)
                
                elif event_type == 'fastest_lap':
                    driver = data.get('driver', 'Unknown')
                    lap_time = data.get('lap_time', 0.0)
                    is_player = data.get('team', '') == self.player_team
                    # Generate fastest lap commentary (simplified)
                    if is_player:
                        text = f"And {driver} sets the fastest lap of the race so far! That's {lap_time:.3f} seconds."
                        commentary_lines.append(ftb_broadcast_commentary.CommentaryLine('pbp', text, 'normal', 90))
            
            # Lap 1 special commentary
            if current_lap == 1:
                lights_out = self.broadcast_generator.generate_lights_out_commentary()
                commentary_lines = lights_out + commentary_lines
            
            # Final lap commentary
            if current_lap == total_laps:
                # Get leader from standings
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT value FROM game_state 
                    WHERE key = 'race_day_standings_p1' AND game_id = ?
                """, (self.game_id,))
                leader_row = cursor.fetchone()
                conn.close()
                
                if leader_row:
                    import json
                    leader_data = json.loads(leader_row[0])
                    leader = leader_data.get('driver', 'Unknown')
                    team = leader_data.get('team', '')
                    is_player_leading = team == self.player_team
                    
                    final_lap = self.broadcast_generator.generate_final_lap_commentary(leader, team, is_player_leading)
                    commentary_lines.extend(final_lap)
            
            # Periodic lap updates (every 5 laps)
            elif current_lap % 5 == 0:
                # Get leader and gap
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT value FROM game_state 
                    WHERE key = 'race_day_standings_p1' AND game_id = ?
                """, (self.game_id,))
                leader_row = cursor.fetchone()
                conn.close()
                
                if leader_row:
                    import json
                    leader_data = json.loads(leader_row[0])
                    leader = leader_data.get('driver', 'Unknown')
                    gap = leader_data.get('gap', 0.0)
                    
                    lap_update = self.broadcast_generator.generate_lap_update(current_lap, total_laps, leader, gap)
                    commentary_lines.extend(lap_update)
            
            # Enqueue commentary lines with appropriate voices
            for line in commentary_lines:
                # Determine voice based on speaker
                if line.speaker == 'pbp':
                    voice = self.pbp_voice_path
                    commentary_type = CommentaryType.BROADCAST_RACE_START
                else:  # color commentator
                    voice = self.color_voice_path
                    commentary_type = CommentaryType.BROADCAST_OVERTAKE
                
                # Enqueue with broadcast-specific handling
                self._enqueue_broadcast_audio(line.text, commentary_type, voice, line.priority)
            
        except Exception as e:
            self.log("ftb_narrator", f"Error generating broadcast commentary: {e}")
            import traceback
            traceback.print_exc()
    
    def _enqueue_broadcast_audio(self, text: str, commentary_type: CommentaryType, voice_path: str, priority: float = 90.0):
        """
        Enqueue broadcast commentary with special handling.
        Uses tier-based audio filtering and higher priority.
        """
        if not self.db_enqueue or not text:
            return
        
        try:
            # Get audio params for current tier
            tier = self.broadcast_generator_tier if hasattr(self, 'broadcast_generator_tier') else 3
            audio_params = ftb_race_day.get_broadcast_audio_params(tier) if ftb_race_day else {}
            
            # Build segment metadata with broadcast-specific params
            metadata = {
                'voice': voice_path or self.voice_path,
                'priority': priority,
                'type': 'broadcast',
                'tier': tier,
                'audio_filter': audio_params.get('filter', 'broadcast_hq'),
                'gain': audio_params.get('gain', 1.0),
                'clarity': audio_params.get('voice_clarity', 1.0)
            }
            
            # Enqueue through runtime
            self.db_enqueue(
                text=text,
                metadata=metadata
            )
            
            self.log("ftb_narrator", f"[BROADCAST] Enqueued: {text[:60]}...")
            
        except Exception as e:
            self.log("ftb_narrator", f"Error enqueuing broadcast audio: {e}")
    
    def _enqueue_audio(self, text: str, commentary_type: CommentaryType):
        """Enqueue commentary to audio system (delegates to priority version)"""
        self._enqueue_audio_with_priority(text, commentary_type, priority=85.0)


# ============================================================================
# META PLUGIN IMPLEMENTATION
# ============================================================================

class FTBNarratorMetaPlugin(MetaPluginBase):
    """
    From The Backmarker Narrator Meta Plugin
    
    Implements universal contract with streaming capability.
    Provides continuous Jarvis-style narration for racing management simulation.
    """
    
    def __init__(self):
        self.runtime_context = None
        self.cfg = None
        self.mem = None
        self.narrator = None
        self.db_path = None
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def initialize(self, runtime_context: Dict[str, Any], cfg: Dict[str, Any], mem: Dict[str, Any]) -> None:
        """Initialize narrator meta plugin"""
        self.runtime_context = runtime_context
        self.cfg = cfg
        self.mem = mem
        
        # Get state DB path from runtime
        station_dir = runtime_context.get('STATION_DIR', '.')
        self.db_path = runtime_context.get('FTB_STATE_DB_PATH') or os.path.join(station_dir, 'ftb_state.db')
        
        print(f"[FTB Narrator] Meta plugin initialized, DB path: {self.db_path}")
    
    def shutdown(self) -> None:
        """Stop narrator thread and cleanup"""
        if self.narrator:
            self.narrator.stop()
        print("[FTB Narrator] Meta plugin shutdown")
    
    # =========================================================================
    # UNIVERSAL INTERFACE
    # =========================================================================
    
    def process_input(self, input_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Process input events for FTB narrator.
        
        Supports:
        - input_type='events': Simulation events from ftb_game.py
        - input_type='init_narrator': Initialize narrator with player team
        """
        input_type = input_data.get('input_type', 'unknown')
        
        if input_type == 'events':
            # Events are now written to DB by ftb_game.py directly
            # This input type is kept for backward compatibility but no-op
            return []  # Narrator reads from DB independently
        
        elif input_type == 'init_narrator':
            # Initialize narrator thread with player team and game_id
            player_team = input_data.get('player_team', 'Unknown Team')
            db_path = input_data.get('db_path') or self.runtime_context.get('FTB_STATE_DB_PATH')
            game_id = input_data.get('game_id', '')
            # Ensure it's a string (extract name if Team object)
            player_team_name = player_team.name if hasattr(player_team, 'name') else str(player_team)
            if db_path and db_path != self.db_path:
                self.db_path = db_path
                if self.narrator:
                    self.narrator.stop()
                    self.narrator = None
            # Always restart narrator if game_id changed to prevent state pollution
            if self.narrator and game_id and hasattr(self.narrator, 'game_id') and self.narrator.game_id != game_id:
                print(f"[FTB Narrator] Game ID changed ({self.narrator.game_id} -> {game_id}), restarting narrator")
                self.narrator.stop()
                self.narrator = None
            if not self.narrator and self.db_path:
                self.narrator = ContinuousNarrator(
                    db_path=self.db_path,
                    player_team=player_team_name,
                    runtime_context=self.runtime_context,
                    cfg=self.cfg,
                    game_id=game_id
                )
                self.narrator.start()
                print(f"[FTB Narrator] Started narrator for {player_team_name} (game_id: {game_id})")
            return []
        
        else:
            return super().process_input(input_data)
    
    # =========================================================================
    # FTB-SPECIFIC INTERFACE
    # =========================================================================
    
    def ftb_emit_segments(self, events: list, state: Any, conn) -> None:
        """
        Process simulation events and emit narrative segments.
        
        This method is called by ftb_game.py after each simulation tick
        to generate narration from the events.
        
        Args:
            events: List of SimEvent objects from the simulation
            state: Current SimState snapshot
            conn: Database connection for writing segments
        """
        # Sync DB path from live state/runtime before any auto-start.
        if state:
            runtime_db_path = self.runtime_context.get('FTB_STATE_DB_PATH')
            state_db_path = getattr(state, 'state_db_path', None)
            db_path = state_db_path or runtime_db_path
            if db_path and db_path != self.db_path:
                self.db_path = db_path
                if self.narrator:
                    self.narrator.stop()
                    self.narrator = None

        # Auto-initialize narrator on first event emission
        if not self.narrator and state:
            player_team = getattr(state, 'player_team', None)
            if player_team and self.db_path:
                # Extract team name if Team object
                player_team_name = player_team.name if hasattr(player_team, 'name') else str(player_team)
                self.narrator = ContinuousNarrator(
                    db_path=self.db_path,
                    player_team=player_team_name,
                    runtime_context=self.runtime_context,
                    cfg=self.cfg
                )
                self.narrator.start()
                print(f"[FTB Narrator] Auto-started narrator for {player_team_name}")
        
        # Narrator reads from DB independently - no action needed here
    
    # =========================================================================
    # CAPABILITY FLAGS
    # =========================================================================
    
    def supports_streaming(self) -> bool:
        """FTB Narrator supports continuous streaming"""
        return True
    
    def get_streaming_handle(self) -> Optional[ContinuousNarrator]:
        """Return narrator thread handle"""
        return self.narrator
    
    def supports_delegation(self) -> bool:
        """FTB Narrator does not support delegation"""
        return False
    
    def cold_open(self) -> Optional[str]:
        """
        Generate FTB pregame narrator cold open.
        
        Called by bookmark.py when station boots or queue is empty.
        Provides ambient, low-frequency narrative flavor while world prepares.
        """
        _crumb("cold_open() called")
        
        # Use call_llm (not llm_generate) - matches runtime_context convention
        if not self.runtime_context or not self.runtime_context.get('call_llm'):
            _crumb("cold_open() early return: no runtime_context or call_llm")
            return None
        
        try:
            call_llm = self.runtime_context['call_llm']
            _crumb(f"cold_open() got call_llm: {call_llm}")
            
            # Safety check: ensure cfg is available
            if not self.cfg or not isinstance(self.cfg, dict):
                print("[FTB Narrator] cold_open: cfg not available, returning None")
                _crumb("cold_open() cfg not available")
                return None
            
            model = self.cfg.get("models", {}).get("narrator", "qwen3:8b")
            _crumb(f"cold_open() using model: {model}")

        except Exception as e:
            print(f"[FTB Narrator] cold_open setup failed: {e}")
            _crumb(f"cold_open() setup exception: {type(e).__name__}: {e}")
            return None

        
        # Pregame narrator prompt from reference.txt
        system_prompt = "You are the pregame narrator for From The Backmarker, a racing management simulation. Your tone is calm, grounded, cinematic but not dramatic, occasionally wry."
        
        user_prompt = """Your job is to create ambient, low-frequency narrative flavor while the game prepares its world. Set the scene before a player starts their run. Your output may take many forms, including:
- Brief exposition of what the game is (It is a racing management sim where players can progress from grassroots to Formula Z by working their way up the ladder)
- General loading screen style tips and tricks (Like how they can assign a delegate Assistant to manage the team for them, but to be careful leaving their team unattended. They can leave their team for greener pastures but it may backfire. Keeping your job in this game is never guaranteed so they must stay on their toes.)

Constraints:
- Speak in short paragraphs or single sentences.
- Do not refer to specific teams, drivers, results, or historical facts.

Perspective & Tone:
- Calm, grounded, observant.
- The world exists independently of the player.
- Slightly cinematic, never dramatic.
- Confident, not instructional.
- Occasionally wry.

Additional content you may reference:
- The existence of leagues and tiers (Grassroots -> Formula V -> Formula X -> Formula Y -> Formula Z).
- That the player's role is undefined or unproven.
- That time, money, and results matter.
- That attention must be earned.

Narrative goals:
- Establish that this is a living simulation, not a scenario.
- Make the player feel small but invited.
- Create anticipation without urgency.
- Fill silence while the world state is being prepared.
- Make repetition feel intentional, not looping.

Allowed techniques:
- Vary phrasing across generations.
- Use implication instead of explanation.
- Reference state rather than events.
- Occasionally acknowledge uncertainty.
- Leave space between thoughts.

Disallowed techniques:
- Lore dumps.
- Tutorials.
- Hype language.
- Second-person commands.
- Meta commentary about AI, models, or generation.

Output:
- 4 to 8 short lines total.
- Each line must stand alone.
- No headers.
- No titles.
- No formatting.

Begin. Go straight into character as the pregame narrator, talk directly to the player."""
        
        try:
            _crumb(f"cold_open() calling call_llm with model={model}")
            response = call_llm(
                model=model,
                prompt=user_prompt,
                system=system_prompt,
                max_tokens=200,
                temperature=0.8,
                timeout=30  # Increased timeout since this runs in background now
            )
            _crumb(f"cold_open() call_llm returned, type={type(response)}")
            
            # Extract text
            if isinstance(response, dict):
                text = response.get("response", "") or response.get("text", "")
            else:
                text = str(response)
            
            text = text.strip()
            _crumb(f"cold_open() extracted text, length={len(text)}")
            
            # Validate output
            if len(text) < 50:
                _crumb("cold_open() text too short, returning None")
                return None
            
            # Clean up any formatting artifacts
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if len(lines) > 8:
                lines = lines[:8]  # Cap at 8 lines
            
            result = '\n'.join(lines)
            _crumb(f"cold_open() returning text, length={len(result)}")
            return result
            
        except Exception as e:
            print(f"[FTB Narrator] Cold open generation failed: {e}")
            _crumb(f"cold_open() exception: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            _dump_breadcrumbs("[FTB Narrator]")
            return None


# ============================================================================
# PLUGIN REGISTRATION
# ============================================================================

# Auto-register when loaded by bookmark.py
try:
    from bookmark import META_PLUGIN_REGISTRY
    META_PLUGIN_REGISTRY.register("ftb_narrator", FTBNarratorMetaPlugin)
    print("[FTB Narrator] Registered with meta plugin registry")
except Exception as e:
    print(f"[FTB Narrator] Registration failed: {e}")
