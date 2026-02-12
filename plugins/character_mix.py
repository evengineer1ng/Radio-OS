"""
Character Mix Plugin

Tracks how often each character speaks and provides visualization + balancing.
Helps ensure all voices get air time, especially in large panels.
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, List, Optional
import math

# Import manifest from your_runtime
try:
    from your_runtime import CFG  # type: ignore
except ImportError:
    CFG = {}

PLUGIN_NAME = "Character Mix"
PLUGIN_DESC = "Track and balance character speaking frequency"
IS_FEED = False

# Global reference set by runtime
RUNTIME_STUB = None


def register_widgets(registry, runtime_stub):
    """Register the character mix pie chart widget."""
    global RUNTIME_STUB
    RUNTIME_STUB = runtime_stub
    
    registry.register(
        "character_mix",
        build_character_mix_widget,
        title="Character • Mix",
        default_panel="right"
    )


def build_character_mix_widget(parent, runtime_stub) -> tk.Widget:
    """Build a pie chart showing character speaking distribution."""
    return CharacterMixWidget(parent, runtime_stub)


class CharacterMixWidget(tk.Frame):
    """
    Displays a pie chart of character speaking frequency.
    Updates every few seconds from station memory.
    """
    
    def __init__(self, parent, runtime_stub):
        super().__init__(parent, bg="#1a1a1a")
        self.runtime_stub = runtime_stub
        self.running = True
        self.sliders = {}  # Store slider references
        
        # Header
        header = tk.Frame(self, bg="#1a1a1a")
        header.pack(fill="x", padx=10, pady=(10, 5))
        
        tk.Label(
            header,
            text="Character Mix",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg="#1a1a1a"
        ).pack(side="left")
        
        # Reset button
        reset_btn = tk.Button(
            header,
            text="Reset Stats",
            command=self._reset_stats,
            bg="#333333",
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=2
        )
        reset_btn.pack(side="right", padx=(5, 0))
        
        # Reset weights button
        reset_weights_btn = tk.Button(
            header,
            text="Reset Weights",
            command=self._reset_weights,
            bg="#333333",
            fg="#ffffff",
            relief="flat",
            padx=8,
            pady=2
        )
        reset_weights_btn.pack(side="right")
        
        # Create scrollable frame for sliders
        slider_container = tk.Frame(self, bg="#1a1a1a")
        slider_container.pack(fill="x", padx=10, pady=(0, 5))
        
        tk.Label(
            slider_container,
            text="Character Weights",
            font=("Segoe UI", 10, "bold"),
            fg="#aaaaaa",
            bg="#1a1a1a"
        ).pack(anchor="w", pady=(5, 5))
        
        self.sliders_frame = tk.Frame(slider_container, bg="#1a1a1a")
        self.sliders_frame.pack(fill="x")
        
        # Status label for debugging
        self.status_label = tk.Label(
            slider_container,
            text="Loading characters...",
            font=("Segoe UI", 9),
            fg="#888888",
            bg="#1a1a1a"
        )
        self.status_label.pack(anchor="w", pady=(5, 5))
        
        # Initialize sliders with characters from manifest
        self._initialize_sliders()
        
        # Canvas for pie chart
        self.canvas = tk.Canvas(
            self,
            bg="#1a1a1a",
            highlightthickness=0,
            width=400,
            height=400
        )
        self.canvas.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Stats text below
        self.stats_label = tk.Label(
            self,
            text="",
            font=("Consolas", 9),
            fg="#888888",
            bg="#1a1a1a",
            justify="left"
        )
        self.stats_label.pack(fill="x", padx=10, pady=(0, 10))
        
        # Start update loop
        self._schedule_update()
    
    def _initialize_sliders(self):
        """Create sliders for each character in the manifest."""
        if not self.running:
            return
            
        try:
            # Get characters from CFG manifest (access at runtime, not import time)
            characters = {}
            print(f"Character Mix Debug: CFG type={type(CFG)}, is dict={isinstance(CFG, dict)}")
            if isinstance(CFG, dict):
                characters = CFG.get("characters") or {}
                print(f"Character Mix Debug: Found {len(characters)} characters: {list(characters.keys())}")
            else:
                print(f"Character Mix Debug: CFG is not a dict, it is: {CFG}")
            
            # If CFG not loaded yet, wait and try again
            if not characters:
                self.status_label.config(text="Waiting for manifest to load...")
                self.after(1000, self._initialize_sliders)
                return
            
            # Get current weights from memory
            try:
                from runtime import mem as _mem  # type: ignore
                mem = _mem if isinstance(_mem, dict) else {}
            except ImportError:
                mem = {}
            
            weights = mem.get("character_mix_weights", {})
            
            # Avoid duplicates - only create if not already created
            if self.sliders:
                return
            
            # Create slider for each character
            for char_name in sorted(characters.keys()):
                self._create_character_slider(char_name, weights.get(char_name, 1.0))
            
            # Update status
            self.status_label.config(text=f"✓ {len(characters)} characters loaded")
            print(f"Character Mix: Initialized {len(characters)} character sliders")
                
        except Exception as e:
            self.status_label.config(text=f"Error: {e}")
            print(f"Error initializing sliders: {e}")
            import traceback
            traceback.print_exc()
    
    def _create_character_slider(self, char_name: str, initial_weight: float):
        """Create a slider row for a character."""
        row = tk.Frame(self.sliders_frame, bg="#1a1a1a")
        row.pack(fill="x", pady=2)
        
        # Character name label
        name_label = tk.Label(
            row,
            text=char_name[:15],  # Truncate long names
            font=("Segoe UI", 9),
            fg="#ffffff",
            bg="#1a1a1a",
            width=15,
            anchor="w"
        )
        name_label.pack(side="left", padx=(0, 5))
        
        # Weight value label
        value_label = tk.Label(
            row,
            text=f"{initial_weight:.2f}",
            font=("Consolas", 9),
            fg="#4ecdc4",
            bg="#1a1a1a",
            width=5,
            anchor="e"
        )
        value_label.pack(side="right", padx=(5, 0))
        
        # Slider
        slider = ttk.Scale(
            row,
            from_=0.0,
            to=3.0,
            orient="horizontal",
            value=initial_weight,
            command=lambda val, cn=char_name, lbl=value_label: self._on_slider_change(cn, val, lbl)
        )
        slider.pack(side="left", fill="x", expand=True, padx=5)
        
        self.sliders[char_name] = {
            "slider": slider,
            "value_label": value_label
        }
    
    def _on_slider_change(self, char_name: str, value: str, label: tk.Label):
        """Handle slider value change."""
        try:
            weight = float(value)
            label.config(text=f"{weight:.2f}")
            
            # Update memory with new weight
            try:
                from runtime import mem as _mem, save_memory  # type: ignore
                if isinstance(_mem, dict):
                    weights = _mem.setdefault("character_mix_weights", {})
                    weights[char_name] = weight
                    save_memory(_mem)
            except ImportError:
                print("Runtime memory not available")
            
        except Exception as e:
            print(f"Slider change error: {e}")
    
    def _reset_weights(self):
        """Reset all character weights to 1.0."""
        try:
            try:
                from runtime import mem as _mem, save_memory  # type: ignore
                if isinstance(_mem, dict):
                    weights = _mem.get("character_mix_weights", {})
                    
                    # Reset all weights to 1.0
                    for char_name in weights.keys():
                        weights[char_name] = 1.0
                        
                        # Update slider if it exists
                        if char_name in self.sliders:
                            self.sliders[char_name]["slider"].set(1.0)
                            self.sliders[char_name]["value_label"].config(text="1.00")
                    
                    save_memory(_mem)
            except ImportError:
                print("Runtime memory not available")
            
        except Exception as e:
            print(f"Reset weights error: {e}")
    
    def _schedule_update(self):
        """Schedule periodic UI updates."""
        if self.running:
            self._update_display()
            self.after(2000, self._schedule_update)
    
    def _update_display(self):
        """Read stats from memory and redraw chart."""
        try:
            try:
                from runtime import mem as _mem  # type: ignore
                mem = _mem if isinstance(_mem, dict) else {}
            except ImportError:
                mem = {}
            
            char_stats = mem.get("character_mix_stats", {})
            
            if not char_stats:
                self._draw_empty()
                return
            
            # Get totals
            total_count = sum(char_stats.values())
            if total_count == 0:
                self._draw_empty()
                return
            
            # Sort by frequency
            sorted_chars = sorted(
                char_stats.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            # Draw pie chart
            self._draw_pie_chart(sorted_chars, total_count)
            
            # Update stats text
            stats_lines = [f"Total: {total_count} utterances"]
            for char, count in sorted_chars:
                pct = (count / total_count) * 100
                stats_lines.append(f"{char}: {count} ({pct:.1f}%)")
            
            self.stats_label.config(text="\n".join(stats_lines))
            
        except Exception as e:
            self.stats_label.config(text=f"Error: {e}")
    
    def _draw_empty(self):
        """Draw empty state."""
        self.canvas.delete("all")
        w = self.canvas.winfo_width() or 400
        h = self.canvas.winfo_height() or 400
        
        self.canvas.create_text(
            w // 2,
            h // 2,
            text="No character data yet.\nStart the station to see distribution.",
            font=("Segoe UI", 10),
            fill="#555555",
            justify="center"
        )
        self.stats_label.config(text="")
    
    def _draw_pie_chart(self, sorted_chars: List[tuple], total: int):
        """Draw a pie chart on the canvas."""
        self.canvas.delete("all")
        
        w = self.canvas.winfo_width() or 400
        h = self.canvas.winfo_height() or 400
        
        # Pie dimensions
        center_x = w // 2
        center_y = (h // 2) - 20
        radius = min(center_x, center_y) - 40
        
        if radius <= 0:
            return
        
        # Color palette
        colors = [
            "#ff6b6b", "#4ecdc4", "#45b7d1", "#f9ca24",
            "#6c5ce7", "#a29bfe", "#fd79a8", "#fdcb6e",
            "#00b894", "#e17055", "#74b9ff", "#a29bfe"
        ]
        
        # Draw slices
        start_angle = 0
        
        for i, (char, count) in enumerate(sorted_chars):
            angle = (count / total) * 360
            color = colors[i % len(colors)]
            
            # Draw pie slice
            self.canvas.create_arc(
                center_x - radius,
                center_y - radius,
                center_x + radius,
                center_y + radius,
                start=start_angle,
                extent=angle,
                fill=color,
                outline="#000000",
                width=2
            )
            
            # Draw label
            mid_angle = start_angle + (angle / 2)
            label_angle = math.radians(mid_angle)
            label_radius = radius * 0.7
            
            label_x = center_x + label_radius * math.cos(label_angle)
            label_y = center_y - label_radius * math.sin(label_angle)
            
            pct = (count / total) * 100
            
            # Only show label if slice is big enough
            if pct >= 5:
                self.canvas.create_text(
                    label_x,
                    label_y,
                    text=f"{char}\n{pct:.0f}%",
                    font=("Segoe UI", 9, "bold"),
                    fill="#ffffff",
                    justify="center"
                )
            
            start_angle += angle
    
    def _reset_stats(self):
        """Reset character statistics."""
        try:
            try:
                from runtime import mem as _mem, save_memory  # type: ignore
                if isinstance(_mem, dict):
                    _mem["character_mix_stats"] = {}
                    save_memory(_mem)
                    self._update_display()
            except ImportError:
                print("Runtime memory not available")
        except Exception as e:
            print(f"Reset error: {e}")
    
    def destroy(self):
        """Clean up when widget is destroyed."""
        self.running = False
        super().destroy()


# ======================
# Runtime Integration Hooks
# ======================

def track_character_speech(character: str, mem: Dict[str, Any]) -> None:
    """
    Track that a character has spoken.
    Called by runtime after each TTS call.
    
    Args:
        character: name of character who spoke
        mem: station memory dict
    """
    if not character:
        return
    
    stats = mem.setdefault("character_mix_stats", {})
    char_key = character.lower().strip()
    stats[char_key] = stats.get(char_key, 0) + 1
    
    # Also maintain recent history for balancing
    history = mem.setdefault("character_mix_history", [])
    history.append(char_key)
    
    # Keep last 100 utterances
    if len(history) > 100:
        history[:] = history[-100:]


def get_balance_boost(character: str, mem: Dict[str, Any]) -> float:
    """
    Calculate a boost score for underused characters.
    Returns a positive boost for characters that haven't spoken much.
    
    Args:
        character: name of character to evaluate
        mem: station memory dict
        
    Returns:
        boost score (0-10) to add to selection weight
    """
    stats = mem.get("character_mix_stats", {})
    char_key = character.lower().strip()
    
    # If no stats yet, no meaningful boost
    if not stats:
        return 0.0
    
    total = sum(stats.values())
    
    if total < 10:
        # Not enough data yet
        return 0.0
    
    char_count = stats.get(char_key, 0)
    
    # If this character has NEVER spoken but others have, give maximum boost
    if char_count == 0 and total > 0:
        return 10.0
    
    char_pct = (char_count / total) * 100
    
    # Calculate expected percentage (equal distribution among all characters in stats)
    # Note: This favors characters in stats dict, but characters not yet speaking
    # are handled by the check above
    num_chars = len(stats)
    expected_pct = 100.0 / num_chars if num_chars > 0 else 0
    
    # Calculate deficit
    deficit = expected_pct - char_pct
    
    # Convert to boost (0-10 scale)
    # Large deficit = large boost
    boost = max(0, min(10, deficit / 2))
    
    return boost


def get_character_stats(mem: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get summary statistics about character usage.
    
    Returns:
        Dictionary with stats and insights
    """
    stats = mem.get("character_mix_stats", {})
    
    if not stats:
        return {
            "total": 0,
            "characters": {},
            "balance_score": 100.0,
            "underused": [],
            "overused": []
        }
    
    total = sum(stats.values())
    num_chars = len(stats)
    expected_pct = 100.0 / num_chars if num_chars > 0 else 0
    
    # Calculate variance from expected
    variances = {}
    for char, count in stats.items():
        actual_pct = (count / total) * 100
        variance = actual_pct - expected_pct
        variances[char] = variance
    
    # Balance score (100 = perfect, lower = worse)
    avg_variance = sum(abs(v) for v in variances.values()) / num_chars if num_chars > 0 else 0
    balance_score = max(0, 100 - (avg_variance * 5))
    
    # Identify under/over used
    underused = [c for c, v in variances.items() if v < -5]
    overused = [c for c, v in variances.items() if v > 5]
    
    return {
        "total": total,
        "characters": stats,
        "percentages": {c: (n/total)*100 for c, n in stats.items()},
        "balance_score": balance_score,
        "underused": underused,
        "overused": overused
    }


def get_character_weight(character: str, mem: Dict[str, Any]) -> float:
    """
    Get the current weight for a character from slider settings.
    
    Args:
        character: name of character
        mem: station memory dict
        
    Returns:
        weight multiplier (default 1.0)
    """
    weights = mem.get("character_mix_weights", {})
    char_key = character.lower().strip()
    return weights.get(character, weights.get(char_key, 1.0))


def apply_character_weights(character_scores: Dict[str, float], mem: Dict[str, Any]) -> Dict[str, float]:
    """
    Apply slider weights to character selection scores.
    
    Args:
        character_scores: dict of character names to base scores
        mem: station memory dict
        
    Returns:
        adjusted scores with weights applied
    """
    weights = mem.get("character_mix_weights", {})
    adjusted = {}
    
    for char, score in character_scores.items():
        weight = get_character_weight(char, mem)
        adjusted[char] = score * weight
    
    return adjusted


def get_all_character_weights(mem: Dict[str, Any]) -> Dict[str, float]:
    """
    Get all character weights.
    
    Args:
        mem: station memory dict
        
    Returns:
        dict of character names to weights
    """
    return mem.get("character_mix_weights", {})

