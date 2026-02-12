"""
From the Backmarker Meta Plugin

Handles ALL LLM interaction for From the Backmarker:
1. Audio narration of simulation events (always active)
2. Player delegate AI decision-making (only when delegated)

LLM usage:
- Navigator → Curator → Producer → Decider pipeline for delegate AI
- Segment generation for race results, financial events, etc.
- Formula Z news cycle (periodic broadcasts)
- Omniscient narrator voice for all events

NO simulation logic here - only language generation.

INTEGRATED NARRATIVE ENGINE:
- EventRouter: Classifies events by narrative relevance
- BeatBuilder: Collapses events into composed narrative moments
- ArcMemory: Persistent story state across sim ticks
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import time
import json
import hashlib

# Import MetaPluginBase from bookmark
try:
    from bookmark import MetaPluginBase
except ImportError:
    # If bookmark not in sys.modules, define a minimal stub
    from abc import ABC, abstractmethod
    class MetaPluginBase(ABC):
        @abstractmethod
        def initialize(self, runtime_context, cfg, mem): pass
        @abstractmethod
        def curate_candidates(self, candidates, state): pass
        @abstractmethod
        def generate_script(self, segment, state): pass
        @abstractmethod
        def generate_narration(self, events, context): pass
        @abstractmethod
        def delegate_decision(self, available_actions, state, identity, focus): pass
        @abstractmethod
        def shutdown(self): pass


# ============================================================================
# Narrative Engine Components (merged from narrative_engine.py)
# ============================================================================

class EventTier(Enum):
    """Narrative relevance tiers"""
    US_CORE = "us_core"           # Events directly about player team entities
    US_CONTEXT = "us_context"     # Events changing player constraints
    WORLD_SIGNAL = "world_signal" # Formula Z / tier changes we might care about
    NOISE = "noise"               # Ignorable or batchable AI team events


class EventRouter:
    """Classify simulation events by narrative importance"""
    
    @staticmethod
    def classify(events: List[Any], state: Any, player_team_name: str) -> Dict[str, List[Any]]:
        """Route events into narrative tiers"""
        classified = {
            "us_core": [],
            "us_context": [],
            "world_signal": [],
            "noise": []
        }
        
        for event in events:
            tier = EventRouter._classify_single(event, state, player_team_name)
            classified[tier.value].append(event)
            print(f"[EVENT ROUTER] Event category={event.category}, team={event.data.get('team', 'N/A')}, tier={tier.value}")
        
        return classified
    
    @staticmethod
    def _classify_single(event: Any, state: Any, player_team_name: str) -> EventTier:
        """Classify a single event"""
        category = event.category
        data = event.data
        event_team = data.get("team", "")
        
        # US_CORE: Direct player team events
        if event_team == player_team_name:
            if category in ["race_result", "qualifying_result", "dnf", "incident",
                          "entity_birthday", "contract_expiry", "staff_change",
                          "driver_hired", "driver_fired", "engineer_hired", "engineer_fired",
                          "season_overachievement", "season_underperformance"]:
                return EventTier.US_CORE
        
        # US_CONTEXT: Constraint changes (financial/operational crises)
        if category in ["financial_update", "budget_crisis", "ultimatum",
                       "ownership_change", "regulation_change",
                       "economic_warning", "hiring_freeze", "development_cancellation",
                       "fire_sale", "administration", "ownership_ultimatum",
                       "prize_money"]:
            if event_team == player_team_name or not event_team:
                return EventTier.US_CONTEXT
        
        # WORLD_SIGNAL: Formula Z / tier changes / season progression
        if category in ["championship_result", "season_end", "tier_promotion",
                       "tier_relegation", "team_liquidation",
                       "team_promotion", "team_relegation",
                       "offseason_end", "enter_race_weekend"]:
            return EventTier.WORLD_SIGNAL
        
        return EventTier.NOISE


@dataclass
class NarratorBeat:
    """Documentary narrator beat (Jarvis voice)"""
    text: str
    intent: str  # turning_point, warning, relief, momentum, setback, opportunity
    facts_bundle: Dict[str, Any]
    priority: float = 50.0
    event_ids: List[int] = field(default_factory=list)
    
    def to_packet(self, voice_name: str = "narrator") -> Dict[str, Any]:
        """Convert to host packet for TTS pipeline"""
        return {
            "event_type": "ftb_narration",
            "source": "ftb",
            "voice": voice_name,
            "host_intro": "",
            "summary": self.text,
            "panel": [],
            "host_takeaway": ""
        }


@dataclass
class NewsBeat:
    """Formula Z news anchor beat"""
    headline: str
    detail: str
    formula_z_data: Dict[str, Any]
    priority: float = 30.0
    
    def to_packet(self, voice_name: str = "formula_z_news") -> Dict[str, Any]:
        """Convert to host packet for TTS pipeline"""
        return {
            "event_type": "ftb_news",
            "source": "ftb",
            "voice": voice_name,
            "host_intro": self.headline,
            "summary": self.detail,
            "panel": [],
            "host_takeaway": ""
        }


class ArcMemory:
    """Persistent narrative state across simulation"""
    
    def __init__(self, mem: Dict[str, Any]):
        self.mem = mem
        self.data = mem.setdefault("ftb_narrative_state", {})
        
        # Initialize fields if missing
        self.data.setdefault("themes", [])
        self.data.setdefault("open_loops", [])
        self.data.setdefault("last_formula_z_top3", [])
        self.data.setdefault("last_formula_z_leader", "")
        self.data.setdefault("last_formula_z_news_tick", 0)
        self.data.setdefault("recent_pain_points", [])
        self.data.setdefault("momentum", "unknown")
    
    def add_theme(self, theme: str) -> None:
        """Add a narrative theme"""
        themes = self.data.get("themes", [])
        if theme not in themes:
            themes.append(theme)
        self.data["themes"] = themes[-20:]
    
    def add_open_loop(self, loop: str) -> None:
        """Add an unresolved story thread"""
        loops = self.data.get("open_loops", [])
        if loop not in loops:
            loops.append(loop)
        self.data["open_loops"] = loops[-10:]
    
    def update_momentum(self, new_momentum: str) -> None:
        """Update trajectory momentum"""
        self.data["momentum"] = new_momentum
    
    def save(self) -> None:
        """Persist to station memory"""
        try:
            import bookmark
            bookmark.save_memory(self.mem)
        except Exception:
            pass


class BeatBuilder:
    """Compose narrative beats from classified events"""
    
    def __init__(self, llm_generate_fn, cfg: Dict[str, Any], log_fn):
        self.llm_generate = llm_generate_fn
        self.cfg = cfg
        self.log = log_fn
    
    def build_beats(self, classified: Dict[str, List[Any]], state: Any,
                   arc_memory: ArcMemory, facts_bundle: Dict[str, Any]) -> List[Any]:
        """Generate beats from classified events"""
        beats = []
        
        # Debug: Log classified event counts
        for tier, events in classified.items():
            if events:
                self.log('meta', f"Classified tier '{tier}': {len(events)} events")
        
        self.log('meta', 'Starting race weekend collapse...')
        # 1. Race weekend collapsing (highest priority)
        race_beats = self._collapse_race_weekend(
            classified.get("us_core", []), state, arc_memory, facts_bundle
        )
        beats.extend(race_beats)
        self.log('meta', f'Race beats generated: {len(race_beats)}')
        
        self.log('meta', 'Starting personnel beats...')
        # 2. Personnel events (hirings, firings, contracts)
        personnel_beats = self._collapse_personnel_events(
            classified.get("us_interaction", []), state, arc_memory, facts_bundle
        )
        beats.extend(personnel_beats)
        self.log('meta', f'Personnel beats generated: {len(personnel_beats)}')
        
        self.log('meta', 'Starting development beats...')
        # 3. Development/technical events
        dev_beats = self._collapse_development_events(
            classified.get("us_context", []), state, arc_memory, facts_bundle
        )
        beats.extend(dev_beats)
        self.log('meta', f'Development beats generated: {len(dev_beats)}')
        
        self.log('meta', 'Starting context collapse...')
        # 4. Financial/context updates (medium priority)
        context_beats = self._collapse_context(
            classified.get("us_context", []), state, arc_memory, facts_bundle
        )
        beats.extend(context_beats)
        self.log('meta', f'Context beats generated: {len(context_beats)}')
        
        self.log('meta', 'Checking Formula Z news...')
        # 5. Formula Z news (periodic, independent)
        formula_z_beat = self._check_formula_z_news(state, arc_memory)
        if formula_z_beat:
            beats.append(formula_z_beat)
            self.log('meta', 'Formula Z beat added')
        
        self.log('meta', f'build_beats complete: {len(beats)} total beats')
        return beats
    
    def _collapse_race_weekend(self, events: List[Any], state: Any,
                               arc_memory: ArcMemory,
                               facts_bundle: Dict[str, Any]) -> List[NarratorBeat]:
        """Collapse qualifying + race events into 1-2 beats"""
        beats = []
        
        qualifying_events = [e for e in events if e.category == "qualifying_result"]
        race_events = [e for e in events if e.category == "race_result"]
        dnf_events = [e for e in events if e.category == "dnf"]
        
        self.log('meta', f"_collapse_race_weekend: qual={len(qualifying_events)}, race={len(race_events)}, dnf={len(dnf_events)}, total_events={len(events)}")
        
        # Debug: Log all event categories
        for e in events:
            self.log('meta', f"  -> Event category: {e.category}")
        
        # DNF takes priority — suppress other race beats
        if dnf_events:
            dnf_event = dnf_events[0]
            beat = self._generate_narrator_beat(
                dnf_event,
                intent="setback",
                facts_bundle=facts_bundle,
                arc_memory=arc_memory
            )
            if beat:
                beats.append(beat)
            return beats
        
        # Qualifying beat (brief)
        if qualifying_events:
            qual_event = qualifying_events[0]
            beat = self._generate_narrator_beat(
                qual_event,
                intent="momentum",
                facts_bundle=facts_bundle,
                arc_memory=arc_memory
            )
            if beat:
                beats.append(beat)
        
        # Race beat (detailed)
        if race_events:
            race_event = race_events[0]
            position = race_event.data.get("position", 0)
            
            if position <= 3:
                intent = "turning_point"
            elif position <= 10:
                intent = "relief"
            else:
                intent = "momentum"
            
            beat = self._generate_narrator_beat(
                race_event,
                intent=intent,
                facts_bundle=facts_bundle,
                arc_memory=arc_memory
            )
            if beat:
                beats.append(beat)
        
        return beats
    
    def _collapse_personnel_events(self, events: List[Any], state: Any,
                                    arc_memory: ArcMemory,
                                    facts_bundle: Dict[str, Any]) -> List[NarratorBeat]:
        """Generate beats for personnel changes (hiring, firing, contracts)"""
        beats = []
        
        self.log('meta', f"_collapse_personnel_events called with {len(events)} events")
        
        # Filter personnel-related events
        hiring_events = [e for e in events if e.category in ["driver_hired", "engineer_hired", "mechanic_hired", "strategist_hired"]]
        firing_events = [e for e in events if e.category in ["driver_fired", "engineer_fired", "mechanic_fired", "strategist_fired"]]
        contract_events = [e for e in events if e.category == "contract_expiry"]
        
        # Firings are highest priority (dramatic)
        if firing_events:
            for event in firing_events[:2]:  # Limit to 2 firings per tick
                beat = self._generate_narrator_beat(
                    event,
                    intent="setback",
                    facts_bundle=facts_bundle,
                    arc_memory=arc_memory
                )
                if beat:
                    beats.append(beat)
                    self.log('meta', f"Generated firing beat from {event.category}")
        
        # Contract warnings (medium priority)
        if contract_events:
            for event in contract_events[:1]:  # One contract warning per tick
                beat = self._generate_narrator_beat(
                    event,
                    intent="warning",
                    facts_bundle=facts_bundle,
                    arc_memory=arc_memory
                )
                if beat:
                    beats.append(beat)
                    self.log('meta', f"Generated contract expiry beat")
        
        # Hirings (positive news, lower priority)
        if hiring_events and not firing_events:  # Don't mix hiring with firing news
            for event in hiring_events[:1]:  # One hiring per tick
                beat = self._generate_narrator_beat(
                    event,
                    intent="momentum",
                    facts_bundle=facts_bundle,
                    arc_memory=arc_memory
                )
                if beat:
                    beats.append(beat)
                    self.log('meta', f"Generated hiring beat from {event.category}")
        
        return beats
    
    def _collapse_development_events(self, events: List[Any], state: Any,
                                      arc_memory: ArcMemory,
                                      facts_bundle: Dict[str, Any]) -> List[NarratorBeat]:
        """Generate beats for development and technical progress"""
        beats = []
        
        self.log('meta', f"_collapse_development_events called with {len(events)} events")
        
        # Filter development-related events
        dev_complete_events = [e for e in events if e.category == "development_complete"]
        upgrade_events = [e for e in events if e.category == "upgrade_installed"]
        regression_events = [e for e in events if e.category in ["development_regression", "reliability_failure"]]
        
        # Regressions/failures (setback)
        if regression_events:
            for event in regression_events[:1]:
                beat = self._generate_narrator_beat(
                    event,
                    intent="setback",
                    facts_bundle=facts_bundle,
                    arc_memory=arc_memory
                )
                if beat:
                    beats.append(beat)
                    self.log('meta', f"Generated regression beat from {event.category}")
        
        # Successful development completions (momentum)
        elif dev_complete_events:  # Only if no regressions
            for event in dev_complete_events[:1]:
                beat = self._generate_narrator_beat(
                    event,
                    intent="momentum",
                    facts_bundle=facts_bundle,
                    arc_memory=arc_memory
                )
                if beat:
                    beats.append(beat)
                    self.log('meta', f"Generated development complete beat")
        
        # Upgrades installed (relief/momentum)
        elif upgrade_events:
            for event in upgrade_events[:1]:
                beat = self._generate_narrator_beat(
                    event,
                    intent="relief",
                    facts_bundle=facts_bundle,
                    arc_memory=arc_memory
                )
                if beat:
                    beats.append(beat)
                    self.log('meta', f"Generated upgrade beat")
        
        return beats
    
    def _collapse_context(self, events: List[Any], state: Any,
                         arc_memory: ArcMemory,
                         facts_bundle: Dict[str, Any]) -> List[NarratorBeat]:
        """Generate beats for financial/constraint changes"""
        beats = []
        
        self.log('meta', f"_collapse_context called with {len(events)} events")
        
        # Financial warnings (hiring freeze, economic warning, etc.)
        warning_events = [e for e in events if e.category in [
            "hiring_freeze", "economic_warning", "development_cancellation",
            "fire_sale", "administration"
        ]]
        
        # Critical financial events
        financial_events = [e for e in events if e.category in [
            "financial_update", "budget_crisis", "ownership_ultimatum"
        ]]
        
        # Emit one beat for most severe financial issue
        if warning_events:
            most_severe = max(warning_events, key=lambda e: e.priority)
            beat = self._generate_narrator_beat(
                most_severe,
                intent="warning",
                facts_bundle=facts_bundle,
                arc_memory=arc_memory
            )
            if beat:
                beats.append(beat)
                self.log('meta', f"Generated warning beat from {most_severe.category}")
        
        elif financial_events:
            for event in financial_events:
                cash = event.data.get("budget", 0)
                if cash < 50000:  # Critical threshold
                    beat = self._generate_narrator_beat(
                        event,
                        intent="warning",
                        facts_bundle=facts_bundle,
                        arc_memory=arc_memory
                    )
                    if beat:
                        beats.append(beat)
                        self.log('meta', f"Generated financial beat from {event.category}")
        
        return beats
    
    def _check_formula_z_news(self, state: Any, arc_memory: ArcMemory) -> Optional[NewsBeat]:
        """Generate periodic Formula Z news beat"""
        current_tick = state.tick
        last_news_tick = arc_memory.data.get("last_formula_z_news_tick", 0)
        news_interval = 50
        
        if current_tick - last_news_tick < news_interval:
            return None
        
        # Find Formula Z league (tier 5)
        formula_z_league = None
        for league in state.leagues.values():
            if league.tier == 5:
                formula_z_league = league
                break
        
        if not formula_z_league:
            return None
        
        standings = sorted(
            formula_z_league.championship_table.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        if not standings:
            return None
        
        current_top3 = [team for team, _ in standings]
        last_top3 = arc_memory.data.get("last_formula_z_top3", [])
        
        standings_changed = current_top3 != last_top3
        
        if not standings_changed and current_tick - last_news_tick < news_interval * 2:
            return None
        
        # Update arc memory
        arc_memory.data["last_formula_z_news_tick"] = current_tick
        arc_memory.data["last_formula_z_top3"] = current_top3
        arc_memory.data["last_formula_z_leader"] = current_top3[0] if current_top3 else ""
        
        headline = f"Formula Z Update: {current_top3[0]} leads championship"
        points_text = ", ".join([f"{team} ({pts}pts)" for team, pts in standings])
        detail = f"Current standings: {points_text}."
        
        return NewsBeat(
            headline=headline,
            detail=detail,
            formula_z_data={"standings": standings},
            priority=30.0
        )
    
    def _generate_narrator_beat(self, event: Any, intent: str,
                                facts_bundle: Dict[str, Any],
                                arc_memory: ArcMemory) -> Optional[NarratorBeat]:
        """Generate a single narrator beat via LLM with natural prompting"""
        if not self.llm_generate:
            self.log("narrator", "llm_generate not available, skipping beat generation")
            return None
        
        try:
            self.log("narrator", f"Generating beat for event {event.category} with intent {intent}")
            system_prompt = self._narrator_system_prompt(facts_bundle, intent, arc_memory)
            user_prompt = self._narrator_user_prompt(event, facts_bundle)
            
            model = self.cfg.get("models", {}).get("narrator", "llama3.1:8b")
            self.log("narrator", f"Calling LLM with model {model}")
            
            text = self.llm_generate(
                prompt=user_prompt,
                system=system_prompt,
                model=model,
                num_predict=150,
                temperature=0.8,
                timeout=10
            )
            
            self.log("narrator", f"LLM returned {len(text) if text else 0} chars")
            
            text = text.strip() if text else ""
            if not text:
                self.log("narrator", "LLM returned empty text")
                return None
            
            beat = NarratorBeat(
                text=text,
                intent=intent,
                facts_bundle=facts_bundle,
                priority=event.priority,
                event_ids=[event.event_id]
            )
            self.log("narrator", f"Beat created successfully: {text[:50]}...")
            return beat
        
        except Exception as e:
            self.log("narrator", f"Beat generation error: {e}")
            import traceback
            self.log("narrator", traceback.format_exc())
            return None
    
    def _narrator_system_prompt(self, facts_bundle: Dict[str, Any],
                                intent: str, arc_memory: ArcMemory) -> str:
        """Build narrator system prompt - natural documentary style"""
        team_name = facts_bundle.get("team", {}).get("name", "the team")
        themes = arc_memory.data.get("themes", [])[-5:]
        open_loops = arc_memory.data.get("open_loops", [])[-3:]
        
        themes_text = ", ".join(themes) if themes else "the journey from the back"
        loops_text = "\n".join([f"- {loop}" for loop in open_loops]) if open_loops else "(none)"
        
        return f"""You are the narrator of a documentary series following {team_name}'s motorsport journey.

Your voice is contemplative, observant, and grounded. Think of nature documentaries or Ken Burns — you're the voice that ties moments into meaning.

Current narrative threads: {themes_text}

Unresolved tensions: 
{loops_text}

This beat represents: {intent}

Speak in natural English as if you're recording voiceover for a film. Write 2-3 sentences that flow as spoken narration. Use past tense. Connect this moment to their larger struggle.

Do not output any labels, tags, or structured formats. Just the narration itself."""
    
    def _narrator_user_prompt(self, event: Any, facts_bundle: Dict[str, Any]) -> str:
        """Build narrator user prompt - natural conversational style"""
        category = event.category
        data = event.data
        team_name = facts_bundle.get("team", {}).get("name", "the team")
        cash = facts_bundle.get("team", {}).get("cash", 0)
        tier = facts_bundle.get("team", {}).get("tier", 0)
        
        # Build natural description
        if category == "race_result":
            position = data.get("position", 0)
            grid = data.get("grid_position", 0)
            points = data.get("points", 0)
            driver = data.get("driver", "the driver")
            
            situation = f"{driver} brought the car home in P{position}, having started {grid}th on the grid. They scored {points} championship points."
        
        elif category == "qualifying_result":
            position = data.get("position", 0)
            gap = data.get("gap_to_pole", 0.0)
            driver = data.get("driver", "the driver")
            
            situation = f"In qualifying, {driver} managed P{position}, {gap:.3f} seconds off pole position."
        
        elif category == "dnf":
            lap = data.get("lap", 0)
            reason = data.get("reason", "unknown")
            driver = data.get("driver", "the driver")
            
            situation = f"On lap {lap}, {driver}'s race came to an end. The reason: {reason}."
        
        elif category == "financial_update":
            situation = f"The team's budget now stands at ${cash:,.0f}."
        
        else:
            situation = f"Something happened: {category}"
        
        return f"""{situation}

{team_name} operates in Tier {tier} with ${cash:,.0f} remaining. 

Narrate this moment as part of their documentary. What does it mean for their trajectory?"""


class FromTheBackmarkerMetaPlugin(MetaPluginBase):
    def __init__(self):
        self.runtime_context = None
        self.cfg = None
        self.mem = None
        self.log = None
        self.llm_generate = None
        self.last_formula_z_news_tick = 0
        self.formula_z_news_interval = 50
        
    def initialize(self, runtime_context, cfg, mem):
        self.runtime_context = runtime_context
        self.cfg = cfg
        self.mem = mem
        self.log = runtime_context.get('log', print)
        try:
            import bookmark
            self.llm_generate = bookmark.llm_generate
        except: pass
        self.log('meta', 'FromTheBackmarkerMetaPlugin initialized')
    
    def generate_narration(self, events, context):
        """
        Convert simulation events into narration segments for audio pipeline.
        
        **DEPRECATED:** FTB now uses the narrative engine pipeline which emits
        beats directly to the DB via ftb_emit_segments().
        
        Returns:
            Empty list (narration now happens via ftb_emit_segments)
        """
        return []
    
    def delegate_decision(self, available_actions, state, identity, focus):
        """
        Make a decision when player delegates control.
        
        Args:
            available_actions: List of Action objects that are legal
            state: SimState snapshot
            identity: List of player identity strings
            focus: Current player focus string (e.g., "development", "results")
        
        Returns:
            Selected Action object or None
        """
        if not available_actions:
            return None
        
        if not self.llm_generate:
            # Fallback: simple heuristic
            return self._heuristic_decision(available_actions, state, focus)
        
        try:
            # Build decision prompt
            situation = self._describe_situation(state)
            actions_desc = self._describe_actions(available_actions, state)
            
            system_prompt = f"""You are the AI principal making decisions for a racing team.

Current focus: {focus}
Player identity: {', '.join(identity) if identity else 'Unknown'}

Goal: Select the best action based on current situation, budget, and focus.

Output STRICT JSON only:
{{
    "action_index": 0,
    "reasoning": "Brief explanation"
}}"""
            
            user_prompt = f"""Current situation:
{situation}

Available actions:
{actions_desc}

Budget: ${state.player_team.budget.cash:,.0f}
Focus: {focus}

Select the best action (return index 0-{len(available_actions)-1})."""
            
            # Generate decision
            host_model = self.cfg.get('models', {}).get('host_model', '')
            response = self.llm_generate(
                prompt=user_prompt,
                system=system_prompt,
                model=host_model,
                num_predict=200,
                temperature=0.7,
                timeout=15,
                force_json=True
            )
            
            # Parse response
            try:
                import bookmark
                decision = bookmark.parse_json_strictish(response)
                action_index = int(decision.get('action_index', 0))
                reasoning = decision.get('reasoning', '')
                
                if 0 <= action_index < len(available_actions):
                    selected = available_actions[action_index]
                    self.log('delegate', f'Selected {selected.name}: {reasoning}')
                    return selected
            
            except Exception:
                pass
        
        except Exception as e:
            self.log('delegate', f'LLM decision failed: {e}')
        
        # Fallback to heuristic
        return self._heuristic_decision(available_actions, state, focus)
    
    def _heuristic_decision(self, available_actions, state, focus) -> Any:
        """Simple heuristic fallback when LLM unavailable"""
        # Score actions by focus alignment and budget fit
        scored = []
        
        for action in available_actions:
            score = 50.0  # Base score
            
            # Budget fit (prefer actions we can afford comfortably)
            if state.player_team:
                budget = state.player_team.budget.cash
                if action.cost <= budget * 0.5:
                    score += 20.0
                elif action.cost <= budget * 0.8:
                    score += 10.0
            
            # Focus alignment (simple keyword matching)
            action_name_lower = action.name.lower()
            focus_lower = (focus or '').lower()
            
            if 'develop' in focus_lower and 'develop' in action_name_lower:
                score += 30.0
            elif 'hire' in focus_lower and 'hire' in action_name_lower:
                score += 30.0
            elif 'result' in focus_lower and 'promote' in action_name_lower:
                score += 30.0
            
            scored.append((action, score))
        
        # Select highest scoring
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored else None
    
    def _describe_situation(self, state) -> str:
        """Generate situation description for LLM"""
        if not state.player_team:
            return "No team data available."
        
        team = state.player_team
        parts = [
            f"Tick: {state.tick}",
            f"Phase: {state.phase}",
            f"Team: {team.name}",
            f"Budget: ${team.budget.cash:,.0f}",
        ]
        
        # Add standings if available
        metrics = team.standing_metrics
        if metrics:
            parts.append(f"Legitimacy: {metrics.get('legitimacy', 50):.0f}")
            parts.append(f"Reputation: {metrics.get('reputation', 50):.0f}")
        
        return "\n".join(parts)
    
    def _describe_actions(self, actions, state) -> str:
        """Generate action descriptions for LLM"""
        lines = []
        for i, action in enumerate(actions):
            lines.append(f"{i}. {action.name} (Cost: ${action.cost:,.0f})")
        return "\n".join(lines)
    
    def generate_formula_z_news(self, state, leagues_dict) -> Optional[Dict[str, Any]]:
        """
        Generate a Formula Z news headline (periodic world context).
        
        Args:
            state: SimState object
            leagues_dict: Dict of league_id -> League
        
        Returns:
            Dict with text, voice, event_id or None
        """
        # Check if enough time has passed
        if state.tick - self.last_formula_z_news_tick < self.formula_z_news_interval:
            return None
        
        self.last_formula_z_news_tick = state.tick
        
        # Find Formula Z league
        formula_z_league = None
        for league_id, league in leagues_dict.items():
            if league.tier == 5 and 'z' in league_id.lower():
                formula_z_league = league
                break
        
        if not formula_z_league or not formula_z_league.teams:
            return None
        
        # Get current standings (top 3 teams)
        standings = sorted(
            formula_z_league.standings.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        if not self.llm_generate:
            # Fallback: simple headline
            if standings:
                top_team = standings[0][0]
                headline = f"Formula Z Update: {top_team} leads championship standings"
            else:
                headline = "Formula Z season continues with intense competition"
            
            return {
                'text': headline,
                'voice': 'formula_z_news',
                'event_id': 0,
                'priority': 30.0
            }
        
        # LLM-generated headline
        try:
            standings_text = "\n".join([f"{i+1}. {team}: {points} points" for i, (team, points) in enumerate(standings)])
            
            system_prompt = """You are a sports news anchor providing a brief Formula Z update.

Write a single 15-word headline about the current state of Formula Z (the top tier).
Focus on standings, championship battles, or notable developments.
Do NOT mention lower tier teams or the player unless they're in Formula Z.

Output ONLY the headline text, no quotes, no introduction."""
            
            user_prompt = f"""Current Formula Z Standings:
{standings_text}

Tick: {state.tick}

Generate a concise Formula Z news headline (15 words max):"""
            
            host_model = self.cfg.get('models', {}).get('host_model', '')
            headline_text = self.llm_generate(
                prompt=user_prompt,
                system=system_prompt,
                model=host_model,
                num_predict=50,
                temperature=0.8,
                timeout=10
            ).strip()
            
            # Validate length
            if len(headline_text.split()) > 20:
                headline_text = ' '.join(headline_text.split()[:20])
            
            return {
                'text': headline_text,
                'voice': 'formula_z_news',
                'event_id': 0,
                'priority': 30.0
            }
        
        except Exception as e:
            self.log('meta', f'Formula Z news generation error: {e}')
            return None
    
    # =========================================================================
    # NEW: Beat-Based Segment Emission
    # =========================================================================
    
    def ftb_emit_segments(self, events: List[Any], state: Any, conn) -> None:
        """
        Convert simulation events into narrative beats and emit as DB segments.
        
        This is the NEW pipeline that replaces atomic event narration.
        
        Args:
            events: List of SimEvent objects from tick
            state: SimState snapshot
            conn: Database connection for segment insertion
        """
        try:
            self.log('meta', f'ftb_emit_segments called with {len(events)} events')
            
            # Early exit if no events
            if not events:
                self.log('meta', 'No events to process')
                return
            
            # Import helpers
            from plugins.ftb_game import FTBNarrationHelpers
            import bookmark
            
            # Get player team name
            player_team_name = FTBNarrationHelpers.get_player_team_name(state)
            if not player_team_name:
                self.log('meta', 'No player team found, skipping narration')
                return
            
            self.log('meta', f'Player team: {player_team_name}')
            
            # 1. Classify events
            self.log('meta', 'Starting event classification...')
            classified = EventRouter.classify(events, state, player_team_name)
            
            # Log classification results
            for tier, tier_events in classified.items():
                if tier_events:
                    self.log('meta', f"Classified tier '{tier}': {len(tier_events)} events")
            
            # 2. Get narration facts bundle
            self.log('meta', 'Getting narration facts...')
            try:
                facts_bundle = FTBNarrationHelpers.get_narration_facts(state, events)
            except Exception as e:
                self.log('meta', f'Error getting narration facts: {e}')
                facts_bundle = {}
            
            # 3. Initialize arc memory
            self.log('meta', 'Initializing arc memory...')
            try:
                arc_memory = ArcMemory(self.mem)
            except Exception as e:
                self.log('meta', f'Error initializing arc memory: {e}')
                return
            
            # 4. Build beats
            self.log('meta', 'Building beats...')
            try:
                beat_builder = BeatBuilder(self.llm_generate, self.cfg, self.log)
                beats = beat_builder.build_beats(classified, state, arc_memory, facts_bundle)
            except Exception as e:
                self.log('meta', f'Error building beats: {e}')
                import traceback
                self.log('meta', traceback.format_exc())
                beats = []
            
            self.log('meta', f'Beat builder returned {len(beats)} beats')
            
            # 5. Convert beats to segments and enqueue
            for beat in beats:
                try:
                    # Get voice from config
                    if isinstance(beat, NarratorBeat):
                        voice_name = self.cfg.get('voices', {}).get('narrator', 'host')
                    elif isinstance(beat, NewsBeat):
                        voice_name = self.cfg.get('voices', {}).get('formula_z_news', 'host')
                    else:
                        voice_name = 'host'
                    
                    # Convert beat to packet
                    packet = beat.to_packet(voice_name)
                    
                    # Create segment dict for DB
                    segment = {
                        "id": self._generate_segment_id(beat),
                        "post_id": self._generate_post_id(beat),
                        "source": "ftb",
                        "event_type": packet["event_type"],
                        "title": packet.get("host_intro", "From the Backmarker")[:200],
                        "body": packet.get("summary", "")[:2000],
                        "comments": [],
                        "angle": beat.intent if isinstance(beat, NarratorBeat) else "formula_z_news",
                        "why": "FTB narrative beat",
                        "key_points": [],
                        "priority": beat.priority,
                        "host_hint": packet["event_type"]
                    }
                    
                    # Enqueue segment
                    bookmark.db_enqueue_segment(conn, segment)
                    
                    self.log('meta', f"Emitted {packet['event_type']} beat: {segment['title'][:40]}")
                
                except Exception as e:
                    self.log('meta', f'Beat emission error: {e}')
            
            # 6. Save arc memory
            try:
                arc_memory.save()
                self.log('meta', 'Arc memory saved')
            except Exception as e:
                self.log('meta', f'Error saving arc memory: {e}')
            
            # Log stats
            total_events = sum(len(v) for v in classified.values())
            self.log('meta', f'Processed {total_events} events → {len(beats)} beats')
            self.log('meta', 'ftb_emit_segments completed successfully')
        
        except Exception as e:
            self.log('meta', f'ftb_emit_segments error: {e}')
            import traceback
            self.log('meta', traceback.format_exc())
    
    def _generate_segment_id(self, beat: Any) -> str:
        """Generate unique segment ID for beat"""
        import hashlib
        import time
        
        if isinstance(beat, NarratorBeat):
            content = beat.text[:100] + str(beat.event_ids)
        elif isinstance(beat, NewsBeat):
            content = beat.headline
        else:
            content = str(time.time())
        
        hash_input = f"ftb_beat|{time.time()}|{content}"
        return hashlib.sha1(hash_input.encode()).hexdigest()[:16]
    
    def _generate_post_id(self, beat: Any) -> str:
        """Generate post ID for beat"""
        import hashlib
        import time
        
        hash_input = f"ftb_post|{time.time()}"
        return hashlib.sha1(hash_input.encode()).hexdigest()[:16]
    
    # =========================================================================
    # Abstract Methods (From The Backmarker Context)
    # =========================================================================
    
    def curate_candidates(self, candidates: List[Any], state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Analyze feed candidates and return 'Discoveries' for radio/news segments.
        For FTB game context, this processes simulation events into broadcastable content.
        
        Returns empty list - FTB uses generate_narration() for event processing.
        """
        # FTB uses generate_narration() directly for simulation events
        # This method exists to satisfy the abstract base class
        return []
    
    def generate_script(self, segment: Dict[str, Any], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Convert a single segment into a 'Host Packet' (JSON script with voices).
        For FTB, narration is generated via generate_narration() instead.
        
        Returns None - FTB uses different narration pipeline.
        """
        # FTB uses generate_narration() for event-driven narration
        # This method exists to satisfy the abstract base class
        return None
    
    def shutdown(self):
        pass
