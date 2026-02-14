"""
FTB Broadcast Commentary Generator

Generates play-by-play and color commentary for races.
Two-voice broadcast crew system (not the narrator).

Voice assignments:
- Play-by-play: Energetic, exclamatory lap-by-lap calls
- Color: Equal-weight analysis with depth and gravitas

STYLE PHILOSOPHY:
  Every call should sound like it MATTERS. No flat position readouts.
  Exclamation marks everywhere — TTS engines interpret them as emphasis.
  Color commentary fires on EVERY event, not 30% of the time.
  Treat every driver equally — drama exists everywhere on the grid.
"""

from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
import random


@dataclass
class CommentaryLine:
    """A single commentary line from broadcast crew"""
    speaker: str  # 'pbp' or 'color'
    text: str
    timing: str  # 'pre_lap', 'during_lap', 'post_lap', 'incident'
    priority: int  # Higher = more important


@dataclass
class RaceContext:
    """Track the context and storylines of the race"""
    lap_number: int = 0
    total_laps: int = 0
    recent_incidents: List[str] = None
    battle_zones: List[Tuple[int, int]] = None  # Position ranges with close battles
    momentum_shifts: Dict[str, int] = None  # Driver name -> momentum (+/- integer)
    championship_implications: Dict[str, str] = None  # Driver -> context string
    weather_changing: bool = False
    safety_car_active: bool = False
    used_phrases: Set[str] = None  # Track what we've said recently
    overtake_count: int = 0  # Track total overtakes this race
    
    def __post_init__(self):
        if self.recent_incidents is None:
            self.recent_incidents = []
        if self.battle_zones is None:
            self.battle_zones = []
        if self.momentum_shifts is None:
            self.momentum_shifts = {}
        if self.championship_implications is None:
            self.championship_implications = {}
        if self.used_phrases is None:
            self.used_phrases = set()


class BroadcastCommentaryGenerator:
    """Generates dramatic, exclamatory commentary for race events.
    
    Every call should feel like a moment. No robotic position readouts.
    Color commentary fires on EVERY significant event.
    """
    
    def __init__(self, league_tier: int, player_team_name: str):
        self.league_tier = league_tier
        self.player_team = player_team_name
        self.commentary_style = self._get_style_for_tier(league_tier)
        self.race_context = RaceContext()
        
        # Commentator personalities (randomized per race)
        self.pbp_personality = random.choice(['enthusiastic', 'dramatic', 'dramatic', 'enthusiastic'])
        self.color_personality = random.choice(['analytical', 'tactical', 'driver_focused', 'analytical'])
        
        # Template pools for varied generation
        self._init_commentary_templates()
    
    def _init_commentary_templates(self):
        """Initialize varied commentary template pools — everything punchy, everything alive."""
        
        # Pre-race openings with personality variations
        self.pre_race_opens = {
            'grassroots': [
                "Alright folks, we are LIVE from {track}! Grid is set, engines are fired up!",
                "Good {time_of_day} everyone! We're here at {track}, and this one feels special!",
                "Welcome to {track}! The drivers are locked in and ready to race!",
                "Here we are at {track}, and what a grid we've got today! Let's go!",
            ],
            'enthusiast': [
                "We're live from {track} and the atmosphere is absolutely electric!",
                "Welcome to {track}! The field is assembled and hungry to race!",
                "Good {time_of_day} race fans! {track} plays host to what could be a classic!",
                "{track} is the venue, and we are minutes from lights out!",
            ],
            'professional': [
                "Good {time_of_day} everyone! We're at {track} and this field is ready to go to war!",
                "Welcome to {track}! The grid is formed, the tension is palpable!",
                "From {track}, welcome to race coverage! Everything is on the line today!",
                "We're live at {track}! The starting procedure is underway!",
            ],
            'premium': [
                "Welcome to {track}! The grid is formed, and you can feel the anticipation building!",
                "Good {time_of_day} from {track}! We're moments from battle!",
                "{track} awaits! The field is assembled for what promises to be a thriller!",
                "From the grid at {track}! We are ready to bring you every single moment!",
            ],
            'world_class': [
                "Welcome to {track}! The grid is formed, and we are moments away from lights out!",
                "From {track}, welcome! The tension is palpable as we approach the start!",
                "Good {time_of_day}! {track} plays host, and the field is primed for battle!",
                "{track} sets the stage! The world's best are moments from green flag racing!",
            ]
        }
        
        # Lights out calls - ALL dramatic, no boring measured ones
        self.lights_out_calls = {
            'enthusiastic': [
                "And it's LIGHTS OUT AND AWAY WE GO!",
                "Green flag! HERE WE GO RACING!",
                "They're away! LET'S GO!",
                "LIGHTS OUT! The race is ON!",
            ],
            'measured': [
                "And we're UNDERWAY! The race begins!",
                "Green flag! They're RACING!",
                "Lights out, and the field launches!",
                "The race is UNDERWAY!",
            ],
            'dramatic': [
                "LIGHTS OUT AND AWAY WE GO!",
                "Green flag! THE BATTLE BEGINS!",
                "They're away! WHAT DRAMA AWAITS!",
                "HERE! WE! GO!",
            ],
            'technical': [
                "Green flag! Clean launches across the field!",
                "Lights out! Launch phase, and they're AWAY!",
                "Race start! Clean getaway from the front!",
                "Green! They're AWAY!",
            ]
        }
        
        # Overtake templates — NO boring "moved up to P4" readouts
        # Every pass is a STORY, not a database update
        self.overtake_templates = {
            'clean_pass': [
                "{driver} finds the gap and TAKES IT! Brilliant move!",
                "OH! {driver} with a beautiful piece of racecraft! What a pass!",
                "{driver} threads the needle! That is MOTORSPORT!",
                "Inch perfect from {driver}! That's why they're out here!",
                "What composure from {driver}! Waited for the moment and POUNCED!",
                "{driver} makes it look EASY! But trust me, it was anything but!",
                "Clinical! {driver} sees daylight and doesn't hesitate!",
                "{driver} with the switchback! Brave, brave racing!",
            ],
            'aggressive': [
                "{driver} SENDS IT! No hesitation, no mercy!",
                "BOLD from {driver}! That took serious courage!",
                "{driver} muscles through! You do NOT want to race that hard!",
                "{driver} goes DEEP on the brakes! Aggressive, committed, brilliant!",
                "{driver} lunges for the inside! The crowd is on their FEET!",
                "WHAT A MOVE from {driver}! That was audacious!",
            ],
            'player_team': [
                "YES! YES! {driver} makes it happen! What a moment!",
                "THERE IT IS! {driver} with the overtake of the race!",
                "COME ON! {driver} is ON FIRE today!",
                "BEAUTIFUL! {driver} just carved through like a hot knife!",
                "{driver} gets it done! This crowd is LOVING it!",
                "WHAT A PASS! {driver} is in the zone, absolutely in the ZONE!",
            ],
            'late_race': [
                "{driver} STRIKES with everything on the line!",
                "This late in the race?! {driver} finds another gear! INCREDIBLE!",
                "{driver} REFUSES to settle! What a competitor!",
                "The race is ALIVE! {driver} making moves when it matters MOST!",
            ]
        }
        
        # Color commentary — fires on EVERY event, never skipped
        # Deep, analytical, ALWAYS adds value
        self.analysis_comments = {
            'analytical': [
                "That's textbook execution! The entry speed was perfect, and they committed fully!",
                "Look at the tyre advantage there! Fresh rubber making all the difference!",
                "The positioning into that corner was masterful! Set the whole thing up two turns back!",
                "That's the kind of racecraft you can NOT teach! Pure instinct!",
                "The gap was closing for three laps, and they timed that strike perfectly!",
                "Interesting line choice! They sacrificed the apex to get the better exit!",
            ],
            'folksy': [
                "THAT is racecraft! That right there is why we watch!",
                "You love to see it! Clean, hard, respectful racing!",
                "That is how you earn respect on this grid!",
                "Wheel to wheel and neither flinched! What a moment!",
                "This is GRASSROOTS motorsport at its absolute finest!",
            ],
            'tactical': [
                "There's a strategic dimension to that pass! It opens up the entire stint!",
                "That changes the whole complexion of this race! Watch the ripple effect!",
                "Brilliant timing! They forced a defensive line and exploited the switchback!",
                "That move just put pressure on everyone behind them! Tactical masterclass!",
                "They've been setting that up for LAPS! Patient, calculated, devastating!",
            ],
            'driver_focused': [
                "You can see the confidence RADIATING from that cockpit! They believe today!",
                "The body language in that car says EVERYTHING! They are ON IT!",
                "Race by race, lap by lap, this driver is finding another level!",
                "That's a driver who came here today with a MISSION!",
                "The adrenaline must be through the ROOF right now!",
            ]
        }
        
        # Incident templates (crashes, spins, etc.) — ALL exclamatory
        self.incident_templates = {
            'player_urgent': [
                "OH NO! {driver} is in TROUBLE!",
                "PROBLEM for {driver}! This is BAD!",
                "{driver} has gone OFF! Heart in mouth!",
                "CONTACT! {driver} caught up in it! This is a disaster!",
                "NO! NO! {driver} spinning! This could change EVERYTHING!",
            ],
            'other_urgent': [
                "INCIDENT! {driver} has gone into the barriers!",
                "{driver} into the wall on lap {lap}! That's a hard hit!",
                "Trouble for {driver}! They're in the barriers!",
                "{driver} has BINNED IT! Debris on track!",
                "BIG crash! {driver} involved! Safety crew scrambling!",
                "OH! {driver} has lost it! That's a nasty one!",
            ],
            'minor': [
                "{driver} with a moment there! Heart skipped a beat!",
                "Small error from {driver}! They gather it up, but that cost time!",
                "{driver} gets sideways! Just manages to hold it!",
                "Lock-up for {driver}! Flat spot on those tyres now!",
            ]
        }
        
        # Dynamic action verbs
        self.action_verbs = ['dives', 'powers', 'surges', 'rockets', 'fires', 'launches', 'storms']
        self.aggressive_verbs = ['slices', 'barges', 'forces', 'muscles', 'lunges', 'sends it', 'torpedoes']
        
        # Descriptive adjectives
        self.pace_adjectives = ['devastating', 'impressive', 'scorching', 'relentless', 'blistering', 'electric']
        self.move_adjectives = ['calculated', 'bold', 'audacious', 'opportunistic', 'clinical', 'fearless']
    
    def _select_unique_template(self, templates: List[str], category: str = 'general') -> str:
        """Select a template and track usage to avoid repetition"""
        # Filter out recently used phrases
        available = [t for t in templates if t not in self.race_context.used_phrases]
        
        if not available:
            # If we've exhausted all options, reset and use any
            self.race_context.used_phrases.clear()
            available = templates
        
        selected = random.choice(available)
        self.race_context.used_phrases.add(selected)
        
        # Limit memory to last 30 phrases (bigger window to avoid repeats)
        if len(self.race_context.used_phrases) > 30:
            oldest = list(self.race_context.used_phrases)[0]
            self.race_context.used_phrases.remove(oldest)
        
        return selected
    
    def _get_time_of_day(self) -> str:
        """Vary time of day mentions"""
        return random.choice(['afternoon', 'morning', 'day', 'evening'])
    
    def _get_style_for_tier(self, tier: int) -> str:
        """Get commentary style based on league tier"""
        styles = {
            1: 'grassroots',     # Casual, local feel
            2: 'enthusiast',     # Knowledgeable fans
            3: 'professional',   # Proper broadcast
            4: 'premium',        # High production value
            5: 'world_class'     # F1-style coverage
        }
        return styles.get(tier, 'professional')
    
    def generate_pre_race_commentary(self, grid: List[Tuple], track_name: str) -> List[CommentaryLine]:
        """Generate pre-race commentary based on grid positions"""
        lines = []
        
        # Opening — use template pool
        style_templates = self.pre_race_opens.get(self.commentary_style, self.pre_race_opens['professional'])
        opening = self._select_unique_template(style_templates, 'pre_race')
        opening = opening.format(track=track_name, time_of_day=self._get_time_of_day())
        
        lines.append(CommentaryLine(
            speaker='pbp',
            text=opening,
            timing='pre_lap',
            priority=10
        ))
        
        # Pole position callout — with excitement
        if grid:
            pole_team, pole_driver, _ = grid[0]
            pole_lines = [
                f"{pole_driver.name} starts from pole for {pole_team.name}! Earned it in qualifying!",
                f"On pole, it's {pole_driver.name}! {pole_team.name} right where they want to be!",
                f"{pole_driver.name} leads the field away for {pole_team.name}! The target is on their back!",
            ]
            lines.append(CommentaryLine(
                speaker='color',
                text=self._select_unique_template(pole_lines, 'pole'),
                timing='pre_lap',
                priority=9
            ))
        
        # Player team if not on pole
        player_pos = next((i for i, (t, _, _) in enumerate(grid, 1) 
                          if t.name == self.player_team), None)
        if player_pos and player_pos > 1:
            player_entry = grid[player_pos - 1]
            player_lines = [
                f"Our team starts P{player_pos}! {player_entry[1].name} will be looking to make up ground!",
                f"P{player_pos} for {player_entry[1].name}! The hunt starts NOW!",
                f"{player_entry[1].name} from P{player_pos}! Everything to play for!",
            ]
            lines.append(CommentaryLine(
                speaker='pbp',
                text=self._select_unique_template(player_lines, 'player_grid'),
                timing='pre_lap',
                priority=8
            ))
        
        return lines
    
    def generate_lights_out_commentary(self) -> CommentaryLine:
        """Generate lights out commentary — always dramatic!"""
        calls = self.lights_out_calls.get(self.pbp_personality, self.lights_out_calls['dramatic'])
        text = self._select_unique_template(calls, 'lights_out')
        
        return CommentaryLine(
            speaker='pbp',
            text=text,
            timing='during_lap',
            priority=10
        )
    
    def generate_overtake_commentary(self, driver_name: str, new_position: int, 
                                     lap_number: int, is_player_team: bool,
                                     passed_driver: str = '', delta: float = 0.0,
                                     team: str = '') -> List[CommentaryLine]:
        """Generate commentary for an overtake — NEVER boring position readouts!
        
        Every pass gets treated like a moment. Color commentary ALWAYS fires.
        Player team and rival team get equal dramatic weight.
        Uses passed_driver, delta, and team for SPECIFIC, narrative-rich calls.
        """
        lines = []
        self.race_context.overtake_count += 1
        
        # Determine template pool based on context
        race_pct = lap_number / max(self.race_context.total_laps, 1) if self.race_context.total_laps else 0.5
        
        # --- PBP CALL: specific, naming who was passed ---
        if passed_driver and passed_driver != driver_name:
            # We have the overtaken driver — make it SPECIFIC
            verb = random.choice(self.action_verbs)
            adj = random.choice(self.move_adjectives)
            if is_player_team:
                specific_calls = [
                    f"YES! {driver_name} {verb} past {passed_driver} for P{new_position}! WHAT A MOVE!",
                    f"COME ON! {driver_name} takes {passed_driver}! That is {adj}! P{new_position}!",
                    f"THERE IT IS! {driver_name} around the outside of {passed_driver}! P{new_position} and CLIMBING!",
                    f"{driver_name} gets it DONE on {passed_driver}! Into P{new_position}! Let's GO!",
                    f"BEAUTIFUL! {driver_name} dispatches {passed_driver}! P{new_position} is THEIRS!",
                ]
            elif race_pct > 0.75:
                specific_calls = [
                    f"{driver_name} {verb} past {passed_driver} for P{new_position}! This late in the race! INCREDIBLE!",
                    f"With laps running out, {driver_name} takes {passed_driver}! P{new_position}! {adj.capitalize()} stuff!",
                    f"{driver_name} REFUSES to settle! Past {passed_driver} for P{new_position}!",
                ]
            else:
                specific_calls = [
                    f"{driver_name} {verb} past {passed_driver}! Into P{new_position}! {adj.capitalize()} move!",
                    f"OH! {driver_name} around {passed_driver}! That was {adj}! P{new_position}!",
                    f"{driver_name} gets the better of {passed_driver}! Clean, {adj}, into P{new_position}!",
                    f"Wheel to wheel and {driver_name} wins out over {passed_driver}! P{new_position}!",
                    f"{driver_name} makes the pass STICK on {passed_driver}! Into P{new_position}!",
                ]
            pbp_text = self._select_unique_template(specific_calls, 'overtake_pbp')
        else:
            # Fallback to generic templates if no passed_driver data
            if is_player_team:
                pool = self.overtake_templates['player_team']
            elif race_pct > 0.75:
                pool = self.overtake_templates['late_race']
            elif random.random() < 0.4:
                pool = self.overtake_templates['aggressive']
            else:
                pool = self.overtake_templates['clean_pass']
            pbp_text = self._select_unique_template(pool, 'overtake_pbp')
            pbp_text = pbp_text.replace('{driver}', driver_name)
        
        lines.append(CommentaryLine(
            speaker='pbp',
            text=pbp_text,
            timing='during_lap',
            priority=8 if is_player_team else 7
        ))
        
        # --- COLOR COMMENTARY: specific analysis using delta & context ---
        if passed_driver and delta > 0:
            # We have real gap data — be specific!
            if delta < 0.3:
                gap_calls = [
                    f"Only {delta:.1f} seconds separated them! That was wheel to wheel, door handle to door handle!",
                    f"A gap of just {delta:.1f} seconds! That pass was on a knife edge!",
                    f"{delta:.1f} seconds the margin! Any hesitation and that doesn't happen!",
                ]
            elif delta < 1.0:
                gap_calls = [
                    f"The gap was {delta:.1f} seconds and closing! {driver_name} timed that strike perfectly!",
                    f"Been reeling {passed_driver} in lap by lap! {delta:.1f} seconds became nothing!",
                    f"{delta:.1f} seconds the delta! {driver_name} had the pace advantage and used it!",
                ]
            else:
                gap_calls = [
                    f"{driver_name} was {delta:.1f} seconds faster! {passed_driver} had no answer to that pace!",
                    f"A {delta:.1f} second pace advantage! That was only a matter of time!",
                    f"The speed differential was clear! {delta:.1f} seconds of pure pace!",
                ]
            color_text = self._select_unique_template(gap_calls, 'overtake_color')
        elif passed_driver:
            # Have passed driver but no delta
            specific_color = [
                f"That changes the dynamic! {passed_driver} will NOT be happy about that!",
                f"{passed_driver} tried to defend but {driver_name} was just too strong!",
                f"The pressure finally told! {passed_driver} couldn't hold {driver_name} back!",
                f"That's experience talking! {driver_name} knew exactly where to make the pass on {passed_driver}!",
            ]
            color_text = self._select_unique_template(specific_color, 'overtake_color')
        else:
            # Generic fallback color
            color_pool = self.analysis_comments.get(self.color_personality,
                                                     self.analysis_comments['analytical'])
            color_text = self._select_unique_template(color_pool, 'overtake_color')
            import re
            color_text = re.sub(r'\{[^}]+\}', '', color_text).strip()
        
        lines.append(CommentaryLine(
            speaker='color',
            text=color_text,
            timing='post_lap',
            priority=6
        ))
        
        return lines
    
    def generate_crash_commentary(self, driver_name: str, team_name: str, 
                                   lap_number: int, is_player_team: bool,
                                   time_loss: float = 0.0, position: int = 0) -> List[CommentaryLine]:
        """Generate commentary for a crash — always dramatic, always with analysis!
        
        Uses time_loss and position for specific, contextual calls.
        """
        lines = []
        
        # Urgent call — exclamatory for ALL drivers, not just player
        if is_player_team:
            pool = self.incident_templates['player_urgent']
            priority = 10
        else:
            pool = self.incident_templates['other_urgent']
            priority = 9  # Raised from 7 — crashes are ALWAYS dramatic!
        
        pbp_text = self._select_unique_template(pool, 'crash_pbp')
        pbp_text = pbp_text.replace('{driver}', driver_name)
        pbp_text = pbp_text.replace('{team}', team_name)
        pbp_text = pbp_text.replace('{lap}', str(lap_number))
        
        lines.append(CommentaryLine(
            speaker='pbp',
            text=pbp_text,
            timing='incident',
            priority=priority
        ))
        
        # Color analysis — SPECIFIC using time_loss and position
        if time_loss > 0 and position > 0:
            if position <= 3:
                # Front-runner crash — championship drama
                analysis_variants = [
                    f"From P{position}! That's {time_loss:.1f} seconds lost and a PODIUM gone! Championship implications are HUGE!",
                    f"They were running P{position}! {time_loss:.1f} seconds dropped! {team_name} will be SICK about this!",
                    f"P{position} and throwing it away! {time_loss:.1f} seconds of damage! That is COSTLY for {team_name}!",
                ]
            elif position <= 10:
                analysis_variants = [
                    f"Running P{position} and now losing {time_loss:.1f} seconds! That's points evaporating for {team_name}!",
                    f"{time_loss:.1f} seconds lost from P{position}! {driver_name} will be FURIOUS with themselves!",
                    f"That {time_loss:.1f} second time loss drops {driver_name} right out of the points! Devastating from P{position}!",
                ]
            else:
                analysis_variants = [
                    f"{time_loss:.1f} seconds gone! {driver_name} was already struggling in P{position}, and this makes it worse!",
                    f"From P{position}, that {time_loss:.1f} second hit pushes them even further back! Tough day for {team_name}!",
                    f"{driver_name} can't catch a break! {time_loss:.1f} seconds dropped from P{position}!",
                ]
        elif time_loss > 0:
            analysis_variants = [
                f"That's going to cost {team_name} about {time_loss:.1f} seconds! Every tenth counts!",
                f"{time_loss:.1f} seconds lost in that incident! {driver_name} has ground to make up!",
                f"The damage assessment: {time_loss:.1f} seconds dropped! {team_name} will be counting the cost!",
            ]
        elif position > 0:
            analysis_variants = [
                f"From P{position}! {team_name} cannot afford incidents like that! Championship points vanishing!",
                f"Running P{position} and it all goes wrong! {driver_name} will be kicking themselves!",
                f"That ends their charge from P{position}! The car looks damaged, the race is compromised!",
            ]
        else:
            # Generic fallback
            analysis_variants = [
                f"That's going to cost {team_name} DEARLY! Championship points vanishing!",
                f"The damage looks significant! This could be race over for {driver_name}!",
                f"What a shame for {driver_name}! They were having such a strong run!",
                f"The safety crew is there quickly! But the car is NOT going anywhere!",
                f"That impact was HEAVY! First priority is the driver, but that's a write-off!",
                f"Heartbreak for {team_name}! All that preparation, gone in an instant!",
            ]
        lines.append(CommentaryLine(
            speaker='color',
            text=self._select_unique_template(analysis_variants, 'crash_color'),
            timing='incident',
            priority=priority - 1
        ))
        
        return lines
    
    def generate_dnf_commentary(self, driver_name: str, team_name: str, 
                                lap_number: int, is_player_team: bool,
                                position: int = 0) -> List[CommentaryLine]:
        """Generate commentary for a DNF — mechanical heartbreak!
        
        Uses position for specific, contextual calls about what was lost.
        """
        lines = []
        
        if is_player_team:
            if position > 0 and position <= 3:
                variants = [
                    f"NO! {driver_name} was P{position}! A PODIUM gone! Smoke from the car, they're pulling off! DEVASTATING!",
                    f"HEARTBREAKING! {driver_name} from P{position}! That was a PODIUM! Mechanical failure takes it ALL away!",
                    f"P{position}! THEY WERE P{position}! {driver_name} retires! I can't BELIEVE it!",
                ]
            elif position > 0:
                variants = [
                    f"NO! {driver_name} is OUT from P{position}! Mechanical failure! This is a DISASTER for us!",
                    f"Retirement for {driver_name} from P{position}! HEARTBREAKING! That's {position} worth of points gone!",
                    f"That's it for {driver_name}! Out from P{position}! The garage will be in pieces!",
                ]
            else:
                variants = [
                    f"NO! This is DEVASTATING! {driver_name} is OUT of the race!",
                    f"Retirement for {driver_name}! HEARTBREAKING! Absolutely heartbreaking!",
                    f"That's it for {driver_name} today! Mechanical failure takes them OUT!",
                    f"OH NO! Smoke from {driver_name}'s car! They're pulling off! This is a DISASTER!",
                ]
            priority = 10
        else:
            if position > 0 and position <= 5:
                variants = [
                    f"{driver_name} retires from P{position}! {team_name} lose a TOP FIVE car! Engine failure, that is BRUTAL!",
                    f"Mechanical DNF for {driver_name} from P{position}! {team_name} watching points slip away!",
                    f"OUT! {driver_name} is OUT from P{position}! {team_name} will be absolutely GUTTED!",
                ]
            elif position > 0:
                variants = [
                    f"{driver_name} pulls off from P{position}! DNF for {team_name}! Tough break!",
                    f"Retirement! {driver_name} out from P{position}! {team_name} lose a car!",
                    f"{driver_name} won't finish from P{position}! Mechanical failure for {team_name}! That HURTS!",
                ]
            else:
                variants = [
                    f"{driver_name} pulls off! That's a DNF for {team_name}! Tough break!",
                    f"Retirement! {driver_name} is OUT! {team_name} will be gutted!",
                    f"{driver_name} won't finish today! Mechanical failure, and the crew looks devastated!",
                    f"Engine failure for {driver_name}! {team_name} loses a car! That HURTS!",
                ]
            priority = 8  # Raised from 6 — DNFs are always significant!
        
        lines.append(CommentaryLine(
            speaker='pbp',
            text=self._select_unique_template(variants, 'dnf_pbp'),
            timing='incident',
            priority=priority
        ))
        
        # Color always fires on DNF — position-aware
        if position > 0 and position <= 5:
            dnf_color = [
                f"From P{position}! That's a disaster for the championship! {team_name} needed those points!",
                f"Losing a car from P{position} is catastrophic! {team_name} cannot recover those points!",
                f"The engineers will be devastated! P{position} and all those points, gone in a puff of smoke!",
            ]
        elif position > 0:
            dnf_color = [
                f"P{position} gone! In a tight championship, every single point matters and {team_name} just lost them all!",
                f"The reliability gods are cruel! Running P{position} and it counts for NOTHING now!",
                f"From P{position}, that's points down the drain! {team_name} will be analysing this for weeks!",
            ]
        else:
            dnf_color = [
                f"That's points down the drain for {team_name}! Every DNF echoes through the championship!",
                f"The engineers will be poring over the data tonight! Something let go at the worst time!",
                f"In a championship this tight, a DNF is a body blow! {team_name} just learned that the hard way!",
                f"Reliability is the silent champion killer! {team_name} just learned that the hard way!",
            ]
        lines.append(CommentaryLine(
            speaker='color',
            text=self._select_unique_template(dnf_color, 'dnf_color'),
            timing='incident',
            priority=priority - 1
        ))
        
        return lines
    
    def generate_final_lap_commentary(self, leader_name: str, leader_team: str, 
                                      is_player_leading: bool) -> List[CommentaryLine]:
        """Generate final lap commentary — maximum drama!"""
        lines = []
        
        if is_player_leading:
            variants = [
                f"FINAL LAP! {leader_name} is going to WIN THIS! Come on!",
                f"Last lap! {leader_name} just needs to bring it HOME! COME ON!",
                f"One lap to go and {leader_name} LEADS! History in the making!",
            ]
        else:
            variants = [
                f"FINAL LAP! {leader_name} leads for {leader_team}! Can anyone stop them?!",
                f"White flag! Last lap! {leader_name} in command for {leader_team}!",
                f"One lap remains! {leader_name} on the verge of VICTORY for {leader_team}!",
            ]
        
        lines.append(CommentaryLine(
            speaker='pbp',
            text=self._select_unique_template(variants, 'final_lap'),
            timing='during_lap',
            priority=10
        ))
        
        return lines
    
    def generate_checkered_flag_commentary(self, winner_name: str, winner_team: str,
                                          is_player_win: bool) -> List[CommentaryLine]:
        """Generate checkered flag commentary — the climax!"""
        lines = []
        
        if is_player_win:
            variants = [
                f"CHECKERED FLAG! {winner_name} WINS IT! WHAT A RESULT!",
                f"VICTORY! {winner_name} takes the WIN for {winner_team}! INCREDIBLE!",
                f"THEY'VE DONE IT! {winner_name} WINS for {winner_team}! Get in there!",
                f"YES! YES! YES! {winner_name} crosses the line FIRST! {winner_team} WIN!",
            ]
        else:
            variants = [
                f"Checkered flag! {winner_name} takes the victory for {winner_team}! Well deserved!",
                f"And {winner_name} crosses the line FIRST! {winner_team} claim the win!",
                f"{winner_name} takes the chequered flag! A dominant display from {winner_team}!",
            ]
        
        lines.append(CommentaryLine(
            speaker='pbp',
            text=self._select_unique_template(variants, 'checkered'),
            timing='post_lap',
            priority=10
        ))
        
        return lines
    
    def generate_player_result_summary(self, position: int, points: int) -> CommentaryLine:
        """Generate summary of player team's race — always with feeling!"""
        if position == 1:
            text = f"Incredible performance! Victory and {points} points! What a day!"
        elif position <= 3:
            text = f"P{position} finish! {points} points! That's a STRONG result!"
        elif position <= 6:
            text = f"P{position} today! {points} points in the bag! Solid, solid work!"
        elif position <= 10:
            text = f"P{position} at the flag! {points} points! They'll take that!"
        else:
            text = f"P{position} at the flag! Tough day, but they'll come back fighting!"
        
        return CommentaryLine(
            speaker='color',
            text=text,
            timing='post_lap',
            priority=9
        )
    
    def generate_lap_update(self, lap_number: int, total_laps: int, 
                           leader_name: str, gap_to_player: Optional[float] = None) -> Optional[CommentaryLine]:
        """Generate periodic lap update — never robotic, always with narrative!"""
        # Only generate updates for certain laps
        if lap_number % 5 != 0:  # Every 5 laps
            return None
        
        race_pct = lap_number / max(total_laps, 1)
        
        if race_pct < 0.3:
            # Early race — setting the scene
            if gap_to_player is not None and gap_to_player > 0:
                variants = [
                    f"Lap {lap_number} of {total_laps}! {leader_name} leads, our team {gap_to_player:.1f} seconds back! Long race ahead, plenty of time!",
                    f"Through {lap_number} laps! {leader_name} out front! The gap to us is {gap_to_player:.1f} seconds but this race is far from over!",
                ]
            else:
                variants = [
                    f"Lap {lap_number} of {total_laps}! {leader_name} continues to lead! The field is settling into rhythm!",
                    f"Through {lap_number} laps! {leader_name} at the front! Everyone finding their pace!",
                ]
        elif race_pct < 0.7:
            # Mid race — tension building
            if gap_to_player is not None and gap_to_player > 0:
                variants = [
                    f"Lap {lap_number}! We're past halfway and {leader_name} leads! Our team is {gap_to_player:.1f} seconds back! The pressure is building!",
                    f"Into the meat of this race! Lap {lap_number}! {leader_name} out front with {total_laps - lap_number} to go!",
                ]
            else:
                variants = [
                    f"Lap {lap_number} of {total_laps}! {leader_name} leads and the gaps are TIGHTENING!",
                    f"Past halfway! Lap {lap_number}! {leader_name} out front but this race is ALIVE!",
                ]
        else:
            # Late race — climax approaching
            remaining = total_laps - lap_number
            if gap_to_player is not None and gap_to_player > 0:
                variants = [
                    f"Lap {lap_number}! Just {remaining} laps to go! {leader_name} leads, {gap_to_player:.1f} seconds is the gap! Can anyone close it?!",
                    f"The final stint! {leader_name} leads with {remaining} laps remaining! This is where champions are MADE!",
                ]
            else:
                variants = [
                    f"Lap {lap_number}! Just {remaining} to go! {leader_name} leads but the tension is INCREDIBLE!",
                    f"{remaining} laps remain! {leader_name} at the front! Every corner counts NOW!",
                ]
        
        text = self._select_unique_template(variants, 'lap_update')
        
        return CommentaryLine(
            speaker='pbp',
            text=text,
            timing='during_lap',
            priority=5
        )
