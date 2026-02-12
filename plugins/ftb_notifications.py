"""
FTB Notifications Plugin

Provides toast notifications and notification center for important game events:
- Race results (player team)
- Sponsorship offers
- Penalties & infractions
- Contract expirations
- Financial warnings (low cash)
- Development project completions
"""

import queue
import sqlite3
import time
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime

# UI imports
try:
    import customtkinter as ctk
    from tkinter import messagebox
    HAS_UI = True
except ImportError:
    HAS_UI = False

# Runtime shim
try:
    from your_runtime import event_q, ui_q, StationEvent, log, now_ts
    HAS_RUNTIME = True
except ImportError:
    HAS_RUNTIME = False

# Plugin metadata
IS_FEED = False
PLUGIN_NAME = "FTB Notifications"
PLUGIN_DESC = "Toast notifications and notification center for game events"


@dataclass
class Notification:
    """Represents a notification"""
    notification_id: str
    timestamp: float
    category: str  # race_result, sponsorship, penalty, contract, financial, development
    title: str
    message: str
    priority: int  # 0=low, 50=normal, 100=critical
    dismissible: bool = True
    read: bool = False
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Notification':
        """Create from dictionary"""
        return Notification(**data)


# Global notification queue (in-memory)
notification_queue: queue.Queue = queue.Queue()
notification_history: List[Notification] = []
MAX_HISTORY = 100


# ==============================================================================
# Database Persistence
# ==============================================================================

def init_notifications_table(db_path: str) -> None:
    """Initialize notifications table in state database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            notification_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            priority INTEGER NOT NULL,
            dismissible INTEGER NOT NULL,
            read INTEGER NOT NULL,
            metadata TEXT
        )
    """)
    
    # Index for querying unread notifications
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_notifications_read 
        ON notifications(read, timestamp DESC)
    """)
    
    conn.commit()
    conn.close()


def write_notification(db_path: str, notif: Notification) -> None:
    """Write notification to database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    import json
    metadata_json = json.dumps(notif.metadata) if notif.metadata else None
    
    cur.execute("""
        INSERT OR REPLACE INTO notifications 
        (notification_id, timestamp, category, title, message, priority, dismissible, read, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        notif.notification_id,
        notif.timestamp,
        notif.category,
        notif.title,
        notif.message,
        notif.priority,
        1 if notif.dismissible else 0,
        1 if notif.read else 0,
        metadata_json
    ))
    
    conn.commit()
    conn.close()


def mark_notification_read(db_path: str, notification_id: str) -> None:
    """Mark notification as read"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE notifications 
        SET read = 1 
        WHERE notification_id = ?
    """, (notification_id,))
    
    conn.commit()
    conn.close()


def query_notifications(db_path: str, unread_only: bool = False, limit: int = 50) -> List[Notification]:
    """Query notifications from database"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    if unread_only:
        cur.execute("""
            SELECT notification_id, timestamp, category, title, message, priority, dismissible, read, metadata
            FROM notifications
            WHERE read = 0
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
    else:
        cur.execute("""
            SELECT notification_id, timestamp, category, title, message, priority, dismissible, read, metadata
            FROM notifications
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
    
    rows = cur.fetchall()
    conn.close()
    
    import json
    notifications = []
    for row in rows:
        metadata = json.loads(row[8]) if row[8] else None
        notif = Notification(
            notification_id=row[0],
            timestamp=row[1],
            category=row[2],
            title=row[3],
            message=row[4],
            priority=row[5],
            dismissible=bool(row[6]),
            read=bool(row[7]),
            metadata=metadata
        )
        notifications.append(notif)
    
    return notifications


def clear_old_notifications(db_path: str, days_to_keep: int = 30) -> None:
    """Clear notifications older than specified days"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cutoff_timestamp = time.time() - (days_to_keep * 86400)
    
    cur.execute("""
        DELETE FROM notifications
        WHERE timestamp < ? AND read = 1
    """, (cutoff_timestamp,))
    
    conn.commit()
    conn.close()


def clear_all_notifications(db_path: str) -> None:
    """Clear all notifications from database (used when starting new game or loading save)"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("DELETE FROM notifications")
    
    conn.commit()
    conn.close()


def mark_all_as_read(db_path: str) -> None:
    """Mark all notifications as read"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("UPDATE notifications SET read = 1")
    
    conn.commit()
    conn.close()


# ==============================================================================
# Notification Creation Helpers
# ==============================================================================

def create_notification(
    category: str,
    title: str,
    message: str,
    priority: int = 50,
    metadata: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None
) -> Notification:
    """Create and queue a notification"""
    import uuid
    
    notif = Notification(
        notification_id=str(uuid.uuid4()),
        timestamp=time.time(),
        category=category,
        title=title,
        message=message,
        priority=priority,
        dismissible=True,
        read=False,
        metadata=metadata
    )
    
    # Add to in-memory queue
    notification_queue.put(notif)
    
    # Add to history
    notification_history.append(notif)
    if len(notification_history) > MAX_HISTORY:
        notification_history.pop(0)
    
    # Persist to database if path provided
    if db_path:
        try:
            write_notification(db_path, notif)
        except Exception as e:
            print(f"[FTB_NOTIF] Failed to write notification to DB: {e}")
    
    return notif


# ==============================================================================
# UI Components
# ==============================================================================

if HAS_UI:
    
    # Theme colors (matches FTB theme)
    class NotifTheme:
        BG = "#0a0e14"
        PANEL = "#151b23"
        SURFACE = "#1f2630"
        CARD = "#2a323d"
        ACCENT = "#ff6b35"
        ACCENT_HOVER = "#ff8555"
        TEXT = "#e6e8ea"
        TEXT_MUTED = "#8b92a0"
        SUCCESS = "#5ecc62"
        WARNING = "#ffa500"
        ERROR = "#ff4757"
        
        # Category colors
        CATEGORY_COLORS = {
            'race_result': '#5ecc62',
            'sponsorship': '#ffa500',
            'penalty': '#ff4757',
            'contract': '#4a9eff',
            'financial': '#ffa500',
            'development': '#9b59b6'
        }
    
    
    class NotificationToast(ctk.CTkFrame):
        """Toast notification that appears at top-right of screen"""
        
        def __init__(self, parent, notification: Notification, on_dismiss: Callable):
            # Make race results extra wide and prominent
            is_race_result = notification.category == 'race_result'
            
            super().__init__(
                parent,
                fg_color=NotifTheme.CARD,
                corner_radius=8,
                border_width=3 if is_race_result else 2,
                border_color=NotifTheme.CATEGORY_COLORS.get(notification.category, NotifTheme.ACCENT)
            )
            
            self.notification = notification
            self.on_dismiss = on_dismiss
            
            # Priority color bar - make extra wide for critical race results
            priority_color = NotifTheme.ERROR if notification.priority >= 80 else \
                           NotifTheme.WARNING if notification.priority >= 50 else \
                           NotifTheme.SUCCESS
            
            bar_width = 8 if is_race_result else 4
            priority_bar = ctk.CTkFrame(self, fg_color=priority_color, width=bar_width, corner_radius=0)
            priority_bar.pack(side="left", fill="y", padx=(0, 10))
            
            # Content
            content_frame = ctk.CTkFrame(self, fg_color="transparent")
            content_frame.pack(side="left", fill="both", expand=True, padx=10, pady=15 if is_race_result else 10)
            
            # Title - larger and bolder for race results
            title_font_size = 16 if is_race_result else 12
            title_label = ctk.CTkLabel(
                content_frame,
                text=notification.title,
                text_color=NotifTheme.TEXT if not is_race_result else NotifTheme.SUCCESS,
                font=("Arial", title_font_size, "bold"),
                anchor="w"
            )
            title_label.pack(anchor="w", fill="x")
            
            # Message - larger for race results
            message_font_size = 12 if is_race_result else 10
            wraplength = 400 if is_race_result else 280
            message_label = ctk.CTkLabel(
                content_frame,
                text=notification.message,
                text_color=NotifTheme.TEXT if is_race_result else NotifTheme.TEXT_MUTED,
                font=("Arial", message_font_size, "bold" if is_race_result else "normal"),
                anchor="w",
                wraplength=wraplength
            )
            message_label.pack(anchor="w", fill="x", pady=(5 if is_race_result else 2, 0))
            
            # Race results get a special "MUST ACKNOWLEDGE" label
            if is_race_result:
                ack_label = ctk.CTkLabel(
                    content_frame,
                    text="⚠️ CLICK TO ACKNOWLEDGE ⚠️",
                    text_color=NotifTheme.WARNING,
                    font=("Arial", 10, "bold"),
                    anchor="w"
                )
                ack_label.pack(anchor="w", fill="x", pady=(5, 0))
            
            # Dismiss button
            if notification.dismissible:
                dismiss_btn = ctk.CTkButton(
                    self,
                    text="✕",
                    command=self._handle_dismiss,
                    width=30,
                    height=30,
                    fg_color="transparent",
                    hover_color=NotifTheme.SURFACE,
                    text_color=NotifTheme.TEXT_MUTED,
                    font=("Arial", 14)
                )
                dismiss_btn.pack(side="right", padx=5)
            
            # Auto-dismiss after 5 seconds for low priority ONLY (race results never auto-dismiss)
            if notification.priority < 80:
                self.after(5000, self._handle_dismiss)
            
            # Add pulsing animation for race results
            if is_race_result:
                self._pulse_count = 0
                self._pulse_animation()
        
        def _handle_dismiss(self):
            """Handle dismiss button click"""
            if self.on_dismiss:
                self.on_dismiss(self.notification)
        
        def _pulse_animation(self):
            """Pulsing border animation for critical race result notifications"""
            if self._pulse_count >= 10:  # Pulse 10 times
                return
            
            self._pulse_count += 1
            
            # Alternate between bright and normal
            if self._pulse_count % 2 == 0:
                self.configure(border_color=NotifTheme.SUCCESS)
            else:
                self.configure(border_color=NotifTheme.WARNING)
            
            # Continue pulsing
            self.after(500, self._pulse_animation)
    
    
    class RaceResultModal(ctk.CTkToplevel):
        """Modal dialog specifically for race results - demands attention!"""
        
        def __init__(self, parent, notification: Notification):
            super().__init__(parent)
            
            # Modal configuration
            self.title("🏁 RACE RESULT")
            self.geometry("500x300")
            self.configure(fg_color=NotifTheme.BG)
            
            # Make modal
            self.transient(parent)
            self.grab_set()
            
            # Center window
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (250)
            y = (self.winfo_screenheight() // 2) - (150)
            self.geometry(f"500x300+{x}+{y}")
            
            # Prevent closing without acknowledgment
            self.protocol("WM_DELETE_WINDOW", self._on_acknowledge)
            
            self._build_ui(notification)
        
        def _build_ui(self, notification: Notification):
            """Build the race result modal UI"""
            
            # Main container with padding
            container = ctk.CTkFrame(self, fg_color=NotifTheme.PANEL, corner_radius=12)
            container.pack(fill="both", expand=True, padx=20, pady=20)
            
            # Header with checkered flag icon
            header = ctk.CTkLabel(
                container,
                text="🏁 RACE COMPLETE 🏁",
                text_color=NotifTheme.TEXT,
                font=("Arial", 24, "bold")
            )
            header.pack(pady=(20, 10))
            
            # Title (position and track)
            title = ctk.CTkLabel(
                container,
                text=notification.title,
                text_color=NotifTheme.SUCCESS,
                font=("Arial", 20, "bold"),
                wraplength=420
            )
            title.pack(pady=10)
            
            # Message (details)
            message = ctk.CTkLabel(
                container,
                text=notification.message,
                text_color=NotifTheme.TEXT,
                font=("Arial", 14),
                wraplength=420,
                justify="center"
            )
            message.pack(pady=10)
            
            # Acknowledge button (large and prominent)
            ack_btn = ctk.CTkButton(
                container,
                text="✓ ACKNOWLEDGED",
                command=self._on_acknowledge,
                font=("Arial", 16, "bold"),
                fg_color=NotifTheme.SUCCESS,
                hover_color=NotifTheme.ACCENT_HOVER,
                height=50,
                width=200
            )
            ack_btn.pack(pady=20)
            
            # Focus the window and button
            self.focus_force()
            ack_btn.focus_set()
        
        def _on_acknowledge(self):
            """Close modal when acknowledged"""
            self.grab_release()
            self.destroy()
    
    
    class NotificationCenter(ctk.CTkToplevel):
        """Notification center window showing notification history"""
        
        def __init__(self, parent, db_path: str):
            super().__init__(parent)
            
            self.db_path = db_path
            
            # Window config
            self.title("Notification Center")
            self.geometry("600x700")
            self.configure(fg_color=NotifTheme.BG)
            
            # Make modal
            self.transient(parent)
            self.grab_set()
            
            # Center window
            self.update_idletasks()
            x = (self.winfo_screenwidth() // 2) - (600 // 2)
            y = (self.winfo_screenheight() // 2) - (700 // 2)
            self.geometry(f"600x700+{x}+{y}")
            
            self._build_ui()
            self._load_notifications()
        
        def _build_ui(self):
            """Build UI"""
            # Header
            header = ctk.CTkFrame(self, fg_color=NotifTheme.PANEL, corner_radius=0)
            header.pack(fill="x")
            
            title = ctk.CTkLabel(
                header,
                text="🔔 Notifications",
                text_color=NotifTheme.TEXT,
                font=("Arial", 18, "bold")
            )
            title.pack(side="left", padx=20, pady=15)
            
            # Filter buttons
            filter_frame = ctk.CTkFrame(header, fg_color="transparent")
            filter_frame.pack(side="right", padx=20)
            
            self.filter_var = ctk.StringVar(value="all")
            
            all_btn = ctk.CTkRadioButton(
                filter_frame,
                text="All",
                variable=self.filter_var,
                value="all",
                command=self._load_notifications,
                fg_color=NotifTheme.ACCENT
            )
            all_btn.pack(side="left", padx=5)
            
            unread_btn = ctk.CTkRadioButton(
                filter_frame,
                text="Unread",
                variable=self.filter_var,
                value="unread",
                command=self._load_notifications,
                fg_color=NotifTheme.ACCENT
            )
            unread_btn.pack(side="left", padx=5)
            
            # Scrollable content
            self.scroll_frame = ctk.CTkScrollableFrame(
                self,
                fg_color=NotifTheme.BG,
                scrollbar_button_color=NotifTheme.SURFACE,
                scrollbar_button_hover_color=NotifTheme.CARD
            )
            self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        def _load_notifications(self):
            """Load notifications from database"""
            # Clear existing
            for widget in self.scroll_frame.winfo_children():
                widget.destroy()
            
            # Load from DB
            try:
                unread_only = (self.filter_var.get() == "unread")
                notifications = query_notifications(self.db_path, unread_only=unread_only, limit=50)
                
                if not notifications:
                    no_data = ctk.CTkLabel(
                        self.scroll_frame,
                        text="No notifications",
                        text_color=NotifTheme.TEXT_MUTED,
                        font=("Arial", 12)
                    )
                    no_data.pack(pady=50)
                    return
                
                for notif in notifications:
                    self._add_notification_card(notif)
                    
            except Exception as e:
                error_label = ctk.CTkLabel(
                    self.scroll_frame,
                    text=f"Error loading notifications: {e}",
                    text_color=NotifTheme.ERROR,
                    font=("Arial", 11)
                )
                error_label.pack(pady=20)
        
        def _add_notification_card(self, notif: Notification):
            """Add notification card to list"""
            card = ctk.CTkFrame(
                self.scroll_frame,
                fg_color=NotifTheme.SURFACE if notif.read else NotifTheme.CARD,
                corner_radius=8,
                border_width=1 if not notif.read else 0,
                border_color=NotifTheme.CATEGORY_COLORS.get(notif.category, NotifTheme.ACCENT)
            )
            card.pack(fill="x", pady=5)
            
            # Category badge
            category_color = NotifTheme.CATEGORY_COLORS.get(notif.category, NotifTheme.ACCENT)
            category_badge = ctk.CTkLabel(
                card,
                text=notif.category.replace('_', ' ').title(),
                text_color=NotifTheme.TEXT,
                fg_color=category_color,
                corner_radius=4,
                font=("Arial", 9, "bold"),
                padx=8,
                pady=2
            )
            category_badge.pack(anchor="nw", padx=15, pady=(15, 5))
            
            # Title
            title = ctk.CTkLabel(
                card,
                text=notif.title,
                text_color=NotifTheme.TEXT,
                font=("Arial", 12, "bold"),
                anchor="w"
            )
            title.pack(anchor="w", padx=15, pady=(0, 5), fill="x")
            
            # Message
            message = ctk.CTkLabel(
                card,
                text=notif.message,
                text_color=NotifTheme.TEXT_MUTED,
                font=("Arial", 10),
                anchor="w",
                wraplength=520,
                justify="left"
            )
            message.pack(anchor="w", padx=15, pady=(0, 5), fill="x")
            
            # Timestamp
            from datetime import datetime
            dt = datetime.fromtimestamp(notif.timestamp)
            time_str = dt.strftime("%b %d, %Y %I:%M %p")
            
            timestamp = ctk.CTkLabel(
                card,
                text=time_str,
                text_color=NotifTheme.TEXT_MUTED,
                font=("Arial", 9),
                anchor="w"
            )
            timestamp.pack(anchor="w", padx=15, pady=(0, 15))
            
            # Mark as read on click
            if not notif.read:
                card.bind("<Button-1>", lambda e: self._mark_read(notif.notification_id))
    
        def _mark_read(self, notification_id: str):
            """Mark notification as read"""
            try:
                mark_notification_read(self.db_path, notification_id)
                self._load_notifications()
            except Exception as e:
                print(f"[FTB_NOTIF] Failed to mark as read: {e}")


# ==============================================================================
# Widget Registration
# ==============================================================================

def register_widgets(registry: Dict[str, Any], runtime_stub: Any) -> None:
    """Register notification widgets"""
    if not HAS_UI:
        return
    
    # We'll add a notification bell icon to the main FTB UI
    # This is integrated directly into ftb_game.py's UI
    pass


# ==============================================================================
# Feed Worker (not used, but required for plugin interface)
# ==============================================================================

def feed_worker(runtime: Dict[str, Any]) -> None:
    """Not used - notifications are created directly by game events"""
    pass


if __name__ == "__main__":
    print("FTB Notifications Plugin")
    print("This plugin provides toast notifications and notification center")
