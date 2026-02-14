"""
FTB DB Explorer Widget - Historical Data Visualization Interface

Provides comprehensive visualization and querying of FTB historical data.
Displays career stats, trends, comparisons, and analytics for teams, drivers,
and league history.

Features:
- Team historical dashboard (career totals, era performance, peak/valley)
- Driver archives (career stats, team stints, development curve)
- League history browser (championship records, tier evolution)
- Analytics dashboard (composite scores, streaks, momentum)
- Custom query console
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import json
from dataclasses import dataclass
from contextlib import contextmanager

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    print("[FTB DB Explorer] Warning: customtkinter not available, using tkinter")

try:
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("[FTB DB Explorer] Warning: matplotlib not available, charts disabled")

try:
    from plugins import ftb_state_db
except ImportError:
    print("[FTB DB Explorer] Warning: Could not import ftb_state_db")
    ftb_state_db = None

try:
    from plugins import ftb_db_archival
except ImportError:
    print("[FTB DB Explorer] Warning: Could not import ftb_db_archival")
    ftb_db_archival = None


# ============================================================================
# PLUGIN METADATA
# ============================================================================

IS_FEED = False
PLUGIN_NAME = "FTB DB Explorer"
PLUGIN_DESC = "Historical data visualization and query interface"


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class TeamHistoricalSummary:
    """Comprehensive historical summary for a team."""
    team_name: str
    
    # Career totals
    seasons_entered: int = 0
    races_entered: int = 0
    wins_total: int = 0
    podiums_total: int = 0
    championships_won: int = 0
    win_rate: float = 0.0
    
    # Current state
    team_pulse: float = 50.0
    competitive_tier: str = "midfield"
    narrative_temperature: str = "stable"
    prestige_index: float = 50.0
    
    # Streaks
    current_points_streak: int = 0
    current_win_streak: int = 0
    longest_points_streak_ever: int = 0
    
    # Performance
    best_season_finish: Optional[int] = None
    best_season_finish_year: Optional[int] = None
    golden_era_start: Optional[int] = None
    golden_era_end: Optional[int] = None


@dataclass
class DriverHistoricalSummary:
    """Comprehensive historical summary for a driver."""
    driver_name: str
    age: int
    current_team: Optional[str] = None
    
    # Career stats
    career_starts: int = 0
    career_wins: int = 0
    career_podiums: int = 0
    championships_won: int = 0
    win_rate_career: float = 0.0
    
    # Legacy
    legacy_score: float = 50.0
    legacy_tier: str = "developing"
    
    # Peak
    peak_rating: float = 0.0
    peak_rating_age: Optional[int] = None
    
    # Pressure
    mettle_under_pressure_index: float = 0.0


# ============================================================================
# DATABASE HELPER
# ============================================================================

class HistoricalDataQuery:
    """Helper class for querying historical data."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def get_team_summary(self, team_name: str) -> Optional[TeamHistoricalSummary]:
        """Get comprehensive historical summary for a team."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get career totals
            cursor.execute("""
                SELECT * FROM team_career_totals WHERE team_name = ?
            """, (team_name,))
            career = cursor.fetchone()
            
            # Get pulse metrics
            cursor.execute("""
                SELECT * FROM team_pulse_metrics WHERE team_name = ?
            """, (team_name,))
            pulse = cursor.fetchone()
            
            # Get prestige
            cursor.execute("""
                SELECT prestige_index FROM team_prestige WHERE team_name = ?
            """, (team_name,))
            prestige_row = cursor.fetchone()
            
            # Get streaks
            cursor.execute("""
                SELECT * FROM active_streaks WHERE team_name = ?
            """, (team_name,))
            streaks = cursor.fetchone()
            
            # Get peak/valley
            cursor.execute("""
                SELECT * FROM team_peak_valley WHERE team_name = ?
            """, (team_name,))
            peak_valley = cursor.fetchone()
            
            if not career:
                return None
            
            return TeamHistoricalSummary(
                team_name=team_name,
                seasons_entered=career['seasons_entered'] if career else 0,
                races_entered=career['races_entered'] if career else 0,
                wins_total=career['wins_total'] if career else 0,
                podiums_total=career['podiums_total'] if career else 0,
                championships_won=career['championships_won'] if career else 0,
                win_rate=career['win_rate'] if career else 0.0,
                team_pulse=pulse['team_pulse'] if pulse else 50.0,
                competitive_tier=pulse['competitive_tier'] if pulse else "midfield",
                narrative_temperature=pulse['narrative_temperature'] if pulse else "stable",
                prestige_index=prestige_row['prestige_index'] if prestige_row else 50.0,
                current_points_streak=streaks['current_points_streak'] if streaks else 0,
                current_win_streak=streaks['current_win_streak'] if streaks else 0,
                longest_points_streak_ever=streaks['longest_points_streak_ever'] if streaks else 0,
                best_season_finish=peak_valley['best_season_finish'] if peak_valley else None,
                best_season_finish_year=peak_valley['best_season_finish_year'] if peak_valley else None,
                golden_era_start=peak_valley['golden_era_start'] if peak_valley else None,
                golden_era_end=peak_valley['golden_era_end'] if peak_valley else None,
            )
    
    def get_driver_summary(self, driver_name: str) -> Optional[DriverHistoricalSummary]:
        """Get comprehensive historical summary for a driver."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Get driver entity
            cursor.execute("""
                SELECT age, team_name FROM entities 
                WHERE name = ? AND entity_type = 'driver'
            """, (driver_name,))
            entity = cursor.fetchone()
            
            if not entity:
                return None
            
            # Get career stats
            cursor.execute("""
                SELECT * FROM driver_career_stats WHERE driver_name = ?
            """, (driver_name,))
            career = cursor.fetchone()
            
            # Get legacy
            cursor.execute("""
                SELECT legacy_score, legacy_tier FROM driver_legacy WHERE driver_name = ?
            """, (driver_name,))
            legacy = cursor.fetchone()
            
            # Get development curve
            cursor.execute("""
                SELECT * FROM driver_development_curve WHERE driver_name = ?
            """, (driver_name,))
            curve = cursor.fetchone()
            
            return DriverHistoricalSummary(
                driver_name=driver_name,
                age=entity['age'],
                current_team=entity['team_name'],
                career_starts=career['career_starts'] if career else 0,
                career_wins=career['career_wins'] if career else 0,
                career_podiums=career['career_podiums'] if career else 0,
                championships_won=career['championships_won'] if career else 0,
                win_rate_career=career['win_rate_career'] if career else 0.0,
                legacy_score=legacy['legacy_score'] if legacy else 50.0,
                legacy_tier=legacy['legacy_tier'] if legacy else "developing",
                peak_rating=curve['peak_rating'] if curve else 0.0,
                peak_rating_age=curve['peak_rating_age'] if curve else None,
                mettle_under_pressure_index=curve['mettle_under_pressure_index'] if curve else 0.0,
            )
    
    def get_all_teams(self) -> List[str]:
        """Get list of all teams (current and folded)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT team_name FROM team_career_totals
                ORDER BY team_name
            """)
            return [row['team_name'] for row in cursor.fetchall()]
    
    def get_all_drivers(self) -> List[str]:
        """Get list of all drivers (current and retired)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DISTINCT driver_name FROM driver_career_stats
                ORDER BY driver_name
            """)
            return [row['driver_name'] for row in cursor.fetchall()]
    
    def get_championship_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get championship history records."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    season,
                    champion_team,
                    champion_points,
                    runner_up_team,
                    runner_up_points,
                    title_margin,
                    title_decided_round,
                    parity_index
                FROM championship_history
                ORDER BY season DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_active_streaks_all(self) -> List[Dict[str, Any]]:
        """Get all active streaks for all teams."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    team_name,
                    current_points_streak,
                    current_win_streak,
                    current_podium_streak,
                    longest_points_streak_ever,
                    longest_win_streak_ever
                FROM active_streaks
                WHERE current_points_streak > 0 
                   OR current_win_streak > 0 
                   OR current_podium_streak > 0
                ORDER BY current_points_streak DESC
            """)
            return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# MAIN WIDGET
# ============================================================================

class FTBDBExplorerWidget:
    """Main DB Explorer widget."""
    
    def __init__(self, parent, db_path: str):
        self.parent = parent
        self.db_path = db_path
        self.query_helper = HistoricalDataQuery(db_path)
        
        self.frame = None
        self.notebook = None
        
        self._build_ui()
    
    def _build_ui(self):
        """Build the main UI structure."""
        if HAS_CTK:
            self.frame = ctk.CTkFrame(self.parent)
        else:
            self.frame = ttk.Frame(self.parent)
        
        self.frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        title_label = tk.Label(
            self.frame,
            text="📊 FTB Historical Data Explorer",
            font=("Arial", 16, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Add tabs
        self._build_teams_tab()
        self._build_drivers_tab()
        self._build_league_tab()
        self._build_analytics_tab()
        self._build_query_tab()
        self._build_archival_tab()
    
    def _build_teams_tab(self):
        """Build the teams historical dashboard tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Teams")
        
        # Team selector
        selector_frame = ttk.Frame(tab)
        selector_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(selector_frame, text="Select Team:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.team_selector = ttk.Combobox(selector_frame, state="readonly")
        self.team_selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.team_selector.bind("<<ComboboxSelected>>", self._on_team_selected)
        
        # Load teams
        teams = self.query_helper.get_all_teams()
        self.team_selector['values'] = teams
        
        # Details frame
        self.team_details_frame = ttk.Frame(tab)
        self.team_details_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._show_team_placeholder()
    
    def _build_drivers_tab(self):
        """Build the drivers archives tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Drivers")
        
        # Driver selector
        selector_frame = ttk.Frame(tab)
        selector_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(selector_frame, text="Select Driver:").pack(side=tk.LEFT, padx=(0, 10))
        
        self.driver_selector = ttk.Combobox(selector_frame, state="readonly")
        self.driver_selector.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.driver_selector.bind("<<ComboboxSelected>>", self._on_driver_selected)
        
        # Load drivers
        drivers = self.query_helper.get_all_drivers()
        self.driver_selector['values'] = drivers
        
        # Details frame
        self.driver_details_frame = ttk.Frame(tab)
        self.driver_details_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._show_driver_placeholder()
    
    def _build_league_tab(self):
        """Build the league history browser tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="League")
        
        # Championship history
        ttk.Label(tab, text="Championship History", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Table
        columns = ("Season", "Champion", "Points", "Runner-Up", "Margin", "Decided Round")
        tree = ttk.Treeview(tab, columns=columns, show="headings", height=15)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=100, anchor=tk.CENTER)
        
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Load championship history
        history = self.query_helper.get_championship_history(limit=20)
        for record in history:
            tree.insert("", tk.END, values=(
                record['season'],
                record['champion_team'],
                f"{record['champion_points']:.1f}",
                record['runner_up_team'],
                f"{record['title_margin']:.1f}",
                record['title_decided_round'] or "Final"
            ))
    
    def _build_analytics_tab(self):
        """Build the analytics dashboard tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Analytics")
        
        ttk.Label(tab, text="🔥 Active Streaks", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Streaks table
        columns = ("Team", "Points Streak", "Win Streak", "Podium Streak", "Record Points")
        tree = ttk.Treeview(tab, columns=columns, show="headings", height=12)
        
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120, anchor=tk.CENTER)
        
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Load streaks
        streaks = self.query_helper.get_active_streaks_all()
        for streak in streaks:
            approaching_record = ""
            if streak['current_points_streak'] >= streak['longest_points_streak_ever'] * 0.8:
                approaching_record = " 🔥"
            
            tree.insert("", tk.END, values=(
                streak['team_name'] + approaching_record,
                streak['current_points_streak'],
                streak['current_win_streak'],
                streak['current_podium_streak'],
                streak['longest_points_streak_ever']
            ))
    
    def _build_query_tab(self):
        """Build the custom query console tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="Query Console")
        
        ttk.Label(tab, text="SQL Query Console", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Query input
        query_frame = ttk.Frame(tab)
        query_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Label(query_frame, text="Query:").pack(anchor=tk.W)
        
        self.query_text = tk.Text(query_frame, height=6, wrap=tk.WORD)
        self.query_text.pack(fill=tk.X, pady=5)
        
        # Example query
        self.query_text.insert("1.0", "SELECT team_name, wins_total, championships_won\nFROM team_career_totals\nORDER BY wins_total DESC\nLIMIT 10;")
        
        # Execute button
        ttk.Button(query_frame, text="Execute Query", command=self._execute_query).pack(pady=5)
        
        # Results
        ttk.Label(tab, text="Results:", font=("Arial", 12, "bold")).pack(padx=10, anchor=tk.W)
        
        self.query_results_text = tk.Text(tab, height=15, wrap=tk.NONE)
        self.query_results_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbars
        scrollbar_y = ttk.Scrollbar(self.query_results_text, orient=tk.VERTICAL, command=self.query_results_text.yview)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.query_results_text.config(yscrollcommand=scrollbar_y.set)
    
    def _build_archival_tab(self):
        """Build the database archival management tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="⚙️ Archival")
        
        ttk.Label(tab, text="Database Archival Management", font=("Arial", 14, "bold")).pack(pady=10)
        
        if not ftb_db_archival:
            ttk.Label(tab, text="Archival module not available", foreground="red").pack(pady=10)
            return
        
        # Info section
        info_frame = ttk.LabelFrame(tab, text="Database Information", padding=10)
        info_frame.pack(fill=tk.X, padx=10, pady=10)
        
        self.archival_info_text = tk.Text(info_frame, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.archival_info_text.pack(fill=tk.BOTH, expand=True)
        
        # Control buttons
        button_frame = ttk.Frame(tab)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        ttk.Button(
            button_frame, 
            text="🔄 Refresh Stats", 
            command=self._refresh_archival_stats
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, 
            text="📦 Archive Old Data", 
            command=self._run_archival
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            button_frame, 
            text="🔍 View Cold DB", 
            command=self._view_cold_db_stats
        ).pack(side=tk.LEFT, padx=5)
        
        # Archival log
        log_frame = ttk.LabelFrame(tab, text="Archival Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.archival_log_text = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.archival_log_text.pack(fill=tk.BOTH, expand=True)
        
        # Initial stats load
        self._refresh_archival_stats()
    
    def _show_team_placeholder(self):
        """Show placeholder when no team selected."""
        for widget in self.team_details_frame.winfo_children():
            widget.destroy()
        
        label = ttk.Label(
            self.team_details_frame,
            text="Select a team to view historical data",
            font=("Arial", 12)
        )
        label.pack(expand=True)
    
    def _show_driver_placeholder(self):
        """Show placeholder when no driver selected."""
        for widget in self.driver_details_frame.winfo_children():
            widget.destroy()
        
        label = ttk.Label(
            self.driver_details_frame,
            text="Select a driver to view career archives",
            font=("Arial", 12)
        )
        label.pack(expand=True)
    
    def _on_team_selected(self, event):
        """Handle team selection."""
        team_name = self.team_selector.get()
        if not team_name:
            return
        
        summary = self.query_helper.get_team_summary(team_name)
        if not summary:
            messagebox.showwarning("No Data", f"No historical data found for {team_name}")
            return
        
        self._display_team_summary(summary)
    
    def _on_driver_selected(self, event):
        """Handle driver selection."""
        driver_name = self.driver_selector.get()
        if not driver_name:
            return
        
        summary = self.query_helper.get_driver_summary(driver_name)
        if not summary:
            messagebox.showwarning("No Data", f"No historical data found for {driver_name}")
            return
        
        self._display_driver_summary(summary)
    
    def _display_team_summary(self, summary: TeamHistoricalSummary):
        """Display comprehensive team summary."""
        for widget in self.team_details_frame.winfo_children():
            widget.destroy()
        
        # Scrollable frame
        canvas = tk.Canvas(self.team_details_frame)
        scrollbar = ttk.Scrollbar(self.team_details_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Career Overview
        career_frame = ttk.LabelFrame(scrollable_frame, text="Career Overview", padding=10)
        career_frame.pack(fill=tk.X, padx=10, pady=5)
        
        career_text = f"""
Seasons: {summary.seasons_entered} | Races: {summary.races_entered}
Wins: {summary.wins_total} | Podiums: {summary.podiums_total} | Championships: {summary.championships_won}
Win Rate: {summary.win_rate:.1f}% | Prestige Index: {summary.prestige_index:.1f}/100
        """.strip()
        
        ttk.Label(career_frame, text=career_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Current State
        state_frame = ttk.LabelFrame(scrollable_frame, text="Current State", padding=10)
        state_frame.pack(fill=tk.X, padx=10, pady=5)
        
        state_text = f"""
Team Pulse: {summary.team_pulse:.1f}/100
Competitive Tier: {summary.competitive_tier.replace('_', ' ').title()}
Narrative Temperature: {summary.narrative_temperature.title()}
        """.strip()
        
        ttk.Label(state_frame, text=state_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Active Streaks
        streak_frame = ttk.LabelFrame(scrollable_frame, text="Active Streaks", padding=10)
        streak_frame.pack(fill=tk.X, padx=10, pady=5)
        
        streak_text = f"""
Current Points Streak: {summary.current_points_streak} races
Current Win Streak: {summary.current_win_streak} races
Record Points Streak: {summary.longest_points_streak_ever} races
        """.strip()
        
        if summary.current_points_streak >= summary.longest_points_streak_ever * 0.8:
            streak_text += "\n\n🔥 APPROACHING ALL-TIME RECORD!"
        
        ttk.Label(streak_frame, text=streak_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Peak Performance
        if summary.best_season_finish:
            peak_frame = ttk.LabelFrame(scrollable_frame, text="Peak Performance", padding=10)
            peak_frame.pack(fill=tk.X, padx=10, pady=5)
            
            peak_text = f"Best Season Finish: P{summary.best_season_finish} (Season {summary.best_season_finish_year})"
            
            if summary.golden_era_start:
                peak_text += f"\nGolden Era: Seasons {summary.golden_era_start}-{summary.golden_era_end}"
            
            ttk.Label(peak_frame, text=peak_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _display_driver_summary(self, summary: DriverHistoricalSummary):
        """Display comprehensive driver summary."""
        for widget in self.driver_details_frame.winfo_children():
            widget.destroy()
        
        # Career Overview
        career_frame = ttk.LabelFrame(self.driver_details_frame, text="Career Overview", padding=10)
        career_frame.pack(fill=tk.X, padx=10, pady=5)
        
        career_text = f"""
Age: {summary.age} | Current Team: {summary.current_team or 'Free Agent'}
Starts: {summary.career_starts} | Wins: {summary.career_wins} | Podiums: {summary.career_podiums}
Championships: {summary.championships_won} | Win Rate: {summary.win_rate_career:.1f}%
        """.strip()
        
        ttk.Label(career_frame, text=career_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Legacy
        legacy_frame = ttk.LabelFrame(self.driver_details_frame, text="Legacy", padding=10)
        legacy_frame.pack(fill=tk.X, padx=10, pady=5)
        
        legacy_text = f"""
Legacy Score: {summary.legacy_score:.1f}/100
Legacy Tier: {summary.legacy_tier.title()}
        """.strip()
        
        ttk.Label(legacy_frame, text=legacy_text, justify=tk.LEFT).pack(anchor=tk.W)
        
        # Peak Performance
        if summary.peak_rating > 0:
            peak_frame = ttk.LabelFrame(self.driver_details_frame, text="Peak Performance", padding=10)
            peak_frame.pack(fill=tk.X, padx=10, pady=5)
            
            peak_text = f"""
Peak Rating: {summary.peak_rating:.1f} (Age {summary.peak_rating_age or 'N/A'})
Mettle Under Pressure: {summary.mettle_under_pressure_index:.1f}/100
            """.strip()
            
            ttk.Label(peak_frame, text=peak_text, justify=tk.LEFT).pack(anchor=tk.W)
    
    def _execute_query(self):
        """Execute custom SQL query."""
        query = self.query_text.get("1.0", tk.END).strip()
        
        if not query:
            messagebox.showwarning("Empty Query", "Please enter a SQL query")
            return
        
        try:
            with self.query_helper._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                results = cursor.fetchall()
                
                # Clear previous results
                self.query_results_text.delete("1.0", tk.END)
                
                if not results:
                    self.query_results_text.insert("1.0", "No results found.")
                    return
                
                # Format results
                if results:
                    # Column headers
                    headers = [desc[0] for desc in cursor.description]
                    header_line = " | ".join(headers)
                    self.query_results_text.insert(tk.END, header_line + "\n")
                    self.query_results_text.insert(tk.END, "-" * len(header_line) + "\n")
                    
                    # Rows
                    for row in results:
                        row_line = " | ".join(str(val) for val in row)
                        self.query_results_text.insert(tk.END, row_line + "\n")
                    
                    self.query_results_text.insert(tk.END, f"\n{len(results)} rows returned.")
        
        except Exception as e:
            messagebox.showerror("Query Error", f"Error executing query:\n{str(e)}")
    
    def _refresh_archival_stats(self):
        """Refresh archival statistics display."""
        if not ftb_db_archival:
            return
        
        try:
            stats = ftb_db_archival.get_archival_stats(self.db_path)
            
            # Update info text
            self.archival_info_text.config(state=tk.NORMAL)
            self.archival_info_text.delete("1.0", tk.END)
            
            info_text = f"""
=== Hot Database ===
Path: {stats['hot_db']['path']}
Size: {stats['hot_db']['size_mb']:.2f} MB
Current Season: {stats['current_season']}

Key Tables (Hot DB):
  • race_results_archive: {stats['hot_db']['table_counts'].get('race_results_archive', 0):,} rows
  • financial_transactions: {stats['hot_db']['table_counts'].get('financial_transactions', 0):,} rows
  • decision_history: {stats['hot_db']['table_counts'].get('decision_history', 0):,} rows
  • events_buffer: {stats['hot_db']['table_counts'].get('events_buffer', 0):,} rows

Policy: Keeping last {ftb_db_archival.ARCHIVAL_POLICY['hot_seasons_count']} seasons in hot DB
Archive threshold: {ftb_db_archival.ARCHIVAL_POLICY['archive_threshold_mb']} MB

"""
            
            if stats['cold_db']['exists']:
                info_text += f"""
=== Cold Database (Archive) ===
Path: {stats['cold_db']['path']}
Size: {stats['cold_db']['size_mb']:.2f} MB

Archived Tables:
  • race_results_archive: {stats['cold_db']['table_counts'].get('race_results_archive', 0):,} rows
  • financial_transactions: {stats['cold_db']['table_counts'].get('financial_transactions', 0):,} rows
  • decision_history: {stats['cold_db']['table_counts'].get('decision_history', 0):,} rows
"""
            else:
                info_text += "\n=== Cold Database ===\nNo archive database yet.\n"
            
            if stats['archival_recommended']:
                info_text += f"\n⚠️  ARCHIVAL RECOMMENDED - Hot DB exceeds {ftb_db_archival.ARCHIVAL_POLICY['archive_threshold_mb']} MB threshold\n"
            
            self.archival_info_text.insert("1.0", info_text.strip())
            self.archival_info_text.config(state=tk.DISABLED)
            
            # Log the refresh
            self._log_archival(f"Statistics refreshed at {time.strftime('%H:%M:%S')}")
        
        except Exception as e:
            messagebox.showerror("Stats Error", f"Error loading archival stats:\n{str(e)}")
    
    def _run_archival(self):
        """Run database archival process."""
        if not ftb_db_archival:
            return
        
        # Confirm with user
        if not messagebox.askyesno(
            "Archive Database",
            "This will move old data from the hot database to a cold archive.\n\n"
            f"Old data (seasons older than {ftb_db_archival.ARCHIVAL_POLICY['hot_seasons_count']} ago) will be archived.\n"
            "Career totals and aggregates will remain in hot DB.\n\n"
            "Continue?"
        ):
            return
        
        try:
            self._log_archival("Starting archival process...")
            
            # Run archival
            stats = ftb_db_archival.archive_old_data(self.db_path, verbose=False)
            
            # Log results
            total_archived = sum(stats['archived_rows'].values())
            self._log_archival(f"✓ Archived {total_archived} total rows")
            
            for table, count in stats['archived_rows'].items():
                self._log_archival(f"  • {table}: {count} rows")
            
            if stats['errors']:
                self._log_archival(f"⚠️  {len(stats['errors'])} errors occurred")
                for error in stats['errors']:
                    self._log_archival(f"  • {error}")
            
            self._log_archival(f"Completed in {stats['duration_seconds']:.2f}s")
            
            # Refresh stats
            self._refresh_archival_stats()
            
            messagebox.showinfo(
                "Archival Complete",
                f"Successfully archived {total_archived} rows.\n"
                f"Time: {stats['duration_seconds']:.2f}s"
            )
        
        except Exception as e:
            error_msg = f"Error during archival: {str(e)}"
            self._log_archival(f"❌ {error_msg}")
            messagebox.showerror("Archival Error", error_msg)
    
    def _view_cold_db_stats(self):
        """Show detailed cold database statistics."""
        if not ftb_db_archival:
            return
        
        try:
            stats = ftb_db_archival.get_archival_stats(self.db_path)
            
            if not stats['cold_db']['exists']:
                messagebox.showinfo("No Archive", "No cold database archive exists yet.")
                return
            
            # Build detailed stats message
            msg = f"Cold Database Archive\n\n"
            msg += f"Path: {stats['cold_db']['path']}\n"
            msg += f"Size: {stats['cold_db']['size_mb']:.2f} MB\n\n"
            msg += "Table Contents:\n"
            
            for table, count in sorted(stats['cold_db']['table_counts'].items()):
                if count > 0:
                    msg += f"  • {table}: {count:,} rows\n"
            
            messagebox.showinfo("Cold DB Stats", msg)
        
        except Exception as e:
            messagebox.showerror("Stats Error", f"Error viewing cold DB stats:\n{str(e)}")
    
    def _log_archival(self, message: str):
        """Add message to archival log."""
        import time
        
        self.archival_log_text.config(state=tk.NORMAL)
        timestamp = time.strftime("%H:%M:%S")
        self.archival_log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.archival_log_text.see(tk.END)
        self.archival_log_text.config(state=tk.DISABLED)


# ============================================================================
# WIDGET REGISTRATION
# ============================================================================

def register_widgets(registry, runtime_stub):
    """Register DB Explorer widget with Radio OS."""
    
    def create_widget(parent, **kwargs):
        db_path = kwargs.get('db_path')
        if not db_path:
            # Try to get from runtime
            if hasattr(runtime_stub, 'get_state_db_path'):
                db_path = runtime_stub.get_state_db_path()
        
        if not db_path:
            print("[FTB DB Explorer] Error: No database path provided")
            return None
        
        widget = FTBDBExplorerWidget(parent, db_path)
        return widget.frame
    
    registry['ftb_db_explorer'] = {
        'constructor': create_widget,
        'name': PLUGIN_NAME,
        'description': PLUGIN_DESC,
        'category': 'ftb'
    }
    
    print(f"[FTB DB Explorer] Registered widget: {PLUGIN_NAME}")
