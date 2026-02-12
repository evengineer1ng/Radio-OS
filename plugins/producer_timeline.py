"""
Producer Timeline Observer
===========================

Widget-only plugin that visualizes the producer's ongoing queue and timeline.

Shows:
- Segments in queue (queued status)
- Segments in flight (claimed by host)
- Recently played segments
- Source distribution
- Priority visualization
- Real-time updates

Useful for:
- Debugging producer behavior
- Monitoring show flow aesthetically
- Understanding queue dynamics

This is NOT a feed plugin - it only provides visualization.
"""

import tkinter as tk
from typing import Any, Dict, List

# Plugin metadata
PLUGIN_NAME = "Producer Timeline Observer"
PLUGIN_DESC = "Visualize producer queue & timeline in real-time"
IS_FEED = False  # Widget-only plugin


def register_widgets(registry, runtime):
    """Register the producer timeline widget"""
    
    BG = "#0e0e0e"
    SURFACE = "#121212"
    CARD = "#1a1a1a"
    TXT = "#e8e8e8"
    MUTED = "#9a9a9a"
    ACCENT = "#4cc9f0"
    QUEUED = "#f72585"
    CLAIMED = "#ffd60a"
    DONE = "#06d6a0"
    
    def producer_timeline_factory(parent, runtime):
        root = tk.Frame(parent, bg=BG)
        
        # Header
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(4, 2))
        
        tk.Label(
            header,
            text="📊 Producer Timeline",
            bg=BG, fg=ACCENT,
            font=("Segoe UI", 11, "bold")
        ).pack(side="left", padx=12)
        
        stats_label = tk.Label(
            header,
            text="",
            bg=BG, fg=MUTED,
            font=("Segoe UI", 8)
        )
        stats_label.pack(side="right", padx=12)
        
        # Tab selector
        tab_frame = tk.Frame(root, bg=BG)
        tab_frame.pack(fill="x", pady=(0, 4))
        
        view_var = tk.StringVar(value="queue")
        
        def switch_view(view):
            view_var.set(view)
            render()
        
        for view_name, label in [("queue", "Queue"), ("claimed", "In Flight"), ("recent", "Recent"), ("stats", "Stats")]:
            btn = tk.Label(
                tab_frame,
                text=label,
                bg=CARD if view_var.get() == view_name else SURFACE,
                fg=ACCENT if view_var.get() == view_name else MUTED,
                font=("Segoe UI", 9),
                padx=12, pady=4,
                cursor="hand2"
            )
            btn.pack(side="left", padx=2)
            btn.bind("<Button-1>", lambda e, v=view_name: switch_view(v))
            
            # Store for color updates
            if not hasattr(root, '_tab_btns'):
                root._tab_btns = {}
            root._tab_btns[view_name] = btn
        
        # Scrollable content area
        scrollbar = tk.Scrollbar(root, orient="vertical")
        canvas = tk.Canvas(root, bg=BG, highlightthickness=0, yscrollcommand=scrollbar.set)
        scrollbar.configure(command=canvas.yview)
        
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        
        content = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")
        
        def sync(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            if e:
                canvas.itemconfigure(window_id, width=e.width)
        
        content.bind("<Configure>", sync)
        canvas.bind("<Configure>", sync)
        
        # Mouse wheel
        def _wheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        
        def get_segments():
            """Query segments database"""
            try:
                import sqlite3
                from runtime import db_connect
                conn = db_connect()
                
                rows = conn.execute("""
                    SELECT id, created_ts, priority, status, 
                           source, title, angle, why
                    FROM segments
                    ORDER BY 
                        CASE status 
                            WHEN 'claimed' THEN 1
                            WHEN 'queued' THEN 2
                            WHEN 'done' THEN 3
                            ELSE 4
                        END,
                        created_ts DESC
                    LIMIT 100
                """).fetchall()
                
                conn.close()
                
                return [{
                    "id": r[0],
                    "created_ts": r[1],
                    "priority": r[2],
                    "status": r[3],
                    "source": r[4],
                    "title": r[5],
                    "angle": r[6],
                    "why": r[7]
                } for r in rows]
            except Exception:
                return []
        
        def render_segment_card(seg: Dict[str, Any], parent_frame: tk.Frame):
            """Render a segment card"""
            status = seg.get("status", "unknown")
            
            if status == "queued":
                color = QUEUED
                icon = "⏸"
            elif status == "claimed":
                color = CLAIMED
                icon = "▶"
            elif status == "done":
                color = DONE
                icon = "✓"
            else:
                color = MUTED
                icon = "?"
            
            card = tk.Frame(parent_frame, bg=CARD, relief="flat", bd=1)
            card.pack(fill="x", padx=12, pady=4)
            
            # Header row
            hdr = tk.Frame(card, bg=CARD)
            hdr.pack(fill="x", padx=10, pady=(6, 4))
            
            tk.Label(
                hdr,
                text=f"{icon} {seg.get('source', 'unknown')}",
                bg=CARD, fg=color,
                font=("Segoe UI", 9, "bold")
            ).pack(side="left")
            
            pri = seg.get("priority", 0)
            tk.Label(
                hdr,
                text=f"P:{int(pri)}",
                bg=CARD, fg=color,
                font=("Segoe UI", 8)
            ).pack(side="right")
            
            # Title
            title = seg.get("title", "No title")
            if title:
                tk.Label(
                    card,
                    text=title[:80] + ("..." if len(title) > 80 else ""),
                    bg=CARD, fg=TXT,
                    font=("Segoe UI", 9),
                    wraplength=360,
                    justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 4))
            
            # Angle
            angle = seg.get("angle", "")
            if angle:
                tk.Label(
                    card,
                    text=f"→ {angle[:100]}",
                    bg=CARD, fg=MUTED,
                    font=("Segoe UI", 8),
                    wraplength=360,
                    justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 6))
        
        def render_stats(segments: List[Dict[str, Any]], parent_frame: tk.Frame):
            """Render statistics view"""
            from collections import Counter
            
            # Status counts
            status_counts = Counter(s.get("status", "unknown") for s in segments)
            
            stats_card = tk.Frame(parent_frame, bg=CARD)
            stats_card.pack(fill="x", padx=12, pady=8)
            
            tk.Label(
                stats_card,
                text="Status Distribution",
                bg=CARD, fg=ACCENT,
                font=("Segoe UI", 10, "bold")
            ).pack(anchor="w", padx=10, pady=(8, 4))
            
            for status, color in [("queued", QUEUED), ("claimed", CLAIMED), ("done", DONE)]:
                count = status_counts.get(status, 0)
                
                row = tk.Frame(stats_card, bg=CARD)
                row.pack(fill="x", padx=10, pady=2)
                
                tk.Label(
                    row,
                    text=f"{status.title()}:",
                    bg=CARD, fg=MUTED,
                    font=("Segoe UI", 9),
                    width=10,
                    anchor="w"
                ).pack(side="left")
                
                tk.Label(
                    row,
                    text=str(count),
                    bg=CARD, fg=color,
                    font=("Segoe UI", 9, "bold")
                ).pack(side="left", padx=4)
                
                # Simple bar
                if count > 0:
                    bar_width = min(count * 10, 200)
                    bar = tk.Frame(row, bg=color, width=bar_width, height=8)
                    bar.pack(side="left", padx=4)
                    bar.pack_propagate(False)
            
            tk.Frame(stats_card, bg=CARD, height=4).pack()
            
            # Source counts
            source_counts = Counter(s.get("source", "unknown") for s in segments)
            
            src_card = tk.Frame(parent_frame, bg=CARD)
            src_card.pack(fill="x", padx=12, pady=8)
            
            tk.Label(
                src_card,
                text="Source Distribution",
                bg=CARD, fg=ACCENT,
                font=("Segoe UI", 10, "bold")
            ).pack(anchor="w", padx=10, pady=(8, 4))
            
            for source, count in source_counts.most_common(10):
                row = tk.Frame(src_card, bg=CARD)
                row.pack(fill="x", padx=10, pady=2)
                
                tk.Label(
                    row,
                    text=f"{source}:",
                    bg=CARD, fg=MUTED,
                    font=("Segoe UI", 9),
                    width=15,
                    anchor="w"
                ).pack(side="left")
                
                tk.Label(
                    row,
                    text=str(count),
                    bg=CARD, fg=TXT,
                    font=("Segoe UI", 9)
                ).pack(side="left", padx=4)
            
            tk.Frame(src_card, bg=CARD, height=8).pack()
        
        def render():
            """Main render function"""
            # Clear content
            for w in content.winfo_children():
                w.destroy()
            
            # Update tab button colors
            current_view = view_var.get()
            for view_name, btn in root._tab_btns.items():
                if view_name == current_view:
                    btn.config(bg=CARD, fg=ACCENT)
                else:
                    btn.config(bg=SURFACE, fg=MUTED)
            
            segments = get_segments()
            
            # Update stats label
            queued_count = len([s for s in segments if s.get("status") == "queued"])
            claimed_count = len([s for s in segments if s.get("status") == "claimed"])
            stats_label.config(text=f"Q:{queued_count} • F:{claimed_count}")
            
            if not segments:
                tk.Label(
                    content,
                    text="No segments in database yet.\nProducer will start generating soon.",
                    bg=BG, fg=MUTED,
                    font=("Segoe UI", 10),
                    justify="center"
                ).pack(expand=True, pady=40)
                return
            
            view = view_var.get()
            
            if view == "stats":
                render_stats(segments, content)
            else:
                # Filter by status
                if view == "queue":
                    filtered = [s for s in segments if s.get("status") == "queued"]
                elif view == "claimed":
                    filtered = [s for s in segments if s.get("status") == "claimed"]
                elif view == "recent":
                    filtered = [s for s in segments if s.get("status") == "done"][:20]
                else:
                    filtered = segments
                
                if not filtered:
                    tk.Label(
                        content,
                        text=f"No {view} segments.",
                        bg=BG, fg=MUTED,
                        font=("Segoe UI", 10)
                    ).pack(pady=20)
                else:
                    for seg in filtered:
                        render_segment_card(seg, content)
        
        def tick():
            """Auto-refresh loop"""
            try:
                render()
            except Exception:
                pass
            root.after(2000, tick)  # Refresh every 2 seconds
        
        tick()
        root.pack(fill="both", expand=True)
        return root
    
    registry.register(
        "producer_timeline",
        producer_timeline_factory,
        title="Producer Timeline",
        default_panel="right"
    )
