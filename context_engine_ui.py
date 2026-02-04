"""
Context Engine UI Helper for shell.py
======================================

Reusable widget for configuring character context engines.
Used by both StationWizard and EditorWindow.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json


def build_context_engine_ui(parent, bg, surface, text_color, muted, accent, get_context_cfg_func, set_context_cfg_func, station_dir=""):
    """
    Build a context engine configuration UI.
    
    Args:
        parent: Parent frame
        bg: Background color
        surface: Surface color  
        text_color: Text color
        muted: Muted text color
        accent: Accent color
        get_context_cfg_func: Callable that returns current context_engine dict
        set_context_cfg_func: Callable(dict) to save context_engine config
        station_dir: Station directory for file browsing
    
    Returns:
        Frame containing the context engine UI
    """
    
    frame = tk.Frame(parent, bg=bg)
    
    # Header
    header = tk.Frame(frame, bg=bg)
    header.pack(fill="x", pady=(10, 5))
    
    tk.Label(
        header,
        text="⚡ Context Engine (Optional)",
        bg=bg, fg=accent,
        font=("Segoe UI", 10, "bold")
    ).pack(side="left")
    
    # Enabled toggle
    enabled_var = tk.BooleanVar()
    
    def update_ui_state():
        """Enable/disable fields based on enabled state"""
        state = "normal" if enabled_var.get() else "disabled"
        type_combo.config(state="readonly" if enabled_var.get() else "disabled")
        desc_entry.config(state=state)
        source_entry.config(state=state)
        browse_btn.config(state=state)
        test_btn.config(state=state)
        
        # Show/hide type-specific fields
        update_type_fields()
    
    tk.Checkbutton(
        header,
        text="Enable",
        variable=enabled_var,
        bg=bg, fg=text_color,
        selectcolor=surface,
        activebackground=bg,
        activeforeground=accent,
        command=update_ui_state
    ).pack(side="left", padx=10)
    
    # Type selection
    type_frame = tk.Frame(frame, bg=bg)
    type_frame.pack(fill="x", pady=5)
    
    tk.Label(type_frame, text="Type:", bg=bg, fg=muted, width=12, anchor="w").pack(side="left")
    
    type_var = tk.StringVar(value="api")
    type_combo = ttk.Combobox(
        type_frame,
        textvariable=type_var,
        values=["api", "db", "text"],
        state="readonly",
        width=15
    )
    type_combo.pack(side="left", padx=5)
    type_combo.bind("<<ComboboxSelected>>", lambda e: update_type_fields())
    
    # Description
    desc_frame = tk.Frame(frame, bg=bg)
    desc_frame.pack(fill="x", pady=5)
    
    tk.Label(desc_frame, text="Description:", bg=bg, fg=muted, width=12, anchor="w").pack(side="left")
    
    desc_var = tk.StringVar()
    desc_entry = tk.Entry(
        desc_frame,
        textvariable=desc_var,
        bg=surface, fg=text_color,
        insertbackground=text_color
    )
    desc_entry.pack(side="left", fill="x", expand=True, padx=5)
    
    # Source (URL, file path, or directory)
    source_frame = tk.Frame(frame, bg=bg)
    source_frame.pack(fill="x", pady=5)
    
    source_label = tk.Label(source_frame, text="Source:", bg=bg, fg=muted, width=12, anchor="w")
    source_label.pack(side="left")
    
    source_var = tk.StringVar()
    source_entry = tk.Entry(
        source_frame,
        textvariable=source_var,
        bg=surface, fg=text_color,
        insertbackground=text_color
    )
    source_entry.pack(side="left", fill="x", expand=True, padx=5)
    
    browse_btn = tk.Button(
        source_frame,
        text="Browse...",
        bg=surface, fg=text_color,
        relief="flat",
        command=lambda: browse_source()
    )
    browse_btn.pack(side="left", padx=2)
    
    def browse_source():
        engine_type = type_var.get()
        if engine_type == "db":
            path = filedialog.askopenfilename(
                parent=parent,
                title="Select SQLite Database",
                filetypes=[("SQLite DB", "*.db *.sqlite"), ("All Files", "*.*")]
            )
        elif engine_type == "text":
            path = filedialog.askdirectory(parent=parent, title="Select Text Files Directory")
        else:
            return  # API doesn't need browse
        
        if path:
            source_var.set(path)
    
    # Type-specific config area
    type_config_frame = tk.Frame(frame, bg=bg)
    type_config_frame.pack(fill="both", expand=True, pady=5)
    
    # API-specific fields
    api_frame = tk.Frame(type_config_frame, bg=bg)
    
    api_key_env_var = tk.StringVar()
    api_method_var = tk.StringVar(value="GET")
    auth_type_var = tk.StringVar(value="bearer")
    
    def make_api_field(parent_frame, label, var):
        row = tk.Frame(parent_frame, bg=bg)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=label, bg=bg, fg=muted, width=15, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var, bg=surface, fg=text_color, insertbackground=text_color).pack(side="left", fill="x", expand=True, padx=5)
    
    make_api_field(api_frame, "API Key (env var):", api_key_env_var)
    
    method_row = tk.Frame(api_frame, bg=bg)
    method_row.pack(fill="x", pady=3)
    tk.Label(method_row, text="Method:", bg=bg, fg=muted, width=15, anchor="w").pack(side="left")
    ttk.Combobox(method_row, textvariable=api_method_var, values=["GET", "POST"], state="readonly", width=10).pack(side="left", padx=5)
    
    auth_row = tk.Frame(api_frame, bg=bg)
    auth_row.pack(fill="x", pady=3)
    tk.Label(auth_row, text="Auth Type:", bg=bg, fg=muted, width=15, anchor="w").pack(side="left")
    ttk.Combobox(auth_row, textvariable=auth_type_var, values=["bearer", "apikey", "none"], state="readonly", width=10).pack(side="left", padx=5)
    
    # DB-specific fields
    db_frame = tk.Frame(type_config_frame, bg=bg)
    
    db_query_var = tk.StringVar()
    tk.Label(db_frame, text="SQL Query (use {param} placeholders):", bg=bg, fg=muted).pack(anchor="w", pady=(5, 2))
    db_query_text = tk.Text(db_frame, height=3, bg=surface, fg=text_color, insertbackground=text_color, wrap="word")
    db_query_text.pack(fill="x", pady=5)
    
    # Text-specific fields
    text_frame = tk.Frame(type_config_frame, bg=bg)
    
    search_mode_var = tk.StringVar(value="keyword")
    max_results_var = tk.IntVar(value=5)
    
    search_row = tk.Frame(text_frame, bg=bg)
    search_row.pack(fill="x", pady=3)
    tk.Label(search_row, text="Search Mode:", bg=bg, fg=muted, width=15, anchor="w").pack(side="left")
    ttk.Combobox(search_row, textvariable=search_mode_var, values=["keyword", "semantic"], state="readonly", width=10).pack(side="left", padx=5)
    
    results_row = tk.Frame(text_frame, bg=bg)
    results_row.pack(fill="x", pady=3)
    tk.Label(results_row, text="Max Results:", bg=bg, fg=muted, width=15, anchor="w").pack(side="left")
    tk.Spinbox(results_row, from_=1, to=20, textvariable=max_results_var, bg=surface, fg=text_color, width=10).pack(side="left", padx=5)
    
    # Cache TTL (common to all)
    cache_frame = tk.Frame(frame, bg=bg)
    cache_frame.pack(fill="x", pady=5)
    
    tk.Label(cache_frame, text="Cache TTL (sec):", bg=bg, fg=muted, width=12, anchor="w").pack(side="left")
    
    cache_ttl_var = tk.IntVar(value=300)
    tk.Spinbox(
        cache_frame,
        from_=0, to=7200,
        textvariable=cache_ttl_var,
        bg=surface, fg=text_color,
        width=10
    ).pack(side="left", padx=5)
    
    # Test button
    test_btn = tk.Button(
        frame,
        text="🧪 Test Query",
        bg=accent, fg="#000",
        relief="flat",
        command=lambda: test_context_engine()
    )
    test_btn.pack(anchor="w", pady=10)
    
    def update_type_fields():
        """Show/hide type-specific configuration"""
        api_frame.pack_forget()
        db_frame.pack_forget()
        text_frame.pack_forget()
        
        engine_type = type_var.get()
        
        if engine_type == "api":
            source_label.config(text="API URL:")
            api_frame.pack(fill="x")
            browse_btn.pack_forget()
        elif engine_type == "db":
            source_label.config(text="DB Path:")
            db_frame.pack(fill="x")
            browse_btn.pack(side="left", padx=2)
        elif engine_type == "text":
            source_label.config(text="Directory:")
            text_frame.pack(fill="x")
            browse_btn.pack(side="left", padx=2)
    
    def test_context_engine():
        """Test the configured context engine"""
        if not enabled_var.get():
            messagebox.showinfo("Test", "Context engine is disabled.")
            return
        
        config = get_current_config()
        
        test_params = {}
        param_win = tk.Toplevel(parent)
        param_win.title("Test Parameters")
        param_win.geometry("400x300")
        param_win.configure(bg=bg)
        param_win.grab_set()
        
        tk.Label(
            param_win,
            text="Enter test query parameters (JSON):",
            bg=bg, fg=text_color,
            font=("Segoe UI", 10)
        ).pack(pady=10)
        
        tk.Label(
            param_win,
            text="Example: {\"player\": \"LeBron\", \"team\": \"Lakers\"}",
            bg=bg, fg=muted,
            font=("Segoe UI", 8)
        ).pack()
        
        params_text = tk.Text(param_win, height=10, bg=surface, fg=text_color, insertbackground=text_color)
        params_text.pack(fill="both", expand=True, padx=10, pady=10)
        params_text.insert("1.0", "{}")
        
        def run_test():
            try:
                params_json = params_text.get("1.0", "end").strip()
                test_params = json.loads(params_json)
                
                # Import and test
                from context_engine import query_context_engine, format_context_for_prompt
                
                result = query_context_engine(config, test_params, station_dir)
                
                if result:
                    formatted = format_context_for_prompt(result, config.get("type", "unknown"))
                    messagebox.showinfo("Test Success", f"Context retrieved!\n\n{formatted[:500]}...")
                else:
                    messagebox.showwarning("Test Result", "No data returned. Check configuration.")
                
                param_win.destroy()
            except json.JSONDecodeError:
                messagebox.showerror("Error", "Invalid JSON in parameters.")
            except Exception as e:
                messagebox.showerror("Test Error", f"Context engine test failed:\n\n{e}")
        
        tk.Button(
            param_win,
            text="Run Test",
            bg=accent, fg="#000",
            relief="flat",
            command=run_test
        ).pack(pady=10)
    
    def get_current_config():
        """Get current UI state as config dict"""
        config = {
            "enabled": enabled_var.get(),
            "type": type_var.get(),
            "description": desc_var.get(),
            "source": source_var.get(),
            "cache_ttl": cache_ttl_var.get()
        }
        
        if type_var.get() == "api":
            config["api_key_env"] = api_key_env_var.get()
            config["method"] = api_method_var.get()
            config["auth_type"] = auth_type_var.get()
        elif type_var.get() == "db":
            config["query"] = db_query_text.get("1.0", "end").strip()
        elif type_var.get() == "text":
            config["search_mode"] = search_mode_var.get()
            config["max_results"] = max_results_var.get()
        
        return config
    
    def load_config(config):
        """Load config into UI"""
        if not config or not isinstance(config, dict):
            config = {}
        
        enabled_var.set(config.get("enabled", False))
        type_var.set(config.get("type", "api"))
        desc_var.set(config.get("description", ""))
        source_var.set(config.get("source", ""))
        cache_ttl_var.set(config.get("cache_ttl", 300))
        
        # Type-specific
        if config.get("type") == "api":
            api_key_env_var.set(config.get("api_key_env", ""))
            api_method_var.set(config.get("method", "GET"))
            auth_type_var.set(config.get("auth_type", "bearer"))
        elif config.get("type") == "db":
            db_query_text.delete("1.0", "end")
            db_query_text.insert("1.0", config.get("query", ""))
        elif config.get("type") == "text":
            search_mode_var.set(config.get("search_mode", "keyword"))
            max_results_var.set(config.get("max_results", 5))
        
        update_type_fields()
        update_ui_state()
    
    # Load initial config
    initial_cfg = get_context_cfg_func()
    load_config(initial_cfg)
    
    # Store functions on frame for external access
    frame.get_config = get_current_config
    frame.load_config = load_config
    
    return frame
