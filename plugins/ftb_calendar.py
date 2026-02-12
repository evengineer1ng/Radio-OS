"""
FTB Calendar Widget - Forward-Looking Strategic Planning Layer

Provides visual calendar showing:
- Competition layer: races, championship rounds, travel windows
- Personnel layer: contract expiries, negotiation windows
- Financial layer: sponsor payments, salaries, upkeep cycles
- Pressure layer: morale decay warnings, sponsor patience
- Player notes: custom reminders and decision triggers

Non-passive: player adds notes, sees approaching deadlines, plans ahead.
Narrator integrates: references upcoming events for time-aware commentary.
"""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from typing import Any, Dict, List, Optional, Tuple
import sys

# Import state DB for calendar queries
try:
    sys.path.insert(0, "plugins")
    import ftb_state_db
except Exception:
    ftb_state_db = None


# ============================================================================
# METADATA (Runtime Discovery)
# ============================================================================

PLUGIN_NAME = "FTB Calendar"
PLUGIN_DESC = "Strategic planning calendar showing upcoming events, deadlines, and player notes"
IS_FEED = False  # UI widget, not feed


# ============================================================================
# DATE CONVERSION UTILITIES
# ============================================================================

# Month names and day counts for 365-day year
MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
]

DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

def day_of_year_to_date(day_of_year: int) -> str:
    """
    Convert day-of-year (1-365) to readable date format.
    
    Args:
        day_of_year: Integer from 1 to 365
    
    Returns:
        Formatted date string like "Jan 15" or "Dec 31"
    """
    if day_of_year < 1 or day_of_year > 365:
        return f"Day {day_of_year}"
    
    cumulative_days = 0
    for month_idx, days_in_month in enumerate(DAYS_IN_MONTH):
        if day_of_year <= cumulative_days + days_in_month:
            day_in_month = day_of_year - cumulative_days
            month_abbr = MONTH_NAMES[month_idx][:3]  # First 3 letters
            return f"{month_abbr} {day_in_month}"
        cumulative_days += days_in_month
    
    # Fallback (shouldn't reach here)
    return f"Day {day_of_year}"


def format_date_with_relative(day_of_year: int, current_day: int) -> str:
    """
    Format date with both absolute date and relative days.
    
    Args:
        day_of_year: Target day
        current_day: Current day
    
    Returns:
        String like "Mar 15 (8 days away)" or "Jan 1 (today)"
    """
    date_str = day_of_year_to_date(day_of_year)
    days_away = day_of_year - current_day
    
    if days_away == 0:
        relative = "today"
    elif days_away == 1:
        relative = "tomorrow"
    elif days_away < 0:
        relative = f"{abs(days_away)} days ago"
    else:
        relative = f"{days_away} days away"
    
    return f"{date_str} ({relative})"


# ============================================================================
# CALENDAR WIDGET
# ============================================================================

class FTBCalendarWidget(ctk.CTkFrame):
    """Calendar widget with timeline, season view, decision inbox, and notes"""
    
    def __init__(self, parent, runtime_stub: Dict[str, Any]):
        super().__init__(parent)
        self.runtime = runtime_stub
        self.log = runtime_stub.get('log', print)
        
        # State tracking
        self._last_tick = -1
        self._last_day = -1
        self.controller = None
        self.db_path = None
        
        # UI Components
        self._build_ui()
        
        self.log("ftb_calendar", "Calendar widget initialized")
    
    def _build_ui(self):
        """Build unified calendar grid UI"""
        # Title
        title = ctk.CTkLabel(
            self, 
            text="📅 Championship Calendar",
            font=("Arial", 16, "bold")
        )
        title.pack(pady=(10, 5))
        
        # Current date display
        self.date_label = ctk.CTkLabel(
            self,
            text="Year 1, Day 1",
            font=("Arial", 12),
            text_color="gray"
        )
        self.date_label.pack(pady=(0, 5))
        
        # Filter controls
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=10, pady=(0, 5))
        
        # Category filters in a single row
        self.category_filters = {}
        categories = [
            ("🏁", "competition"),
            ("👥", "personnel"),
            ("💰", "financial"),
            ("⚠️", "pressure"),
            ("📝", "player")
        ]
        
        for emoji, key in categories:
            var = tk.BooleanVar(value=True)
            cb = ctk.CTkCheckBox(
                filter_frame,
                text=emoji,
                variable=var,
                font=("Arial", 14),
                width=40,
                command=self._refresh_calendar_grid
            )
            cb.pack(side="left", padx=2)
            self.category_filters[key] = var
        
        # Navigation controls
        nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        nav_frame.pack(fill="x", padx=10, pady=(5, 5))
        
        ctk.CTkButton(nav_frame, text="◀◀", width=50, command=self._jump_backward).pack(side="left", padx=2)
        ctk.CTkButton(nav_frame, text="◀", width=50, command=self._prev_page).pack(side="left", padx=2)
        ctk.CTkButton(nav_frame, text="Today", width=60, command=self._jump_to_today).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(nav_frame, text="▶", width=50, command=self._next_page).pack(side="left", padx=2)
        ctk.CTkButton(nav_frame, text="▶▶", width=50, command=self._jump_forward).pack(side="left", padx=2)
        
        # Single unified calendar grid (scrollable)
        self.calendar_grid = ctk.CTkScrollableFrame(self, width=400, height=500)
        self.calendar_grid.pack(fill="both", expand=True, padx=10, pady=5)
        
        # State for pagination
        self.current_day_view = 1  # Start at day 1
        self.days_per_page = 60  # Show 60 days (~2 months) at a time
    
    def _jump_backward(self):
        """Jump back 60 days"""
        self.current_day_view = max(1, self.current_day_view - 60)
        self._refresh_calendar_grid()
    
    def _prev_page(self):
        """Previous page (30 days)"""
        self.current_day_view = max(1, self.current_day_view - 30)
        self._refresh_calendar_grid()
    
    def _next_page(self):
        """Next page (30 days)"""
        self.current_day_view = min(365 - self.days_per_page + 1, self.current_day_view + 30)
        self._refresh_calendar_grid()
    
    def _jump_forward(self):
        """Jump forward 60 days"""
        self.current_day_view = min(365 - self.days_per_page + 1, self.current_day_view + 60)
        self._refresh_calendar_grid()
    
    def _jump_to_today(self):
        """Jump to current day"""
        if hasattr(self, 'current_day_of_year'):
            self.current_day_view = max(1, self.current_day_of_year - 15)  # Center current day
            self._refresh_calendar_grid()
    
    def _refresh_calendar_grid(self):
        """Refresh the unified calendar grid"""
        # Clear grid
        for widget in self.calendar_grid.winfo_children():
            widget.destroy()
        
        if not self.db_path or not ftb_state_db:
            placeholder = ctk.CTkLabel(
                self.calendar_grid,
                text="Database not connected",
                text_color="gray"
            )
            placeholder.pack(pady=20)
            return
        
        try:
            # Query events for the visible window
            end_day = min(365, self.current_day_view + self.days_per_page - 1)
            entries = ftb_state_db.query_calendar_window(
                self.db_path,
                self.current_day_view,
                end_day
            )
            
            # Filter by selected categories
            active_categories = [cat for cat, var in self.category_filters.items() if var.get()]
            filtered_entries = [e for e in entries if e['category'] in active_categories]
            
            # Group entries by day
            entries_by_day = {}
            for entry in filtered_entries:
                day = entry['entry_day']
                if day not in entries_by_day:
                    entries_by_day[day] = []
                entries_by_day[day].append(entry)
            
            # Display days with events
            current_day = getattr(self, 'current_day_of_year', 1)
            
            if not entries_by_day:
                placeholder = ctk.CTkLabel(
                    self.calendar_grid,
                    text=f"No events from day {self.current_day_view} to {end_day}",
                    text_color="gray"
                )
                placeholder.pack(pady=20)
                return
            
            # Render each day that has events
            for day in sorted(entries_by_day.keys()):
                self._create_day_card(day, entries_by_day[day], current_day)
        
        except Exception as e:
            self.log("ftb_calendar", f"Calendar grid refresh error: {e}")
            error_label = ctk.CTkLabel(
                self.calendar_grid,
                text=f"Error loading calendar: {e}",
                text_color="red"
            )
            error_label.pack(pady=20)
    
    def _create_day_card(self, day: int, entries: List[Dict], current_day: int):
        """Create a card for a single day with its events"""
        # Category colors
        category_colors = {
            'competition': '#3498db',
            'personnel': '#f39c12',
            'financial': '#2ecc71',
            'pressure': '#e74c3c',
            'player': '#9b59b6'
        }
        
        # Day card frame
        is_today = (day == current_day)
        is_past = (day < current_day)
        
        frame_color = "#2c2c2c" if is_today else ("#1a1a1a" if is_past else "transparent")
        
        day_card = ctk.CTkFrame(self.calendar_grid, fg_color=frame_color, corner_radius=8)
        day_card.pack(fill="x", padx=5, pady=5)
        
        # Day header
        date_str = day_of_year_to_date(day)
        days_away = day - current_day
        
        if is_today:
            status = "TODAY"
            status_color = "#2ecc71"
        elif is_past:
            status = f"{abs(days_away)}d ago"
            status_color = "gray"
        else:
            status = f"in {days_away}d"
            status_color = "#3498db"
        
        header_frame = ctk.CTkFrame(day_card, fg_color="transparent")
        header_frame.pack(fill="x", padx=10, pady=5)
        
        day_label = ctk.CTkLabel(
            header_frame,
            text=f"Day {day} • {date_str}",
            font=("Arial", 11, "bold"),
            anchor="w"
        )
        day_label.pack(side="left")
        
        status_label = ctk.CTkLabel(
            header_frame,
            text=status,
            font=("Arial", 9),
            text_color=status_color,
            anchor="e"
        )
        status_label.pack(side="right")
        
        # Event list for this day
        for entry in entries:
            self._create_event_row(day_card, entry, category_colors)
    
    def _create_event_row(self, parent, entry: Dict, category_colors: Dict):
        """Create a single event row"""
        color = category_colors.get(entry['category'], 'gray')
        
        event_frame = ctk.CTkFrame(parent, fg_color="transparent")
        event_frame.pack(fill="x", padx=15, pady=2)
        
        # Category indicator (colored dot)
        indicator = ctk.CTkLabel(
            event_frame,
            text="●",
            font=("Arial", 14),
            text_color=color,
            width=20
        )
        indicator.pack(side="left")
        
        # Event text
        title_text = entry['title']
        if entry.get('action_required'):
            title_text = "⚠️ " + title_text
        
        event_label = ctk.CTkLabel(
            event_frame,
            text=title_text,
            font=("Arial", 10),
            anchor="w"
        )
        event_label.pack(side="left", fill="x", expand=True)
    
    def _add_note(self):
        """Add player note to calendar"""
        if not self.db_path or not ftb_state_db:
            self.log("ftb_calendar", "Cannot add note: no database connection")
            return
        
        # Get inputs
        day_str = self.note_day_entry.get().strip()
        title = self.note_title_entry.get().strip()
        description = self.note_desc_entry.get("1.0", "end").strip()
        
        if not day_str or not title:
            self.log("ftb_calendar", "Cannot add note: day and title required")
            return
        
        try:
            day = int(day_str)
        except ValueError:
            self.log("ftb_calendar", f"Invalid day: {day_str}")
            return
        
        # Clear description if it's the placeholder
        if description == "Optional notes...":
            description = ""
        
        # Add to database
        try:
            note_id = ftb_state_db.add_player_note(self.db_path, day, title, description)
            self.log("ftb_calendar", f"Added note #{note_id}: '{title}' on day {day}")
            
            # Clear inputs
            self.note_day_entry.delete(0, "end")
            self.note_title_entry.delete(0, "end")
            self.note_desc_entry.delete("1.0", "end")
            self.note_desc_entry.insert("1.0", "Optional notes...")
            
            # Refresh display
            self._refresh_notes()
        except Exception as e:
            self.log("ftb_calendar", f"Error adding note: {e}")
    
    def _delete_note(self, note_id: int):
        """Delete player note"""
        if not self.db_path or not ftb_state_db:
            return
        
        try:
            if ftb_state_db.delete_player_note(self.db_path, note_id):
                self.log("ftb_calendar", f"Deleted note #{note_id}")
                self._refresh_notes()
        except Exception as e:
            self.log("ftb_calendar", f"Error deleting note: {e}")
    
    def start_poll(self):
        """Start polling controller state"""
        self.after(500, self._poll)
    
    def _poll(self):
        """Poll controller for state updates"""
        try:
            # Get controller reference
            if not self.controller:
                self.controller = self.runtime.get("ftb_controller")
                if self.controller and hasattr(self.controller, 'state_db_path'):
                    self.db_path = self.controller.state_db_path
                    self.log("ftb_calendar", f"Connected to state DB: {self.db_path}")
                elif self.controller:
                    self.log("ftb_calendar", "Warning: Controller has no state_db_path")
            elif self.controller and hasattr(self.controller, 'state_db_path'):
                if self.controller.state_db_path and self.controller.state_db_path != self.db_path:
                    self.db_path = self.controller.state_db_path
                    self.log("ftb_calendar", f"Switched state DB: {self.db_path}")
            
            # Check if state changed
            if self.controller and self.controller.state:
                state = self.controller.state
                
                # Only refresh if tick or day changed
                if state.tick != self._last_tick or state.sim_day_of_year != self._last_day:
                    self._refresh_from_state(state)
                    self._last_tick = state.tick
                    self._last_day = state.sim_day_of_year
        
        except Exception as e:
            self.log("ftb_calendar", f"Poll error: {e}")
        
        # Schedule next poll
        self.after(500, self._poll)
    
    def _refresh_from_state(self, state):
        """Refresh calendar display from simulation state"""
        try:
            # Update current date with readable format
            readable_date = day_of_year_to_date(state.sim_day_of_year)
            self.date_label.configure(text=f"Year {state.sim_year}, {readable_date} (Day {state.sim_day_of_year})")
            
            # Update current day tracking
            self.current_day_of_year = state.sim_day_of_year
            
            # Refresh the unified calendar grid
            self._refresh_calendar_grid()
            
        except Exception as e:
            self.log("ftb_calendar", f"Refresh error: {e}")


# ============================================================================
# WIDGET REGISTRATION
# ============================================================================

def register_widgets(registry, runtime_stub):
    """Register calendar widget with runtime"""
    def factory(parent, rt):
        widget = FTBCalendarWidget(parent, runtime_stub)
        widget.start_poll()
        return widget
    
    registry.register(
        "ftb_calendar",
        factory,
        title="📅 Calendar",
        default_panel="right"
    )
