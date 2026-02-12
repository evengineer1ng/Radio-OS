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

# Import game state structures
try:
    sys.path.insert(0, "plugins")
    import ftb_state_db
    from ftb_game import RaceResult, LapData, RaceEventRecord
except Exception:
    ftb_state_db = None
    RaceResult = None
    LapData = None
    RaceEventRecord = None


# ============================================================================
# METADATA (Runtime Discovery)
# ============================================================================

PLUGIN_NAME = "FTB Play-by-Play"
PLUGIN_DESC = "Live race action with lap-by-lap updates, overtakes, and telemetry"
IS_FEED = False  # UI widget, not feed


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


def update_race_data(race_result: Any, state: Any):
    """
    Called when a race completes to cache data for display.
    This would be called from the simulation or event hook.
    """
    global CURRENT_RACE, RACE_HISTORY
    
    if not race_result:
        return
    
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
    """Start a drip-feed play-by-play session for a completed race sim."""
    global CURRENT_RACE, RACE_HISTORY
    global LIVE_FEED_EVENTS, LIVE_FEED_CURSOR, LIVE_FEED_ACTIVE, LIVE_FEED_INTERVAL, LIVE_FEED_LAST_TS

    if not race_result:
        return

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
        self.log = runtime_stub.get('log', print)
        
        # State tracking
        self._last_tick = -1
        self._current_view = "live"  # live, history, telemetry
        self._selected_race_idx = 0
        
        # UI Components
        self._build_ui()
        
        # Start refresh loop
        self.after(1000, self._refresh_loop)
    
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
    
    def _refresh_loop(self):
        """Periodic refresh to check for new race data"""
        try:
            # Check runtime for state updates
            state = self.runtime.get('state')
            if state and hasattr(state, 'tick'):
                if state.tick != self._last_tick:
                    self._last_tick = state.tick
                    self._refresh_content()
            if _advance_live_feed():
                self._refresh_content()
        except Exception as e:
            pass
        
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
    
    def _render_live_view(self):
        """Render live race overview"""
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
        
        positions = race['final_positions'][:10]  # Top 10
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
        """Render position standings with gaps"""
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
    
    def _render_events_view(self):
        """Render race events timeline"""
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
    
    print(f"[{PLUGIN_NAME}] Widget registered")
