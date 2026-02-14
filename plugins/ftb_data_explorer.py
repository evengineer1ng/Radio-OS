"""
FTB Data Explorer Plugin - Direct DB Query Interface

Provides on-demand database queries for historical data exploration
without loading everything into the main game state.
"""

from typing import Any, Dict, List, Optional
import sqlite3
from plugins import ftb_state_db

PLUGIN_NAME = "FTB Data Explorer"
PLUGIN_DESC = "Historical data exploration interface"
IS_FEED = False


def register_widgets(registry: Dict[str, Any], runtime_stub: Any) -> None:
    """Register data explorer query endpoints"""
    
    # Get the cold (archival) database path from runtime
    station_dir = runtime_stub.get('STATION_DIR', '')
    cold_db_path = None
    
    # Try to get cold DB path from station directory
    if station_dir:
        import os
        cold_db_path = os.path.join(station_dir, 'ftb_state_cold.db')
        if not os.path.exists(cold_db_path):
            print(f"[FTB Data Explorer] Cold DB not found at {cold_db_path}, queries may fail")
    
    # Register using the proper WidgetRegistry.register() method
    # Or if it's a dict, use dict assignment
    if hasattr(registry, 'register'):
        # It's a WidgetRegistry object - create a single widget with query methods
        def data_explorer_factory(parent, runtime):
            """Factory for data explorer widget"""
            try:
                import tkinter as tk
                from tkinter import ttk
                
                frame = ttk.Frame(parent)
                
                ttk.Label(frame, text="Data Explorer", font=('Arial', 14, 'bold')).pack(pady=10)
                ttk.Label(frame, text="Historical data queries available via ftb_cmd_q").pack(pady=5)
                
                # Show DB path
                if cold_db_path:
                    ttk.Label(frame, text=f"Database: {cold_db_path}", font=('Arial', 9)).pack(pady=5)
                
                return frame
            except Exception as e:
                print(f"[FTB Data Explorer] Error creating widget: {e}")
                return None
        
        registry.register('ftb_data_explorer', data_explorer_factory, title="Data Explorer")
    else:
        # Fallback: treat as dict
        registry['ftb_data_queries'] = {
            'query_season_summaries': lambda **kwargs: query_season_summaries(cold_db_path, **kwargs),
            'query_race_history': lambda **kwargs: query_race_history(cold_db_path, **kwargs),
            'query_financial_history': lambda **kwargs: query_financial_history(cold_db_path, **kwargs),
            'query_career_stats': lambda **kwargs: query_career_stats(cold_db_path, **kwargs),
            'query_team_outcomes': lambda **kwargs: query_team_outcomes(cold_db_path, **kwargs),
            'query_championship_history': lambda **kwargs: query_championship_history(cold_db_path, **kwargs),
        }
    
    # Also store the query functions directly on the runtime for easy access
    if hasattr(runtime_stub, '__setitem__'):
        runtime_stub['ftb_data_queries'] = {
            'query_season_summaries': lambda **kwargs: query_season_summaries(cold_db_path, **kwargs),
            'query_race_history': lambda **kwargs: query_race_history(cold_db_path, **kwargs),
            'query_financial_history': lambda **kwargs: query_financial_history(cold_db_path, **kwargs),
            'query_career_stats': lambda **kwargs: query_career_stats(cold_db_path, **kwargs),
            'query_team_outcomes': lambda **kwargs: query_team_outcomes(cold_db_path, **kwargs),
            'query_championship_history': lambda **kwargs: query_championship_history(cold_db_path, **kwargs),
        }


def query_season_summaries(db_path: str, team_name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get season summary records"""
    if not db_path:
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if team_name:
            cursor.execute("""
                SELECT * FROM season_summaries
                WHERE team_name = ?
                ORDER BY season DESC
                LIMIT ?
            """, (team_name, limit))
        else:
            cursor.execute("""
                SELECT * FROM season_summaries
                ORDER BY season DESC, total_points DESC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[FTB Data] Error querying season summaries: {e}")
        return []


def query_race_history(db_path: str, team_name: Optional[str] = None, season: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get race result history"""
    if not db_path:
        return []
    
    try:
        results = ftb_state_db.query_race_results(
            db_path,
            team_names=[team_name] if team_name else None,
            seasons=[season] if season else None,
            limit=limit
        )
        return results
    except Exception as e:
        print(f"[FTB Data] Error querying race history: {e}")
        return []


def query_financial_history(db_path: str, team_name: Optional[str] = None, season: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Get financial transaction history"""
    if not db_path:
        return []
    
    try:
        transactions = ftb_state_db.query_financial_transactions(
            db_path,
            team_names=[team_name] if team_name else None,
            seasons=[season] if season else None,
            limit=limit
        )
        return transactions
    except Exception as e:
        print(f"[FTB Data] Error querying financial history: {e}")
        return []


def query_career_stats(db_path: str, entity_name: Optional[str] = None, role: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get career statistics for drivers/engineers"""
    if not db_path:
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM career_totals WHERE 1=1"
        params = []
        
        if entity_name:
            query += " AND entity_name = ?"
            params.append(entity_name)
        
        if role:
            query += " AND role = ?"
            params.append(role)
        
        query += " ORDER BY races_entered DESC LIMIT 100"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[FTB Data] Error querying career stats: {e}")
        return []


def query_team_outcomes(db_path: str, team_name: Optional[str] = None, season: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get team outcome records for ML training"""
    if not db_path:
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM team_outcomes WHERE 1=1"
        params = []
        
        if team_name:
            query += " AND team_name = ?"
            params.append(team_name)
        
        if season:
            query += " AND season = ?"
            params.append(season)
        
        query += " ORDER BY season DESC, championship_position ASC LIMIT 100"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[FTB Data] Error querying team outcomes: {e}")
        return []


def query_championship_history(db_path: str, league_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Get championship history records"""
    if not db_path:
        return []
    
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if league_id:
            cursor.execute("""
                SELECT * FROM championship_history
                WHERE league_id = ?
                ORDER BY season DESC, championship_position ASC
                LIMIT ?
            """, (league_id, limit))
        else:
            cursor.execute("""
                SELECT * FROM championship_history
                ORDER BY season DESC, championship_position ASC
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[FTB Data] Error querying championship history: {e}")
        return []


def query_all_tables(db_path: str) -> Dict[str, int]:
    """Get count of records in all tables"""
    if not db_path:
        return {}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get all table names
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        
        # Get count for each table
        counts = {}
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]
            except Exception:
                counts[table] = 0
        
        conn.close()
        return counts
    except Exception as e:
        print(f"[FTB Data] Error querying table counts: {e}")
        return {}
