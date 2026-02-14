"""
FTB Broadcast Commentary Generator - LLM Beat Architecture (v2)

Narrative-driven, memory-aware broadcast engine.
Replaces event-reactive TTS with beat-based commentary:

    Lap -> Event Aggregation -> Significance Scoring -> Narrative Beat -> Prompt -> Speech

Core principles:
  - We are broadcasting a race, not narrating telemetry.
  - Every race tells a story: selection, escalation, memory.
  - Silence matters. Not every event deserves narration.
  - Commentary binds across laps via NarrativeState.
  - Late-race escalation: frequency, intensity, and color all increase.

Voice assignments per tier:
  Tier 1 (Grassroots):    pbp: am_puck,   color: bf_lily
  Tier 2 (Enthusiast):    pbp: am_eric,   color: af_river
  Tier 3 (Professional):  pbp: am_adam,   color: af_bella
  Tier 4 (Premium):       pbp: bm_lewis,  color: bf_emma
  Tier 5 (World Class):   pbp: bm_george, color: bf_alice
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
import random
import time


# ============================================================================
# VOICE CONFIG
# ============================================================================

TIER_VOICES = {
    1: {'pbp': 'am_puck',   'color': 'bf_lily'},
    2: {'pbp': 'am_eric',   'color': 'af_river'},
    3: {'pbp': 'am_adam',   'color': 'af_bella'},
    4: {'pbp': 'bm_lewis',  'color': 'bf_emma'},
    5: {'pbp': 'bm_george', 'color': 'bf_alice'},
}


# ============================================================================
# SECTION 1 - Season Context
# ============================================================================

@dataclass
class SeasonContext:
    """Rich season and championship context for LLM prompts."""
    player_position: int = 0
    player_points: int = 0
    championship_leader: str = ""
    championship_leader_points: int = 0
    points_gap_to_leader: int = 0

    race_number: int = 0
    total_races: int = 0
    races_remaining: int = 0

    last_three_results: List[int] = field(default_factory=list)
    recent_dnfs: int = 0
    points_last_three: int = 0

    team_morale: float = 50.0
    team_momentum: str = "neutral"
    budget_tier: str = "midfield"

    closest_rival: Optional[str] = None
    rival_points_gap: int = 0

    can_win_championship: bool = True
    mathematically_safe: bool = False
    relegation_danger: bool = False

    best_finish_this_season: int = 99
    worst_finish_this_season: int = 99

    track_name: str = ""
    player_best_result_here: Optional[int] = None

    def to_prompt_context(self) -> str:
        """Convert to natural language context for LLM."""
        parts = []
        if self.player_position > 0:
            parts.append(
                f"Currently P{self.player_position} in the championship "
                f"with {self.player_points} points"
            )
            if self.points_gap_to_leader > 0:
                parts.append(
                    f"{self.points_gap_to_leader} points behind leader "
                    f"{self.championship_leader}"
                )
            elif self.player_position == 1:
                parts.append("Leading the championship")
        parts.append(
            f"Race {self.race_number} of {self.total_races} "
            f"({self.races_remaining} races remaining)"
        )
        if self.last_three_results:
            parts.append(
                "Recent results: "
                + ", ".join(f"P{r}" for r in self.last_three_results)
            )
        if self.team_momentum == "rising":
            parts.append("Team momentum is building")
        elif self.team_momentum == "falling":
            parts.append("Team struggling recently")
        if not self.can_win_championship:
            parts.append("Championship hopes fading")
        elif self.relegation_danger:
            parts.append("Fighting to avoid relegation")
        elif self.races_remaining <= 3 and self.player_position <= 3:
            parts.append("In championship contention with races running out")
        return ". ".join(parts) + "."

    def should_inject_championship(self) -> bool:
        """Only inject championship context when it narratively matters."""
        if self.races_remaining <= 3:
            return True
        if self.player_position <= 3:
            return True
        if self.relegation_danger:
            return True
        if self.recent_dnfs > 0 and self.player_position <= 5:
            return True
        return False


# ============================================================================
# SECTION 2 - Event Significance Scoring
# ============================================================================

EVENT_BASE_WEIGHT = {
    "lead_change":          10.0,
    "player_overtake_top5":  9.0,
    "player_crash":         10.0,
    "leader_crash":          9.0,
    "podium_change":         8.0,
    "multi_position_gain":   7.0,
    "player_overtake":       6.0,
    "crash":                 6.0,
    "mechanical_dnf":        7.0,
    "player_dnf":           10.0,
    "midfield_overtake":     3.0,
    "position_swap_back":    2.0,
}


@dataclass
class ScoredEvent:
    """A race event tagged with a computed narrative weight."""
    raw_event: Dict[str, Any]
    event_class: str
    base_weight: float
    final_weight: float = 0.0
    lap: int = 0
    driver: str = ""
    team: str = ""
    is_player_team: bool = False
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def classify_event(event, player_team, current_leader):
    """Classify a raw event dict and assign a base weight."""
    etype = event.get("event_type", "")
    drivers = event.get("drivers", [])
    driver = event.get("driver", drivers[0] if drivers else "")
    team = event.get("team", "")
    is_player = bool(player_team and team == player_team)
    new_pos = event.get("new_position", event.get("position", 99))
    old_pos = event.get("old_position", 99)
    positions_gained = event.get("positions_gained", max(0, old_pos - new_pos))
    description = event.get("description", "")

    if etype == "overtake":
        if new_pos == 1:
            ec = "lead_change"
        elif is_player and new_pos <= 5:
            ec = "player_overtake_top5"
        elif new_pos <= 3:
            ec = "podium_change"
        elif is_player:
            ec = "player_overtake"
        elif positions_gained >= 3:
            ec = "multi_position_gain"
        else:
            ec = "midfield_overtake"
    elif etype in ("crash", "spin", "collision"):
        if is_player:
            ec = "player_crash"
        elif driver == current_leader:
            ec = "leader_crash"
        else:
            ec = "crash"
    elif etype in ("mechanical_dnf", "dnf"):
        ec = "player_dnf" if is_player else "mechanical_dnf"
    else:
        ec = etype

    return ScoredEvent(
        raw_event=event,
        event_class=ec,
        base_weight=EVENT_BASE_WEIGHT.get(ec, 3.0),
        lap=event.get("lap", 0),
        driver=driver,
        team=team,
        is_player_team=is_player,
        description=description,
        metadata=event.get("metadata", {}),
    )


def apply_weight_modifiers(scored, lap, total_laps, narrative, season):
    """Apply phase / championship / rivalry modifiers to the base weight."""
    w = scored.base_weight

    # Late-race multiplier
    if total_laps > 0:
        remaining = total_laps - lap
        if remaining <= 3:
            w *= 1.8
        elif remaining <= 5:
            w *= 1.5
        elif lap <= total_laps * 0.15:
            w *= 1.2  # opening-lap drama

    # Championship implications
    if scored.is_player_team and season.should_inject_championship():
        w *= 1.3

    # Active-battle bonus
    if narrative.active_battles:
        for pair in narrative.active_battles:
            if scored.driver in pair:
                w *= 1.2
                break

    # Recovery-arc bonus
    if scored.is_player_team and narrative.player_arc == "recovering":
        w *= 1.3

    scored.final_weight = w
    return w


# ============================================================================
# SECTION 3 - Narrative Memory Layer
# ============================================================================

@dataclass
class NarrativeState:
    """
    Lightweight in-race narrative tracker.
    Fed into every prompt so the LLM can bind commentary across laps.
    """
    # Leader continuity
    leader: str = ""
    leader_team: str = ""
    leader_since_lap: int = 0
    laps_led: int = 0

    # Active battles (driver-name pairs)
    active_battles: List[Tuple[str, str]] = field(default_factory=list)

    # Player narrative arc
    player_arc: str = "neutral"
    player_arc_detail: str = ""

    # Incident memory
    drivers_recovering: Dict[str, int] = field(default_factory=dict)

    # Race phase
    race_phase: str = "early"
    green_flag_laps: int = 0

    # Memory buffers
    last_major_event: Optional[Dict[str, Any]] = field(default=None)
    last_player_event: Optional[Dict[str, Any]] = field(default=None)
    commentary_log: List[str] = field(default_factory=list)

    # Per-lap event collector
    current_lap_events: List[ScoredEvent] = field(default_factory=list)

    # Cadence stats
    total_commentary_lines: int = 0
    laps_since_commentary: int = 0

    def update_leader(self, driver, team, lap):
        if driver != self.leader:
            self.leader = driver
            self.leader_team = team
            self.leader_since_lap = lap
            self.laps_led = 1
        else:
            self.laps_led = lap - self.leader_since_lap + 1

    def update_phase(self, lap, total_laps):
        if total_laps <= 0:
            self.race_phase = "mid"
            return
        progress = lap / total_laps
        if progress <= 0.25:
            self.race_phase = "early"
        elif progress <= 0.65:
            self.race_phase = "mid"
        elif progress <= 0.90:
            self.race_phase = "late"
        else:
            self.race_phase = "final"

    def register_incident(self, driver, lap):
        self.drivers_recovering[driver] = lap
        self.green_flag_laps = 0

    def tick_green(self):
        self.green_flag_laps += 1

    def update_player_arc(self, player_pos, player_start_pos, had_incident):
        if had_incident:
            self.player_arc = "recovering"
            self.player_arc_detail = "fighting back after incident"
        elif player_pos <= 3 and player_start_pos > 5:
            self.player_arc = "charging"
            self.player_arc_detail = f"climbed from P{player_start_pos} to P{player_pos}"
        elif player_pos == 1:
            self.player_arc = "dominant"
            self.player_arc_detail = "controlling the race from the front"
        elif player_pos <= player_start_pos - 3:
            self.player_arc = "charging"
            self.player_arc_detail = f"on the move, up to P{player_pos}"
        elif player_pos >= player_start_pos + 3:
            self.player_arc = "defending"
            self.player_arc_detail = f"dropped to P{player_pos}, under pressure"
        else:
            self.player_arc = "neutral"
            self.player_arc_detail = ""

    def detect_battles(self, positions):
        """positions: [(driver_name, gap_to_leader), ...] sorted by pos."""
        battles = []
        for i in range(len(positions) - 1):
            gap = abs(positions[i + 1][1] - positions[i][1])
            if gap < 1.2:
                battles.append((positions[i][0], positions[i + 1][0]))
        self.active_battles = battles[:3]

    def to_narrative_summary(self):
        """Natural-language summary injected into every LLM prompt."""
        lines = []
        if self.leader:
            if self.laps_led >= 3:
                lines.append(
                    f"{self.leader} ({self.leader_team}) has led since "
                    f"lap {self.leader_since_lap} ({self.laps_led} laps)."
                )
            else:
                lines.append(f"{self.leader} ({self.leader_team}) leads.")
        for a, b in self.active_battles[:2]:
            lines.append(f"Active battle: {a} vs {b}.")
        if self.player_arc != "neutral" and self.player_arc_detail:
            lines.append(f"Player team: {self.player_arc_detail}.")
        for drv, lap in list(self.drivers_recovering.items())[:2]:
            lines.append(f"{drv} recovering from incident on lap {lap}.")
        if self.green_flag_laps >= 5:
            lines.append(
                f"Long green-flag run: {self.green_flag_laps} uninterrupted laps."
            )
        return "\n".join(lines) if lines else "No significant narrative threads yet."

    def log_commentary(self, text):
        self.commentary_log.append(text)
        if len(self.commentary_log) > 5:
            self.commentary_log.pop(0)
        self.total_commentary_lines += 1
        self.laps_since_commentary = 0

    def remember_event(self, event):
        mem = {
            "driver": event.driver,
            "team": event.team,
            "class": event.event_class,
            "lap": event.lap,
            "description": event.description,
        }
        self.last_major_event = mem
        if event.is_player_team:
            self.last_player_event = mem


# ============================================================================
# SECTION 4 - Commentary Prompt dataclass
# ============================================================================

@dataclass
class CommentaryPrompt:
    """A prompt destined for LLM generation."""
    speaker: str  # 'pbp' or 'color'
    prompt: str
    event_type: str
    max_tokens: int = 60
    priority: int = 5


# ============================================================================
# SECTION 5 - Beat Dispatcher and Silence Logic
# ============================================================================

@dataclass
class BeatConfig:
    """Tunable knobs for the beat dispatcher."""
    min_gap_sec: float = 6.0
    silence_min: float = 5.0
    silence_max: float = 8.0
    max_beats_per_lap: int = 2
    late_race_lap_threshold: int = 5
    late_race_min_gap: float = 4.0
    late_race_max_beats: int = 3
    color_probability: float = 0.35
    late_race_color_probability: float = 0.55
    narration_threshold: float = 4.0
    final_lap_always: bool = True


class BeatDispatcher:
    """
    Collects events per lap, scores them, selects top beats,
    enforces silence, and dispatches commentary.
    """

    def __init__(self, config=None):
        self.cfg = config or BeatConfig()
        self.last_speech_time = 0.0
        self._silent_until = 0.0

    def select_beats(self, lap_events, lap, total_laps, narrative):
        """Pick top 1-2 events worth narrating this lap."""
        remaining = total_laps - lap
        is_late = remaining <= self.cfg.late_race_lap_threshold
        max_beats = self.cfg.late_race_max_beats if is_late else self.cfg.max_beats_per_lap

        candidates = [e for e in lap_events if e.final_weight >= self.cfg.narration_threshold]
        candidates.sort(key=lambda e: e.final_weight, reverse=True)
        return candidates[:max_beats]

    def should_stay_silent(self, lap, total_laps, narrative):
        """Decide if this lap should be engine-only silence."""
        now = time.time()
        if now < self._silent_until:
            return True
        remaining = total_laps - lap
        if remaining <= 3:
            return False
        if narrative.laps_since_commentary <= 1:
            return True
        return False

    def schedule_silence(self):
        """Insert an intentional engine-only breathing gap."""
        gap = random.uniform(self.cfg.silence_min, self.cfg.silence_max)
        self._silent_until = time.time() + gap

    def can_speak_now(self, lap, total_laps):
        """Enforce minimum gap between speech lines."""
        now = time.time()
        if now < self._silent_until:
            return False
        remaining = total_laps - lap
        min_gap = (
            self.cfg.late_race_min_gap
            if remaining <= self.cfg.late_race_lap_threshold
            else self.cfg.min_gap_sec
        )
        return (now - self.last_speech_time) >= min_gap

    def mark_spoken(self):
        self.last_speech_time = time.time()

    def color_roll(self, lap, total_laps):
        """Roll for color commentary following PBP."""
        remaining = total_laps - lap
        prob = (
            self.cfg.late_race_color_probability
            if remaining <= self.cfg.late_race_lap_threshold
            else self.cfg.color_probability
        )
        return random.random() < prob


# ============================================================================
# SECTION 6 - LLM Commentary Generator (prompt building)
# ============================================================================

class LLMCommentaryGenerator:
    """Builds contextually-rich prompts for LLM with narrative memory."""

    def __init__(self, league_tier, player_team_name, season_context=None):
        self.league_tier = league_tier
        self.player_team = player_team_name
        self.season_context = season_context or SeasonContext()

        self.voices = TIER_VOICES.get(league_tier, TIER_VOICES[3])
        self.commentary_style = self._get_style_for_tier(league_tier)
        self.pbp_personality = self._get_pbp_personality(league_tier)
        self.color_personality = self._get_color_personality(league_tier)

    # ---- tier style tables ----

    def _get_style_for_tier(self, tier):
        styles = {
            1: {
                "name": "grassroots",
                "pbp_style": "enthusiastic local commentator, casual language, excited about action",
                "color_style": "knowledgeable fan perspective, relatable observations, supportive",
                "broadcast_quality": "community radio feel, personal connection with drivers",
                "language_level": "casual, accessible, some local references",
                "energy": "high enthusiasm, genuine excitement for racing",
            },
            2: {
                "name": "enthusiast",
                "pbp_style": "passionate racing fan doing commentary, detailed calls, racing terminology",
                "color_style": "deep racing knowledge, driver psychology focus, tactical insights",
                "broadcast_quality": "dedicated sports channel, professional but personable",
                "language_level": "racing terminology comfortable, fan-oriented",
                "energy": "passionate engagement, analytical excitement",
            },
            3: {
                "name": "professional",
                "pbp_style": "experienced sports broadcaster, polished delivery, authoritative",
                "color_style": "ex-driver or team insider perspective, technical depth, measured analysis",
                "broadcast_quality": "major sports network standard, balanced coverage",
                "language_level": "professional broadcast standard, clear explanations",
                "energy": "controlled excitement, professional composure",
            },
            4: {
                "name": "premium",
                "pbp_style": "elite sports commentator, dramatic flair, iconic calls for big moments",
                "color_style": "championship-level analyst, strategy depth, insider knowledge",
                "broadcast_quality": "premium sports network, cinematic production value",
                "language_level": "eloquent, sophisticated vocabulary, storytelling",
                "energy": "building drama, memorable calls, narrative threading",
            },
            5: {
                "name": "world_class",
                "pbp_style": "legendary F1-style broadcaster, iconic delivery, historical perspective",
                "color_style": "world champion analyst, technical mastery, global context",
                "broadcast_quality": "world feed standard, multiple language consideration",
                "language_level": "broadcast excellence, quotable moments, legacy awareness",
                "energy": "controlled intensity, moment recognition, history-making awareness",
            },
        }
        return styles.get(tier, styles[3])

    def _get_pbp_personality(self, tier):
        p = {
            1: "enthusiastic local announcer who knows all the drivers personally",
            2: "passionate racing enthusiast with encyclopedic knowledge",
            3: "experienced professional broadcaster with authoritative voice",
            4: "elite commentator known for dramatic and memorable calls",
            5: "legendary voice of motorsport with decades of history",
        }
        return p.get(tier, p[3])

    def _get_color_personality(self, tier):
        p = {
            1: "supportive local racing expert who explains things clearly",
            2: "analytical fan perspective with driver psychology insights",
            3: "former driver turned analyst with technical expertise",
            4: "championship-winning strategist with insider knowledge",
            5: "world champion analyst providing masterclass commentary",
        }
        return p.get(tier, p[3])

    def get_voice_config(self):
        return {
            "play_by_play": self.voices["pbp"],
            "color_commentator": self.voices["color"],
        }

    # ---- prompt core ----

    def _build_base_prompt(self, speaker, narrative):
        """Build base prompt with personality, style, narrative thread,
        and selective prior-moment memory."""
        style = self.commentary_style
        narrative_block = narrative.to_narrative_summary()

        # Selective championship injection (color only, when it matters)
        season_block = ""
        if speaker == "color" and self.season_context.should_inject_championship():
            season_block = (
                "\nChampionship context:\n"
                + self.season_context.to_prompt_context()
                + "\n"
            )

        # Prior-moment memory for continuity
        memory_block = ""
        if narrative.last_major_event:
            lme = narrative.last_major_event
            memory_block = (
                f"\nPrior major moment (lap {lme.get('lap', '?')}): "
                f"{lme.get('description', '')}\n"
            )
        if speaker == "color" and narrative.last_player_event:
            lpe = narrative.last_player_event
            if lpe != narrative.last_major_event:
                memory_block += (
                    f"Last player moment (lap {lpe.get('lap', '?')}): "
                    f"{lpe.get('description', '')}\n"
                )

        if speaker == "pbp":
            return (
                f"You are the play-by-play commentator: {self.pbp_personality}.\n\n"
                f"Style: {style['pbp_style']}\n"
                f"Broadcast quality: {style['broadcast_quality']}\n"
                f"Language: {style['language_level']}\n"
                f"Energy: {style['energy']}\n\n"
                f"Ongoing narrative:\n{narrative_block}\n"
                f"{memory_block}\n"
                "CRITICAL RULES:\n"
                "- 1-2 sentences maximum (40-60 words)\n"
                "- Present tense, immediate action\n"
                '- NO player references ("our team", "we", "you")\n'
                "- Use driver/team names objectively\n"
                "- Match the tier style exactly\n"
                "- Natural, conversational flow - interpret, don't recite telemetry\n"
                "- You may refer back to earlier events for narrative continuity\n"
            )
        else:
            return (
                f"You are the color commentator: {self.color_personality}.\n\n"
                f"Style: {style['color_style']}\n"
                f"Analysis level: {style['broadcast_quality']}\n"
                f"Language: {style['language_level']}\n\n"
                f"Ongoing narrative:\n{narrative_block}\n"
                f"{season_block}{memory_block}\n"
                "CRITICAL RULES:\n"
                "- 1-2 sentences maximum (40-60 words)\n"
                "- Analytical, context-adding perspective: strategy, momentum, psychology\n"
                '- NO player references ("our team", "we", "you")\n'
                "- Use driver/team names objectively\n"
                "- Do NOT restate positions - interpret what they mean\n"
                "- Match the tier style exactly\n"
                "- Complement play-by-play with insight, not repetition\n"
            )

    # ---------- Pre-race ----------

    def generate_pre_race_prompt(self, grid, track_name, narrative):
        prompts = []
        self.season_context.track_name = track_name

        pole_info = ""
        player_grid = ""
        player_pos = None
        if grid:
            pole_team, pole_driver, _ = grid[0]
            pole_info = f"{pole_driver.name} on pole for {pole_team.name}"
            player_pos = next(
                (i for i, (t, _, _) in enumerate(grid, 1) if t.name == self.player_team),
                None,
            )
            if player_pos:
                entry = grid[player_pos - 1]
                player_grid = f"{entry[1].name} starts P{player_pos} for {self.player_team}"

        pbp_base = self._build_base_prompt("pbp", narrative)
        stakes = ""
        if self.season_context.should_inject_championship():
            stakes = (
                f"Championship stakes: P{self.season_context.player_position}, "
                f"{self.season_context.points_gap_to_leader} points from lead, "
                f"{self.season_context.races_remaining} rounds left. "
            )
        prompts.append(CommentaryPrompt(
            speaker="pbp",
            prompt=(
                f"{pbp_base}\n"
                f"TASK: Deliver the race opening. We're at {track_name}, grid is set, moments from lights out.\n"
                f"Key facts: {pole_info}. {player_grid}. {stakes}\n"
                "Generate the opening call:"
            ),
            event_type="pre_race",
            max_tokens=70,
            priority=10,
        ))

        if self.season_context.player_position > 0:
            color_base = self._build_base_prompt("color", narrative)
            prompts.append(CommentaryPrompt(
                speaker="color",
                prompt=(
                    f"{color_base}\n"
                    "TASK: Set the scene - championship implications, track characteristics, what to watch for.\n"
                    f"{self.player_team} starts P{player_pos or '?'}, currently P{self.season_context.player_position} in standings.\n"
                    "Generate pre-race analysis:"
                ),
                event_type="pre_race",
                max_tokens=70,
                priority=9,
            ))
        return prompts

    # ---------- Lights out ----------

    def generate_lights_out_prompt(self, narrative):
        pbp_base = self._build_base_prompt("pbp", narrative)
        return CommentaryPrompt(
            speaker="pbp",
            prompt=(
                f"{pbp_base}\n"
                "TASK: Deliver the iconic lights out call for the race start.\n"
                "This is THE moment - make it match your tier's style and energy.\n"
                "Generate the lights out call:"
            ),
            event_type="lights_out",
            max_tokens=40,
            priority=10,
        )

    # ---------- Beat prompt (aggregated lap events) ----------

    def generate_beat_prompt(self, beats, lap, total_laps, narrative, include_color=False):
        """Generate commentary for the top beat(s) selected for a lap.
        This is the core of the beat architecture: one prompt per lap,
        not one prompt per raw event."""
        prompts = []
        if not beats:
            return prompts

        primary = beats[0]
        secondary_desc = ""
        if len(beats) > 1:
            secondary_desc = f"Also this lap: {beats[1].description}"

        remaining = total_laps - lap

        # PBP
        pbp_base = self._build_base_prompt("pbp", narrative)
        significance = self._interpret_significance(primary, narrative)

        player_note = ""
        if primary.is_player_team:
            player_note = "PLAYER TEAM INVOLVED - higher energy but stay objective"

        prompts.append(CommentaryPrompt(
            speaker="pbp",
            prompt=(
                f"{pbp_base}\n"
                f"RACE MOMENT (lap {lap}/{total_laps}, {remaining} to go, {narrative.race_phase} phase):\n"
                f"{primary.description}\n"
                f"Significance: {significance}\n"
                f"{secondary_desc}\n"
                f"{player_note}\n\n"
                "TASK: Call this moment. Interpret it, don't just recite. 1-2 sentences.\n"
                "Generate commentary:"
            ),
            event_type=primary.event_class,
            max_tokens=55,
            priority=min(10, int(primary.final_weight)),
        ))

        # Color (conditional)
        if include_color:
            color_base = self._build_base_prompt("color", narrative)
            color_angle = self._pick_color_angle(primary, narrative)
            prompts.append(CommentaryPrompt(
                speaker="color",
                prompt=(
                    f"{color_base}\n"
                    f"CONTEXT: {primary.description} (lap {lap}).\n"
                    f"{color_angle}\n\n"
                    "TASK: Provide analytical follow-up. Interpret - don't repeat the play-by-play. 1-2 sentences.\n"
                    "Generate analysis:"
                ),
                event_type=primary.event_class + "_analysis",
                max_tokens=55,
                priority=max(3, min(8, int(primary.final_weight) - 2)),
            ))

        return prompts

    # ---------- Lap update (quiet laps / milestones) ----------

    def generate_lap_update_prompt(self, lap, total_laps, narrative, player_pos=None):
        """Generate a periodic update only on milestones or quiet stretches."""
        remaining = total_laps - lap
        is_milestone = (lap % 5 == 0) or remaining in (5, 3, 1) or lap == 1

        if narrative.laps_since_commentary < 2 and not is_milestone:
            return None
        if not is_milestone and narrative.laps_since_commentary < 3:
            return None

        pbp_base = self._build_base_prompt("pbp", narrative)
        player_ctx = ""
        if player_pos:
            player_ctx = f"{self.player_team} running P{player_pos}. "

        return CommentaryPrompt(
            speaker="pbp",
            prompt=(
                f"{pbp_base}\n"
                f"STATUS: Lap {lap}/{total_laps}. {narrative.race_phase.upper()} phase. {player_ctx}\n"
                f"{narrative.to_narrative_summary()}\n\n"
                "TASK: Paint the picture - don't just state facts. Thread the narrative. 1-2 sentences.\n"
                "Generate:"
            ),
            event_type="lap_update",
            max_tokens=60,
            priority=5 if remaining <= 5 else 3,
        )

    # ---------- Final lap ----------

    def generate_final_lap_prompt(self, narrative, player_pos=None):
        pbp_base = self._build_base_prompt("pbp", narrative)
        drama = "FINAL LAP"
        if player_pos == 1:
            drama += f" - {self.player_team} LEADING"
        elif player_pos and player_pos <= 3:
            drama += f" - {self.player_team} ON THE PODIUM"

        return CommentaryPrompt(
            speaker="pbp",
            prompt=(
                f"{pbp_base}\n"
                f"MOMENT: {drama}. {narrative.leader} ({narrative.leader_team}) leads.\n"
                f"{narrative.to_narrative_summary()}\n\n"
                "TASK: Deliver the final lap call with escalated drama. This is the climax. 1-2 sentences.\n"
                "Generate:"
            ),
            event_type="final_lap",
            max_tokens=60,
            priority=10,
        )

    # ---------- Checkered flag ----------

    def generate_checkered_flag_prompt(self, winner_name, winner_team, narrative,
                                      player_pos=None, player_points=None):
        prompts = []
        is_player_win = (player_pos == 1)
        is_podium = bool(player_pos and player_pos <= 3)

        pbp_base = self._build_base_prompt("pbp", narrative)
        player_flag = ""
        if is_player_win:
            player_flag = "PLAYER TEAM VICTORY"
        elif is_podium:
            player_flag = "PLAYER ON THE PODIUM"

        prompts.append(CommentaryPrompt(
            speaker="pbp",
            prompt=(
                f"{pbp_base}\n"
                f"CHECKERED FLAG: {winner_name} ({winner_team}) wins!\n"
                f"{player_flag}\n"
                f"Race narrative: {narrative.to_narrative_summary()}\n\n"
                "TASK: Deliver the finish call. Make it iconic. 1-2 sentences.\n"
                "Generate:"
            ),
            event_type="checkered_flag",
            max_tokens=60,
            priority=10,
        ))

        if player_pos and self.season_context.player_position > 0:
            color_base = self._build_base_prompt("color", narrative)
            championship_angle = ""
            if is_player_win:
                championship_angle = "Victory reshapes the championship. "
            elif player_points:
                championship_angle = f"P{player_pos} finish and {player_points} points. "

            prompts.append(CommentaryPrompt(
                speaker="color",
                prompt=(
                    f"{color_base}\n"
                    f"RESULT: {self.player_team} finishes P{player_pos}. {championship_angle}\n"
                    f"Championship: P{self.season_context.player_position}, {self.season_context.races_remaining} races remaining.\n"
                    f"Race story: {narrative.to_narrative_summary()}\n\n"
                    "TASK: Wrap the race - championship picture, momentum, what this means. 1-2 sentences.\n"
                    "Generate:"
                ),
                event_type="race_summary",
                max_tokens=70,
                priority=9,
            ))

        return prompts

    # ---------- Internal helpers ----------

    def _interpret_significance(self, event, narrative):
        """Generate a significance label the LLM can work with."""
        parts = []
        sig_map = {
            "lead_change": "Lead change - race-defining moment",
            "player_crash": "PLAYER CRISIS - season implications",
            "player_dnf": "PLAYER CRISIS - season implications",
            "player_overtake_top5": "Player charging into the top 5",
            "podium_change": "Podium reshuffle",
            "multi_position_gain": "Massive move through the field",
            "leader_crash": "Leader incident - race wide open",
        }
        parts.append(sig_map.get(event.event_class, "Notable moment"))

        if narrative.race_phase == "final":
            parts.append("in the closing stages")
        elif narrative.race_phase == "late":
            parts.append("as the race enters its final phase")

        if event.driver in narrative.drivers_recovering:
            inc_lap = narrative.drivers_recovering[event.driver]
            parts.append(f"({event.driver} recovering since lap {inc_lap})")

        return " - ".join(parts)

    def _pick_color_angle(self, event, narrative):
        """Pick the right analytical angle for color commentary."""
        if event.event_class in ("player_crash", "player_dnf", "leader_crash"):
            if self.season_context.should_inject_championship():
                return "Angle: championship implications of this incident."
            return "Angle: damage assessment and recovery chances."
        if event.event_class in ("lead_change", "podium_change"):
            return "Angle: what strategy or racecraft made this happen."
        if narrative.player_arc in ("charging", "recovering"):
            return f"Angle: {narrative.player_arc_detail} - momentum analysis."
        if narrative.active_battles:
            pair = narrative.active_battles[0]
            return f"Angle: the developing battle between {pair[0]} and {pair[1]}."
        return "Angle: tactical context and what to watch next."

    def update_season_context(self, context):
        self.season_context = context


# ============================================================================
# SECTION 7 - Helpers and Exports
# ============================================================================

def get_commentary_voices_for_tier(tier):
    """Get the voice configuration for a given tier."""
    return TIER_VOICES.get(tier, TIER_VOICES[3])


__all__ = [
    "LLMCommentaryGenerator",
    "CommentaryPrompt",
    "SeasonContext",
    "NarrativeState",
    "ScoredEvent",
    "BeatDispatcher",
    "BeatConfig",
    "classify_event",
    "apply_weight_modifiers",
    "get_commentary_voices_for_tier",
    "TIER_VOICES",
]


# ============================================================================
# SECTION 8 - Plugin Metadata
# ============================================================================

PLUGIN_NAME = "ftb_broadcast_commentary_llm"
PLUGIN_DESC = "LLM-powered beat-based race commentary with narrative memory (v2)"
IS_FEED = True


# ============================================================================
# SECTION 9 - Beat-Based Feed Worker
# ============================================================================

def feed_worker(stop_event, mem, payload, runtime):
    """
    Beat-based commentary feed worker.

    Architecture:
      1. Collect events per lap into NarrativeState.current_lap_events.
      2. On lap boundary: score -> select top beats -> generate prompt -> speak.
      3. Enforce silence gaps between commentary.
      4. Thread narrative across laps via NarrativeState.
      5. Escalate in final laps.
      6. Clear stale events - never narrate the past.
    """
    import threading
    import queue as queue_mod

    log = runtime.get("log", print)
    event_q = runtime.get("event_q")
    if not event_q:
        log("[commentary] No event queue available")
        return

    log("[commentary] Beat-based commentary feed starting...")

    # ---- mutable state ----
    active_race = False
    generator = None
    league_tier = 3
    player_team = ""
    season_ctx = SeasonContext()
    narrative = NarrativeState()
    dispatcher = BeatDispatcher()

    current_lap = 0
    total_laps = 0
    player_start_pos = 0
    player_had_incident = False

    # ---- helpers ----

    def _speak(prompt):
        """Generate LLM text and emit speech event (runs on background thread)."""
        try:
            from model_provider import get_model

            model = get_model(role="host")
            if not model:
                return
            response = model.generate_content(prompt.prompt)
            text = (
                response.text.strip()
                if hasattr(response, "text")
                else str(response).strip()
            )
            if text.startswith('"') and text.endswith('"'):
                text = text[1:-1]

            voices = TIER_VOICES.get(league_tier, TIER_VOICES[3])
            voice_id = voices.get(prompt.speaker, voices["pbp"])

            event_q.put({
                "type": "commentary_speech",
                "source": "ftb_commentary",
                "payload": {
                    "text": text,
                    "voice": voice_id,
                    "priority": prompt.priority,
                    "speaker": prompt.speaker,
                },
            })
            narrative.log_commentary(text)
            dispatcher.mark_spoken()
            log(f"[commentary] {prompt.speaker.upper()}: {text[:80]}...")
        except Exception as exc:
            log(f"[commentary] Generation error: {exc}")

    def _dispatch_prompts(prompts):
        """Fire prompts sequentially on background threads with stagger."""
        for i, p in enumerate(prompts):
            threading.Thread(target=_speak, args=(p,), daemon=True).start()
            if i < len(prompts) - 1:
                time.sleep(1.0)  # stagger PBP -> Color

    def _infer_player_pos():
        return mem.get("player_position") if mem else None

    def _process_lap_boundary():
        """End-of-lap: score -> select -> dispatch."""
        nonlocal player_had_incident

        if not generator or not active_race:
            return

        # Score all collected events for this lap
        for se in narrative.current_lap_events:
            apply_weight_modifiers(se, current_lap, total_laps, narrative, season_ctx)

        # Select top beats
        beats = dispatcher.select_beats(
            narrative.current_lap_events, current_lap, total_laps, narrative
        )

        # Remember the top event for narrative continuity
        if beats:
            narrative.remember_event(beats[0])

        # Silence logic
        if not beats and dispatcher.should_stay_silent(current_lap, total_laps, narrative):
            narrative.laps_since_commentary += 1
            dispatcher.schedule_silence()
            narrative.current_lap_events.clear()
            return

        # Final lap
        if current_lap == total_laps:
            prompt = generator.generate_final_lap_prompt(
                narrative, player_pos=_infer_player_pos()
            )
            _dispatch_prompts([prompt])
            narrative.current_lap_events.clear()
            return

        # Beat commentary
        if beats and dispatcher.can_speak_now(current_lap, total_laps):
            include_color = dispatcher.color_roll(current_lap, total_laps)
            prompts = generator.generate_beat_prompt(
                beats, current_lap, total_laps, narrative, include_color=include_color
            )
            _dispatch_prompts(prompts)
        elif narrative.laps_since_commentary >= 3:
            # Quiet stretch - try a scenic lap update
            update = generator.generate_lap_update_prompt(
                current_lap, total_laps, narrative, player_pos=_infer_player_pos()
            )
            if update:
                _dispatch_prompts([update])
        else:
            narrative.laps_since_commentary += 1

        narrative.current_lap_events.clear()

    # ---- main event loop ----
    try:
        while not stop_event.is_set():
            try:
                station_event = event_q.get(timeout=0.5)

                # Normalise event shape
                if isinstance(station_event, dict):
                    etype = station_event.get("type", "")
                    source = station_event.get("source", "")
                    epayload = station_event.get("payload", station_event.get("data", {}))
                elif hasattr(station_event, "type"):
                    etype = station_event.type
                    source = getattr(station_event, "source", "")
                    epayload = getattr(
                        station_event, "payload",
                        getattr(station_event, "data", {})
                    )
                else:
                    continue

                # ======== Race start ========
                if etype in ("race_start", "enter_race_weekend") or (
                    source == "ftb" and etype == "race_streaming_started"
                ):
                    active_race = True
                    current_lap = 0
                    player_had_incident = False
                    player_start_pos = 0
                    narrative = NarrativeState()
                    dispatcher = BeatDispatcher()

                    lid = epayload.get("league_id", "")
                    player_team = epayload.get("player_team", "")
                    total_laps = epayload.get("total_laps", 50)

                    tier_map = {
                        "grassroots": 1, "enthusiast": 2,
                        "professional": 3, "premium": 4,
                        "formulaz": 5, "world": 5,
                    }
                    league_tier = 3
                    for kw, t in tier_map.items():
                        if kw in lid.lower():
                            league_tier = t
                            break

                    generator = LLMCommentaryGenerator(
                        league_tier=league_tier,
                        player_team_name=player_team or "Unknown Team",
                        season_context=season_ctx,
                    )

                    log(f"[commentary] Race started - Tier {league_tier} beat engine active")

                    prompt = generator.generate_lights_out_prompt(narrative)
                    _dispatch_prompts([prompt])

                # ======== Race finish ========
                elif active_race and etype in ("race_finish", "checkered_flag"):
                    _process_lap_boundary()

                    if generator:
                        winner = epayload.get("winner", narrative.leader or "Unknown")
                        winner_team = epayload.get("winner_team", narrative.leader_team or "Unknown")
                        player_pos = epayload.get("player_position", _infer_player_pos())
                        prompts = generator.generate_checkered_flag_prompt(
                            winner, winner_team, narrative, player_pos=player_pos
                        )
                        _dispatch_prompts(prompts)

                    active_race = False

                # ======== Lap boundary ========
                elif active_race and etype in ("lap_complete", "lap_update", "new_lap"):
                    new_lap = epayload.get("lap", current_lap + 1)

                    leader = epayload.get("leader", narrative.leader)
                    leader_tm = epayload.get("leader_team", narrative.leader_team)
                    narrative.update_leader(leader, leader_tm, new_lap)
                    narrative.update_phase(new_lap, total_laps)

                    player_pos = epayload.get("player_position", _infer_player_pos())
                    if player_pos and player_start_pos == 0:
                        player_start_pos = player_pos
                    if player_pos:
                        narrative.update_player_arc(player_pos, player_start_pos, player_had_incident)

                    gaps = epayload.get("position_gaps")
                    if gaps:
                        narrative.detect_battles(gaps)

                    # Green-flag tracking
                    had_incident_this_lap = any(
                        se.event_class in ("crash", "player_crash", "leader_crash")
                        for se in narrative.current_lap_events
                    )
                    if not had_incident_this_lap:
                        narrative.tick_green()

                    current_lap = new_lap
                    _process_lap_boundary()

                # ======== In-race events (collected, NOT immediately narrated) ========
                elif active_race and etype in (
                    "overtake", "race_overtake",
                    "crash", "race_crash", "incident",
                    "mechanical_dnf", "dnf",
                    "spin", "collision", "race_pbp",
                ):
                    if not generator:
                        continue

                    evt = dict(epayload)
                    if "event_type" not in evt:
                        evt["event_type"] = etype.replace("race_", "")

                    # Classify and collect - DO NOT narrate yet
                    scored = classify_event(evt, player_team, narrative.leader)
                    scored.lap = evt.get("lap", current_lap)
                    narrative.current_lap_events.append(scored)

                    # Track player incidents for narrative arc
                    if scored.is_player_team and scored.event_class in ("player_crash", "player_dnf"):
                        player_had_incident = True
                        narrative.register_incident(scored.driver, scored.lap)
                    elif scored.event_class in ("crash", "leader_crash"):
                        narrative.register_incident(scored.driver, scored.lap)

                    # Immediate break for catastrophic player events.
                    # These bypass the lap-boundary collector so the player
                    # hears about their own crash/DNF without waiting.
                    if scored.event_class in ("player_crash", "player_dnf"):
                        if dispatcher.can_speak_now(current_lap, total_laps):
                            apply_weight_modifiers(
                                scored, current_lap, total_laps, narrative, season_ctx
                            )
                            narrative.remember_event(scored)
                            beat_prompts = generator.generate_beat_prompt(
                                [scored], current_lap, total_laps, narrative, include_color=True
                            )
                            _dispatch_prompts(beat_prompts)
                            # Remove from collector to avoid double-narration
                            if scored in narrative.current_lap_events:
                                narrative.current_lap_events.remove(scored)

            except queue_mod.Empty:
                continue
            except Exception as exc:
                log(f"[commentary] Event processing error: {exc}")

    finally:
        log("[commentary] Beat-based commentary feed stopped")
