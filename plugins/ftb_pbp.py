"""
FTB Play-by-Play Widget - Live Race Commentary and Telemetry

Displays real-time race action with:
- Lap-by-lap position standings
- Overtakes, crashes, DNFs as they happen
- Live gap intervals
- Race events timeline
- Post-race telemetry analysis

Integrates with lap-by-lap simulation to show rich race data.
"""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from typing import Any, Dict, List, Optional, Tuple
import sys
import time
import os

# Import game state structures
try:
    sys.path.insert(0, "plugins")
    import ftb_state_db
    from ftb_game import RaceResult, LapData, RaceEventRecord
    from plugins import ftb_race_day
except Exception:
    ftb_state_db = None
    RaceResult = None
    LapData = None
    RaceEventRecord = None
    ftb_race_day = None


# ============================================================================
# METADATA (Runtime Discovery)
# ============================================================================

PLUGIN_NAME = "FTB Play-by-Play"
PLUGIN_DESC = "Live race action with lap-by-lap updates, overtakes, and telemetry"
IS_FEED = False  # UI widget, not feed

# ── Debug gate ──────────────────────────────────────────────
FTB_DEBUG: bool = os.environ.get("FTB_DEBUG", "").strip() in ("1", "true", "yes")

def _dbg(*args, **kwargs):
    if FTB_DEBUG:
        print(*args, **kwargs)
# ────────────────────────────────────────────────────────────


# ============================================================================
# RACE DATA CACHE
# ============================================================================

# Global cache for current/recent race data
CURRENT_RACE: Optional[Dict[str, Any]] = None
RACE_HISTORY: List[Dict[str, Any]] = []  # Last 10 races
MAX_HISTORY = 10

LIVE_FEED_EVENTS: List[Any] = []
LIVE_FEED_CURSOR: int = 0
LIVE_FEED_ACTIVE: bool = False
LIVE_FEED_INTERVAL: float = 1.5
LIVE_FEED_LAST_TS: float = 0.0


def _is_player_race(race_result: Any, state: Any) -> bool:
    """Check if this race belongs to the player's league.
    
    CRITICAL FIX: Without this, every AI race overwrites CURRENT_RACE,
    making it impossible to view your own races after the first one.
    """
    if not race_result or not state:
        return False
    
    if not state.player_team:
        return False
    
    player_league_id = state.player_team.league_id
    if not player_league_id:
        return False
    
    # Check if race's league matches player's league by name
    # (league_id may not be stored in race_result)
    for league in state.leagues.values():
        if league.league_id == player_league_id and league.name == race_result.league_name:
            return True
    
    return False


def update_race_data(race_result: Any, state: Any):
    """
    Called when a race completes to cache data for display.
    This would be called from the simulation or event hook.
    
    CRITICAL FIX: Only caches PLAYER races, not AI races.
    Otherwise every AI league race overwrites the player's race.
    """
    global CURRENT_RACE, RACE_HISTORY
    
    if not race_result:
        return
    
    # CRITICAL FIX: Only track player's races
    if not _is_player_race(race_result, state):
        # Don't spam logs for every AI race
        return
    
    _dbg(f"[FTB PBP] ✅ Caching player race: {race_result.league_name} at {race_result.track_name}")
    
    # Package race data
    race_data = {
        'race_id': race_result.race_id,
        'league_name': race_result.league_name,
        'track_name': race_result.track_name,
        'round': race_result.round_number,
        'season': race_result.season,
        'final_positions': race_result.final_positions,
        'laps': race_result.laps,
        'events': race_result.race_events,
        'telemetry': race_result.telemetry,
        'fastest_lap': race_result.fastest_lap,
        'total_laps': len(set(l.lap_number for l in race_result.laps)) if race_result.laps else 0,
        'live_mode': False
    }
    
    CURRENT_RACE = race_data
    RACE_HISTORY.insert(0, race_data)
    
    # Trim history
    if len(RACE_HISTORY) > MAX_HISTORY:
        RACE_HISTORY.pop()


def start_live_feed(race_result: Any, state: Any, interval_sec: float = 1.5):
    """Start a drip-feed play-by-play session for a completed race sim.
    
    CRITICAL FIX: Only starts live feed for PLAYER races.
    """
    global CURRENT_RACE, RACE_HISTORY
    global LIVE_FEED_EVENTS, LIVE_FEED_CURSOR, LIVE_FEED_ACTIVE, LIVE_FEED_INTERVAL, LIVE_FEED_LAST_TS

    if not race_result:
        return
    
    # CRITICAL FIX: Only track player's races
    if not _is_player_race(race_result, state):
        return
    
    _dbg(f"[FTB PBP] ▶️ Starting live feed for player race: {race_result.league_name}")

    race_data = {
        'race_id': race_result.race_id,
        'league_name': race_result.league_name,
        'track_name': race_result.track_name,
        'round': race_result.round_number,
        'season': race_result.season,
        'final_positions': race_result.final_positions,
        'laps': race_result.laps,
        'events': [],
        'telemetry': race_result.telemetry,
        'fastest_lap': race_result.fastest_lap,
        'total_laps': len(set(l.lap_number for l in race_result.laps)) if race_result.laps else 0,
        'live_mode': True
    }

    CURRENT_RACE = race_data
    RACE_HISTORY.insert(0, race_data)
    if len(RACE_HISTORY) > MAX_HISTORY:
        RACE_HISTORY.pop()

    LIVE_FEED_EVENTS = sorted(list(race_result.race_events), key=lambda e: e.lap_number)
    LIVE_FEED_CURSOR = 0
    LIVE_FEED_ACTIVE = True
    LIVE_FEED_INTERVAL = max(0.5, interval_sec)
    LIVE_FEED_LAST_TS = time.time()


def _advance_live_feed() -> bool:
    """Advance the live feed by one event at fixed time intervals."""
    global LIVE_FEED_CURSOR, LIVE_FEED_ACTIVE, LIVE_FEED_LAST_TS

    if not LIVE_FEED_ACTIVE or not CURRENT_RACE:
        return False

    now = time.time()
    if now - LIVE_FEED_LAST_TS < LIVE_FEED_INTERVAL:
        return False

    if LIVE_FEED_CURSOR < len(LIVE_FEED_EVENTS):
        CURRENT_RACE['events'].append(LIVE_FEED_EVENTS[LIVE_FEED_CURSOR])
        LIVE_FEED_CURSOR += 1
        LIVE_FEED_LAST_TS = now
        return True
    else:
        LIVE_FEED_ACTIVE = False
        return False


# ============================================================================
# PLAY-BY-PLAY WIDGET
# ============================================================================

class FTBPlayByPlayWidget(ctk.CTkFrame):
    """Race play-by-play with live updates and telemetry"""
    
    def __init__(self, parent, runtime_stub: Dict[str, Any]):
        super().__init__(parent)
        self.runtime = runtime_stub
        _raw_log = runtime_stub.get('log', None)
        # Wrap log so single-arg calls work (runtime log expects (category, msg))
        if _raw_log and _raw_log is not print:
            self.log = lambda msg: _raw_log('ftb_pbp', msg)
        else:
            self.log = print
        
        # State tracking
        self._last_tick = -1
        self._current_view = "live"  # live, history, telemetry
        self._selected_race_idx = 0
        
        # Live race playback state
        self._race_streaming = False
        self._race_paused = False
        self._race_speed = 10.0  # seconds per lap
        self._current_lap = 0
        self._total_laps = 0
        self._race_events_stream = []
        self._live_standings = []
        self._last_stream_time = 0.0
        
        # UI Components
        self._build_ui()
        
        # Start refresh loop
        self.after(1000, self._refresh_loop)
    
    def _get_state(self):
        """Get game state from the FTB controller.
        
        The PBP widget shares the runtime_stub dict with the FTB controller,
        but state lives on controller.state, not in runtime_stub['state'].
        """
        # First try runtime_stub['state'] (in case it's set elsewhere)
        state = self.runtime.get('state')
        if state:
            return state
        # Look up via the controller
        controller = self.runtime.get('ftb_controller')
        if controller and hasattr(controller, 'state'):
            return controller.state
        return None
    
    def _build_ui(self):
        """Build the widget UI structure"""
        self.configure(fg_color="#1a1a1a")
        
        # Header
        header = ctk.CTkFrame(self, fg_color="#2a2a2a", corner_radius=8)
        header.pack(fill="x", padx=8, pady=(8, 4))
        
        title = ctk.CTkLabel(
            header,
            text="🏁 Race Play-by-Play",
            font=("Segoe UI", 16, "bold"),
            text_color="#ffffff"
        )
        title.pack(side="left", padx=12, pady=8)
        
        self.status_label = ctk.CTkLabel(
            header,
            text="No active race",
            font=("Segoe UI", 11),
            text_color="#888888"
        )
        self.status_label.pack(side="right", padx=12, pady=8)
        
        # View tabs
        tab_frame = ctk.CTkFrame(self, fg_color="transparent")
        tab_frame.pack(fill="x", padx=8, pady=4)
        
        self.tab_buttons = {}
        tabs = [
            ("live", "🔴 Live Race"),
            ("positions", "📊 Standings"),
            ("events", "📰 Events"),
            ("telemetry", "📈 Telemetry"),
            ("history", "🕐 History")
        ]
        
        for tab_id, tab_label in tabs:
            btn = ctk.CTkButton(
                tab_frame,
                text=tab_label,
                width=100,
                height=28,
                fg_color="#333333",
                hover_color="#444444",
                corner_radius=6,
                font=("Segoe UI", 11),
                command=lambda t=tab_id: self._switch_tab(t)
            )
            btn.pack(side="left", padx=2)
            self.tab_buttons[tab_id] = btn
        
        # Race control panel (hidden by default, shown when race ready)
        self.race_control_panel = ctk.CTkFrame(self, fg_color="#2a2a2a", corner_radius=8)
        self._build_race_control_panel()
        # Don't pack yet - will be shown dynamically
        
        # Content area (scrollable)
        self.content_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="#1a1a1a",
            corner_radius=0
        )
        self.content_frame.pack(fill="both", expand=True, padx=8, pady=4)
        
        # Initial content
        self._refresh_content()
    
    def _switch_tab(self, tab_id: str):
        """Switch active tab and refresh content"""
        self._current_view = tab_id
        
        # Update button styles
        for tid, btn in self.tab_buttons.items():
            if tid == tab_id:
                btn.configure(fg_color="#4a4a4a", text_color="#ffffff")
            else:
                btn.configure(fg_color="#333333", text_color="#aaaaaa")
        
        self._refresh_content()
    
    def _build_race_control_panel(self):
        """Build the race control panel (play, pause, speed)"""
        # Title
        title_label = ctk.CTkLabel(
            self.race_control_panel,
            text="🏁 Race Ready - Live Playback Controls",
            font=("Segoe UI", 13, "bold"),
            text_color="#00ff88"
        )
        title_label.pack(padx=12, pady=(12, 8))
        
        # Control buttons frame
        controls_frame = ctk.CTkFrame(self.race_control_panel, fg_color="transparent")
        controls_frame.pack(padx=12, pady=8)
        
        # Play button
        self.play_btn = ctk.CTkButton(
            controls_frame,
            text="▶️ Play Live Race",
            width=150,
            height=40,
            fg_color="#00aa44",
            hover_color="#00cc55",
            font=("Segoe UI", 13, "bold"),
            corner_radius=8,
            command=self._on_play_race
        )
        self.play_btn.pack(side="left", padx=4)
        
        # Pause button (initially disabled)
        self.pause_btn = ctk.CTkButton(
            controls_frame,
            text="⏸️ Pause",
            width=100,
            height=40,
            fg_color="#666666",
            hover_color="#777777",
            font=("Segoe UI", 12),
            corner_radius=8,
            state="disabled",
            command=self._on_pause_race
        )
        self.pause_btn.pack(side="left", padx=4)
        
        # Speed control frame
        speed_frame = ctk.CTkFrame(self.race_control_panel, fg_color="transparent")
        speed_frame.pack(padx=12, pady=(0, 12), fill="x")
        
        speed_label = ctk.CTkLabel(
            speed_frame,
            text="⚡ Playback Speed:",
            font=("Segoe UI", 11),
            text_color="#aaaaaa"
        )
        speed_label.pack(side="left", padx=(0, 8))
        
        # Speed buttons
        speed_options = [
            ("🐌 Slow (30s/lap)", 30.0),
            ("🚶 Medium (10s/lap)", 10.0),
            ("🏃 Fast (5s/lap)", 5.0),
            ("⚡ Turbo (1s/lap)", 1.0)
        ]
        
        self.speed_buttons = {}
        for label, speed in speed_options:
            btn = ctk.CTkButton(
                speed_frame,
                text=label,
                width=120,
                height=28,
                fg_color="#333333" if speed != 10.0 else "#4a4a4a",
                hover_color="#444444",
                font=("Segoe UI", 10),
                corner_radius=6,
                command=lambda s=speed: self._set_race_speed(s)
            )
            btn.pack(side="left", padx=2)
            self.speed_buttons[speed] = btn
        
        # Progress bar
        self.progress_label = ctk.CTkLabel(
            self.race_control_panel,
            text="Lap 0 / 0",
            font=("Consolas", 11),
            text_color="#888888"
        )
        self.progress_label.pack(padx=12, pady=(0, 4))
        
        self.progress_bar = ctk.CTkProgressBar(
            self.race_control_panel,
            width=400,
            height=8,
            corner_radius=4,
            fg_color="#333333",
            progress_color="#00ff88"
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(padx=12, pady=(0, 12))
    
    def _check_race_ready(self):
        """Check if race is ready to play and show control panel"""
        state = self._get_state()
        if not state or not ftb_race_day:
            return False
        
        if not hasattr(state, 'race_day_state') or not state.race_day_state:
            return False
        
        rds = state.race_day_state
        phase = rds.phase
        
        # Show control panel if quali complete and not already streaming
        if phase == ftb_race_day.RaceDayPhase.QUALI_COMPLETE and not self._race_streaming:
            # CRITICAL FIX: Reset widget state for new race
            # If control panel was hidden from previous race, reset everything
            if not self.race_control_panel.winfo_ismapped():
                _dbg(f"[FTB PBP] 🔄 Resetting widget state for new race...")
                self._race_streaming = False
                self._race_paused = False
                self.play_btn.configure(
                    state="normal",
                    text="▶️ Play Live Race",
                    fg_color="#00aa44"
                )
                self.pause_btn.configure(state="disabled", fg_color="#666666", text="⏸️ Pause")
                self.progress_bar.set(0.0)
                _dbg(f"[FTB PBP] ✅ Widget state reset complete")
                
                _dbg(f"[FTB PBP] 🎮 Packing race control panel (phase={phase.name})...")
                self.race_control_panel.pack(fill="x", padx=8, pady=4)
                _dbg(f"[FTB PBP] 🎮 Race control panel shown")
            return True
        
        # Hide control panel if not in ready state
        if phase != ftb_race_day.RaceDayPhase.QUALI_COMPLETE:
            if self.race_control_panel.winfo_ismapped():
                self.race_control_panel.pack_forget()
        
        return False
    
    def _set_race_speed(self, speed: float):
        """Set race playback speed"""
        self._race_speed = speed
        
        # Update button styles
        for s, btn in self.speed_buttons.items():
            if s == speed:
                btn.configure(fg_color="#4a4a4a", text_color="#ffffff")
            else:
                btn.configure(fg_color="#333333", text_color="#aaaaaa")
        
        self.log(f"[FTB PBP] ⚡ Race speed set to {speed}s per lap")
    
    def _on_play_race(self):
        """Start live race playback"""
        _dbg("[FTB PBP] ▶️ _on_play_race CALLED")
        self.log("[FTB PBP] ▶️ Starting live race playback...")
        
        # Get race info from state
        state = self._get_state()
        _dbg(f"[FTB PBP] State found: {state is not None}")
        if state and hasattr(state, 'race_day_state') and state.race_day_state:
            rds = state.race_day_state
            self._total_laps = rds.total_laps if hasattr(rds, 'total_laps') else 0
            self._current_lap = rds.current_lap if hasattr(rds, 'current_lap') else 0
            _dbg(f"[FTB PBP] Race day state: phase={rds.phase}, total_laps={self._total_laps}, current_lap={self._current_lap}")
        
        # Switch to live view tab within PBP widget immediately
        self._switch_tab("live")
        
        # Tell the shell to activate the PBP widget tab in its floating window
        ui_q = self.runtime.get('ui_q')
        if ui_q:
            ui_q.put(("activate_widget_tab", {"widget_key": "ftb_pbp"}))
            _dbg("[FTB PBP] 📺 Sent activate_widget_tab for ftb_pbp to ui_q")
        
        # Send command to game controller
        ftb_cmd_q = self.runtime.get('ftb_cmd_q')
        _dbg(f"[FTB PBP] ftb_cmd_q found: {ftb_cmd_q is not None}, runtime keys: {[k for k in self.runtime.keys() if 'ftb' in k.lower()]}")
        if ftb_cmd_q:
            ftb_cmd_q.put({
                'cmd': 'ftb_start_live_race',
                'speed': self._race_speed
            })
            _dbg(f"[FTB PBP] ✅ Sent ftb_start_live_race command (speed={self._race_speed})")
        else:
            _dbg("[FTB PBP] ❌ NO ftb_cmd_q - command NOT sent!")
        
        # Update UI state
        self._race_streaming = True
        self._race_paused = False
        self.play_btn.configure(state="disabled", fg_color="#555555")
        self.pause_btn.configure(state="normal", fg_color="#ff8800")
        
        # Start streaming loop
        self._last_stream_time = time.time()
        self.after(100, self._stream_race_update)
    
    def _on_pause_race(self):
        """Pause/resume live race playback"""
        self._race_paused = not self._race_paused
        
        if self._race_paused:
            self.pause_btn.configure(text="▶️ Resume", fg_color="#00aa44")
            self.log("[FTB PBP] ⏸️ Race playback paused")
        else:
            self.pause_btn.configure(text="⏸️ Pause", fg_color="#ff8800")
            self._last_stream_time = time.time()  # Reset timer
            self.log("[FTB PBP] ▶️ Race playback resumed")
    
    def _stream_race_update(self):
        """Called periodically to advance race lap-by-lap"""
        if not self._race_streaming:
            return
        
        # Check if enough time has passed for next lap
        if not self._race_paused:
            now = time.time()
            elapsed = now - self._last_stream_time
            
            if elapsed >= self._race_speed:
                self._advance_race_lap()
                self._last_stream_time = now
        
        # Schedule next update
        self.after(100, self._stream_race_update)
    
    def _advance_race_lap(self):
        """Advance race by one lap and update display"""
        state = self._get_state()
        if not state or not hasattr(state, 'race_day_state'):
            return
        
        rds = state.race_day_state
        
        # Send command to game controller to advance lap
        ftb_cmd_q = self.runtime.get('ftb_cmd_q')
        if ftb_cmd_q:
            ftb_cmd_q.put({'cmd': 'ftb_advance_race_lap'})
        
        # Data will be updated by game controller
        # Read current state (might lag by one cycle but that's OK)
        self._current_lap = rds.current_lap
        self._total_laps = rds.total_laps
        self._live_standings = rds.live_standings.copy() if rds.live_standings else []
        self._race_events_stream = rds.live_events.copy() if rds.live_events else []
        
        # Update progress
        if self._total_laps > 0:
            progress = min(1.0, self._current_lap / self._total_laps)
            self.progress_bar.set(progress)
            self.progress_label.configure(text=f"Lap {self._current_lap} / {self._total_laps}")
        
        # Refresh display to show new events
        self._refresh_content()
        
        self.log(f"[FTB PBP] 🏁 Advanced to lap {self._current_lap}")
        
        # Check if race complete
        if self._current_lap >= self._total_laps and self._total_laps > 0:
            self._complete_race()
    
    def _complete_race(self):
        """Called when race playback completes"""
        self.log("[FTB PBP] 🏁 Race playback complete!")
        
        self._race_streaming = False
        self._race_paused = False
        
        # Update UI
        self.play_btn.configure(state="disabled", text="✅ Race Complete")
        self.pause_btn.configure(state="disabled")
        self.progress_bar.set(1.0)
        
        # Send completion command
        ftb_cmd_q = self.runtime.get('ftb_cmd_q')
        if ftb_cmd_q:
            ftb_cmd_q.put({'cmd': 'ftb_complete_race_day'})
        
        # Hide control panel after a delay
        self.after(2000, lambda: self.race_control_panel.pack_forget())
    
    def _refresh_loop(self):
        """Periodic refresh to check for new race data"""
        try:
            # Check for race ready state
            self._check_race_ready()
            
            # Check runtime for state updates
            state = self._get_state()
            if state and hasattr(state, 'tick'):
                if state.tick != self._last_tick:
                    self._last_tick = state.tick
                    self._refresh_content()
            if _advance_live_feed():
                self._refresh_content()
        except Exception as e:
            _dbg(f"[FTB PBP] ❌ _refresh_loop error: {e}")
            import traceback
            traceback.print_exc()
        
        # Schedule next refresh
        self.after(2000, self._refresh_loop)
    
    def _refresh_content(self):
        """Refresh content based on current view"""
        # Clear content
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        
        if self._current_view == "live":
            self._render_live_view()
        elif self._current_view == "positions":
            self._render_positions_view()
        elif self._current_view == "events":
            self._render_events_view()
        elif self._current_view == "telemetry":
            self._render_telemetry_view()
        elif self._current_view == "history":
            self._render_history_view()
    
    def _render_live_race_stream(self):
        """Render live race streaming view with real-time updates"""
        state = self._get_state()
        if not state or not hasattr(state, 'race_day_state'):
            return
        
        rds = state.race_day_state
        
        # Always read fresh from state
        if rds:
            self._current_lap = rds.current_lap
            self._total_laps = rds.total_laps
            self._live_standings = rds.live_standings.copy() if rds.live_standings else []
            self._race_events_stream = rds.live_events.copy() if rds.live_events else []
        
        # Live race header
        header_card = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
        header_card.pack(fill="x", pady=(0, 8))
        
        status_text = f"🔴 LIVE: Lap {self._current_lap} / {self._total_laps}"
        if self._race_paused:
            status_text = f"⏸️ PAUSED: Lap {self._current_lap} / {self._total_laps}"
        
        status_label = ctk.CTkLabel(
            header_card,
            text=status_text,
            font=("Segoe UI", 16, "bold"),
            text_color="#ff4444" if not self._race_paused else "#ff8800"
        )
        status_label.pack(padx=16, pady=12)
        
        # Live standings (if available)
        if self._live_standings:
            standings_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
            standings_frame.pack(fill="x", pady=(0, 8))
            
            standings_title = ctk.CTkLabel(
                standings_frame,
                text="📊 Current Positions",
                font=("Segoe UI", 13, "bold"),
                text_color="#ffffff"
            )
            standings_title.pack(padx=12, pady=(12, 8), anchor="w")
            
            # Show all drivers (full field, not just top 10)
            for idx, standing in enumerate(self._live_standings, 1):
                driver_name = standing.get('driver', 'Unknown')
                team_name = standing.get('team', 'Unknown')
                gap = standing.get('gap', 0.0)
                status = standing.get('status', 'racing')
                
                # Highlight player team
                is_player = standing.get('is_player', False)
                bg_color = "#3a3a3a" if is_player else "#333333"
                
                pos_card = ctk.CTkFrame(standings_frame, fg_color=bg_color, corner_radius=4)
                pos_card.pack(fill="x", padx=12, pady=1)
                
                # Position and driver
                pos_text = f"P{idx:2d}  {driver_name:20s} ({team_name:15s})"
                
                # Gap to leader
                if idx == 1:
                    gap_text = "Leader"
                elif gap > 0:
                    gap_text = f"+{gap:.1f}s"
                else:
                    gap_text = ""
                
                if status != 'racing':
                    gap_text = status.upper()
                
                full_text = f"{pos_text:50s} {gap_text}"
                
                pos_label = ctk.CTkLabel(
                    pos_card,
                    text=full_text,
                    font=("Consolas", 11, "bold" if is_player else "normal"),
                    text_color="#00ff88" if is_player else "#cccccc",
                    anchor="w"
                )
                pos_label.pack(padx=12, pady=4, fill="x")
        
        # Recent events feed
        if self._race_events_stream:
            events_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
            events_frame.pack(fill="both", expand=True, pady=(0, 8))
            
            events_title = ctk.CTkLabel(
                events_frame,
                text="📰 Live Event Feed",
                font=("Segoe UI", 13, "bold"),
                text_color="#ffffff"
            )
            events_title.pack(padx=12, pady=(12, 8), anchor="w")
            
            # Show last 15 events
            for event in self._race_events_stream[-15:]:
                event_text = event.get('text', '')
                event_lap = event.get('lap', 0)
                event_type = event.get('type', 'info')
                
                # Color code by event type
                if 'crash' in event_type.lower() or 'dnf' in event_type.lower():
                    event_color = "#ff6666"
                elif 'overtake' in event_type.lower():
                    event_color = "#ffaa00"
                elif 'fastest' in event_type.lower():
                    event_color = "#00ff88"
                else:
                    event_color = "#aaaaaa"
                
                event_card = ctk.CTkFrame(events_frame, fg_color="#333333", corner_radius=4)
                event_card.pack(fill="x", padx=12, pady=2)
                
                event_label = ctk.CTkLabel(
                    event_card,
                    text=f"Lap {event_lap:3d}: {event_text}",
                    font=("Consolas", 10),
                    text_color=event_color,
                    anchor="w"
                )
                event_label.pack(padx=12, pady=4, fill="x")
        else:
            # No events yet
            msg = ctk.CTkLabel(
                self.content_frame,
                text="🏁 Race starting...\nEvents will appear here as the race progresses",
                font=("Segoe UI", 12),
                text_color="#666666",
                justify="center"
            )
            msg.pack(pady=40)
    
    def _render_live_view(self):
        """Render live race overview"""
        # Check if we're in live streaming mode
        if self._race_streaming:
            self._render_live_race_stream()
            return
        
        if not CURRENT_RACE:
            msg = ctk.CTkLabel(
                self.content_frame,
                text="No race data available\n\nRace data will appear here during and after races",
                font=("Segoe UI", 13),
                text_color="#666666",
                justify="center"
            )
            msg.pack(pady=60)
            return
        
        race = CURRENT_RACE
        
        # Update status
        self.status_label.configure(
            text=f"{race['league_name']} • Round {race['round']} • {race['track_name']}"
        )
        
        # Race header card
        header_card = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
        header_card.pack(fill="x", pady=(0, 8))
        
        info_text = f"""
🏆 {race['league_name']} • Season {race['season']} • Round {race['round']}
🏁 {race['track_name']}
📊 {race['total_laps']} Laps Completed • {len(race['events'])} Race Events
        """.strip()
        
        info_label = ctk.CTkLabel(
            header_card,
            text=info_text,
            font=("Consolas", 11),
            text_color="#cccccc",
            justify="left"
        )
        info_label.pack(padx=16, pady=12, anchor="w")
        
        # Top 3 podium
        podium_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
        podium_frame.pack(fill="x", pady=(0, 8))
        
        podium_title = ctk.CTkLabel(
            podium_frame,
            text="🏆 Final Results",
            font=("Segoe UI", 14, "bold"),
            text_color="#ffffff"
        )
        podium_title.pack(padx=12, pady=(12, 8), anchor="w")
        
        positions = race['final_positions']  # Full field
        for idx, (driver_name, team_name, status) in enumerate(positions, 1):
            pos_color = "#FFD700" if idx == 1 else "#C0C0C0" if idx == 2 else "#CD7F32" if idx == 3 else "#444444"
            
            pos_card = ctk.CTkFrame(podium_frame, fg_color=pos_color if idx <= 3 else "#333333", corner_radius=4)
            pos_card.pack(fill="x", padx=12, pady=2)
            
            pos_text = f"P{idx}  {driver_name} ({team_name})"
            if status != 'finished':
                pos_text += f" - {status.upper()}"
            
            pos_label = ctk.CTkLabel(
                pos_card,
                text=pos_text,
                font=("Consolas", 12, "bold" if idx <= 3 else "normal"),
                text_color="#000000" if idx <= 3 else "#cccccc"
            )
            pos_label.pack(padx=12, pady=6, anchor="w")
        
        podium_frame.pack_configure(pady=(0, 8))
        
        # Fastest lap
        if race.get('fastest_lap'):
            driver, lap_time = race['fastest_lap']
            fl_card = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
            fl_card.pack(fill="x", pady=(0, 8))
            
            fl_label = ctk.CTkLabel(
                fl_card,
                text=f"⚡ Fastest Lap: {driver} - {lap_time:.3f}s",
                font=("Segoe UI", 12),
                text_color="#00ff88"
            )
            fl_label.pack(padx=12, pady=8)
    
    def _render_positions_view(self):
        """Render position standings with gaps — live or post-race"""
        # During live streaming, show live standings from race_day_state
        if self._race_streaming:
            self._render_live_positions()
            return

        if not CURRENT_RACE:
            self._render_no_data()
            return
        
        race = CURRENT_RACE
        
        # Update status
        self.status_label.configure(
            text=f"{race['league_name']} • Round {race['round']}"
        )
        
        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text=f"Race Standings - {race['track_name']}",
            font=("Segoe UI", 14, "bold"),
            text_color="#ffffff"
        )
        title.pack(pady=(8, 12))
        
        # Table header
        header_frame = ctk.CTkFrame(self.content_frame, fg_color="#333333", corner_radius=4)
        header_frame.pack(fill="x", padx=4, pady=(0, 4))
        
        headers = ["POS", "DRIVER", "TEAM", "STATUS"]
        col_widths = [50, 200, 200, 100]
        
        for header, width in zip(headers, col_widths):
            lbl = ctk.CTkLabel(
                header_frame,
                text=header,
                font=("Segoe UI", 11, "bold"),
                text_color="#aaaaaa",
                width=width,
                anchor="w"
            )
            lbl.pack(side="left", padx=8, pady=6)
        
        # Position rows
        for idx, (driver_name, team_name, status) in enumerate(race['final_positions'], 1):
            row_color = "#2a2a2a" if idx % 2 == 0 else "#242424"
            
            row_frame = ctk.CTkFrame(self.content_frame, fg_color=row_color, corner_radius=4)
            row_frame.pack(fill="x", padx=4, pady=1)
            
            # Position
            pos_lbl = ctk.CTkLabel(
                row_frame,
                text=f"P{idx}",
                font=("Consolas", 11, "bold"),
                text_color="#ffffff" if idx <= 3 else "#cccccc",
                width=col_widths[0],
                anchor="w"
            )
            pos_lbl.pack(side="left", padx=8, pady=4)
            
            # Driver
            driver_lbl = ctk.CTkLabel(
                row_frame,
                text=driver_name,
                font=("Segoe UI", 11),
                text_color="#ffffff",
                width=col_widths[1],
                anchor="w"
            )
            driver_lbl.pack(side="left", padx=8, pady=4)
            
            # Team
            team_lbl = ctk.CTkLabel(
                row_frame,
                text=team_name,
                font=("Segoe UI", 11),
                text_color="#aaaaaa",
                width=col_widths[2],
                anchor="w"
            )
            team_lbl.pack(side="left", padx=8, pady=4)
            
            # Status
            status_color = "#00ff88" if status == "finished" else "#ff6666"
            status_lbl = ctk.CTkLabel(
                row_frame,
                text=status.upper(),
                font=("Segoe UI", 10, "bold"),
                text_color=status_color,
                width=col_widths[3],
                anchor="w"
            )
            status_lbl.pack(side="left", padx=8, pady=4)
    
    def _render_live_positions(self):
        """Render full-field live standings during a race"""
        state = self._get_state()
        rds = state.race_day_state if state and hasattr(state, 'race_day_state') else None
        standings = rds.live_standings if rds and rds.live_standings else self._live_standings

        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text=f"🔴 LIVE Standings — Lap {self._current_lap} / {self._total_laps}",
            font=("Segoe UI", 14, "bold"),
            text_color="#ff4444"
        )
        title.pack(pady=(8, 12))

        if not standings:
            self._render_no_data()
            return

        # Column headers
        header_frame = ctk.CTkFrame(self.content_frame, fg_color="#333333", corner_radius=4)
        header_frame.pack(fill="x", padx=4, pady=(0, 4))

        headers = ["POS", "DRIVER", "TEAM", "GAP", "STATUS"]
        col_widths = [50, 170, 170, 90, 80]

        for header, width in zip(headers, col_widths):
            lbl = ctk.CTkLabel(
                header_frame,
                text=header,
                font=("Segoe UI", 11, "bold"),
                text_color="#aaaaaa",
                width=width,
                anchor="w"
            )
            lbl.pack(side="left", padx=6, pady=6)

        # Full field
        for idx, standing in enumerate(standings, 1):
            driver_name = standing.get('driver', 'Unknown')
            team_name = standing.get('team', 'Unknown')
            gap = standing.get('gap', 0.0)
            status = standing.get('status', 'racing')
            is_player = standing.get('is_player', False)

            row_color = "#2d3a2d" if is_player else ("#2a2a2a" if idx % 2 == 0 else "#242424")

            row_frame = ctk.CTkFrame(self.content_frame, fg_color=row_color, corner_radius=4)
            row_frame.pack(fill="x", padx=4, pady=1)

            # Position
            pos_color = "#FFD700" if idx == 1 else "#C0C0C0" if idx == 2 else "#CD7F32" if idx == 3 else "#ffffff"
            ctk.CTkLabel(
                row_frame, text=f"P{idx}", font=("Consolas", 11, "bold"),
                text_color=pos_color, width=col_widths[0], anchor="w"
            ).pack(side="left", padx=6, pady=4)

            # Driver
            ctk.CTkLabel(
                row_frame, text=driver_name, font=("Segoe UI", 11, "bold" if is_player else "normal"),
                text_color="#00ff88" if is_player else "#ffffff", width=col_widths[1], anchor="w"
            ).pack(side="left", padx=6, pady=4)

            # Team
            ctk.CTkLabel(
                row_frame, text=team_name, font=("Segoe UI", 10),
                text_color="#00cc66" if is_player else "#aaaaaa", width=col_widths[2], anchor="w"
            ).pack(side="left", padx=6, pady=4)

            # Gap
            gap_text = "LEADER" if idx == 1 else f"+{gap:.1f}s" if gap > 0 else ""
            if status != 'racing':
                gap_text = ""
            ctk.CTkLabel(
                row_frame, text=gap_text, font=("Consolas", 10),
                text_color="#cccccc", width=col_widths[3], anchor="w"
            ).pack(side="left", padx=6, pady=4)

            # Status
            if status == 'racing':
                st_text, st_color = "RACING", "#00ff88"
            elif status == 'finished':
                st_text, st_color = "FIN", "#00ff88"
            else:
                st_text, st_color = status.upper()[:6], "#ff6666"
            ctk.CTkLabel(
                row_frame, text=st_text, font=("Segoe UI", 10, "bold"),
                text_color=st_color, width=col_widths[4], anchor="w"
            ).pack(side="left", padx=6, pady=4)

    def _render_live_events(self):
        """Render live event feed during a race — full timeline"""
        state = self._get_state()
        rds = state.race_day_state if state and hasattr(state, 'race_day_state') else None
        events = rds.live_events if rds and rds.live_events else self._race_events_stream

        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text=f"🔴 LIVE Events — Lap {self._current_lap} / {self._total_laps}  ({len(events)} events)",
            font=("Segoe UI", 14, "bold"),
            text_color="#ff4444"
        )
        title.pack(pady=(8, 12))

        if not events:
            ctk.CTkLabel(
                self.content_frame,
                text="🏁 Waiting for race events...",
                font=("Segoe UI", 12), text_color="#666666"
            ).pack(pady=30)
            return

        # Show all events, most recent first
        for event in reversed(events):
            event_type = event.get('type', 'info').lower() if isinstance(event, dict) else getattr(event, 'event_type', 'info').lower()
            event_text = event.get('text', '') if isinstance(event, dict) else getattr(event, 'description', str(event))
            event_lap = event.get('lap', 0) if isinstance(event, dict) else getattr(event, 'lap_number', 0)

            if 'crash' in event_type or 'collision' in event_type or 'accident' in event_type:
                color, icon = "#ff6666", "💥"
            elif 'dnf' in event_type or 'retire' in event_type or 'mechanical' in event_type:
                color, icon = "#ff8844", "🔧"
            elif 'overtake' in event_type:
                color, icon = "#4488ff", "🔄"
            elif 'fastest' in event_type:
                color, icon = "#00ff88", "⚡"
            elif 'pit' in event_type:
                color, icon = "#ffcc00", "🔧"
            else:
                color, icon = "#aaaaaa", "ℹ️"

            event_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=4)
            event_frame.pack(fill="x", padx=4, pady=2)

            ctk.CTkLabel(
                event_frame, text=f"Lap {event_lap:3d}",
                font=("Consolas", 10, "bold"), text_color=color, width=70
            ).pack(side="left", padx=(10, 6), pady=6)

            ctk.CTkLabel(
                event_frame, text=f"{icon} {event_text}",
                font=("Segoe UI", 11), text_color="#cccccc", anchor="w"
            ).pack(side="left", fill="x", expand=True, padx=(0, 10), pady=6)

    def _render_live_telemetry(self):
        """Render live telemetry during a race — gaps, positions, lap data"""
        state = self._get_state()
        rds = state.race_day_state if state and hasattr(state, 'race_day_state') else None

        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text=f"🔴 LIVE Telemetry — Lap {self._current_lap} / {self._total_laps}",
            font=("Segoe UI", 14, "bold"),
            text_color="#ff4444"
        )
        title.pack(pady=(8, 12))

        if not rds or not rds.race_result:
            ctk.CTkLabel(
                self.content_frame,
                text="Telemetry data populating...",
                font=("Segoe UI", 12), text_color="#666666"
            ).pack(pady=30)
            return

        race_result = rds.race_result
        current_lap = rds.current_lap
        standings = rds.live_standings or []
        player_team = state.player_team.name if state and state.player_team else ''

        # ---- Gap chart: show all drivers with gap bars ----
        gap_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
        gap_frame.pack(fill="x", padx=4, pady=(0, 8))

        ctk.CTkLabel(
            gap_frame, text="📊 Gap to Leader",
            font=("Segoe UI", 13, "bold"), text_color="#ffffff"
        ).pack(padx=12, pady=(12, 8), anchor="w")

        max_gap = max((s.get('gap', 0) for s in standings), default=1) or 1

        for s in standings:
            driver = s.get('driver', '?')
            gap = s.get('gap', 0.0)
            is_player = s.get('is_player', False)
            bar_frac = min(1.0, gap / max_gap) if max_gap > 0 else 0

            row = ctk.CTkFrame(gap_frame, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=1)

            ctk.CTkLabel(
                row, text=f"{driver[:18]:18s}",
                font=("Consolas", 10, "bold" if is_player else "normal"),
                text_color="#00ff88" if is_player else "#cccccc", width=140, anchor="w"
            ).pack(side="left")

            bar = ctk.CTkProgressBar(row, width=200, height=10, corner_radius=3,
                                     fg_color="#333333",
                                     progress_color="#00ff88" if is_player else "#4488ff")
            bar.set(bar_frac)
            bar.pack(side="left", padx=4)

            ctk.CTkLabel(
                row, text=f"+{gap:.1f}s" if gap > 0 else "LEADER",
                font=("Consolas", 9), text_color="#aaaaaa", width=70, anchor="w"
            ).pack(side="left", padx=4)

        # ---- Lap-by-lap driver data (from race_result.laps) ----
        laps = [l for l in race_result.laps if l.lap_number == current_lap]
        if laps:
            lap_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
            lap_frame.pack(fill="x", padx=4, pady=(0, 8))

            ctk.CTkLabel(
                lap_frame, text=f"🏎️ Lap {current_lap} Details",
                font=("Segoe UI", 13, "bold"), text_color="#ffffff"
            ).pack(padx=12, pady=(12, 8), anchor="w")

            # Column headers
            hdr = ctk.CTkFrame(lap_frame, fg_color="#333333", corner_radius=4)
            hdr.pack(fill="x", padx=12, pady=(0, 4))
            for h, w in [("POS", 40), ("DRIVER", 160), ("TEAM", 140), ("LAP TIME", 90), ("GAP", 80)]:
                ctk.CTkLabel(hdr, text=h, font=("Segoe UI", 9, "bold"),
                             text_color="#aaaaaa", width=w, anchor="w").pack(side="left", padx=4, pady=4)

            laps.sort(key=lambda l: l.position)
            for ld in laps:
                is_pl = (ld.team_name == player_team)
                rc = "#2d3a2d" if is_pl else "#2a2a2a"
                r = ctk.CTkFrame(lap_frame, fg_color=rc, corner_radius=3)
                r.pack(fill="x", padx=12, pady=1)

                ctk.CTkLabel(r, text=f"P{ld.position}", font=("Consolas", 10, "bold"),
                             text_color="#ffffff", width=40, anchor="w").pack(side="left", padx=4, pady=3)
                ctk.CTkLabel(r, text=ld.driver_name, font=("Segoe UI", 10, "bold" if is_pl else "normal"),
                             text_color="#00ff88" if is_pl else "#ffffff", width=160, anchor="w").pack(side="left", padx=4, pady=3)
                ctk.CTkLabel(r, text=ld.team_name, font=("Segoe UI", 9),
                             text_color="#aaaaaa", width=140, anchor="w").pack(side="left", padx=4, pady=3)
                ctk.CTkLabel(r, text=f"{ld.lap_time:.3f}s" if hasattr(ld, 'lap_time') and ld.lap_time else "—",
                             font=("Consolas", 10), text_color="#cccccc", width=90, anchor="w").pack(side="left", padx=4, pady=3)
                ctk.CTkLabel(r, text=f"+{ld.gap_to_leader:.1f}s" if ld.gap_to_leader > 0 else "LEAD",
                             font=("Consolas", 10), text_color="#cccccc", width=80, anchor="w").pack(side="left", padx=4, pady=3)

        # ---- Race statistics summary ----
        stats_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=8)
        stats_frame.pack(fill="x", padx=4, pady=(0, 8))

        ctk.CTkLabel(
            stats_frame, text="📈 Race Statistics",
            font=("Segoe UI", 13, "bold"), text_color="#ffffff"
        ).pack(padx=12, pady=(12, 8), anchor="w")

        total_events = len([e for e in race_result.race_events if e.lap_number <= current_lap])
        overtakes = len([e for e in race_result.race_events if e.lap_number <= current_lap and 'overtake' in e.event_type.lower()])
        incidents = len([e for e in race_result.race_events if e.lap_number <= current_lap and ('crash' in e.event_type.lower() or 'dnf' in e.event_type.lower())])
        dnfs = len(set(d for e in race_result.race_events if e.lap_number <= current_lap and 'dnf' in e.event_type.lower() for d in e.involved_drivers))

        stats_text = (
            f"  Laps completed:   {current_lap} / {rds.total_laps}\n"
            f"  Race events:      {total_events}\n"
            f"  Overtakes:        {overtakes}\n"
            f"  Incidents:        {incidents}\n"
            f"  Retirements:      {dnfs}\n"
            f"  Drivers running:  {len([s for s in standings if s.get('status') == 'racing'])}"
        )

        ctk.CTkLabel(
            stats_frame, text=stats_text, font=("Consolas", 11),
            text_color="#cccccc", justify="left", anchor="w"
        ).pack(padx=12, pady=(0, 12), anchor="w")

    def _render_events_view(self):
        """Render race events timeline"""
        # During live streaming, show live events
        if self._race_streaming:
            self._render_live_events()
            return

        if not CURRENT_RACE:
            self._render_no_data()
            return
        
        race = CURRENT_RACE
        events = race.get('events', [])
        
        # Update status
        self.status_label.configure(
            text=f"{len(events)} race events"
        )
        
        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text=f"Race Events - {race['track_name']}",
            font=("Segoe UI", 14, "bold"),
            text_color="#ffffff"
        )
        title.pack(pady=(8, 12))
        
        if not events:
            msg = ctk.CTkLabel(
                self.content_frame,
                text="No race events recorded",
                font=("Segoe UI", 12),
                text_color="#666666"
            )
            msg.pack(pady=30)
            return
        
        # Event cards
        for event in events:
            event_type = event.event_type
            
            # Color by type
            if event_type == "overtake":
                color = "#4488ff"
                icon = "🔄"
            elif event_type == "mechanical_dnf":
                color = "#ff6666"
                icon = "🔧"
            elif event_type == "crash":
                color = "#ff8844"
                icon = "💥"
            else:
                color = "#666666"
                icon = "ℹ️"
            
            event_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=6)
            event_frame.pack(fill="x", padx=4, pady=3)
            
            # Lap indicator
            lap_lbl = ctk.CTkLabel(
                event_frame,
                text=f"Lap {event.lap_number}",
                font=("Consolas", 10, "bold"),
                text_color=color,
                width=80
            )
            lap_lbl.pack(side="left", padx=(12, 8), pady=8)
            
            # Event description
            desc_lbl = ctk.CTkLabel(
                event_frame,
                text=f"{icon} {event.description}",
                font=("Segoe UI", 11),
                text_color="#cccccc",
                anchor="w"
            )
            desc_lbl.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)
    
    def _render_telemetry_view(self):
        """Render telemetry analysis"""
        # During live streaming, show live telemetry
        if self._race_streaming:
            self._render_live_telemetry()
            return

        if not CURRENT_RACE:
            self._render_no_data()
            return
        
        race = CURRENT_RACE
        telemetry = race.get('telemetry', {})
        
        # Update status
        self.status_label.configure(
            text=f"{len(telemetry)} drivers analyzed"
        )
        
        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text=f"Telemetry Analysis - {race['track_name']}",
            font=("Segoe UI", 14, "bold"),
            text_color="#ffffff"
        )
        title.pack(pady=(8, 12))
        
        if not telemetry:
            msg = ctk.CTkLabel(
                self.content_frame,
                text="No telemetry data available",
                font=("Segoe UI", 12),
                text_color="#666666"
            )
            msg.pack(pady=30)
            return
        
        # Table header
        header_frame = ctk.CTkFrame(self.content_frame, fg_color="#333333", corner_radius=4)
        header_frame.pack(fill="x", padx=4, pady=(0, 4))
        
        headers = ["DRIVER", "AVG LAP", "FASTEST", "CONSISTENCY", "TIRE MGMT"]
        col_widths = [180, 100, 100, 120, 120]
        
        for header, width in zip(headers, col_widths):
            lbl = ctk.CTkLabel(
                header_frame,
                text=header,
                font=("Segoe UI", 10, "bold"),
                text_color="#aaaaaa",
                width=width,
                anchor="w"
            )
            lbl.pack(side="left", padx=6, pady=6)
        
        # Telemetry rows
        for driver_name, metrics in telemetry.items():
            row_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=4)
            row_frame.pack(fill="x", padx=4, pady=2)
            
            # Driver
            driver_lbl = ctk.CTkLabel(
                row_frame,
                text=driver_name,
                font=("Segoe UI", 11),
                text_color="#ffffff",
                width=col_widths[0],
                anchor="w"
            )
            driver_lbl.pack(side="left", padx=6, pady=4)
            
            # Average lap time
            avg_lap = metrics.get('avg_lap_time', 0)
            avg_lbl = ctk.CTkLabel(
                row_frame,
                text=f"{avg_lap:.3f}s" if avg_lap > 0 else "N/A",
                font=("Consolas", 10),
                text_color="#cccccc",
                width=col_widths[1],
                anchor="w"
            )
            avg_lbl.pack(side="left", padx=6, pady=4)
            
            # Fastest lap
            fastest = metrics.get('fastest_lap', 0)
            fast_lbl = ctk.CTkLabel(
                row_frame,
                text=f"{fastest:.3f}s" if fastest > 0 else "N/A",
                font=("Consolas", 10),
                text_color="#00ff88",
                width=col_widths[2],
                anchor="w"
            )
            fast_lbl.pack(side="left", padx=6, pady=4)
            
            # Consistency rating
            consistency = metrics.get('consistency_rating', 0)
            cons_color = "#00ff88" if consistency >= 70 else "#ffaa44" if consistency >= 50 else "#ff6666"
            cons_lbl = ctk.CTkLabel(
                row_frame,
                text=f"{consistency:.1f}/100" if consistency > 0 else "N/A",
                font=("Consolas", 10),
                text_color=cons_color,
                width=col_widths[3],
                anchor="w"
            )
            cons_lbl.pack(side="left", padx=6, pady=4)
            
            # Tire management
            tire_mgmt = metrics.get('tire_management', 0)
            tire_color = "#00ff88" if tire_mgmt >= 70 else "#ffaa44" if tire_mgmt >= 50 else "#ff6666"
            tire_lbl = ctk.CTkLabel(
                row_frame,
                text=f"{tire_mgmt:.1f}/100" if tire_mgmt > 0 else "N/A",
                font=("Consolas", 10),
                text_color=tire_color,
                width=col_widths[4],
                anchor="w"
            )
            tire_lbl.pack(side="left", padx=6, pady=4)
    
    def _render_history_view(self):
        """Render race history list"""
        if not RACE_HISTORY:
            self._render_no_data()
            return
        
        # Update status
        self.status_label.configure(
            text=f"{len(RACE_HISTORY)} recent races"
        )
        
        # Header
        title = ctk.CTkLabel(
            self.content_frame,
            text="Race History",
            font=("Segoe UI", 14, "bold"),
            text_color="#ffffff"
        )
        title.pack(pady=(8, 12))
        
        # Race list
        for idx, race in enumerate(RACE_HISTORY):
            race_frame = ctk.CTkFrame(self.content_frame, fg_color="#2a2a2a", corner_radius=6)
            race_frame.pack(fill="x", padx=4, pady=4)
            
            # Race info
            info_frame = ctk.CTkFrame(race_frame, fg_color="transparent")
            info_frame.pack(fill="x", padx=12, pady=8)
            
            # Title
            race_title = ctk.CTkLabel(
                info_frame,
                text=f"{race['league_name']} • Round {race['round']}",
                font=("Segoe UI", 12, "bold"),
                text_color="#ffffff",
                anchor="w"
            )
            race_title.pack(anchor="w")
            
            # Details
            winner = race['final_positions'][0] if race['final_positions'] else ("Unknown", "Unknown", "unknown")
            details = f"{race['track_name']} • Winner: {winner[0]} ({winner[1]}) • {race['total_laps']} laps • {len(race['events'])} events"
            
            details_lbl = ctk.CTkLabel(
                info_frame,
                text=details,
                font=("Segoe UI", 10),
                text_color="#888888",
                anchor="w"
            )
            details_lbl.pack(anchor="w")
            
            # View button
            view_btn = ctk.CTkButton(
                race_frame,
                text="View Details →",
                width=120,
                height=24,
                fg_color="#444444",
                hover_color="#555555",
                corner_radius=4,
                font=("Segoe UI", 10),
                command=lambda r=race: self._view_race_details(r)
            )
            view_btn.pack(padx=12, pady=(0, 8), anchor="e")
    
    def _view_race_details(self, race: Dict[str, Any]):
        """Switch to live view with selected race as current"""
        global CURRENT_RACE
        CURRENT_RACE = race
        self._switch_tab("live")
    
    def _render_no_data(self):
        """Render no data message"""
        msg = ctk.CTkLabel(
            self.content_frame,
            text="No race data available\n\nComplete a race to see details here",
            font=("Segoe UI", 13),
            text_color="#666666",
            justify="center"
        )
        msg.pack(pady=60)


# ============================================================================
# WIDGET REGISTRATION
# ============================================================================

def register_widgets(registry, runtime_stub):
    """Register the play-by-play widget"""
    
    def widget_factory(parent_frame):
        """Factory function to create widget instance"""
        widget = FTBPlayByPlayWidget(parent_frame, runtime_stub)
        return widget
    
    # Register the widget
    registry.register(
        "ftb_pbp",
        widget_factory
    )
    
    _dbg(f"[{PLUGIN_NAME}] Widget registered")
