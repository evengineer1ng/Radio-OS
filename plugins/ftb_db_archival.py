"""
FTB Database Archival System - Hot/Cold Database Management

Manages database size for long-running FTB simulations by:
- Maintaining a "hot" database for recent/active data
- Archiving older data to a "cold" database
- Providing transparent queries across both databases
- Preserving important historical data while reducing hot DB size

Hot database keeps:
- Current season + last N seasons of detailed data
- All career totals and aggregates (always hot)
- Active entities, teams, leagues
- Recent events buffer

Cold database stores:
- Older race results
- Older financial transactions
- Older decision history
- Historical events
"""

import sqlite3
import time
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


# Archival policy configuration
ARCHIVAL_POLICY = {
    # How many recent seasons to keep in hot database (detailed data)
    'hot_seasons_count': 3,
    
    # Tables that should NEVER be archived (always stay hot)
    'always_hot_tables': {
        'game_state_snapshot',
        'player_state',
        'teams',
        'entities',
        'league_standings',
        'job_board',
        'sponsorships',
        'free_agents',
        'narrator_context',
        'ui_context',
        'calendar_entries',
        'league_economic_state',
        'penalties',  # Recent penalties only, archived by season
        'notifications',
        
        # Career/aggregate tables - never archive these
        'team_career_totals',
        'team_pulse_metrics',
        'team_prestige',
        'team_peak_valley',
        'team_era_performance',
        'regulation_eras',
        'driver_career_stats',
        'driver_legacy',
        'driver_development_curve',
        'driver_team_stints',
        'championship_history',
        'tier_definitions',
        'team_tier_history',
        'active_streaks',
        'expectation_models',
        'narrative_heat_scores',
        'season_summaries',  # Kept for quick season-by-season view
    },
    
    # Tables to archive by season (move old seasons to cold DB)
    'archive_by_season_tables': {
        'race_results_archive': 'season',
        'financial_transactions': 'season',
        'decision_history': 'season',
        'events_buffer': None,  # Archive old events by tick/season logic
        'ai_decisions': 'season',
        'team_outcomes': 'season',
    },
    
    # Tables to archive by tick/time (not season-based)
    'archive_by_tick_tables': {
        'events_buffer': 'tick',
    },
    
    # Whether to vacuum after archival
    'vacuum_after_archive': True,
    
    # Minimum hot DB size before archival is suggested (MB)
    'archive_threshold_mb': 500,
}


def get_db_size_mb(db_path: str) -> float:
    """Get database file size in megabytes."""
    try:
        size_bytes = Path(db_path).stat().st_size
        return size_bytes / (1024 * 1024)
    except Exception:
        return 0.0


def get_cold_db_path(hot_db_path: str) -> str:
    """Get cold database path from hot database path."""
    db_path = Path(hot_db_path)
    cold_path = db_path.parent / f"{db_path.stem}_cold{db_path.suffix}"
    return str(cold_path)


def init_cold_db(cold_db_path: str, hot_db_path: str) -> None:
    """
    Initialize cold database with same schema as hot database.
    
    Args:
        cold_db_path: Path to cold database
        hot_db_path: Path to hot database (to copy schema from)
    """
    # Get schema from hot database
    hot_conn = sqlite3.connect(hot_db_path)
    hot_cursor = hot_conn.cursor()
    
    # Get all CREATE TABLE statements from hot DB
    hot_cursor.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type='table' AND sql IS NOT NULL
        ORDER BY name
    """)
    create_statements = [row[0] for row in hot_cursor.fetchall()]
    
    # Get all CREATE INDEX statements from hot DB
    hot_cursor.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type='index' AND sql IS NOT NULL
        ORDER BY name
    """)
    index_statements = [row[0] for row in hot_cursor.fetchall()]
    
    hot_conn.close()
    
    # Create cold database with same schema
    cold_conn = sqlite3.connect(cold_db_path)
    cold_cursor = cold_conn.cursor()
    
    for stmt in create_statements:
        try:
            cold_cursor.execute(stmt)
        except sqlite3.Error as e:
            print(f"[FTB Archival] Warning: Could not create table in cold DB: {e}")
    
    for stmt in index_statements:
        try:
            cold_cursor.execute(stmt)
        except sqlite3.Error as e:
            print(f"[FTB Archival] Warning: Could not create index in cold DB: {e}")
    
    cold_conn.commit()
    cold_conn.close()
    
    print(f"[FTB Archival] Initialized cold database: {cold_db_path}")


def get_current_season(hot_db_path: str) -> int:
    """Get current season from hot database."""
    conn = sqlite3.connect(hot_db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT season FROM game_state_snapshot WHERE id = 1")
        row = cursor.fetchone()
        season = row[0] if row else 1
    except Exception:
        season = 1
    
    conn.close()
    return season


def archive_old_data(hot_db_path: str, cold_db_path: Optional[str] = None, 
                     verbose: bool = True) -> Dict[str, Any]:
    """
    Archive old data from hot database to cold database.
    
    Args:
        hot_db_path: Path to hot database
        cold_db_path: Path to cold database (auto-generated if None)
        verbose: Whether to print progress
    
    Returns:
        Dictionary with archival statistics
    """
    if cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    # Check if cold DB exists, create if not
    if not Path(cold_db_path).exists():
        if verbose:
            print(f"[FTB Archival] Creating cold database...")
        init_cold_db(cold_db_path, hot_db_path)
    
    current_season = get_current_season(hot_db_path)
    hot_seasons_count = ARCHIVAL_POLICY['hot_seasons_count']
    archive_cutoff_season = current_season - hot_seasons_count
    
    if verbose:
        print(f"[FTB Archival] Current season: {current_season}")
        print(f"[FTB Archival] Archiving data older than season {archive_cutoff_season}")
    
    stats = {
        'archived_rows': {},
        'deleted_rows': {},
        'tables_processed': [],
        'errors': [],
        'start_time': time.time(),
    }
    
    hot_conn = sqlite3.connect(hot_db_path)
    cold_conn = sqlite3.connect(cold_db_path)
    
    hot_cursor = hot_conn.cursor()
    cold_cursor = cold_conn.cursor()
    
    try:
        # Archive season-based tables
        for table, season_col in ARCHIVAL_POLICY['archive_by_season_tables'].items():
            if season_col is None:
                continue
            
            try:
                # Check if table exists
                hot_cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table,)
                )
                if not hot_cursor.fetchone():
                    continue
                
                # Get rows to archive
                hot_cursor.execute(f"""
                    SELECT * FROM {table} WHERE {season_col} < ?
                """, (archive_cutoff_season,))
                rows = hot_cursor.fetchall()
                
                if not rows:
                    if verbose:
                        print(f"[FTB Archival] {table}: No rows to archive")
                    continue
                
                # Get column names
                hot_cursor.execute(f"PRAGMA table_info({table})")
                columns = [col[1] for col in hot_cursor.fetchall()]
                placeholders = ','.join(['?' for _ in columns])
                
                # Insert into cold database
                cold_cursor.executemany(
                    f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})",
                    rows
                )
                
                # Delete from hot database
                hot_cursor.execute(f"""
                    DELETE FROM {table} WHERE {season_col} < ?
                """, (archive_cutoff_season,))
                
                deleted_count = hot_cursor.rowcount
                stats['archived_rows'][table] = len(rows)
                stats['deleted_rows'][table] = deleted_count
                stats['tables_processed'].append(table)
                
                if verbose:
                    print(f"[FTB Archival] {table}: Archived {len(rows)} rows, deleted {deleted_count} from hot DB")
            
            except Exception as e:
                error_msg = f"Error archiving {table}: {e}"
                stats['errors'].append(error_msg)
                if verbose:
                    print(f"[FTB Archival] {error_msg}")
        
        # Archive events buffer (special case - by tick and age)
        try:
            # Archive events older than 1000 ticks
            hot_cursor.execute("""
                SELECT tick FROM game_state_snapshot WHERE id = 1
            """)
            current_tick_row = hot_cursor.fetchone()
            if current_tick_row:
                current_tick = current_tick_row[0]
                archive_tick_cutoff = current_tick - 1000
                
                hot_cursor.execute("""
                    SELECT * FROM events_buffer WHERE tick < ?
                """, (archive_tick_cutoff,))
                event_rows = hot_cursor.fetchall()
                
                if event_rows:
                    hot_cursor.execute("PRAGMA table_info(events_buffer)")
                    event_columns = [col[1] for col in hot_cursor.fetchall()]
                    placeholders = ','.join(['?' for _ in event_columns])
                    
                    cold_cursor.executemany(
                        f"INSERT OR REPLACE INTO events_buffer VALUES ({placeholders})",
                        event_rows
                    )
                    
                    hot_cursor.execute("""
                        DELETE FROM events_buffer WHERE tick < ?
                    """, (archive_tick_cutoff,))
                    
                    deleted_count = hot_cursor.rowcount
                    stats['archived_rows']['events_buffer'] = len(event_rows)
                    stats['deleted_rows']['events_buffer'] = deleted_count
                    
                    if verbose:
                        print(f"[FTB Archival] events_buffer: Archived {len(event_rows)} old events")
        
        except Exception as e:
            error_msg = f"Error archiving events_buffer: {e}"
            stats['errors'].append(error_msg)
            if verbose:
                print(f"[FTB Archival] {error_msg}")
        
        # Commit changes
        hot_conn.commit()
        cold_conn.commit()
        
        # Vacuum hot database to reclaim space
        if ARCHIVAL_POLICY['vacuum_after_archive']:
            if verbose:
                print("[FTB Archival] Vacuuming hot database...")
            hot_cursor.execute("VACUUM")
            if verbose:
                print("[FTB Archival] Vacuum complete")
    
    finally:
        hot_conn.close()
        cold_conn.close()
    
    stats['end_time'] = time.time()
    stats['duration_seconds'] = stats['end_time'] - stats['start_time']
    
    if verbose:
        print(f"[FTB Archival] Complete in {stats['duration_seconds']:.2f}s")
        print(f"[FTB Archival] Hot DB size: {get_db_size_mb(hot_db_path):.2f} MB")
        print(f"[FTB Archival] Cold DB size: {get_db_size_mb(cold_db_path):.2f} MB")
    
    return stats


def query_across_databases(hot_db_path: str, query: str, params: Tuple = (),
                           cold_db_path: Optional[str] = None) -> List[Tuple]:
    """
    Execute a query across both hot and cold databases.
    
    Useful for queries that need historical data spanning both databases.
    
    Args:
        hot_db_path: Path to hot database
        query: SQL query to execute
        params: Query parameters
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        Combined results from both databases
    """
    if cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    results = []
    
    # Query hot database
    hot_conn = sqlite3.connect(hot_db_path)
    hot_cursor = hot_conn.cursor()
    try:
        hot_cursor.execute(query, params)
        results.extend(hot_cursor.fetchall())
    except sqlite3.Error as e:
        print(f"[FTB Archival] Error querying hot DB: {e}")
    finally:
        hot_conn.close()
    
    # Query cold database if it exists
    if Path(cold_db_path).exists():
        cold_conn = sqlite3.connect(cold_db_path)
        cold_cursor = cold_conn.cursor()
        try:
            cold_cursor.execute(query, params)
            results.extend(cold_cursor.fetchall())
        except sqlite3.Error as e:
            print(f"[FTB Archival] Error querying cold DB: {e}")
        finally:
            cold_conn.close()
    
    return results


def get_archival_stats(hot_db_path: str, cold_db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get statistics about hot and cold databases.
    
    Args:
        hot_db_path: Path to hot database
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        Dictionary with database statistics
    """
    if cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    stats = {
        'hot_db': {
            'path': hot_db_path,
            'size_mb': get_db_size_mb(hot_db_path),
            'exists': Path(hot_db_path).exists(),
            'table_counts': {},
        },
        'cold_db': {
            'path': cold_db_path,
            'size_mb': get_db_size_mb(cold_db_path) if Path(cold_db_path).exists() else 0.0,
            'exists': Path(cold_db_path).exists(),
            'table_counts': {},
        },
        'current_season': 0,
        'archival_recommended': False,
    }
    
    # Get hot DB stats
    if stats['hot_db']['exists']:
        hot_conn = sqlite3.connect(hot_db_path)
        hot_cursor = hot_conn.cursor()
        
        try:
            # Get current season
            hot_cursor.execute("SELECT season FROM game_state_snapshot WHERE id = 1")
            row = hot_cursor.fetchone()
            stats['current_season'] = row[0] if row else 0
            
            # Get table counts
            hot_cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='table' ORDER BY name
            """)
            tables = [row[0] for row in hot_cursor.fetchall()]
            
            for table in tables:
                try:
                    hot_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = hot_cursor.fetchone()[0]
                    stats['hot_db']['table_counts'][table] = count
                except Exception:
                    pass
        
        finally:
            hot_conn.close()
    
    # Get cold DB stats
    if stats['cold_db']['exists']:
        cold_conn = sqlite3.connect(cold_db_path)
        cold_cursor = cold_conn.cursor()
        
        try:
            cold_cursor.execute("""
                SELECT name FROM sqlite_master WHERE type='table' ORDER BY name
            """)
            tables = [row[0] for row in cold_cursor.fetchall()]
            
            for table in tables:
                try:
                    cold_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cold_cursor.fetchone()[0]
                    stats['cold_db']['table_counts'][table] = count
                except Exception:
                    pass
        
        finally:
            cold_conn.close()
    
    # Determine if archival is recommended
    threshold_mb = ARCHIVAL_POLICY['archive_threshold_mb']
    stats['archival_recommended'] = stats['hot_db']['size_mb'] > threshold_mb
    
    return stats


def restore_from_cold(hot_db_path: str, table: str, season: int,
                     cold_db_path: Optional[str] = None) -> int:
    """
    Restore data from cold database back to hot database.
    
    Useful for bringing back specific historical data for analysis.
    
    Args:
        hot_db_path: Path to hot database
        table: Table name to restore
        season: Season to restore
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        Number of rows restored
    """
    if cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    if not Path(cold_db_path).exists():
        print(f"[FTB Archival] Cold database does not exist: {cold_db_path}")
        return 0
    
    cold_conn = sqlite3.connect(cold_db_path)
    hot_conn = sqlite3.connect(hot_db_path)
    
    cold_cursor = cold_conn.cursor()
    hot_cursor = hot_conn.cursor()
    
    rows_restored = 0
    
    try:
        # Get season column name for this table
        season_col = ARCHIVAL_POLICY['archive_by_season_tables'].get(table)
        if not season_col:
            print(f"[FTB Archival] Table {table} is not configured for archival")
            return 0
        
        # Get rows from cold database
        cold_cursor.execute(f"""
            SELECT * FROM {table} WHERE {season_col} = ?
        """, (season,))
        rows = cold_cursor.fetchall()
        
        if not rows:
            print(f"[FTB Archival] No data found in cold DB for {table} season {season}")
            return 0
        
        # Get column names
        cold_cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cold_cursor.fetchall()]
        placeholders = ','.join(['?' for _ in columns])
        
        # Insert into hot database
        hot_cursor.executemany(
            f"INSERT OR REPLACE INTO {table} VALUES ({placeholders})",
            rows
        )
        
        hot_conn.commit()
        rows_restored = len(rows)
        
        print(f"[FTB Archival] Restored {rows_restored} rows from cold DB to hot DB")
    
    except Exception as e:
        print(f"[FTB Archival] Error restoring data: {e}")
    
    finally:
        cold_conn.close()
        hot_conn.close()
    
    return rows_restored


# ============================================================================
# NARRATOR-FRIENDLY QUERY HELPERS
# ============================================================================

def query_race_results_extended(
    hot_db_path: str,
    season: Optional[int] = None,
    team_name: Optional[str] = None,
    limit: int = 50,
    include_cold: bool = False,
    cold_db_path: Optional[str] = None
) -> List[Tuple]:
    """
    Query race results with optional cold database access.
    
    Narrator can use this to access deep historical race data for comparisons.
    By default only queries hot DB (fast), but can optionally query cold too.
    
    Args:
        hot_db_path: Path to hot database
        season: Optional season filter
        team_name: Optional team name filter
        limit: Maximum number of results
        include_cold: Whether to also query cold database
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        List of race result tuples
    """
    query = "SELECT * FROM race_results_archive WHERE 1=1"
    params = []
    
    if season is not None:
        query += " AND season = ?"
        params.append(season)
    
    if team_name:
        query += " AND player_team_name = ?"
        params.append(team_name)
    
    query += " ORDER BY season DESC, round_number DESC LIMIT ?"
    params.append(limit)
    
    if include_cold and cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    if include_cold and Path(cold_db_path).exists():
        # Query both databases
        return query_across_databases(hot_db_path, query, tuple(params), cold_db_path)
    else:
        # Query hot database only (default, fast)
        hot_conn = sqlite3.connect(hot_db_path)
        hot_cursor = hot_conn.cursor()
        hot_cursor.execute(query, tuple(params))
        results = hot_cursor.fetchall()
        hot_conn.close()
        return results


def query_financial_history_extended(
    hot_db_path: str,
    season: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 100,
    include_cold: bool = False,
    cold_db_path: Optional[str] = None
) -> List[Tuple]:
    """
    Query financial transactions with optional cold database access.
    
    Narrator can use this for financial trend analysis across all history.
    
    Args:
        hot_db_path: Path to hot database
        season: Optional season filter
        category: Optional category filter (e.g., 'prize', 'salary', 'development')
        limit: Maximum number of results
        include_cold: Whether to also query cold database
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        List of financial transaction tuples
    """
    query = "SELECT * FROM financial_transactions WHERE 1=1"
    params = []
    
    if season is not None:
        query += " AND season = ?"
        params.append(season)
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    query += " ORDER BY tick DESC LIMIT ?"
    params.append(limit)
    
    if include_cold and cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    if include_cold and Path(cold_db_path).exists():
        return query_across_databases(hot_db_path, query, tuple(params), cold_db_path)
    else:
        hot_conn = sqlite3.connect(hot_db_path)
        hot_cursor = hot_conn.cursor()
        hot_cursor.execute(query, tuple(params))
        results = hot_cursor.fetchall()
        hot_conn.close()
        return results


def query_decision_history_extended(
    hot_db_path: str,
    season: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 50,
    include_cold: bool = False,
    cold_db_path: Optional[str] = None
) -> List[Tuple]:
    """
    Query decision history with optional cold database access.
    
    Narrator can use this to reference past strategic decisions for context.
    
    Args:
        hot_db_path: Path to hot database
        season: Optional season filter
        category: Optional category filter (e.g., 'hiring', 'development', 'strategy')
        limit: Maximum number of results
        include_cold: Whether to also query cold database
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        List of decision history tuples
    """
    query = "SELECT * FROM decision_history WHERE 1=1"
    params = []
    
    if season is not None:
        query += " AND season = ?"
        params.append(season)
    
    if category:
        query += " AND category = ?"
        params.append(category)
    
    query += " ORDER BY tick DESC LIMIT ?"
    params.append(limit)
    
    if include_cold and cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    
    if include_cold and Path(cold_db_path).exists():
        return query_across_databases(hot_db_path, query, tuple(params), cold_db_path)
    else:
        hot_conn = sqlite3.connect(hot_db_path)
        hot_cursor = hot_conn.cursor()
        hot_cursor.execute(query, tuple(params))
        results = hot_cursor.fetchall()
        hot_conn.close()
        return results


def has_cold_database(hot_db_path: str, cold_db_path: Optional[str] = None) -> bool:
    """
    Check if a cold database exists for this hot database.
    
    Narrator can use this to determine if deep historical queries are available.
    
    Args:
        hot_db_path: Path to hot database
        cold_db_path: Path to cold database (auto-generated if None)
    
    Returns:
        True if cold database exists
    """
    if cold_db_path is None:
        cold_db_path = get_cold_db_path(hot_db_path)
    return Path(cold_db_path).exists()


# Command-line interface
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("FTB Database Archival System")
        print()
        print("Usage:")
        print("  python ftb_db_archival.py <hot_db_path> [command]")
        print()
        print("Commands:")
        print("  archive  - Archive old data to cold database (default)")
        print("  stats    - Show hot/cold database statistics")
        print("  restore <table> <season> - Restore data from cold to hot")
        print()
        print("Example:")
        print("  python ftb_db_archival.py /path/to/ftb_state.db archive")
        sys.exit(1)
    
    hot_db = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "archive"
    
    if command == "archive":
        stats = archive_old_data(hot_db, verbose=True)
        print(f"\nArchived {sum(stats['archived_rows'].values())} total rows")
        if stats['errors']:
            print(f"Errors: {len(stats['errors'])}")
    
    elif command == "stats":
        stats = get_archival_stats(hot_db)
        print("\n=== Hot Database ===")
        print(f"Path: {stats['hot_db']['path']}")
        print(f"Size: {stats['hot_db']['size_mb']:.2f} MB")
        print(f"Current Season: {stats['current_season']}")
        print(f"\nTable Counts:")
        for table, count in sorted(stats['hot_db']['table_counts'].items()):
            print(f"  {table}: {count:,}")
        
        if stats['cold_db']['exists']:
            print("\n=== Cold Database ===")
            print(f"Path: {stats['cold_db']['path']}")
            print(f"Size: {stats['cold_db']['size_mb']:.2f} MB")
            print(f"\nTable Counts:")
            for table, count in sorted(stats['cold_db']['table_counts'].items()):
                print(f"  {table}: {count:,}")
        
        if stats['archival_recommended']:
            print(f"\n⚠️  Archival recommended (hot DB > {ARCHIVAL_POLICY['archive_threshold_mb']} MB)")
    
    elif command == "restore":
        if len(sys.argv) < 5:
            print("Usage: restore <table> <season>")
            sys.exit(1)
        
        table = sys.argv[3]
        season = int(sys.argv[4])
        rows = restore_from_cold(hot_db, table, season)
        print(f"Restored {rows} rows")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
