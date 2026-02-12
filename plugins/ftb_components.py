"""
FTB Game - CustomTkinter Component Library

Reusable styled components for the From the Backmarker racing management game.
Provides consistent theming and behavior across all UI elements.
"""

import customtkinter as ctk
import tkinter as tk
from typing import Callable, Dict, List, Any, Optional, Tuple
from tkinter import messagebox
import math
from PIL import Image


# ============================================================
# THEME & STYLING
# ============================================================

class FTBTheme:
    """Color theme for FTB UI - Racing-inspired vibrant design"""
    
    # Base colors - Deep midnight blue inspired by race tracks at night
    BG = "#0a0e1a"
    PANEL = "#131720"
    CARD = "#1a1f2e"
    CARD_HOVER = "#242b3d"
    SURFACE = "#0d1117"
    
    # Border and outline colors for definition
    BORDER = "#2a3441"
    BORDER_ACCENT = "#00d9ff"
    
    # Text colors - High contrast for readability
    TEXT = "#f0f3f7"
    TEXT_MUTED = "#a8b5c7"
    TEXT_DIM = "#6b7a90"
    
    # Accent colors - Vibrant racing palette
    ACCENT = "#00d9ff"         # Electric cyan (like LED racing lights)
    ACCENT_HOVER = "#00b8e6"   # Darker cyan for hover
    DANGER = "#ff2e63"         # Vibrant red (danger/warning lights)
    DANGER_HOVER = "#e6194d"   # Darker red for hover
    WARNING = "#ffb800"        # Golden yellow (caution flag)
    WARNING_HOVER = "#e6a300"  # Darker yellow for hover
    WARNING_BG = "#2a2315"     # Dark warning background
    SUCCESS = "#00ff88"        # Neon green (success/go signal)
    SUCCESS_HOVER = "#00e673"  # Darker green for hover
    INFO = "#00d9ff"           # Electric cyan
    
    # Semantic colors - Enhanced vibrancy
    POSITIVE = "#00ff88"       # Bright green
    NEGATIVE = "#ff2e63"       # Vivid red
    NEUTRAL = "#7c8ba6"        # Soft blue-gray
    
    # Stat ratings - Racing performance colors
    STAT_EXCELLENT = "#00ff88" # Neon green (pole position)
    STAT_GOOD = "#00d9ff"      # Electric cyan (podium)
    STAT_AVERAGE = "#ffb800"   # Golden yellow (midfield)
    STAT_POOR = "#ff2e63"      # Vivid red (back of grid)
    STAT_HIGH = "#00ff88"      # Alias for positive values
    STAT_LOW = "#ff2e63"       # Alias for negative values
    
    # Button hover colors - Pre-defined for consistency
    BUTTON_PRIMARY_HOVER = "#00b8e6"
    BUTTON_SECONDARY_HOVER = "#1e2533"
    BUTTON_DANGER_HOVER = "#e6194d"
    BUTTON_SUCCESS_HOVER = "#00e673"
    
    @staticmethod
    def get_stat_color(value: float, max_value: float = 100.0) -> str:
        """Get color for stat value"""
        value_num = _safe_float(value, 0.0)
        max_value_num = _safe_float(max_value, 100.0)
        if max_value_num <= 0:
            max_value_num = 100.0
        percentage = (value_num / max_value_num) * 100
        if percentage >= 75:
            return FTBTheme.STAT_EXCELLENT
        elif percentage >= 60:
            return FTBTheme.STAT_GOOD
        elif percentage >= 40:
            return FTBTheme.STAT_AVERAGE
        else:
            return FTBTheme.STAT_POOR
    
    @staticmethod
    def get_severity_color(severity: str) -> str:
        """Get color for event severity"""
        severity_map = {
            "info": FTBTheme.INFO,
            "success": FTBTheme.SUCCESS,
            "warning": FTBTheme.WARNING,
            "danger": FTBTheme.DANGER,
            "error": FTBTheme.DANGER,
            "major": FTBTheme.ACCENT,
        }
        return severity_map.get(severity.lower(), FTBTheme.TEXT)


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def format_currency(amount: float) -> str:
    """Format number as currency"""
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    else:
        return f"${amount:.0f}"


def format_percentage(value: float) -> str:
    """Format as percentage"""
    return f"{value:.1f}%"


def format_trend(current: float, previous: float) -> Tuple[str, str]:
    """Return trend indicator and color"""
    if current > previous + 0.5:
        return "↑", FTBTheme.POSITIVE
    elif current < previous - 0.5:
        return "↓", FTBTheme.NEGATIVE
    else:
        return "→", FTBTheme.NEUTRAL


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce a value to float with a safe fallback."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "rating", "score"):
            if key in value:
                try:
                    return float(value[key])
                except (TypeError, ValueError):
                    break
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def format_stat_comparison(value: float, good_above: float = 50.0) -> str:
    """Format stat with +/- relative to baseline"""
    diff = value - good_above
    if abs(diff) < 1.0:
        return "~"
    elif diff > 0:
        return f"+{diff:.0f}"
    else:
        return f"{diff:.0f}"


# ============================================================
# BASE COMPONENTS
# ============================================================

class StatBar(ctk.CTkFrame):
    """Labeled horizontal progress bar for displaying stats"""
    
    def __init__(self, parent, label: str, value: float, max_value: float = 100.0, 
                 show_value: bool = True, **kwargs):
        super().__init__(parent, fg_color=FTBTheme.CARD, **kwargs)
        
        self.max_value = _safe_float(max_value, 100.0)
        if self.max_value <= 0:
            self.max_value = 100.0
        value_num = _safe_float(value, 0.0)
        
        # Label
        self.label = ctk.CTkLabel(
            self, 
            text=label,
            text_color=FTBTheme.TEXT,
            anchor="w",
            width=150
        )
        self.label.pack(side="left", padx=(10, 5), pady=5)
        
        # Progress bar
        color = FTBTheme.get_stat_color(value_num, self.max_value)
        self.bar = ctk.CTkProgressBar(
            self,
            width=200,
            progress_color=color,
            fg_color=FTBTheme.SURFACE
        )
        self.bar.set(value_num / self.max_value)
        self.bar.pack(side="left", padx=5, pady=5, expand=True, fill="x")
        
        # Value label
        if show_value:
            self.value_label = ctk.CTkLabel(
                self,
                text=f"{value_num:.0f}",
                text_color=color,
                width=40
            )
            self.value_label.pack(side="left", padx=(5, 10), pady=5)
    
    def update_value(self, value: float):
        """Update bar value and color"""
        value_num = _safe_float(value, 0.0)
        self.bar.set(value_num / self.max_value)
        color = FTBTheme.get_stat_color(value_num, self.max_value)
        self.bar.configure(progress_color=color)
        if hasattr(self, 'value_label'):
            self.value_label.configure(text=f"{value_num:.0f}", text_color=color)


class EntityCard(ctk.CTkFrame):
    """Clickable card displaying entity summary"""
    
    def __init__(self, parent, entity: Any, on_click: Optional[Callable] = None, image_pil: Optional[Image.Image] = None, **kwargs):
        super().__init__(parent, fg_color=FTBTheme.CARD, corner_radius=8, **kwargs)
        
        self.entity = entity
        self.on_click = on_click
        
        # Make clickable
        if on_click:
            self.bind("<Button-1>", lambda e: on_click(entity))
            self.configure(cursor="hand2")
        
        # Create horizontal layout container
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Add sprite image if provided
        if image_pil:
            try:
                ctk_image = ctk.CTkImage(light_image=image_pil, dark_image=image_pil, size=(32, 32))
                image_label = ctk.CTkLabel(
                    content_frame,
                    image=ctk_image,
                    text=""
                )
                image_label.pack(side=tk.LEFT, padx=(0, 10))
                
                # Make image clickable too
                if on_click:
                    image_label.bind("<Button-1>", lambda e: on_click(entity))
                    image_label.configure(cursor="hand2")
            except Exception as e:
                print(f"[FTB] Error displaying sprite in EntityCard: {e}")
        
        # Text content container
        text_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Entity name
        name_label = ctk.CTkLabel(
            text_frame,
            text=entity.name,
            text_color=FTBTheme.TEXT,
            font=("Arial", 14, "bold"),
            anchor="w"
        )
        name_label.pack(pady=(0, 2), anchor="w")
        
        # Entity type and age
        entity_type = type(entity).__name__
        info_text = f"{entity_type}"
        if hasattr(entity, 'age'):
            info_text += f" • Age {entity.age}"
        
        info_label = ctk.CTkLabel(
            text_frame,
            text=info_text,
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11),
            anchor="w"
        )
        info_label.pack(pady=(0, 5), anchor="w")
        
        # Overall rating
        if hasattr(entity, 'overall_rating'):
            rating = entity.overall_rating
            rating_color = FTBTheme.get_stat_color(rating)
            rating_label = ctk.CTkLabel(
                text_frame,
                text=f"Overall: {rating:.0f}/100",
                text_color=rating_color,
                font=("Arial", 12, "bold")
            )
            rating_label.pack(pady=(0, 0), anchor="w")
        
        # Hover effect
        if on_click:
            self.bind("<Enter>", lambda e: self.configure(fg_color=FTBTheme.CARD_HOVER))
            self.bind("<Leave>", lambda e: self.configure(fg_color=FTBTheme.CARD))


class StatsTable(ctk.CTkFrame):
    """Styled data table"""
    
    def __init__(self, parent, headers: List[str], rows: List[List[str]], **kwargs):
        super().__init__(parent, fg_color=FTBTheme.PANEL, **kwargs)
        
        # Header row
        header_frame = ctk.CTkFrame(self, fg_color=FTBTheme.SURFACE)
        header_frame.pack(fill="x", padx=2, pady=2)
        
        for header in headers:
            label = ctk.CTkLabel(
                header_frame,
                text=header,
                text_color=FTBTheme.TEXT,
                font=("Arial", 11, "bold"),
                width=100
            )
            label.pack(side="left", padx=5, pady=5, expand=True)
        
        # Data rows
        for row in rows:
            row_frame = ctk.CTkFrame(self, fg_color=FTBTheme.CARD)
            row_frame.pack(fill="x", padx=2, pady=1)
            
            for cell in row:
                label = ctk.CTkLabel(
                    row_frame,
                    text=str(cell),
                    text_color=FTBTheme.TEXT,
                    font=("Arial", 11),
                    width=100
                )
                label.pack(side="left", padx=5, pady=5, expand=True)


class MetricDisplay(ctk.CTkFrame):
    """Large metric display with label"""
    
    def __init__(self, parent, label: str, value: str, color: str = FTBTheme.TEXT, 
                 sublabel: str = "", **kwargs):
        super().__init__(parent, fg_color=FTBTheme.CARD, corner_radius=8, **kwargs)
        
        # Main label
        self.label_widget = ctk.CTkLabel(
            self,
            text=label,
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11)
        )
        self.label_widget.pack(padx=15, pady=(15, 2))
        
        # Value
        self.value_widget = ctk.CTkLabel(
            self,
            text=value,
            text_color=color,
            font=("Arial", 24, "bold")
        )
        self.value_widget.pack(padx=15, pady=(0, 2))
        
        # Sublabel
        if sublabel:
            self.sublabel_widget = ctk.CTkLabel(
                self,
                text=sublabel,
                text_color=FTBTheme.TEXT_DIM,
                font=("Arial", 10)
            )
            self.sublabel_widget.pack(padx=15, pady=(0, 15))
    
    def update(self, value: str, color: str = FTBTheme.TEXT, sublabel: str = ""):
        """Update display value"""
        self.value_widget.configure(text=value, text_color=color)
        if sublabel and hasattr(self, 'sublabel_widget'):
            self.sublabel_widget.configure(text=sublabel)


# ============================================================
# DIALOG COMPONENTS
# ============================================================

class DecisionModal(ctk.CTkToplevel):
    """Modal dialog for multi-option decisions"""
    
    def __init__(self, parent, decision_event: Any, on_resolve: Callable):
        super().__init__(parent)
        
        self.decision_event = decision_event
        self.on_resolve = on_resolve
        self.selected_option_id = None
        
        # Window config
        self.title("Decision Required")
        self.geometry("600x500")
        self.configure(fg_color=FTBTheme.BG)
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (600 // 2)
        y = (self.winfo_screenheight() // 2) - (500 // 2)
        self.geometry(f"600x500+{x}+{y}")
        
        # Build UI
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkLabel(
            self,
            text="⚠️ Decision Required",
            text_color=FTBTheme.WARNING,
            font=("Arial", 18, "bold")
        )
        header.pack(padx=20, pady=(20, 10))
        
        # Prompt
        prompt_frame = ctk.CTkFrame(self, fg_color=FTBTheme.CARD, corner_radius=8)
        prompt_frame.pack(padx=20, pady=10, fill="x")
        
        prompt_label = ctk.CTkLabel(
            prompt_frame,
            text=self.decision_event.prompt,
            text_color=FTBTheme.TEXT,
            font=("Arial", 13),
            wraplength=540,
            justify="left"
        )
        prompt_label.pack(padx=15, pady=15)
        
        # Options
        options_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=FTBTheme.PANEL,
            corner_radius=8
        )
        options_frame.pack(padx=20, pady=10, fill="both", expand=True)
        
        self.option_buttons = []
        for option in self.decision_event.options:
            self._create_option_card(options_frame, option)
        
        # Deadline warning
        if hasattr(self.decision_event, 'deadline_tick'):
            warning = ctk.CTkLabel(
                self,
                text=f"⏰ Auto-resolves at tick {self.decision_event.deadline_tick}",
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 10, "italic")
            )
            warning.pack(padx=20, pady=(0, 10))
        
        # Action buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=(0, 20), fill="x")
        
        confirm_btn = ctk.CTkButton(
            button_frame,
            text="Confirm",
            command=self._confirm,
            fg_color=FTBTheme.ACCENT,
            hover_color=FTBTheme.ACCENT_HOVER,
            height=40,
            font=("Arial", 13, "bold")
        )
        confirm_btn.pack(side="right", padx=(10, 0))
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text="Cancel",
            command=self.destroy,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.BUTTON_SECONDARY_HOVER,
            height=40,
            font=("Arial", 13)
        )
        cancel_btn.pack(side="right")
    
    def _create_option_card(self, parent, option):
        card = ctk.CTkFrame(parent, fg_color=FTBTheme.CARD, corner_radius=8)
        card.pack(padx=10, pady=5, fill="x")
        
        # Radio button
        radio = ctk.CTkRadioButton(
            card,
            text="",
            variable=None,
            value=option.id,
            command=lambda: self._select_option(option.id),
            fg_color=FTBTheme.ACCENT,
            hover_color=FTBTheme.CARD_HOVER
        )
        radio.pack(side="left", padx=10, pady=10)
        
        # Option details
        details_frame = ctk.CTkFrame(card, fg_color="transparent")
        details_frame.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
        
        # Label
        label_text = option.label
        if option.cost > 0:
            label_text += f" ({format_currency(option.cost)})"
        
        label = ctk.CTkLabel(
            details_frame,
            text=label_text,
            text_color=FTBTheme.TEXT,
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        label.pack(anchor="w")
        
        # Description
        if option.description:
            desc = ctk.CTkLabel(
                details_frame,
                text=option.description,
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 10),
                anchor="w",
                wraplength=450,
                justify="left"
            )
            desc.pack(anchor="w", pady=(2, 0))
        
        # Consequence preview
        if option.consequence_preview:
            consequence = ctk.CTkLabel(
                details_frame,
                text=f"→ {option.consequence_preview}",
                text_color=FTBTheme.TEXT_DIM,
                font=("Arial", 10, "italic"),
                anchor="w",
                wraplength=450,
                justify="left"
            )
            consequence.pack(anchor="w", pady=(2, 0))
        
        # Make entire card clickable
        card.bind("<Button-1>", lambda e: self._select_option(option.id))
        radio.bind("<Button-1>", lambda e: self._select_option(option.id))
        
        self.option_buttons.append((option.id, radio, card))
    
    def _select_option(self, option_id: str):
        self.selected_option_id = option_id
        # Update visual state
        for opt_id, radio, card in self.option_buttons:
            if opt_id == option_id:
                radio.select()
                card.configure(fg_color=FTBTheme.CARD_HOVER)
            else:
                radio.deselect()
                card.configure(fg_color=FTBTheme.CARD)
    
    def _confirm(self):
        if self.selected_option_id:
            self.on_resolve(self.decision_event, self.selected_option_id)
            self.destroy()
        else:
            messagebox.showwarning("No Selection", "Please select an option before confirming.")


class ConfirmDialog(ctk.CTkToplevel):
    """Simple confirmation dialog"""
    
    def __init__(self, parent, title: str, message: str, on_confirm: Callable, 
                 confirm_text: str = "Confirm", cancel_text: str = "Cancel"):
        super().__init__(parent)
        
        self.on_confirm = on_confirm
        self.confirmed = False
        
        # Window config
        self.title(title)
        self.geometry("400x200")
        self.configure(fg_color=FTBTheme.BG)
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.winfo_screenheight() // 2) - (200 // 2)
        self.geometry(f"400x200+{x}+{y}")
        
        # Message
        msg_label = ctk.CTkLabel(
            self,
            text=message,
            text_color=FTBTheme.TEXT,
            font=("Arial", 13),
            wraplength=360,
            justify="center"
        )
        msg_label.pack(padx=20, pady=40, expand=True)
        
        # Buttons
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(padx=20, pady=(0, 20), fill="x")
        
        confirm_btn = ctk.CTkButton(
            button_frame,
            text=confirm_text,
            command=self._confirm,
            fg_color=FTBTheme.DANGER,
            hover_color=FTBTheme.DANGER_HOVER,
            height=40,
            font=("Arial", 12, "bold"),
            width=120
        )
        confirm_btn.pack(side="right", padx=(10, 0))
        
        cancel_btn = ctk.CTkButton(
            button_frame,
            text=cancel_text,
            command=self.destroy,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            font=("Arial", 12),
            width=120
        )
        cancel_btn.pack(side="right")
    
    def _confirm(self):
        self.confirmed = True
        self.on_confirm()
        self.destroy()


# ============================================================
# COMPLEX WIZARDS
# ============================================================

class DevelopmentWizard(ctk.CTkToplevel):
    """Multi-step wizard for starting development projects"""
    
    def __init__(self, parent, available_engineers: List[Any], team_budget: float, on_submit: Callable):
        super().__init__(parent)
        
        self.available_engineers = available_engineers
        self.team_budget = team_budget
        self.on_submit = on_submit
        
        self.current_step = 1
        self.total_steps = 4
        
        # Data collection
        self.selected_subsystem = None
        self.subsystem_var = ctk.StringVar(value="")  # Radio button group variable
        self.risk_level = 0.5  # 0.0 = conservative, 1.0 = aggressive
        self.assigned_engineers = []
        self.budget_allocation = 0.0
        self.priority = "normal"
        
        # Window config
        self.title("New Development Project")
        self.geometry("700x750")
        self.configure(fg_color=FTBTheme.BG)
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (700 // 2)
        y = (self.winfo_screenheight() // 2) - (750 // 2)
        self.geometry(f"700x750+{x}+{y}")
        
        # Build UI
        self._build_ui()
    
    def _build_ui(self):
        # Header with step indicator
        self.header_frame = ctk.CTkFrame(self, fg_color=FTBTheme.PANEL, corner_radius=0)
        self.header_frame.pack(fill="x")
        
        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text="New Development Project",
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        self.title_label.pack(padx=20, pady=(15, 5))
        
        self.step_label = ctk.CTkLabel(
            self.header_frame,
            text=f"Step 1 of {self.total_steps}",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11)
        )
        self.step_label.pack(padx=20, pady=(0, 15))
        
        # Content area (will be swapped based on step)
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Navigation buttons
        self.nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        self.next_btn = ctk.CTkButton(
            self.nav_frame,
            text="Next",
            command=self._next_step,
            fg_color=FTBTheme.ACCENT,
            hover_color=FTBTheme.ACCENT_HOVER,
            height=40,
            width=120,
            font=("Arial", 12, "bold")
        )
        self.next_btn.pack(side="right")
        
        self.back_btn = ctk.CTkButton(
            self.nav_frame,
            text="Back",
            command=self._previous_step,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            width=120,
            font=("Arial", 12)
        )
        self.back_btn.pack(side="right", padx=(0, 10))
        self.back_btn.configure(state="disabled")
        
        self.cancel_btn = ctk.CTkButton(
            self.nav_frame,
            text="Cancel",
            command=self.destroy,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            width=100,
            font=("Arial", 12)
        )
        self.cancel_btn.pack(side="left")
        
        # Show first step
        self._show_step_1()
    
    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def _show_step_1(self):
        """Step 1: Choose subsystem"""
        self._clear_content()
        self.step_label.configure(text=f"Step 1 of {self.total_steps}: Choose Subsystem")
        
        subsystems = [
            ("Aerodynamics", "Downforce, drag, aero efficiency"),
            ("Power Unit", "Power output, delivery smoothness"),
            ("Suspension", "Mechanical grip, platform stability"),
            ("Reliability", "Component wear, thermal tolerance"),
            ("Driveability", "Setup window, balance sensitivity"),
            ("Strategy Tools", "Tire modeling, race simulation")
        ]
        
        for subsystem, description in subsystems:
            card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
            card.pack(fill="x", pady=5)
            
            # Radio button with subsystem name
            radio = ctk.CTkRadioButton(
                card,
                text=subsystem,
                variable=self.subsystem_var,
                value=subsystem,
                fg_color=FTBTheme.ACCENT,
                text_color=FTBTheme.TEXT,
                font=("Arial", 13, "bold")
            )
            radio.pack(anchor="w", padx=15, pady=(15, 5))
            
            # Description label
            desc = ctk.CTkLabel(
                card,
                text=description,
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 10),
                anchor="w"
            )
            desc.pack(anchor="w", padx=40, pady=(0, 15))
    
    def _show_step_2(self):
        """Step 2: Set risk profile"""
        self._clear_content()
        self.step_label.configure(text=f"Step 2 of {self.total_steps}: Set Risk Profile")
        
        # Risk slider
        slider_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        slider_frame.pack(fill="x", pady=20, padx=20)
        
        slider_label = ctk.CTkLabel(
            slider_frame,
            text="Risk Level",
            text_color=FTBTheme.TEXT,
            font=("Arial", 14, "bold")
        )
        slider_label.pack(padx=20, pady=(20, 10))
        
        self.risk_slider = ctk.CTkSlider(
            slider_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=10,
            command=self._on_risk_change,
            fg_color=FTBTheme.SURFACE,
            progress_color=FTBTheme.ACCENT,
            button_color=FTBTheme.ACCENT,
            button_hover_color=FTBTheme.CARD_HOVER
        )
        self.risk_slider.set(self.risk_level)
        self.risk_slider.pack(padx=20, pady=10, fill="x")
        
        # Risk level indicators
        indicator_frame = ctk.CTkFrame(slider_frame, fg_color="transparent")
        indicator_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        conservative_label = ctk.CTkLabel(
            indicator_frame,
            text="Conservative\nSafer • Lower cost • Smaller gains",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 10),
            justify="left"
        )
        conservative_label.pack(side="left")
        
        aggressive_label = ctk.CTkLabel(
            indicator_frame,
            text="Aggressive\nRisky • Higher cost • Bigger swings",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 10),
            justify="right"
        )
        aggressive_label.pack(side="right")
        
        # Impact preview
        preview_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.PANEL, corner_radius=8)
        preview_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        self.cost_preview = ctk.CTkLabel(
            preview_frame,
            text="Estimated Cost: $80K - $120K",
            text_color=FTBTheme.TEXT,
            font=("Arial", 12)
        )
        self.cost_preview.pack(padx=20, pady=(20, 5))
        
        self.gain_preview = ctk.CTkLabel(
            preview_frame,
            text="Expected Gain: +2 to +4 in target stats",
            text_color=FTBTheme.TEXT,
            font=("Arial", 12)
        )
        self.gain_preview.pack(padx=20, pady=5)
        
        self.time_preview = ctk.CTkLabel(
            preview_frame,
            text="Development Time: 4-6 weeks",
            text_color=FTBTheme.TEXT,
            font=("Arial", 12)
        )
        self.time_preview.pack(padx=20, pady=(5, 20))
        
        self._on_risk_change(self.risk_level)
    
    def _on_risk_change(self, value):
        """Update preview based on risk level"""
        self.risk_level = float(value)
        
        # Calculate estimates based on risk
        base_cost = 80000
        cost_multiplier = 1.0 + (self.risk_level * 0.5)
        cost_min = base_cost * cost_multiplier * 0.9
        cost_max = base_cost * cost_multiplier * 1.2
        
        gain_min = 2 + int(self.risk_level * 2)
        gain_max = 4 + int(self.risk_level * 4)
        
        time_min = 6 - int(self.risk_level * 2)
        time_max = 8 - int(self.risk_level * 2)
        
        if hasattr(self, 'cost_preview'):
            self.cost_preview.configure(text=f"Estimated Cost: {format_currency(cost_min)} - {format_currency(cost_max)}")
            self.gain_preview.configure(text=f"Expected Gain: +{gain_min} to +{gain_max} in target stats")
            self.time_preview.configure(text=f"Development Time: {time_min}-{time_max} weeks")
    
    def _show_step_3(self):
        """Step 3: Assign engineers"""
        self._clear_content()
        self.step_label.configure(text=f"Step 3 of {self.total_steps}: Assign Engineers")
        
        if not self.available_engineers:
            no_engineers = ctk.CTkLabel(
                self.content_frame,
                text="No engineers available to assign",
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 13)
            )
            no_engineers.pack(pady=50)
            return
        
        # Engineers list
        engineers_frame = ctk.CTkScrollableFrame(
            self.content_frame,
            fg_color=FTBTheme.PANEL,
            corner_radius=8
        )
        engineers_frame.pack(fill="both", expand=True)
        
        self.engineer_vars = {}
        
        for engineer in self.available_engineers:
            card = ctk.CTkFrame(engineers_frame, fg_color=FTBTheme.CARD, corner_radius=8)
            card.pack(fill="x", pady=5, padx=10)
            
            # Checkbox
            var = ctk.BooleanVar(value=engineer in self.assigned_engineers)
            self.engineer_vars[engineer.name] = (var, engineer)
            
            checkbox = ctk.CTkCheckBox(
                card,
                text="",
                variable=var,
                fg_color=FTBTheme.ACCENT,
                hover_color=FTBTheme.CARD_HOVER
            )
            checkbox.pack(side="left", padx=15, pady=15)
            
            # Engineer info
            info_frame = ctk.CTkFrame(card, fg_color="transparent")
            info_frame.pack(side="left", fill="both", expand=True, pady=10)
            
            name_label = ctk.CTkLabel(
                info_frame,
                text=engineer.name,
                text_color=FTBTheme.TEXT,
                font=("Arial", 13, "bold"),
                anchor="w"
            )
            name_label.pack(anchor="w")
            
            rating = engineer.overall_rating if hasattr(engineer, 'overall_rating') else 50.0
            rating_color = FTBTheme.get_stat_color(rating)
            
            rating_label = ctk.CTkLabel(
                info_frame,
                text=f"Overall Rating: {rating:.0f}/100",
                text_color=rating_color,
                font=("Arial", 11),
                anchor="w"
            )
            rating_label.pack(anchor="w")
        
        # Team quality preview
        quality_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        quality_frame.pack(fill="x", pady=(10, 0))
        
        self.team_quality_label = ctk.CTkLabel(
            quality_frame,
            text="Select engineers to see team quality",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 12)
        )
        self.team_quality_label.pack(padx=20, pady=15)
    
    def _show_step_4(self):
        """Step 4: Resource allocation"""
        self._clear_content()
        self.step_label.configure(text=f"Step 4 of {self.total_steps}: Resource Allocation")
        
        # Budget input
        budget_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        budget_frame.pack(fill="x", pady=10)
        
        budget_label = ctk.CTkLabel(
            budget_frame,
            text="Budget Allocation",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        budget_label.pack(padx=20, pady=(15, 5), anchor="w")
        
        budget_info = ctk.CTkLabel(
            budget_frame,
            text=f"Available: {format_currency(self.team_budget)} • Minimum: $80K",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11)
        )
        budget_info.pack(padx=20, pady=(0, 10), anchor="w")
        
        self.budget_entry = ctk.CTkEntry(
            budget_frame,
            placeholder_text="Enter amount...",
            fg_color=FTBTheme.SURFACE,
            border_color=FTBTheme.ACCENT,
            font=("Arial", 12),
            height=40
        )
        self.budget_entry.pack(padx=20, pady=(0, 15), fill="x")
        
        # Priority selector
        priority_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        priority_frame.pack(fill="x", pady=10)
        
        priority_label = ctk.CTkLabel(
            priority_frame,
            text="Priority Level",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        priority_label.pack(padx=20, pady=(15, 10), anchor="w")
        
        self.priority_var = ctk.StringVar(value=self.priority)
        
        priorities = [
            ("normal", "Normal - Standard development timeline"),
            ("high", "High - Faster completion, +10% cost"),
            ("critical", "Critical - Rush job, +25% cost")
        ]
        
        for priority_val, description in priorities:
            radio = ctk.CTkRadioButton(
                priority_frame,
                text=description,
                variable=self.priority_var,
                value=priority_val,
                fg_color=FTBTheme.ACCENT,
                font=("Arial", 11)
            )
            radio.pack(padx=20, pady=5, anchor="w")
        
        priority_frame.pack(padx=0, pady=(0, 15))
        
        # Summary
        summary_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.PANEL, corner_radius=8)
        summary_frame.pack(fill="both", expand=True, pady=10)
        
        summary_label = ctk.CTkLabel(
            summary_frame,
            text="Project Summary",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        summary_label.pack(padx=20, pady=(15, 10))
        
        summary_text = f"""
Subsystem: {self.selected_subsystem or 'Not selected'}
Risk Level: {'Conservative' if self.risk_level < 0.33 else 'Balanced' if self.risk_level < 0.66 else 'Aggressive'}
Engineers: {len(self.assigned_engineers)} assigned
        """.strip()
        
        summary_content = ctk.CTkLabel(
            summary_frame,
            text=summary_text,
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11),
            justify="left"
        )
        summary_content.pack(padx=20, pady=(0, 15), anchor="w")
    
    def _next_step(self):
        """Move to next step"""
        if self.current_step == 1:
            self.selected_subsystem = self.subsystem_var.get()
            if not self.selected_subsystem:
                messagebox.showwarning("Selection Required", "Please select a subsystem")
                return
            self.current_step = 2
            self._show_step_2()
            self.back_btn.configure(state="normal")
        elif self.current_step == 2:
            self.current_step = 3
            self._show_step_3()
        elif self.current_step == 3:
            # Collect selected engineers
            self.assigned_engineers = [
                engineer for var, engineer in self.engineer_vars.values() if var.get()
            ]
            self.current_step = 4
            self._show_step_4()
            self.next_btn.configure(text="Start Project")
        elif self.current_step == 4:
            self._finish()
    
    def _previous_step(self):
        """Move to previous step"""
        if self.current_step > 1:
            self.current_step -= 1
            
            if self.current_step == 1:
                self._show_step_1()
                self.back_btn.configure(state="disabled")
                self.next_btn.configure(text="Next")
            elif self.current_step == 2:
                self._show_step_2()
                self.next_btn.configure(text="Next")
            elif self.current_step == 3:
                self._show_step_3()
                self.next_btn.configure(text="Next")
    
    def _finish(self):
        """Submit project configuration"""
        try:
            budget = float(self.budget_entry.get())
        except (ValueError, AttributeError):
            messagebox.showerror("Invalid Input", "Please enter a valid budget amount")
            return
        
        if budget < 80000:
            messagebox.showwarning("Insufficient Budget", "Minimum budget is $80K")
            return
        
        if budget > self.team_budget:
            messagebox.showwarning("Insufficient Funds", f"Your team only has {format_currency(self.team_budget)} available")
            return
        
        project_config = {
            'subsystem': self.selected_subsystem,
            'risk_level': self.risk_level,
            'engineers': self.assigned_engineers,
            'budget': budget,
            'priority': self.priority_var.get()
        }
        
        self.on_submit(project_config)
        self.destroy()


class FireEntityWizard(ctk.CTkToplevel):
    """Multi-step wizard for firing team entities with full cost disclosure"""
    
    def __init__(self, parent, entity: Any, team: Any, state: Any, on_confirm: Callable):
        super().__init__(parent)
        
        self.entity = entity
        self.team = team
        self.sim_state = state
        self.on_confirm = on_confirm
        
        self.current_step = 1
        self.total_steps = 4
        
        # Calculate buyout info immediately
        self.contract = self.sim_state.contracts.get(entity.entity_id) if self.sim_state.contracts else None
        self.buyout_cost = self._calculate_buyout()
        self.morale_penalty = self._calculate_morale_penalty()
        self.reputation_penalty = self._calculate_reputation_penalty()
        
        # Replacement tracking
        self.selected_replacement = None
        self.shortlisted_agents = []
        
        # Window config
        self.title(f"Fire {entity.name}")
        self.geometry("750x800")
        self.configure(fg_color=FTBTheme.BG)
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (750 // 2)
        y = (self.winfo_screenheight() // 2) - (800 // 2)
        self.geometry(f"750x800+{x}+{y}")
        
        # Build UI
        self._build_ui()
    
    def _calculate_buyout(self) -> int:
        """Calculate contract buyout cost"""
        if not self.contract:
            return 0
        
        # Import here to avoid circular dependency
        from ftb_game import calculate_contract_buyout
        
        current_day = getattr(self.sim_state, "current_day", None)
        if current_day is None:
            current_day = getattr(self.sim_state, "sim_day_of_year", 0)
        team_tier = self.team.tier
        return calculate_contract_buyout(self.contract, team_tier, current_day)
    
    def _calculate_morale_penalty(self) -> int:
        """Calculate team morale penalty"""
        entity_type = type(self.entity).__name__.lower()
        if entity_type == 'driver':
            return 5
        elif entity_type == 'engineer':
            return 3
        else:
            return 2
    
    def _calculate_reputation_penalty(self) -> int:
        """Calculate reputation penalty (mainly for drivers)"""
        entity_type = type(self.entity).__name__.lower()
        if entity_type == 'driver':
            # Higher penalty for senior/high-rated drivers
            rating = getattr(self.entity, 'overall_rating', 50.0)
            if rating > 80:
                return 10
            elif rating > 60:
                return 5
            else:
                return 2
        return 0
    
    def _fetch_replacement_candidates(self) -> List[Any]:
        """Fetch compatible free agents for role"""
        entity_type = type(self.entity).__name__
        candidates = []
        
        if hasattr(self.sim_state, 'free_agents'):
            for fa in self.sim_state.free_agents:
                if fa.entity_type == entity_type:
                    candidates.append(fa)
        
        # Sort by overall rating (descending), then asking salary (ascending)
        candidates.sort(key=lambda x: (-x.overall_rating, x.asking_salary))
        
        return candidates[:15]  # Top 15 candidates
    
    def _build_ui(self):
        # Header with step indicator
        self.header_frame = ctk.CTkFrame(self, fg_color=FTBTheme.PANEL, corner_radius=0)
        self.header_frame.pack(fill="x")
        
        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text=f"Fire {self.entity.name}",
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        self.title_label.pack(padx=20, pady=(15, 5))
        
        self.step_label = ctk.CTkLabel(
            self.header_frame,
            text=f"Step 1 of {self.total_steps}",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11)
        )
        self.step_label.pack(padx=20, pady=(0, 15))
        
        # Content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Navigation buttons
        self.nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        self.next_btn = ctk.CTkButton(
            self.nav_frame,
            text="Next",
            command=self._next_step,
            fg_color=FTBTheme.ACCENT,
            hover_color=FTBTheme.ACCENT_HOVER,
            height=40,
            width=120,
            font=("Arial", 12, "bold")
        )
        self.next_btn.pack(side="right")
        
        self.back_btn = ctk.CTkButton(
            self.nav_frame,
            text="Back",
            command=self._previous_step,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            width=120,
            font=("Arial", 12)
        )
        self.back_btn.pack(side="right", padx=(0, 10))
        self.back_btn.configure(state="disabled")
        
        self.cancel_btn = ctk.CTkButton(
            self.nav_frame,
            text="Cancel",
            command=self.destroy,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            width=100,
            font=("Arial", 12)
        )
        self.cancel_btn.pack(side="left")
        
        # Show first step
        self._show_step_1()
    
    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def _show_step_1(self):
        """Step 1: Entity review"""
        self._clear_content()
        self.step_label.configure(text=f"Step 1 of {self.total_steps}: Review Entity")
        
        # Entity card
        entity_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        entity_card.pack(fill="x", pady=10)
        
        name_label = ctk.CTkLabel(
            entity_card,
            text=self.entity.name,
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        name_label.pack(padx=20, pady=(20, 5))
        
        entity_type = type(self.entity).__name__
        type_label = ctk.CTkLabel(
            entity_card,
            text=entity_type,
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 12)
        )
        type_label.pack(padx=20, pady=(0, 15))
        
        # Stats section
        stats_frame = ctk.CTkFrame(entity_card, fg_color=FTBTheme.SURFACE, corner_radius=6)
        stats_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        rating = getattr(self.entity, 'overall_rating', 50.0)
        rating_color = FTBTheme.get_stat_color(rating)
        
        rating_label = ctk.CTkLabel(
            stats_frame,
            text=f"Overall Rating: {rating:.0f}/100",
            text_color=rating_color,
            font=("Arial", 13, "bold")
        )
        rating_label.pack(padx=15, pady=10)
        
        # Key attributes (if driver)
        if hasattr(self.entity, 'speed'):
            attrs_frame = ctk.CTkFrame(stats_frame, fg_color="transparent")
            attrs_frame.pack(fill="x", padx=15, pady=(0, 10))
            
            for attr_name in ['speed', 'racecraft', 'consistency']:
                if hasattr(self.entity, attr_name):
                    value = getattr(self.entity, attr_name, 0.0)
                    attr_label = ctk.CTkLabel(
                        attrs_frame,
                        text=f"{attr_name.title()}: {value:.0f}",
                        text_color=FTBTheme.TEXT,
                        font=("Arial", 11)
                    )
                    attr_label.pack(anchor="w", pady=2)
        
        # Contract info
        if self.contract:
            contract_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
            contract_frame.pack(fill="x", pady=10)
            
            contract_title = ctk.CTkLabel(
                contract_frame,
                text="Contract Details",
                text_color=FTBTheme.TEXT,
                font=("Arial", 14, "bold")
            )
            contract_title.pack(padx=20, pady=(15, 10))
            
            contract_info = ctk.CTkFrame(contract_frame, fg_color=FTBTheme.SURFACE, corner_radius=6)
            contract_info.pack(fill="x", padx=20, pady=(0, 15))
            
            salary_label = ctk.CTkLabel(
                contract_info,
                text=f"Base Salary: {format_currency(self.contract.base_salary)}/season",
                text_color=FTBTheme.TEXT,
                font=("Arial", 11)
            )
            salary_label.pack(anchor="w", padx=15, pady=(10, 2))
            
            current_day = getattr(self.sim_state, "current_day", None)
            if current_day is None:
                current_day = getattr(self.sim_state, "sim_day_of_year", 0)
            seasons_remaining = self.contract.seasons_remaining(current_day)
            duration_label = ctk.CTkLabel(
                contract_info,
                text=f"Seasons Remaining: {seasons_remaining}",
                text_color=FTBTheme.TEXT,
                font=("Arial", 11)
            )
            duration_label.pack(anchor="w", padx=15, pady=2)
            
            if self.contract.signing_bonus:
                bonus_label = ctk.CTkLabel(
                    contract_info,
                    text=f"Signing Bonus: {format_currency(self.contract.signing_bonus)}",
                    text_color=FTBTheme.TEXT_MUTED,
                    font=("Arial", 10)
                )
                bonus_label.pack(anchor="w", padx=15, pady=(2, 10))
            else:
                ctk.CTkLabel(contract_info, text="").pack(pady=5)
        
        # Warning notice
        warning_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.WARNING_BG, corner_radius=8)
        warning_frame.pack(fill="x", pady=10)
        
        warning_label = ctk.CTkLabel(
            warning_frame,
            text="⚠️ Warning: This action cannot be undone",
            text_color=FTBTheme.WARNING_TEXT,
            font=("Arial", 12, "bold")
        )
        warning_label.pack(padx=15, pady=15)
    
    def _show_step_2(self):
        """Step 2: Cost breakdown"""
        self._clear_content()
        self.step_label.configure(text=f"Step 2 of {self.total_steps}: Financial Impact")
        
        # Buyout cost card
        buyout_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        buyout_card.pack(fill="x", pady=10)
        
        buyout_title = ctk.CTkLabel(
            buyout_card,
            text="Contract Buyout",
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        buyout_title.pack(padx=20, pady=(20, 10))
        
        buyout_amount = ctk.CTkLabel(
            buyout_card,
            text=format_currency(self.buyout_cost),
            text_color=FTBTheme.ACCENT,
            font=("Arial", 24, "bold")
        )
        buyout_amount.pack(padx=20, pady=(0, 15))
        
        # Breakdown details
        if self.contract:
            breakdown_frame = ctk.CTkFrame(buyout_card, fg_color=FTBTheme.SURFACE, corner_radius=6)
            breakdown_frame.pack(fill="x", padx=20, pady=(0, 20))
            
            current_day = getattr(self.sim_state, "current_day", None)
            if current_day is None:
                current_day = getattr(self.sim_state, "sim_day_of_year", 0)
            seasons_remaining = self.contract.seasons_remaining(current_day)
            remaining_value = self.contract.base_salary * seasons_remaining
            
            details = [
                ("Contract Value Remaining", format_currency(remaining_value)),
                ("Team Tier Payout %", f"{self._get_payout_pct() * 100:.0f}%"),
                ("Role Multiplier", f"{self._get_role_multiplier():.1%}"),
            ]
            
            if self.contract.exit_clauses and self.contract.exit_clauses.get('buyout_cost', 0) > 0:
                clause_cost = self.contract.exit_clauses['buyout_cost']
                details.append(("Exit Clause Override", format_currency(clause_cost)))
            
            for label, value in details:
                detail_row = ctk.CTkFrame(breakdown_frame, fg_color="transparent")
                detail_row.pack(fill="x", padx=15, pady=5)
                
                detail_label = ctk.CTkLabel(
                    detail_row,
                    text=label,
                    text_color=FTBTheme.TEXT_MUTED,
                    font=("Arial", 11),
                    anchor="w"
                )
                detail_label.pack(side="left", fill="x", expand=True)
                
                detail_value = ctk.CTkLabel(
                    detail_row,
                    text=value,
                    text_color=FTBTheme.TEXT,
                    font=("Arial", 11, "bold"),
                    anchor="e"
                )
                detail_value.pack(side="right")
        
        # Team consequences
        consequences_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        consequences_card.pack(fill="x", pady=10)
        
        consequences_title = ctk.CTkLabel(
            consequences_card,
            text="Team Impact",
            text_color=FTBTheme.TEXT,
            font=("Arial", 14, "bold")
        )
        consequences_title.pack(padx=20, pady=(15, 10))
        
        consequences_frame = ctk.CTkFrame(consequences_card, fg_color=FTBTheme.SURFACE, corner_radius=6)
        consequences_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        impacts = [
            (f"Team Morale: -{self.morale_penalty} points", FTBTheme.STAT_LOW),
        ]
        
        if self.reputation_penalty > 0:
            impacts.append((f"Reputation: -{self.reputation_penalty} points", FTBTheme.STAT_LOW))
        
        # Calculate new budget
        current_cash = getattr(self.team.budget, 'cash', 0)
        remaining_cash = current_cash - self.buyout_cost
        impacts.append((f"Cash After Buyout: {format_currency(remaining_cash)}", 
                       FTBTheme.STAT_HIGH if remaining_cash > 0 else FTBTheme.STAT_LOW))
        
        for impact_text, color in impacts:
            impact_label = ctk.CTkLabel(
                consequences_frame,
                text=impact_text,
                text_color=color,
                font=("Arial", 12)
            )
            impact_label.pack(anchor="w", padx=15, pady=5)
        
        # Affordability check
        if self.buyout_cost > current_cash:
            warning_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.WARNING_BG, corner_radius=8)
            warning_frame.pack(fill="x", pady=10)
            
            warning_label = ctk.CTkLabel(
                warning_frame,
                text="⚠️ Warning: Insufficient funds for buyout! This will put you in debt.",
                text_color=FTBTheme.WARNING_TEXT,
                font=("Arial", 11, "bold")
            )
            warning_label.pack(padx=15, pady=15)
    
    def _get_payout_pct(self) -> float:
        """Get buyout percentage for team tier"""
        BUYOUT_PCT_BY_TIER = {
            1: 0.10, 2: 0.15, 3: 0.20, 4: 0.25, 5: 0.30
        }
        return BUYOUT_PCT_BY_TIER.get(self.team.tier, 0.2)
    
    def _get_role_multiplier(self) -> float:
        """Get role multiplier for buyout"""
        entity_type = type(self.entity).__name__.lower()
        multipliers = {
            'driver': 1.0,
            'engineer': 0.8,
            'mechanic': 0.7,
            'strategist': 0.9,
            'aiprincipal': 1.0,
            'principal': 1.0
        }
        return multipliers.get(entity_type, 0.85)
    
    def _show_step_3(self):
        """Step 3: Replacement planning"""
        self._clear_content()
        self.step_label.configure(text=f"Step 3 of {self.total_steps}: Find Replacement")
        
        info_label = ctk.CTkLabel(
            self.content_frame,
            text="Browse available free agents. You can hire them after completing the firing process.",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11),
            wraplength=700
        )
        info_label.pack(pady=(0, 10))
        
        # Fetch candidates
        candidates = self._fetch_replacement_candidates()
        
        if not candidates:
            no_candidates = ctk.CTkLabel(
                self.content_frame,
                text="No compatible free agents available",
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 13)
            )
            no_candidates.pack(pady=50)
            return
        
        # Scrollable candidates list
        candidates_frame = ctk.CTkScrollableFrame(
            self.content_frame,
            fg_color=FTBTheme.PANEL,
            corner_radius=8
        )
        candidates_frame.pack(fill="both", expand=True)
        
        for fa in candidates:
            candidate_card = ctk.CTkFrame(candidates_frame, fg_color=FTBTheme.CARD, corner_radius=8)
            candidate_card.pack(fill="x", pady=5, padx=10)
            
            # Name and rating
            info_frame = ctk.CTkFrame(candidate_card, fg_color="transparent")
            info_frame.pack(fill="x", padx=15, pady=15)
            
            name_label = ctk.CTkLabel(
                info_frame,
                text=fa.entity.name,
                text_color=FTBTheme.TEXT,
                font=("Arial", 13, "bold"),
                anchor="w"
            )
            name_label.pack(side="left", fill="x", expand=True)
            
            rating_color = FTBTheme.get_stat_color(fa.overall_rating)
            rating_label = ctk.CTkLabel(
                info_frame,
                text=f"{fa.overall_rating:.0f}/100",
                text_color=rating_color,
                font=("Arial", 12, "bold")
            )
            rating_label.pack(side="right")
            
            # Salary demand
            salary_label = ctk.CTkLabel(
                candidate_card,
                text=f"Asking Salary: {format_currency(fa.asking_salary)}/season",
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 10)
            )
            salary_label.pack(anchor="w", padx=15, pady=(0, 5))
            
            # Exit reason if relevant
            if fa.exit_reason:
                reason_text = f"Left previous team: {fa.exit_reason.replace('_', ' ').title()}"
                reason_label = ctk.CTkLabel(
                    candidate_card,
                    text=reason_text,
                    text_color=FTBTheme.TEXT_MUTED,
                    font=("Arial", 9, "italic")
                )
                reason_label.pack(anchor="w", padx=15, pady=(0, 10))
    
    def _show_step_4(self):
        """Step 4: Final confirmation"""
        self._clear_content()
        self.step_label.configure(text=f"Step 4 of {self.total_steps}: Confirm Firing")
        
        # Summary card
        summary_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        summary_card.pack(fill="both", expand=True, pady=10)
        
        summary_title = ctk.CTkLabel(
            summary_card,
            text="Summary",
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        summary_title.pack(padx=20, pady=(20, 15))
        
        # Entity being fired
        entity_section = ctk.CTkFrame(summary_card, fg_color=FTBTheme.SURFACE, corner_radius=6)
        entity_section.pack(fill="x", padx=20, pady=5)
        
        entity_label = ctk.CTkLabel(
            entity_section,
            text=f"Firing: {self.entity.name} ({type(self.entity).__name__})",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        entity_label.pack(padx=15, pady=10)
        
        # Financial summary
        finance_section = ctk.CTkFrame(summary_card, fg_color=FTBTheme.SURFACE, corner_radius=6)
        finance_section.pack(fill="x", padx=20, pady=5)
        
        buyout_label = ctk.CTkLabel(
            finance_section,
            text=f"Buyout Cost: {format_currency(self.buyout_cost)}",
            text_color=FTBTheme.ACCENT,
            font=("Arial", 12, "bold")
        )
        buyout_label.pack(padx=15, pady=10)
        
        # Impact summary
        impact_section = ctk.CTkFrame(summary_card, fg_color=FTBTheme.SURFACE, corner_radius=6)
        impact_section.pack(fill="x", padx=20, pady=5)
        
        impact_title = ctk.CTkLabel(
            impact_section,
            text="Team Impact:",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11, "bold")
        )
        impact_title.pack(anchor="w", padx=15, pady=(10, 5))
        
        impacts = [
            f"• Morale: -{self.morale_penalty}",
            f"• Reputation: -{self.reputation_penalty}" if self.reputation_penalty > 0 else None,
            f"• Roster spot freed for new hire"
        ]
        
        for impact in impacts:
            if impact:
                impact_label = ctk.CTkLabel(
                    impact_section,
                    text=impact,
                    text_color=FTBTheme.TEXT,
                    font=("Arial", 11)
                )
                impact_label.pack(anchor="w", padx=30, pady=2)
        
        ctk.CTkLabel(impact_section, text="").pack(pady=5)
        
        # Final warning
        warning_frame = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.WARNING_BG, corner_radius=8)
        warning_frame.pack(fill="x", pady=15)
        
        warning_label = ctk.CTkLabel(
            warning_frame,
            text="This action is permanent and cannot be undone.",
            text_color=FTBTheme.WARNING_TEXT,
            font=("Arial", 12, "bold")
        )
        warning_label.pack(padx=20, pady=15)
        
        # Update button text
        self.next_btn.configure(text="Confirm & Fire", fg_color=FTBTheme.WARNING_BG)
    
    def _next_step(self):
        """Move to next step"""
        if self.current_step < self.total_steps:
            self.current_step += 1
            
            if self.current_step == 2:
                self._show_step_2()
                self.back_btn.configure(state="normal")
            elif self.current_step == 3:
                self._show_step_3()
            elif self.current_step == 4:
                self._show_step_4()
        else:
            # Final step - confirm firing
            self._finish()
    
    def _previous_step(self):
        """Move to previous step"""
        if self.current_step > 1:
            self.current_step -= 1
            
            if self.current_step == 1:
                self._show_step_1()
                self.back_btn.configure(state="disabled")
                self.next_btn.configure(text="Next", fg_color=FTBTheme.ACCENT)
            elif self.current_step == 2:
                self._show_step_2()
                self.next_btn.configure(text="Next", fg_color=FTBTheme.ACCENT)
            elif self.current_step == 3:
                self._show_step_3()
                self.next_btn.configure(text="Next", fg_color=FTBTheme.ACCENT)
    
    def _finish(self):
        """Execute firing confirmation"""
        self.on_confirm(self.entity)
        self.destroy()


class UpgradeWizard(ctk.CTkToplevel):
    """Unified wizard for infrastructure upgrades - Direct or R&D path"""
    
    def __init__(self, parent, facility_key: str, current_quality: float, team: Any, 
                 state: Any, available_engineers: List[Any], on_submit: Callable):
        super().__init__(parent)
        
        self.facility_key = facility_key
        self.current_quality = current_quality
        self.team = team
        self.sim_state = state
        self.available_engineers = available_engineers
        self.on_submit = on_submit
        
        self.current_step = 1
        self.total_steps = 4
        
        # Data collection
        self.upgrade_path = None  # "direct" or "rd"
        self.path_var = ctk.StringVar(value="")
        
        # Direct upgrade data
        self.upgrade_amount = 10.0
        self.estimated_cost = 0
        
        # R&D project data (reuse DevelopmentWizard pattern)
        self.risk_level = 0.5
        self.assigned_engineers = []
        self.budget_allocation = 0.0
        self.priority = "normal"
        
        # Calculate league average for comparison
        self.league_avg_quality = self._get_league_avg_quality()
        
        # Window config
        self.title(f"Upgrade {self._get_facility_display_name()}")
        self.geometry("750x800")
        self.configure(fg_color=FTBTheme.BG)
        self.resizable(False, False)
        
        # Make modal
        self.transient(parent)
        self.grab_set()
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (750 // 2)
        y = (self.winfo_screenheight() // 2) - (800 // 2)
        self.geometry(f"750x800+{x}+{y}")
        
        # Build UI
        self._build_ui()
    
    def _get_facility_display_name(self) -> str:
        """Convert facility_key to readable name"""
        return self.facility_key.replace('_', ' ').title()
    
    def _get_league_avg_quality(self) -> float:
        """Calculate league average quality for this facility"""
        if not hasattr(self.sim_state, 'ai_teams'):
            return 50.0
        
        qualities = []
        if self.sim_state.player_team:
            qualities.append(self.current_quality)
        
        for team in self.sim_state.ai_teams:
            if self.facility_key in team.infrastructure:
                qualities.append(team.infrastructure[self.facility_key])
        
        if not qualities:
            return 50.0
        
        return sum(qualities) / len(qualities)
    
    def _calculate_direct_cost(self, amount: float) -> int:
        """Calculate cost for direct upgrade"""
        from ftb_game import get_facility_base_cost_per_point, INFRASTRUCTURE_EFFECTS
        
        base_cost_per_point = get_facility_base_cost_per_point(self.facility_key)
        exponent = INFRASTRUCTURE_EFFECTS['direct_upgrade_cost_exponent']
        quality_for_cost = max(50.0, self.current_quality)
        cost = base_cost_per_point * ((quality_for_cost / 50.0) ** exponent) * amount
        
        return int(cost)
    
    def _estimate_performance_benefit(self, quality_delta: float) -> str:
        """Estimate performance improvements from quality increase"""
        # This is simplified - actual benefits vary by facility type
        dev_speed_bonus = quality_delta * 0.002 * 100  # % improvement
        success_bonus = quality_delta * 0.001 * 100
        
        benefits = []
        if dev_speed_bonus >= 1.0:
            benefits.append(f"+{dev_speed_bonus:.1f}% development speed")
        if success_bonus >= 0.5:
            benefits.append(f"+{success_bonus:.1f}% R&D success rate")
        
        if not benefits:
            return "Minor performance improvement"
        
        return " • ".join(benefits)
    
    def _build_ui(self):
        # Header with step indicator
        self.header_frame = ctk.CTkFrame(self, fg_color=FTBTheme.PANEL, corner_radius=0)
        self.header_frame.pack(fill="x")
        
        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text=f"Upgrade {self._get_facility_display_name()}",
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        self.title_label.pack(padx=20, pady=(15, 5))
        
        self.step_label = ctk.CTkLabel(
            self.header_frame,
            text=f"Step 1 of {self.total_steps}",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11)
        )
        self.step_label.pack(padx=20, pady=(0, 15))
        
        # Content area
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Navigation buttons
        self.nav_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        self.next_btn = ctk.CTkButton(
            self.nav_frame,
            text="Next",
            command=self._next_step,
            fg_color=FTBTheme.ACCENT,
            hover_color=FTBTheme.ACCENT_HOVER,
            height=40,
            width=120,
            font=("Arial", 12, "bold")
        )
        self.next_btn.pack(side="right")
        
        self.back_btn = ctk.CTkButton(
            self.nav_frame,
            text="Back",
            command=self._previous_step,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            width=120,
            font=("Arial", 12)
        )
        self.back_btn.pack(side="right", padx=(0, 10))
        self.back_btn.configure(state="disabled")
        
        self.cancel_btn = ctk.CTkButton(
            self.nav_frame,
            text="Cancel",
            command=self.destroy,
            fg_color=FTBTheme.SURFACE,
            hover_color=FTBTheme.CARD_HOVER,
            height=40,
            width=100,
            font=("Arial", 12)
        )
        self.cancel_btn.pack(side="left")
        
        # Show first step
        self._show_step_1()
    
    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
    
    def _show_step_1(self):
        """Step 1: Choose upgrade path"""
        self._clear_content()
        self.step_label.configure(text=f"Step 1 of {self.total_steps}: Choose Upgrade Path")
        
        # Current status
        status_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        status_card.pack(fill="x", pady=(0, 15))
        
        status_title = ctk.CTkLabel(
            status_card,
            text="Current Status",
            text_color=FTBTheme.TEXT,
            font=("Arial", 14, "bold")
        )
        status_title.pack(padx=20, pady=(15, 10))
        
        quality_color = FTBTheme.get_stat_color(self.current_quality)
        current_label = ctk.CTkLabel(
            status_card,
            text=f"Current Quality: {self.current_quality:.1f}/100",
            text_color=quality_color,
            font=("Arial", 13, "bold")
        )
        current_label.pack(padx=20, pady=5)
        
        league_avg_color = FTBTheme.get_stat_color(self.league_avg_quality)
        league_label = ctk.CTkLabel(
            status_card,
            text=f"League Average: {self.league_avg_quality:.1f}/100",
            text_color=league_avg_color,
            font=("Arial", 11)
        )
        league_label.pack(padx=20, pady=(0, 15))
        
        # Path options
        paths = [
            ("direct", "Direct Instant Upgrade",
             "Expensive but immediate. Purchase quality points directly using team cash.",
             f"Cost: Variable • Time: Instant • Gain: Customizable (1-50 points)"),
            ("rd", "R&D Development Project",
             "Cheaper but takes time. Assign engineers to develop improvements over multiple weeks.",
             f"Cost: Lower • Time: 4-8 weeks • Gain: 5-15 points (varies by risk)")
        ]
        
        for path_value, path_name, description, details in paths:
            card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
            card.pack(fill="x", pady=8)
            
            # Radio button with path name
            radio = ctk.CTkRadioButton(
                card,
                text=path_name,
                variable=self.path_var,
                value=path_value,
                fg_color=FTBTheme.ACCENT,
                text_color=FTBTheme.TEXT,
                font=("Arial", 14, "bold")
            )
            radio.pack(anchor="w", padx=15, pady=(15, 5))
            
            # Description
            desc_label = ctk.CTkLabel(
                card,
                text=description,
                text_color=FTBTheme.TEXT,
                font=("Arial", 11),
                anchor="w",
                wraplength=650
            )
            desc_label.pack(anchor="w", padx=40, pady=(0, 5))
            
            # Details
            details_label = ctk.CTkLabel(
                card,
                text=details,
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 10, "italic"),
                anchor="w"
            )
            details_label.pack(anchor="w", padx=40, pady=(0, 15))
    
    def _show_step_2_direct(self):
        """Step 2 (Direct path): Set upgrade amount"""
        self._clear_content()
        self.step_label.configure(text=f"Step 2 of {self.total_steps}: Configure Upgrade")
        
        # Slider for upgrade amount
        slider_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        slider_card.pack(fill="x", pady=10)
        
        slider_title = ctk.CTkLabel(
            slider_card,
            text="Upgrade Amount (Quality Points)",
            text_color=FTBTheme.TEXT,
            font=("Arial", 14, "bold")
        )
        slider_title.pack(padx=20, pady=(20, 10))
        
        # Determine max upgrade
        max_upgrade = min(50.0, 100.0 - self.current_quality)
        
        self.amount_slider = ctk.CTkSlider(
            slider_card,
            from_=1.0,
            to=max_upgrade,
            number_of_steps=int(max_upgrade),
            command=self._on_amount_change,
            fg_color=FTBTheme.SURFACE,
            progress_color=FTBTheme.ACCENT,
            button_color=FTBTheme.ACCENT,
            button_hover_color=FTBTheme.CARD_HOVER
        )
        self.amount_slider.set(min(10.0, max_upgrade))
        self.amount_slider.pack(padx=20, pady=10, fill="x")
        
        # Amount label
        self.amount_label = ctk.CTkLabel(
            slider_card,
            text=f"+{self.upgrade_amount:.0f} points",
            text_color=FTBTheme.ACCENT,
            font=("Arial", 16, "bold")
        )
        self.amount_label.pack(padx=20, pady=5)
        
        # Min/Max indicators
        indicator_frame = ctk.CTkFrame(slider_card, fg_color="transparent")
        indicator_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        min_label = ctk.CTkLabel(
            indicator_frame,
            text="Minimum (1 pt)",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 9)
        )
        min_label.pack(side="left")
        
        max_label = ctk.CTkLabel(
            indicator_frame,
            text=f"Maximum ({max_upgrade:.0f} pts)",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 9)
        )
        max_label.pack(side="right")
        
        # Cost preview card
        self.preview_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.PANEL, corner_radius=8)
        self.preview_card.pack(fill="both", expand=True, pady=10)
        
        preview_title = ctk.CTkLabel(
            self.preview_card,
            text="Upgrade Preview",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        preview_title.pack(padx=20, pady=(15, 10))
        
        self.cost_preview_label = ctk.CTkLabel(
            self.preview_card,
            text="Cost: Calculating...",
            text_color=FTBTheme.TEXT,
            font=("Arial", 12)
        )
        self.cost_preview_label.pack(padx=20, pady=5)
        
        self.new_quality_label = ctk.CTkLabel(
            self.preview_card,
            text="",
            text_color=FTBTheme.TEXT,
            font=("Arial", 12)
        )
        self.new_quality_label.pack(padx=20, pady=5)
        
        self.benefit_label = ctk.CTkLabel(
            self.preview_card,
            text="",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 11),
            wraplength=650
        )
        self.benefit_label.pack(padx=20, pady=(5, 15))
        
        # Trigger initial update
        self._on_amount_change(self.amount_slider.get())
    
    def _on_amount_change(self, value):
        """Update preview when amount slider changes"""
        self.upgrade_amount = float(value)
        new_quality = min(100.0, self.current_quality + self.upgrade_amount)
        self.estimated_cost = self._calculate_direct_cost(self.upgrade_amount)
        benefit = self._estimate_performance_benefit(self.upgrade_amount)
        
        if hasattr(self, 'amount_label'):
            self.amount_label.configure(text=f"+{self.upgrade_amount:.0f} points")
        
        if hasattr(self, 'cost_preview_label'):
            affordable = self.team.budget.cash >= self.estimated_cost
            cost_color = FTBTheme.TEXT if affordable else FTBTheme.STAT_LOW
            self.cost_preview_label.configure(
                text=f"Cost: {format_currency(self.estimated_cost)}",
                text_color=cost_color
            )
        
        if hasattr(self, 'new_quality_label'):
            quality_color = FTBTheme.get_stat_color(new_quality)
            self.new_quality_label.configure(
                text=f"New Quality: {self.current_quality:.1f} → {new_quality:.1f}",
                text_color=quality_color
            )
        
        if hasattr(self, 'benefit_label'):
            self.benefit_label.configure(text=f"Estimated Benefit: {benefit}")
    
    def _show_step_2_rd(self):
        """Step 2 (R&D path): Configure R&D project"""
        self._clear_content()
        self.step_label.configure(text=f"Step 2 of {self.total_steps}: Configure R&D Project")
        
        # Risk slider
        risk_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        risk_card.pack(fill="x", pady=10)
        
        risk_title = ctk.CTkLabel(
            risk_card,
            text="Risk Profile",
            text_color=FTBTheme.TEXT,
            font=("Arial", 14, "bold")
        )
        risk_title.pack(padx=20, pady=(15, 10))
        
        self.risk_slider = ctk.CTkSlider(
            risk_card,
            from_=0.0,
            to=1.0,
            number_of_steps=10,
            command=self._on_risk_change,
            fg_color=FTBTheme.SURFACE,
            progress_color=FTBTheme.ACCENT,
            button_color=FTBTheme.ACCENT,
            button_hover_color=FTBTheme.CARD_HOVER
        )
        self.risk_slider.set(self.risk_level)
        self.risk_slider.pack(padx=20, pady=10, fill="x")
        
        # Risk indicators
        indicator_frame = ctk.CTkFrame(risk_card, fg_color="transparent")
        indicator_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        conservative_label = ctk.CTkLabel(
            indicator_frame,
            text="Conservative\nSafer • Lower cost",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 10),
            justify="left"
        )
        conservative_label.pack(side="left")
        
        aggressive_label = ctk.CTkLabel(
            indicator_frame,
            text="Aggressive\nRisky • Higher gains",
            text_color=FTBTheme.TEXT_MUTED,
            font=("Arial", 10),
            justify="right"
        )
        aggressive_label.pack(side="right")
        
        # Engineers selection
        if self.available_engineers:
            engineers_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
            engineers_card.pack(fill="both", expand=True, pady=10)
            
            engineers_title = ctk.CTkLabel(
                engineers_card,
                text="Assign Engineers (Optional)",
                text_color=FTBTheme.TEXT,
                font=("Arial", 13, "bold")
            )
            engineers_title.pack(padx=20, pady=(15, 10))
            
            engineers_scroll = ctk.CTkScrollableFrame(
                engineers_card,
                fg_color=FTBTheme.SURFACE,
                corner_radius=6,
                height=200
            )
            engineers_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 15))
            
            self.engineer_vars = {}
            
            for engineer in self.available_engineers[:10]:  # Limit to 10 for space
                var = ctk.BooleanVar(value=False)
                self.engineer_vars[engineer.name] = (var, engineer)
                
                checkbox = ctk.CTkCheckBox(
                    engineers_scroll,
                    text=f"{engineer.name} (Rating: {engineer.overall_rating:.0f})",
                    variable=var,
                    fg_color=FTBTheme.ACCENT,
                    font=("Arial", 11)
                )
                checkbox.pack(anchor="w", padx=10, pady=5)
        else:
            no_engineers_label = ctk.CTkLabel(
                self.content_frame,
                text="No engineers available (project will use baseline team capability)",
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 11)
            )
            no_engineers_label.pack(pady=10)
        
        self._on_risk_change(self.risk_level)
    
    def _on_risk_change(self, value):
        """Update preview when risk slider changes"""
        self.risk_level = float(value)
    
    def _show_step_3(self):
        """Step 3: Review & ROI"""
        self._clear_content()
        self.step_label.configure(text=f"Step 3 of {self.total_steps}: Review & Impact")
        
        # Summary card
        summary_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        summary_card.pack(fill="x", pady=10)
        
        summary_title = ctk.CTkLabel(
            summary_card,
            text="Upgrade Summary",
            text_color=FTBTheme.TEXT,
            font=("Arial", 15, "bold")
        )
        summary_title.pack(padx=20, pady=(20, 15))
        
        if self.upgrade_path == "direct":
            new_quality = min(100.0, self.current_quality + self.upgrade_amount)
            
            path_label = ctk.CTkLabel(
                summary_card,
                text="Path: Direct Instant Upgrade",
                text_color=FTBTheme.ACCENT,
                font=("Arial", 12, "bold")
            )
            path_label.pack(anchor="w", padx=20, pady=5)
            
            quality_label = ctk.CTkLabel(
                summary_card,
                text=f"Quality: {self.current_quality:.1f} → {new_quality:.1f} (+{self.upgrade_amount:.0f} points)",
                text_color=FTBTheme.TEXT,
                font=("Arial", 12)
            )
            quality_label.pack(anchor="w", padx=20, pady=5)
            
            cost_label = ctk.CTkLabel(
                summary_card,
                text=f"Total Cost: {format_currency(self.estimated_cost)}",
                text_color=FTBTheme.TEXT,
                font=("Arial", 12)
            )
            cost_label.pack(anchor="w", padx=20, pady=5)
            
            time_label = ctk.CTkLabel(
                summary_card,
                text="Time to Complete: Immediate",
                text_color=FTBTheme.STAT_HIGH,
                font=("Arial", 12)
            )
            time_label.pack(anchor="w", padx=20, pady=(5, 15))
            
        else:  # R&D path
            estimated_gain = 5 + int(self.risk_level * 10)
            estimated_weeks = 6 - int(self.risk_level * 2)
            estimated_cost = 60000 + int(self.risk_level * 40000)
            
            path_label = ctk.CTkLabel(
                summary_card,
                text="Path: R&D Development Project",
                text_color=FTBTheme.ACCENT,
                font=("Arial", 12, "bold")
            )
            path_label.pack(anchor="w", padx=20, pady=5)
            
            risk_text = "Conservative" if self.risk_level < 0.33 else "Balanced" if self.risk_level < 0.66 else "Aggressive"
            risk_label = ctk.CTkLabel(
                summary_card,
                text=f"Risk Level: {risk_text}",
                text_color=FTBTheme.TEXT,
                font=("Arial", 12)
            )
            risk_label.pack(anchor="w", padx=20, pady=5)
            
            num_engineers = len([v for v, _ in self.engineer_vars.values() if v.get()]) if hasattr(self, 'engineer_vars') else 0
            engineers_label = ctk.CTkLabel(
                summary_card,
                text=f"Engineers Assigned: {num_engineers}",
                text_color=FTBTheme.TEXT,
                font=("Arial", 12)
            )
            engineers_label.pack(anchor="w", padx=20, pady=5)
            
            gain_label = ctk.CTkLabel(
                summary_card,
                text=f"Expected Quality Gain: +{estimated_gain-2} to +{estimated_gain+2} points",
                text_color=FTBTheme.TEXT,
                font=("Arial", 12)
            )
            gain_label.pack(anchor="w", padx=20, pady=5)
            
            cost_label = ctk.CTkLabel(
                summary_card,
                text=f"Estimated Cost: {format_currency(estimated_cost)}",
                text_color=FTBTheme.TEXT,
                font=("Arial", 12)
            )
            cost_label.pack(anchor="w", padx=20, pady=5)
            
            time_label = ctk.CTkLabel(
                summary_card,
                text=f"Estimated Time: {estimated_weeks} weeks",
                text_color=FTBTheme.TEXT_MUTED,
                font=("Arial", 12)
            )
            time_label.pack(anchor="w", padx=20, pady=(5, 15))
        
        # Comparison to league
        comparison_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.PANEL, corner_radius=8)
        comparison_card.pack(fill="x", pady=10)
        
        comparison_title = ctk.CTkLabel(
            comparison_card,
            text="League Comparison",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        comparison_title.pack(padx=20, pady=(15, 10))
        
        if self.upgrade_path == "direct":
            new_quality = min(100.0, self.current_quality + self.upgrade_amount)
        else:
            estimated_gain = 5 + int(self.risk_level * 10)
            new_quality = min(100.0, self.current_quality + estimated_gain)
        
        current_vs_league = self.current_quality - self.league_avg_quality
        new_vs_league = new_quality - self.league_avg_quality
        
        current_color = FTBTheme.STAT_HIGH if current_vs_league > 0 else FTBTheme.STAT_LOW
        new_color = FTBTheme.STAT_HIGH if new_vs_league > 0 else FTBTheme.STAT_LOW
        
        current_comp = ctk.CTkLabel(
            comparison_card,
            text=f"Current vs. League: {current_vs_league:+.1f} points",
            text_color=current_color,
            font=("Arial", 11)
        )
        current_comp.pack(anchor="w", padx=20, pady=5)
        
        new_comp = ctk.CTkLabel(
            comparison_card,
            text=f"After Upgrade vs. League: {new_vs_league:+.1f} points",
            text_color=new_color,
            font=("Arial", 11)
        )
        new_comp.pack(anchor="w", padx=20, pady=(5, 15))
        
        # Performance impact
        impact_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        impact_card.pack(fill="x", pady=10)
        
        impact_title = ctk.CTkLabel(
            impact_card,
            text="Performance Impact",
            text_color=FTBTheme.TEXT,
            font=("Arial", 13, "bold")
        )
        impact_title.pack(padx=20, pady=(15, 10))
        
        quality_delta = new_quality - self.current_quality
        benefit = self._estimate_performance_benefit(quality_delta)
        
        benefit_label = ctk.CTkLabel(
            impact_card,
            text=benefit,
            text_color=FTBTheme.TEXT,
            font=("Arial", 11),
            wraplength=650
        )
        benefit_label.pack(anchor="w", padx=20, pady=(0, 15))
    
    def _show_step_4(self):
        """Step 4: Final confirmation"""
        self._clear_content()
        self.step_label.configure(text=f"Step 4 of {self.total_steps}: Confirm Upgrade")
        
        confirmation_card = ctk.CTkFrame(self.content_frame, fg_color=FTBTheme.CARD, corner_radius=8)
        confirmation_card.pack(fill="both", expand=True, pady=20)
        
        confirm_title = ctk.CTkLabel(
            confirmation_card,
            text="Ready to Proceed",
            text_color=FTBTheme.TEXT,
            font=("Arial", 16, "bold")
        )
        confirm_title.pack(padx=20, pady=(30, 20))
        
        if self.upgrade_path == "direct":
            message = f"""
Direct upgrade of {self._get_facility_display_name()}
by {self.upgrade_amount:.0f} quality points
for {format_currency(self.estimated_cost)}

This upgrade will take effect immediately.
            """.strip()
        else:
            message = f"""
Starting R&D development project to improve
{self._get_facility_display_name()}

Engineers will be assigned and the project
will begin immediately.
            """.strip()
        
        message_label = ctk.CTkLabel(
            confirmation_card,
            text=message,
            text_color=FTBTheme.TEXT,
            font=("Arial", 13),
            justify="center"
        )
        message_label.pack(padx=20, pady=20)
        
        # Affordability check for direct upgrades
        if self.upgrade_path == "direct" and self.estimated_cost > self.team.budget.cash:
            warning_frame = ctk.CTkFrame(confirmation_card, fg_color=FTBTheme.WARNING_BG, corner_radius=8)
            warning_frame.pack(fill="x", padx=20, pady=15)
            
            warning_label = ctk.CTkLabel(
                warning_frame,
                text="⚠️ Warning: Insufficient funds for this upgrade!",
                text_color=FTBTheme.WARNING_TEXT,
                font=("Arial", 12, "bold")
            )
            warning_label.pack(padx=15, pady=15)
            
            # Disable next button
            self.next_btn.configure(state="disabled")
        else:
            self.next_btn.configure(text="Confirm & Upgrade", fg_color=FTBTheme.ACCENT)
    
    def _next_step(self):
        """Move to next step"""
        if self.current_step == 1:
            self.upgrade_path = self.path_var.get()
            if not self.upgrade_path:
                messagebox.showwarning("Selection Required", "Please select an upgrade path")
                return
            
            self.current_step = 2
            if self.upgrade_path == "direct":
                self._show_step_2_direct()
            else:
                self._show_step_2_rd()
            self.back_btn.configure(state="normal")
            
        elif self.current_step == 2:
            if self.upgrade_path == "rd" and hasattr(self, 'engineer_vars'):
                # Collect selected engineers
                self.assigned_engineers = [
                    engineer for var, engineer in self.engineer_vars.values() if var.get()
                ]
            
            self.current_step = 3
            self._show_step_3()
            
        elif self.current_step == 3:
            self.current_step = 4
            self._show_step_4()
            self.next_btn.configure(text="Next")
            
        elif self.current_step == 4:
            self._finish()
    
    def _previous_step(self):
        """Move to previous step"""
        if self.current_step > 1:
            self.current_step -= 1
            
            if self.current_step == 1:
                self._show_step_1()
                self.back_btn.configure(state="disabled")
                self.next_btn.configure(text="Next", fg_color=FTBTheme.ACCENT, state="normal")
            elif self.current_step == 2:
                if self.upgrade_path == "direct":
                    self._show_step_2_direct()
                else:
                    self._show_step_2_rd()
                self.next_btn.configure(text="Next", fg_color=FTBTheme.ACCENT, state="normal")
            elif self.current_step == 3:
                self._show_step_3()
                self.next_btn.configure(text="Next", fg_color=FTBTheme.ACCENT, state="normal")
    
    def _finish(self):
        """Submit upgrade configuration"""
        if self.upgrade_path == "direct":
            # Direct upgrade configuration
            config = {
                'path': 'direct',
                'facility': self.facility_key,
                'amount': self.upgrade_amount,
                'cost': self.estimated_cost
            }
        else:
            # R&D project configuration
            config = {
                'path': 'rd',
                'facility': self.facility_key,
                'subsystem': f"{self._get_facility_display_name()} Upgrade",  # For R&D system
                'risk_level': self.risk_level,
                'engineers': self.assigned_engineers,
                'budget': 60000 + int(self.risk_level * 40000),
                'priority': 'normal'
            }
        
        self.on_submit(config)
        self.destroy()
