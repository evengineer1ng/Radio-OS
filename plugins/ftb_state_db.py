"""
FTB State Database - Narrator State Awareness Layer

Hybrid data architecture:
- Game state persists via JSON (ftb_autosave.json)
- Narrator reads from SQLite for real-time state awareness
- Decouples simulation from narration completely

Database serves as read-only interface for narrator and delegate AI.
Game writes comprehensive state snapshots after each tick.
"""

import sqlite3
import json
import threading
import os
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from contextlib import contextmanager


# Thread-local storage for connection pooling
_thread_local = threading.local()


# ============================================================================
# CONNECTION HELPERS
# ============================================================================

def close_connection_cache(db_path: Optional[str] = None) -> None:
    """Close cached SQLite connections, optionally for a specific DB path."""
    if not hasattr(_thread_local, "connections"):
        return

    if db_path:
        conn = _thread_local.connections.pop(db_path, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
        return

    for conn in _thread_local.connections.values():
        try:
            conn.close()
        except Exception:
            pass
    _thread_local.connections = {}


def backup_db(src_path: str, dest_path: str) -> None:
    """Copy a SQLite database using the backup API for consistency."""
    if not src_path or not dest_path:
        return
    if not os.path.exists(src_path):
        return

    os.makedirs(os.path.dirname(os.path.abspath(dest_path)), exist_ok=True)
    with sqlite3.connect(src_path) as src_conn:
        with sqlite3.connect(dest_path) as dest_conn:
            src_conn.backup(dest_conn)


# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db(db_path: str) -> None:
    """Initialize FTB state database with schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Game state snapshot (singleton row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state_snapshot (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            tick INTEGER NOT NULL,
            phase TEXT NOT NULL,
            season INTEGER NOT NULL,
            day_of_year INTEGER NOT NULL,
            time_mode TEXT NOT NULL,
            control_mode TEXT NOT NULL,
            active_tab TEXT,
            seed TEXT NOT NULL,
            game_id TEXT,
            races_completed_this_season INTEGER DEFAULT 0,
            last_updated_ts REAL NOT NULL
        )
    """)
    
    # Player state (singleton row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS player_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            team_name TEXT NOT NULL,
            budget REAL NOT NULL,
            championship_position INTEGER,
            points REAL NOT NULL,
            morale REAL NOT NULL,
            reputation REAL NOT NULL,
            tier INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            focus TEXT,
            identity_json TEXT NOT NULL,
            ownership_type TEXT DEFAULT 'hired_manager'
        )
    """)
    
    # Teams snapshot
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_name TEXT PRIMARY KEY,
            tier INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            budget REAL NOT NULL,
            championship_position INTEGER,
            points REAL NOT NULL,
            is_player_team INTEGER NOT NULL,
            principal_name TEXT,
            ownership_type TEXT,
            standing_metrics_json TEXT,
            infrastructure_summary_json TEXT
        )
    """)
    
    # Entities (drivers, engineers, mechanics, strategists)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            entity_id INTEGER PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            team_name TEXT,
            overall_rating REAL NOT NULL,
            stats_json TEXT NOT NULL,
            contract_end_day INTEGER,
            salary REAL,
            is_free_agent INTEGER DEFAULT 0,
            time_in_pool_days INTEGER DEFAULT 0,
            exit_reason TEXT
        )
    """)
    
    # Events buffer for narrator
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events_buffer (
            event_id INTEGER PRIMARY KEY,
            tick INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            category TEXT NOT NULL,
            priority REAL NOT NULL,
            severity TEXT NOT NULL,
            team TEXT,
            data_json TEXT NOT NULL,
            emitted_to_narrator INTEGER DEFAULT 0,
            created_ts REAL NOT NULL
        )
    """)
    
    # League standings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS league_standings (
            league_id TEXT PRIMARY KEY,
            tier INTEGER NOT NULL,
            league_name TEXT NOT NULL,
            standings_json TEXT NOT NULL
        )
    """)
    
    # Job board
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_board (
            listing_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            role TEXT NOT NULL,
            tier INTEGER NOT NULL,
            salary REAL NOT NULL,
            visibility_threshold REAL DEFAULT 0.0,
            created_tick INTEGER NOT NULL
        )
    """)
    
    # Sponsorships (extended with rich behavioral profiles)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sponsorships (
            sponsorship_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            sponsor_name TEXT NOT NULL,
            sponsor_id TEXT,
            tier TEXT NOT NULL,
            financial_tier TEXT,
            industry TEXT,
            sub_industry TEXT,
            base_payment_per_season INTEGER NOT NULL,
            duration_seasons INTEGER NOT NULL,
            seasons_active INTEGER DEFAULT 0,
            confidence REAL DEFAULT 100.0,
            contract_type TEXT DEFAULT 'season_partnership',
            evaluation_cadence INTEGER DEFAULT 5,
            signed_tick INTEGER DEFAULT 0,
            last_evaluated_tick INTEGER DEFAULT 0,
            warning_issued INTEGER DEFAULT 0,
            has_bailed_out INTEGER DEFAULT 0,
            bailout_count INTEGER DEFAULT 0,
            brand_profile_json TEXT,
            contract_behavior_json TEXT,
            activation_style_json TEXT,
            narrative_hooks_json TEXT,
            exclusivity_clauses_json TEXT,
            performance_history_json TEXT
        )
    """)
    
    # Free agents pool
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS free_agents (
            entity_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL,
            age INTEGER NOT NULL,
            tier INTEGER NOT NULL,
            overall_rating REAL NOT NULL,
            asking_salary REAL NOT NULL,
            time_in_pool_days INTEGER DEFAULT 0,
            exit_reason TEXT
        )
    """)
    
    # Folded teams (historical record of team collapses)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folded_teams (
            id TEXT PRIMARY KEY,
            team_name TEXT NOT NULL,
            fold_tick INTEGER NOT NULL,
            fold_season INTEGER NOT NULL,
            final_budget_cash REAL,
            final_reputation REAL,
            fold_reason TEXT NOT NULL,
            championship_position INTEGER,
            seasons_active INTEGER,
            metadata_json TEXT
        )
    """)
    
    # Penalties
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS penalties (
            penalty_id INTEGER PRIMARY KEY AUTOINCREMENT,
            race_id INTEGER,
            team_name TEXT NOT NULL,
            driver_name TEXT,
            penalty_type TEXT NOT NULL,
            magnitude INTEGER NOT NULL,
            reason TEXT NOT NULL,
            game_day INTEGER NOT NULL,
            tier INTEGER NOT NULL,
            issued_by TEXT DEFAULT 'Stewards',
            appealable INTEGER DEFAULT 0,
            applied INTEGER DEFAULT 0,
            metadata_json TEXT
        )
    """)
    
    # Index for efficient penalty queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_penalties_team_day ON penalties(team_name, game_day DESC)
    """)
    
    # Narrator context (singleton row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS narrator_context (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            last_commentary_time REAL,
            topics_discussed_json TEXT DEFAULT '[]',
            active_themes_json TEXT DEFAULT '[]',
            player_streak_data_json TEXT DEFAULT '{}',
            segment_history_json TEXT DEFAULT '{}',
            player_team TEXT,
            save_timestamp REAL,
            current_motif TEXT DEFAULT 'quiet climb',
            open_loop TEXT DEFAULT '',
            named_focus TEXT DEFAULT '',
            stakes_axis TEXT DEFAULT 'budget',
            tone TEXT DEFAULT 'wry',
            last_generated_spine TEXT DEFAULT '',
            last_generated_beat TEXT DEFAULT '',
            claim_tags_json TEXT DEFAULT '[]',
            segments_since_motif_change INTEGER DEFAULT 0
        )
    """)
    
    # UI context (singleton row)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ui_context (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            active_tab TEXT NOT NULL,
            last_tab_change_tick INTEGER NOT NULL
        )
    """)
    
    # Calendar entries (forward-looking projection for strategic planning)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calendar_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_day INTEGER NOT NULL,
            entry_type TEXT NOT NULL,
            category TEXT NOT NULL,
            entity_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            is_player_authored INTEGER DEFAULT 0,
            priority INTEGER DEFAULT 50,
            action_required INTEGER DEFAULT 0,
            metadata_json TEXT,
            created_at REAL NOT NULL
        )
    """)
    
    # League economic state (global sponsor market health)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS league_economic_state (
            season INTEGER PRIMARY KEY,
            sponsor_market_multiplier REAL DEFAULT 1.0,
            recent_folds_count INTEGER DEFAULT 0,
            tier_stability REAL DEFAULT 1.0,
            last_update_tick INTEGER DEFAULT 0,
            metadata_json TEXT
        )
    """)
    
    # Decision history (player and delegate decisions)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_history (
            decision_id TEXT PRIMARY KEY,
            tick INTEGER NOT NULL,
            season INTEGER NOT NULL,
            game_day INTEGER NOT NULL,
            category TEXT NOT NULL,
            decision_text TEXT NOT NULL,
            options_json TEXT NOT NULL,
            chosen_option_id TEXT,
            chosen_option_label TEXT,
            immediate_cost REAL DEFAULT 0.0,
            rationale TEXT,
            resolved_by TEXT,
            metadata_json TEXT
        )
    """)
    
    # Race results archive (historical performance records)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS race_results_archive (
            race_id TEXT PRIMARY KEY,
            season INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            track_name TEXT NOT NULL,
            tick INTEGER NOT NULL,
            player_team_name TEXT NOT NULL,
            player_drivers_json TEXT NOT NULL,
            finish_positions_json TEXT NOT NULL,
            grid_position INTEGER,
            prize_money REAL DEFAULT 0.0,
            fastest_lap_holder TEXT,
            incidents_json TEXT,
            championship_position_after INTEGER,
            points_after REAL,
            metadata_json TEXT
        )
    """)
    
    # Financial transactions (all income and expenses)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS financial_transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tick INTEGER NOT NULL,
            season INTEGER NOT NULL,
            game_day INTEGER NOT NULL,
            type TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            balance_after REAL NOT NULL,
            description TEXT NOT NULL,
            related_entity TEXT,
            metadata_json TEXT
        )
    """)
    
    # Season summaries (end-of-season performance records)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS season_summaries (
            season INTEGER PRIMARY KEY,
            team_name TEXT NOT NULL,
            tier TEXT NOT NULL,
            league_id TEXT NOT NULL,
            championship_position INTEGER,
            total_points REAL DEFAULT 0.0,
            races_entered INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            podiums INTEGER DEFAULT 0,
            poles INTEGER DEFAULT 0,
            season_prize_money REAL DEFAULT 0.0,
            season_sponsor_income REAL DEFAULT 0.0,
            season_expenses REAL DEFAULT 0.0,
            starting_balance REAL DEFAULT 0.0,
            ending_balance REAL DEFAULT 0.0,
            promoted INTEGER DEFAULT 0,
            relegated INTEGER DEFAULT 0,
            metadata_json TEXT
        )
    """)
    
    # ML TRAINING: AI decisions log (for imitation learning)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tick INTEGER NOT NULL,
            season INTEGER NOT NULL,
            team_id TEXT NOT NULL,
            team_name TEXT NOT NULL,
            state_vector_json TEXT NOT NULL,
            action_chosen_json TEXT NOT NULL,
            action_scores_json TEXT,
            principal_stats_json TEXT NOT NULL,
            budget_before REAL NOT NULL,
            budget_after REAL NOT NULL,
            championship_position INTEGER,
            created_ts REAL NOT NULL
        )
    """)
    
    # ML TRAINING: Team outcomes (for success scoring)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_outcomes (
            outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            team_name TEXT NOT NULL,
            season INTEGER NOT NULL,
            championship_position INTEGER NOT NULL,
            total_points REAL DEFAULT 0.0,
            starting_budget REAL NOT NULL,
            ending_budget REAL NOT NULL,
            budget_health_score REAL DEFAULT 0.0,
            roi_score REAL DEFAULT 0.0,
            survival_flag INTEGER DEFAULT 1,
            folded_tick INTEGER,
            seasons_survived INTEGER DEFAULT 1,
            created_ts REAL NOT NULL
        )
    """)
    
    # Create indexes for common queries
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_emitted ON events_buffer(emitted_to_narrator)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_tick ON events_buffer(tick)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_team ON entities(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_free_agent ON entities(is_free_agent)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_board_tier ON job_board(tier)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sponsorships_team ON sponsorships(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sponsorships_sponsor_id ON sponsorships(sponsor_id, team_name)")
    
    # Indexes for history tables
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_history_tick ON decision_history(tick DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_history_category ON decision_history(category, tick DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_race_results_season ON race_results_archive(season DESC, round_number DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_financial_transactions_tick ON financial_transactions(tick DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_financial_transactions_type ON financial_transactions(type, category, tick DESC)")
    
    # Indexes for ML training tables
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_team ON ai_decisions(team_id, season, tick)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_tick ON ai_decisions(tick DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_outcomes_team ON team_outcomes(team_id, season)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_outcomes_success ON team_outcomes(budget_health_score DESC, roi_score DESC)")
    
    # ========================================================================
    # HISTORICAL DATA SYSTEM - Phase 1 Foundation
    # ========================================================================
    
    # I. TEAM HISTORICAL RECORDS
    
    # Team career totals (all-time stats)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_career_totals (
            team_name TEXT PRIMARY KEY,
            seasons_entered INTEGER DEFAULT 0,
            races_entered INTEGER DEFAULT 0,
            wins_total INTEGER DEFAULT 0,
            podiums_total INTEGER DEFAULT 0,
            poles_total INTEGER DEFAULT 0,
            fastest_laps_total INTEGER DEFAULT 0,
            points_total REAL DEFAULT 0.0,
            championships_won INTEGER DEFAULT 0,
            runner_up_finishes INTEGER DEFAULT 0,
            constructors_titles INTEGER DEFAULT 0,
            total_dnfs INTEGER DEFAULT 0,
            mechanical_dnfs INTEGER DEFAULT 0,
            crash_dnfs INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0,
            podium_rate REAL DEFAULT 0.0,
            points_per_race_career REAL DEFAULT 0.0,
            reliability_career REAL DEFAULT 0.0,
            championship_conversion_rate REAL DEFAULT 0.0,
            titles_per_top3_season REAL DEFAULT 0.0,
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # Team era performance
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS regulation_eras (
            era_id TEXT PRIMARY KEY,
            era_label TEXT NOT NULL,
            start_season INTEGER NOT NULL,
            end_season INTEGER,
            major_regulation_changes TEXT,
            description TEXT,
            created_tick INTEGER NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_era_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            era_id TEXT NOT NULL,
            era_label TEXT NOT NULL,
            start_season INTEGER NOT NULL,
            end_season INTEGER NOT NULL,
            races_entered INTEGER DEFAULT 0,
            avg_finish REAL DEFAULT 0.0,
            avg_cpi REAL DEFAULT 0.0,
            cpi_percentile REAL DEFAULT 0.0,
            championships INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            podiums INTEGER DEFAULT 0,
            performance_vs_previous_era REAL DEFAULT 0.0,
            decline_after_rule_change REAL DEFAULT 0.0,
            adaptability_score REAL DEFAULT 50.0,
            last_updated_tick INTEGER NOT NULL,
            UNIQUE(team_name, era_id)
        )
    """)
    
    # Team peak & valley metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_peak_valley (
            team_name TEXT PRIMARY KEY,
            best_season_finish INTEGER,
            best_season_finish_year INTEGER,
            worst_season_finish INTEGER,
            worst_season_finish_year INTEGER,
            best_single_season_points REAL DEFAULT 0.0,
            best_season_points_year INTEGER,
            worst_season_points REAL DEFAULT 0.0,
            worst_season_points_year INTEGER,
            longest_title_drought INTEGER DEFAULT 0,
            longest_win_drought INTEGER DEFAULT 0,
            longest_podium_drought INTEGER DEFAULT 0,
            current_title_drought INTEGER DEFAULT 0,
            current_win_drought INTEGER DEFAULT 0,
            current_podium_drought INTEGER DEFAULT 0,
            biggest_season_overperformance REAL DEFAULT 0.0,
            biggest_season_collapse REAL DEFAULT 0.0,
            volatility_index REAL DEFAULT 0.0,
            golden_era_start INTEGER,
            golden_era_end INTEGER,
            golden_era_avg_finish REAL,
            consecutive_top3_seasons INTEGER DEFAULT 0,
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # II. DRIVER HISTORICAL ARCHIVES
    
    # Driver career stats
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_career_stats (
            driver_name TEXT PRIMARY KEY,
            career_starts INTEGER DEFAULT 0,
            career_wins INTEGER DEFAULT 0,
            career_podiums INTEGER DEFAULT 0,
            career_poles INTEGER DEFAULT 0,
            career_points REAL DEFAULT 0.0,
            career_dnfs INTEGER DEFAULT 0,
            career_teams_driven_for INTEGER DEFAULT 0,
            championships_won INTEGER DEFAULT 0,
            best_season_finish INTEGER,
            best_season_finish_year INTEGER,
            worst_season_finish INTEGER,
            worst_season_finish_year INTEGER,
            win_rate_career REAL DEFAULT 0.0,
            podium_rate_career REAL DEFAULT 0.0,
            points_per_race_career REAL DEFAULT 0.0,
            reliability_career REAL DEFAULT 0.0,
            clutch_index REAL DEFAULT 0.0,
            debut_season INTEGER,
            debut_team TEXT,
            current_team TEXT,
            seasons_active INTEGER DEFAULT 0,
            is_retired INTEGER DEFAULT 0,
            retirement_season INTEGER,
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # Driver team stints
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_team_stints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            driver_name TEXT NOT NULL,
            team_name TEXT NOT NULL,
            start_season INTEGER NOT NULL,
            end_season INTEGER,
            races INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            podiums INTEGER DEFAULT 0,
            points REAL DEFAULT 0.0,
            years_at_team INTEGER DEFAULT 0,
            teammate_name TEXT,
            performance_delta_vs_teammate REAL DEFAULT 0.0,
            teammate_comparison_index REAL DEFAULT 0.0,
            quali_head_to_head_wins INTEGER DEFAULT 0,
            quali_head_to_head_losses INTEGER DEFAULT 0,
            race_head_to_head_wins INTEGER DEFAULT 0,
            race_head_to_head_losses INTEGER DEFAULT 0,
            last_updated_tick INTEGER NOT NULL,
            UNIQUE(driver_name, team_name, start_season)
        )
    """)
    
    # Driver development curve
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_development_curve (
            driver_name TEXT PRIMARY KEY,
            peak_rating REAL DEFAULT 0.0,
            peak_rating_age INTEGER,
            peak_performance_season INTEGER,
            peak_performance_metric REAL DEFAULT 0.0,
            age_curve_json TEXT,
            mettle_under_pressure_index REAL DEFAULT 0.0,
            performance_when_championship_close REAL DEFAULT 0.0,
            post_crash_recovery_performance REAL DEFAULT 0.0,
            improvement_rate REAL DEFAULT 0.0,
            consistency_index REAL DEFAULT 0.0,
            volatility_score REAL DEFAULT 0.0,
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # III. LEAGUE & CHAMPIONSHIP HISTORY
    
    # Championship history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS championship_history (
            season INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            tier INTEGER NOT NULL,
            champion_team TEXT NOT NULL,
            champion_points REAL NOT NULL,
            runner_up_team TEXT NOT NULL,
            runner_up_points REAL NOT NULL,
            third_place_team TEXT NOT NULL,
            third_place_points REAL NOT NULL,
            title_margin REAL NOT NULL,
            title_decided_round INTEGER,
            avg_points_to_win REAL DEFAULT 0.0,
            most_dominant_season REAL DEFAULT 0.0,
            closest_title_fight REAL DEFAULT 0.0,
            is_repeat_champion INTEGER DEFAULT 0,
            consecutive_titles_for_winner INTEGER DEFAULT 0,
            parity_index REAL DEFAULT 0.0,
            championship_compression_score REAL DEFAULT 0.0,
            last_updated_tick INTEGER NOT NULL,
            PRIMARY KEY (season, league_id)
        )
    """)
    
    # Tier definitions and history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tier_definitions (
            season INTEGER NOT NULL,
            performance_tier TEXT NOT NULL,
            min_percentile REAL NOT NULL,
            max_percentile REAL NOT NULL,
            PRIMARY KEY (season, performance_tier)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_tier_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            season INTEGER NOT NULL,
            tier INTEGER NOT NULL,
            performance_tier TEXT NOT NULL,
            tier_percentile REAL DEFAULT 0.0,
            seasons_in_tier INTEGER DEFAULT 0,
            total_seasons_in_tier INTEGER DEFAULT 0,
            promoted_from_tier INTEGER,
            relegated_from_tier INTEGER,
            tier_change_reason TEXT,
            last_updated_tick INTEGER NOT NULL,
            UNIQUE(team_name, season)
        )
    """)
    
    # IV. STREAK TRACKING
    
    # Active team streaks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_streaks (
            team_name TEXT PRIMARY KEY,
            current_points_streak INTEGER DEFAULT 0,
            current_podium_streak INTEGER DEFAULT 0,
            current_dnf_streak INTEGER DEFAULT 0,
            current_win_streak INTEGER DEFAULT 0,
            consecutive_points_finishes INTEGER DEFAULT 0,
            consecutive_outqualified_teammate INTEGER DEFAULT 0,
            consecutive_mechanical_failures INTEGER DEFAULT 0,
            consecutive_top5_finishes INTEGER DEFAULT 0,
            consecutive_outside_top10 INTEGER DEFAULT 0,
            longest_points_streak_ever INTEGER DEFAULT 0,
            longest_win_streak_ever INTEGER DEFAULT 0,
            longest_dnf_streak_ever INTEGER DEFAULT 0,
            longest_podium_streak_ever INTEGER DEFAULT 0,
            last_points_finish_race TEXT,
            last_points_finish_season INTEGER,
            last_podium_race TEXT,
            last_podium_season INTEGER,
            last_win_race TEXT,
            last_win_season INTEGER,
            last_dnf_race TEXT,
            last_dnf_season INTEGER,
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # Active driver streaks
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_active_streaks (
            driver_name TEXT PRIMARY KEY,
            current_points_streak INTEGER DEFAULT 0,
            current_podium_streak INTEGER DEFAULT 0,
            current_dnf_streak INTEGER DEFAULT 0,
            current_win_streak INTEGER DEFAULT 0,
            consecutive_outqualified_teammate INTEGER DEFAULT 0,
            longest_points_streak_ever INTEGER DEFAULT 0,
            longest_win_streak_ever INTEGER DEFAULT 0,
            longest_podium_streak_ever INTEGER DEFAULT 0,
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # V. COMPOSITE METRICS
    
    # Team pulse metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_pulse_metrics (
            team_name TEXT PRIMARY KEY,
            team_pulse REAL DEFAULT 50.0,
            performance_trend_component REAL DEFAULT 0.0,
            financial_stability_component REAL DEFAULT 0.0,
            development_speed_component REAL DEFAULT 0.0,
            league_percentile_component REAL DEFAULT 0.0,
            competitive_tier TEXT DEFAULT 'midfield',
            narrative_temperature TEXT DEFAULT 'stable',
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # Team prestige
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_prestige (
            team_name TEXT PRIMARY KEY,
            prestige_index REAL DEFAULT 50.0,
            championship_prestige REAL DEFAULT 0.0,
            wins_prestige REAL DEFAULT 0.0,
            longevity_prestige REAL DEFAULT 0.0,
            era_dominance_prestige REAL DEFAULT 0.0,
            financial_resilience_prestige REAL DEFAULT 0.0,
            legacy_tier TEXT DEFAULT 'emerging',
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # Driver legacy
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS driver_legacy (
            driver_name TEXT PRIMARY KEY,
            legacy_score REAL DEFAULT 50.0,
            titles_legacy REAL DEFAULT 0.0,
            win_rate_legacy REAL DEFAULT 0.0,
            teammate_dominance_legacy REAL DEFAULT 0.0,
            clutch_index_legacy REAL DEFAULT 0.0,
            peak_rating_legacy REAL DEFAULT 0.0,
            longevity_legacy REAL DEFAULT 0.0,
            legacy_tier TEXT DEFAULT 'developing',
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # VI. EXPECTATION MODELS
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expectation_models (
            team_name TEXT NOT NULL,
            season INTEGER NOT NULL,
            round_number INTEGER NOT NULL,
            expected_finish REAL DEFAULT 0.0,
            actual_finish INTEGER,
            expectation_gap REAL DEFAULT 0.0,
            historical_baseline_finish REAL DEFAULT 0.0,
            regression_to_mean_indicator REAL DEFAULT 0.0,
            sustainable_performance_score REAL DEFAULT 0.0,
            overachieving_vs_history_index REAL DEFAULT 0.0,
            strongest_start_comparison TEXT,
            performance_vs_career_avg REAL DEFAULT 0.0,
            created_tick INTEGER NOT NULL,
            PRIMARY KEY (team_name, season, round_number)
        )
    """)
    
    # VII. TIME-BASED METRICS
    
    # Momentum metrics
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS momentum_metrics (
            team_name TEXT PRIMARY KEY,
            form_last_3_races REAL DEFAULT 0.0,
            form_last_5_races REAL DEFAULT 0.0,
            momentum_slope REAL DEFAULT 0.0,
            momentum_state TEXT DEFAULT 'stable',
            last_updated_tick INTEGER NOT NULL
        )
    """)
    
    # Narrative heat scores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS narrative_heat_scores (
            team_name TEXT NOT NULL,
            story_type TEXT NOT NULL,
            heat_score REAL DEFAULT 0.0,
            peak_heat REAL DEFAULT 0.0,
            decay_rate REAL DEFAULT 5.0,
            story_start_tick INTEGER NOT NULL,
            last_boosted_tick INTEGER NOT NULL,
            days_since_last_boost INTEGER DEFAULT 0,
            story_description TEXT,
            key_players TEXT,
            PRIMARY KEY (team_name, story_type)
        )
    """)
    
    # VIII. HISTORICAL INDEXES
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_career_championships ON team_career_totals(championships_won DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_career_wins ON team_career_totals(wins_total DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_era_performance_team ON team_era_performance(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_era_performance_era ON team_era_performance(era_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_driver_career_championships ON driver_career_stats(championships_won DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_driver_career_wins ON driver_career_stats(career_wins DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_driver_stints_driver ON driver_team_stints(driver_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_driver_stints_team ON driver_team_stints(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_championship_history_season ON championship_history(season)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_championship_history_champion ON championship_history(champion_team)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_tier_history_team ON team_tier_history(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_tier_history_season ON team_tier_history(season)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_expectation_team_season ON expectation_models(team_name, season)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_narrative_heat_team ON narrative_heat_scores(team_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_narrative_heat_score ON narrative_heat_scores(heat_score DESC)")
    
    # Initialize default tier definitions
    cursor.execute("""
        INSERT OR IGNORE INTO tier_definitions (season, performance_tier, min_percentile, max_percentile) VALUES
        (0, 'dominant', 0.0, 5.0),
        (0, 'contender', 5.0, 20.0),
        (0, 'upper_midfield', 20.0, 40.0),
        (0, 'midfield', 40.0, 60.0),
        (0, 'lower_midfield', 60.0, 80.0),
        (0, 'backmarker', 80.0, 95.0),
        (0, 'crisis', 95.0, 100.0)
    """)
    
    # Generic key-value store for streaming state (race day, etc.)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state_kv (
            game_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_ts REAL,
            PRIMARY KEY (game_id, key)
        )
    """)
    
    conn.commit()
    conn.close()
    
    print(f"[FTB State DB] Initialized database at {db_path}")
    
    # Run migration to add any missing columns to existing tables
    migrate_narrator_context_schema(db_path)
    migrate_history_tables(db_path)


def migrate_history_tables(db_path: str) -> None:
    """
    Migrate database to add history tables if they don't exist.
    Called after init_db to ensure existing databases get new tables.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if history tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        # Add decision_history if missing
        if 'decision_history' not in existing_tables:
            print("[FTB State DB] Creating decision_history table...")
            cursor.execute("""
                CREATE TABLE decision_history (
                    decision_id TEXT PRIMARY KEY,
                    tick INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    game_day INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    decision_text TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    chosen_option_id TEXT,
                    chosen_option_label TEXT,
                    immediate_cost REAL DEFAULT 0.0,
                    rationale TEXT,
                    resolved_by TEXT,
                    metadata_json TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_history_tick ON decision_history(tick DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_history_category ON decision_history(category, tick DESC)")
        
        # Add race_results_archive if missing
        if 'race_results_archive' not in existing_tables:
            print("[FTB State DB] Creating race_results_archive table...")
            cursor.execute("""
                CREATE TABLE race_results_archive (
                    race_id TEXT PRIMARY KEY,
                    season INTEGER NOT NULL,
                    round_number INTEGER NOT NULL,
                    league_id TEXT NOT NULL,
                    track_name TEXT NOT NULL,
                    tick INTEGER NOT NULL,
                    player_team_name TEXT NOT NULL,
                    player_drivers_json TEXT NOT NULL,
                    finish_positions_json TEXT NOT NULL,
                    grid_position INTEGER,
                    prize_money REAL DEFAULT 0.0,
                    fastest_lap_holder TEXT,
                    incidents_json TEXT,
                    championship_position_after INTEGER,
                    points_after REAL,
                    metadata_json TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_race_results_season ON race_results_archive(season DESC, round_number DESC)")
        
        # Add financial_transactions if missing
        if 'financial_transactions' not in existing_tables:
            print("[FTB State DB] Creating financial_transactions table...")
            cursor.execute("""
                CREATE TABLE financial_transactions (
                    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    game_day INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    description TEXT NOT NULL,
                    related_entity TEXT,
                    metadata_json TEXT
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_financial_transactions_tick ON financial_transactions(tick DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_financial_transactions_type ON financial_transactions(type, category, tick DESC)")
        
        # Add season_summaries if missing
        if 'season_summaries' not in existing_tables:
            print("[FTB State DB] Creating season_summaries table...")
            cursor.execute("""
                CREATE TABLE season_summaries (
                    season INTEGER PRIMARY KEY,
                    team_name TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    league_id TEXT NOT NULL,
                    championship_position INTEGER,
                    total_points REAL DEFAULT 0.0,
                    races_entered INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    podiums INTEGER DEFAULT 0,
                    poles INTEGER DEFAULT 0,
                    season_prize_money REAL DEFAULT 0.0,
                    season_sponsor_income REAL DEFAULT 0.0,
                    season_expenses REAL DEFAULT 0.0,
                    starting_balance REAL DEFAULT 0.0,
                    ending_balance REAL DEFAULT 0.0,
                    promoted INTEGER DEFAULT 0,
                    relegated INTEGER DEFAULT 0,
                    metadata_json TEXT
                )
            """)
        
        # ML TRAINING: Add ai_decisions table if missing
        if 'ai_decisions' not in existing_tables:
            print("[FTB State DB] Creating ai_decisions table for ML training...")
            cursor.execute("""
                CREATE TABLE ai_decisions (
                    decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tick INTEGER NOT NULL,
                    season INTEGER NOT NULL,
                    team_id TEXT NOT NULL,
                    team_name TEXT NOT NULL,
                    state_vector_json TEXT NOT NULL,
                    action_chosen_json TEXT NOT NULL,
                    action_scores_json TEXT,
                    principal_stats_json TEXT NOT NULL,
                    budget_before REAL NOT NULL,
                    budget_after REAL NOT NULL,
                    championship_position INTEGER,
                    created_ts REAL NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_team ON ai_decisions(team_id, season, tick)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ai_decisions_tick ON ai_decisions(tick DESC)")
        
        # ML TRAINING: Add team_outcomes table if missing
        if 'team_outcomes' not in existing_tables:
            print("[FTB State DB] Creating team_outcomes table for ML training...")
            cursor.execute("""
                CREATE TABLE team_outcomes (
                    outcome_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    team_id TEXT NOT NULL,
                    team_name TEXT NOT NULL,
                    season INTEGER NOT NULL,
                    championship_position INTEGER NOT NULL,
                    total_points REAL DEFAULT 0.0,
                    starting_budget REAL NOT NULL,
                    ending_budget REAL NOT NULL,
                    budget_health_score REAL DEFAULT 0.0,
                    roi_score REAL DEFAULT 0.0,
                    survival_flag INTEGER DEFAULT 1,
                    folded_tick INTEGER,
                    seasons_survived INTEGER DEFAULT 1,
                    created_ts REAL NOT NULL
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_outcomes_team ON team_outcomes(team_id, season)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_team_outcomes_success ON team_outcomes(budget_health_score DESC, roi_score DESC)")
        
        conn.commit()
        print("[FTB State DB] History tables migration complete")
    except Exception as e:
        print(f"[FTB State DB] Warning: Could not migrate history tables: {e}")
    finally:
        conn.close()


def migrate_narrator_context_schema(db_path: str) -> None:
    """
    Migrate narrator_context table to add Show Bible columns if missing.
    Called separately after init_db to handle existing databases.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Get current columns
        cursor.execute("PRAGMA table_info(narrator_context)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # Define new columns with their types and defaults
        new_columns = {
            'player_team': "TEXT",
            'current_motif': "TEXT DEFAULT 'quiet climb'",
            'open_loop': "TEXT DEFAULT ''",
            'named_focus': "TEXT DEFAULT ''",
            'stakes_axis': "TEXT DEFAULT 'budget'",
            'tone': "TEXT DEFAULT 'wry'",
            'last_generated_spine': "TEXT DEFAULT ''",
            'last_generated_beat': "TEXT DEFAULT ''",
            'claim_tags_json': "TEXT DEFAULT '[]'",
            'segments_since_motif_change': "INTEGER DEFAULT 0"
        }
        
        # Add missing columns
        for col_name, col_def in new_columns.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE narrator_context ADD COLUMN {col_name} {col_def}")
                    print(f"[FTB State DB] Added column {col_name} to narrator_context")
                except sqlite3.OperationalError as e:
                    # Column might already exist or duplicate column error
                    if "duplicate column" not in str(e).lower():
                        print(f"[FTB State DB] Warning: Could not add column {col_name}: {e}")
        
        conn.commit()
    except Exception as e:
        print(f"[FTB State DB] Schema migration error: {e}")
    finally:
        conn.close()


def migrate_seed_column(db_path: str) -> None:
    """
    Migrate game_state_snapshot.seed column from INTEGER to TEXT.
    Handles arbitrarily large seed values that exceed SQLite INTEGER limit.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check current column type
        cursor.execute("PRAGMA table_info(game_state_snapshot)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        
        if 'seed' in columns and columns['seed'] == 'INTEGER':
            print("[FTB State DB] Migrating seed column from INTEGER to TEXT...")
            
            # Read existing data
            cursor.execute("SELECT * FROM game_state_snapshot WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                # Backup current data
                game_data = {
                    'tick': row[1],
                    'phase': row[2],
                    'season': row[3],
                    'day_of_year': row[4],
                    'time_mode': row[5],
                    'control_mode': row[6],
                    'active_tab': row[7],
                    'seed': str(row[8]),  # Convert to string
                    'last_updated_ts': row[9]
                }
                
                # Drop and recreate table with TEXT seed and races_completed_this_season
                cursor.execute("DROP TABLE game_state_snapshot")
                cursor.execute("""
                    CREATE TABLE game_state_snapshot (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        tick INTEGER NOT NULL,
                        phase TEXT NOT NULL,
                        season INTEGER NOT NULL,
                        day_of_year INTEGER NOT NULL,
                        time_mode TEXT NOT NULL,
                        control_mode TEXT NOT NULL,
                        active_tab TEXT,
                        seed TEXT NOT NULL,
                        races_completed_this_season INTEGER DEFAULT 0,
                        last_updated_ts REAL NOT NULL
                    )
                """)
                
                # Restore data
                cursor.execute("""
                    INSERT INTO game_state_snapshot 
                    (id, tick, phase, season, day_of_year, time_mode, control_mode, active_tab, seed, races_completed_this_season, last_updated_ts)
                    VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    game_data['tick'],
                    game_data['phase'],
                    game_data['season'],
                    game_data['day_of_year'],
                    game_data['time_mode'],
                    game_data['control_mode'],
                    game_data['active_tab'],
                    game_data['seed'],
                    game_data.get('races_completed_this_season', 0),
                    game_data['last_updated_ts']
                ))
                
                print("[FTB State DB] Seed column migration complete")
            else:
                # No data exists, just recreate table
                cursor.execute("DROP TABLE game_state_snapshot")
                cursor.execute("""
                    CREATE TABLE game_state_snapshot (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        tick INTEGER NOT NULL,
                        phase TEXT NOT NULL,
                        season INTEGER NOT NULL,
                        day_of_year INTEGER NOT NULL,
                        time_mode TEXT NOT NULL,
                        control_mode TEXT NOT NULL,
                        active_tab TEXT,
                        seed TEXT NOT NULL,
                        races_completed_this_season INTEGER DEFAULT 0,
                        last_updated_ts REAL NOT NULL
                    )
                """)
                print("[FTB State DB] Seed column migration complete (no existing data)")
        
        conn.commit()
    except Exception as e:
        print(f"[FTB State DB] Seed column migration error: {e}")
    finally:
        conn.close()


def migrate_game_id_column(db_path: str) -> None:
    """
    Add game_id column to game_state_snapshot if it doesn't exist.
    Provides session tracking for autosave management.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if game_id column exists
        cursor.execute("PRAGMA table_info(game_state_snapshot)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if 'game_id' not in columns:
            print("[FTB State DB] Adding game_id column...")
            cursor.execute("ALTER TABLE game_state_snapshot ADD COLUMN game_id TEXT")
            conn.commit()
            print("[FTB State DB] game_id column added successfully")
        
    except Exception as e:
        print(f"[FTB State DB] game_id column migration error: {e}")
    finally:
        conn.close()


@contextmanager
def get_connection(db_path: str):
    """Thread-safe database connection context manager."""
    if not hasattr(_thread_local, 'connections'):
        _thread_local.connections = {}
    
    if db_path not in _thread_local.connections:
        _thread_local.connections[db_path] = sqlite3.connect(db_path, check_same_thread=False)
        _thread_local.connections[db_path].row_factory = sqlite3.Row
    
    conn = _thread_local.connections[db_path]
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e


# ============================================================================
# WRITE OPERATIONS (Called by ftb_game.py)
# ============================================================================


def upsert_game_state(cursor, game_id: str, key: str, value: str) -> None:
    """Insert or update a key-value pair in the game_state_kv table.

    Designed to be called within an existing cursor/transaction so race-day
    writes can batch many keys in a single commit.

    Args:
        cursor: An open sqlite3.Cursor
        game_id: Current game UUID
        key: State key (e.g. 'race_day_phase')
        value: String value to store
    """
    import time as _time
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_state_kv (
            game_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT,
            updated_ts REAL,
            PRIMARY KEY (game_id, key)
        )
    """)
    cursor.execute(
        """INSERT OR REPLACE INTO game_state_kv (game_id, key, value, updated_ts)
           VALUES (?, ?, ?, ?)""",
        (game_id, key, value, _time.time()),
    )


def write_game_snapshot(db_path: str, state: Any) -> None:
    """Write complete game state snapshot after tick.
    
    Args:
        db_path: Database path
        state: SimState object from ftb_game.py
    """
    import time
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Game state snapshot
        cursor.execute("""
            INSERT OR REPLACE INTO game_state_snapshot 
            (id, tick, phase, season, day_of_year, time_mode, control_mode, active_tab, seed, game_id, races_completed_this_season, last_updated_ts)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            state.tick,
            state.phase,
            state.season_number,
            state.sim_day_of_year,
            state.time_mode,
            state.control_mode,
            getattr(state, 'active_tab', None),
            str(state.seed),  # Convert to string to handle large integers
            getattr(state, 'game_id', ''),  # Game session identifier
            getattr(state, 'races_completed_this_season', 0),
            time.time()
        ))
        
        # Player state
        if state.player_team:
            team = state.player_team
            champ_position = team.standing_metrics.get('championship_position', 0)
            champ_points = team.standing_metrics.get('points', 0)

            # Prefer live league standings when available
            try:
                player_league = None
                for league in state.leagues.values():
                    if team in league.teams:
                        player_league = league
                        break
                if player_league:
                    standings = sorted(
                        player_league.championship_table.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )
                    for pos, (team_name, points) in enumerate(standings, 1):
                        if team_name == team.name:
                            champ_position = pos
                            champ_points = points
                            break
            except Exception:
                pass

            cursor.execute("""
                INSERT OR REPLACE INTO player_state
                (id, team_name, budget, championship_position, points, morale, reputation, tier, league_id, focus, identity_json, ownership_type)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                team.name,
                team.budget.cash,
                champ_position,
                champ_points,
                team.standing_metrics.get('morale', 50.0),
                team.standing_metrics.get('reputation', 0.0),
                team.tier,
                team.league_id,
                state.player_focus,
                json.dumps(state.player_identity),
                getattr(team, 'ownership_type', 'hired_manager')
            ))
        
        # Teams
        cursor.execute("DELETE FROM teams")
        # Build unique team list (player_team may already be in ai_teams)
        all_teams = []
        seen_names = set()
        if state.player_team and state.player_team.name not in seen_names:
            all_teams.append(state.player_team)
            seen_names.add(state.player_team.name)
        for team in state.ai_teams:
            if team.name not in seen_names:
                all_teams.append(team)
                seen_names.add(team.name)
        
        for team in all_teams:
            # Calculate infrastructure summary for narrator
            infra_summary = {
                'avg_quality': 0,
                'facilities_at_zero': 0,
                'high_tier_facilities': 0,
                'high_tier_at_zero': 0,
                'total_unlocked': 0
            }
            
            if hasattr(team, 'infrastructure'):
                quality_values = []
                high_tier_count = 0
                high_tier_zero = 0
                facilities_at_zero = 0
                total_unlocked = 0
                
                for facility_key, value in team.infrastructure.items():
                    if facility_key.endswith('_unlocked'):
                        if value:  # Facility is unlocked
                            total_unlocked += 1
                        continue
                    
                    unlock_key = f"{facility_key}_unlocked"
                    is_unlocked = team.infrastructure.get(unlock_key, False)
                    
                    if is_unlocked:
                        quality_values.append(value)
                        
                        # Track facilities at zero (sold)
                        if value == 0:
                            facilities_at_zero += 1
                        
                        # Track high-tier facilities (Formula Y/Z)
                        try:
                            from plugins.ftb_game import FACILITY_TIER_MAP
                            facility_tier = FACILITY_TIER_MAP.get(facility_key, 1)
                            if facility_tier >= 4:
                                high_tier_count += 1
                                if value == 0:
                                    high_tier_zero += 1
                        except:
                            pass
                
                infra_summary['avg_quality'] = sum(quality_values) / len(quality_values) if quality_values else 50.0
                infra_summary['facilities_at_zero'] = facilities_at_zero
                infra_summary['high_tier_facilities'] = high_tier_count
                infra_summary['high_tier_at_zero'] = high_tier_zero
                infra_summary['total_unlocked'] = total_unlocked
            
            cursor.execute("""
                INSERT OR REPLACE INTO teams
                (team_name, tier, league_id, budget, championship_position, points, is_player_team, principal_name, ownership_type, standing_metrics_json, infrastructure_summary_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                team.name,
                team.tier,
                team.league_id,
                team.budget.cash,
                team.standing_metrics.get('championship_position', 0),
                team.standing_metrics.get('points', 0),
                1 if team == state.player_team else 0,
                team.principal.name if team.principal else None,
                getattr(team, 'ownership_type', 'hired_manager'),
                json.dumps(team.standing_metrics),
                json.dumps(infra_summary)
            ))
        
        # Entities (drivers, engineers, mechanics, strategists)
        cursor.execute("DELETE FROM entities WHERE is_free_agent = 0")
        for team in all_teams:
            for driver in team.drivers:
                _insert_entity(cursor, driver, "Driver", team.name, state)
            for engineer in team.engineers:
                _insert_entity(cursor, engineer, "Engineer", team.name, state)
            for mechanic in team.mechanics:
                _insert_entity(cursor, mechanic, "Mechanic", team.name, state)
            if team.strategist:
                _insert_entity(cursor, team.strategist, "Strategist", team.name, state)
        
        # League standings
        cursor.execute("DELETE FROM league_standings")
        for league_id, league in state.leagues.items():
            standings = []
            for team in sorted(league.teams, key=lambda t: t.standing_metrics.get('points', 0), reverse=True):
                standings.append({
                    'team': team.name,
                    'points': team.standing_metrics.get('points', 0),
                    'position': team.standing_metrics.get('championship_position', 0)
                })
            
            cursor.execute("""
                INSERT OR REPLACE INTO league_standings (league_id, tier, league_name, standings_json)
                VALUES (?, ?, ?, ?)
            """, (league_id, league.tier, league.name, json.dumps(standings)))
        
        # Job board
        cursor.execute("DELETE FROM job_board")
        if hasattr(state, 'job_board') and state.job_board:
            for idx, listing in enumerate(state.job_board.vacancies):
                cursor.execute("""
                    INSERT OR REPLACE INTO job_board (team_name, role, tier, salary, visibility_threshold, created_tick)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    listing.team_name or (listing.team.name if hasattr(listing, 'team') and listing.team else ""),
                    listing.role,
                    listing.tier,
                    listing.salary,
                    getattr(listing, 'visibility_threshold', 0.0),
                    getattr(listing, 'created_tick', state.tick)
                ))
        
        # Sponsorships
        cursor.execute("DELETE FROM sponsorships")
        if hasattr(state, 'sponsorships'):
            for team_name, sponsors_list in state.sponsorships.items():
                for sponsor in sponsors_list:
                    cursor.execute("""
                        INSERT INTO sponsorships (
                            team_name, sponsor_name, sponsor_id, tier, financial_tier,
                            industry, sub_industry, base_payment_per_season, duration_seasons,
                            seasons_active, confidence, contract_type, evaluation_cadence,
                            signed_tick, last_evaluated_tick, warning_issued,
                            brand_profile_json, contract_behavior_json, activation_style_json,
                            narrative_hooks_json, exclusivity_clauses_json, performance_history_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        team_name,
                        sponsor.sponsor_name,
                        sponsor.sponsor_id,
                        sponsor.tier,
                        sponsor.financial_tier,
                        sponsor.industry,
                        sponsor.sub_industry,
                        sponsor.base_payment_per_season,
                        sponsor.duration_seasons,
                        sponsor.seasons_active,
                        sponsor.confidence,
                        sponsor.contract_type,
                        sponsor.evaluation_cadence,
                        sponsor.signed_tick,
                        sponsor.last_evaluated_tick,
                        1 if sponsor.warning_issued else 0,
                        sponsor.brand_profile_json,
                        sponsor.contract_behavior_json,
                        sponsor.activation_style_json,
                        sponsor.narrative_hooks_json,
                        json.dumps(sponsor.exclusivity_clauses),
                        json.dumps(sponsor.performance_history)
                    ))
        
        # Penalties
        _write_penalties(cursor, state)


def _insert_entity(cursor, entity, entity_type: str, team_name: str, state: Any):
    """Helper to insert entity record."""
    contract = state.contracts.get(entity.entity_id) if hasattr(state, 'contracts') else None
    
    cursor.execute("""
        INSERT OR REPLACE INTO entities
        (entity_id, entity_type, name, age, team_name, overall_rating, stats_json, contract_end_day, salary, is_free_agent, time_in_pool_days, exit_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, NULL)
    """, (
        entity.entity_id,
        entity_type,
        entity.name,
        entity.age,
        team_name,
        entity.overall_rating,
        json.dumps(entity.current_ratings),
        contract.start_day + contract.duration_days if contract else None,
        getattr(entity, 'salary', 0),
    ))


def write_event_batch(db_path: str, events: List[Any]) -> None:
    """Append events to buffer for narrator consumption.
    
    Args:
        db_path: Database path
        events: List of SimEvent objects
    """
    import time
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        for event in events:
            cursor.execute("""
                INSERT OR IGNORE INTO events_buffer
                (event_id, tick, event_type, category, priority, severity, team, data_json, emitted_to_narrator, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """, (
                event.event_id,
                event.ts,
                event.event_type,
                event.category,
                event.priority,
                event.severity,
                event.data.get('team', ''),
                json.dumps(event.data),
                time.time()
            ))


def write_ui_context(db_path: str, active_tab: str, tick: int) -> None:
    """Update UI context (current tab) for narrator awareness.
    
    Args:
        db_path: Database path
        active_tab: Name of active UI tab
        tick: Current game tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO ui_context (id, active_tab, last_tab_change_tick)
            VALUES (1, ?, ?)
        """, (active_tab, tick))


def write_free_agents(db_path: str, free_agents: List[Any]) -> None:
    """Update free agent pool.
    
    Args:
        db_path: Database path
        free_agents: List of FreeAgent wrappers or entity objects
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Clear and repopulate
        cursor.execute("DELETE FROM free_agents")
        
        for agent in free_agents:
            entity = agent.entity if hasattr(agent, 'entity') else agent
            if entity is None:
                continue
            asking_salary = agent.asking_salary if hasattr(agent, 'asking_salary') else getattr(entity, 'asking_salary', 50000)
            time_in_pool = agent.time_in_pool_days if hasattr(agent, 'time_in_pool_days') else getattr(entity, 'time_in_pool_days', 0)
            exit_reason = agent.exit_reason if hasattr(agent, 'exit_reason') else getattr(entity, 'exit_reason', None)
            cursor.execute("""
                INSERT OR REPLACE INTO free_agents
                (entity_id, role, age, tier, overall_rating, asking_salary, time_in_pool_days, exit_reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entity.entity_id,
                entity.__class__.__name__,
                entity.age,
                getattr(entity, 'tier', 1),
                entity.overall_rating,
                asking_salary,
                time_in_pool,
                exit_reason
            ))


def write_decision_history(db_path: str, decision_record: Dict[str, Any]) -> None:
    """Log a resolved player/delegate decision.
    
    Args:
        db_path: Database path
        decision_record: Dict containing decision details
            Required keys: decision_id, tick, season, game_day, category, decision_text,
                          options_json, chosen_option_id, chosen_option_label
            Optional keys: immediate_cost, rationale, resolved_by, metadata_json
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO decision_history
            (decision_id, tick, season, game_day, category, decision_text, options_json,
             chosen_option_id, chosen_option_label, immediate_cost, rationale, resolved_by, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            decision_record['decision_id'],
            decision_record['tick'],
            decision_record['season'],
            decision_record['game_day'],
            decision_record['category'],
            decision_record['decision_text'],
            decision_record['options_json'],
            decision_record.get('chosen_option_id'),
            decision_record.get('chosen_option_label'),
            decision_record.get('immediate_cost', 0.0),
            decision_record.get('rationale'),
            decision_record.get('resolved_by', 'player'),
            decision_record.get('metadata_json')
        ))


def write_race_result_archive(db_path: str, race_record: Dict[str, Any]) -> None:
    """Archive a completed race result.
    
    Args:
        db_path: Database path
        race_record: Dict containing race result details
            Required keys: race_id, season, round_number, league_id, track_name, tick,
                          player_team_name, player_drivers_json, finish_positions_json
            Optional keys: grid_position, prize_money, fastest_lap_holder, incidents_json,
                          championship_position_after, points_after, metadata_json
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO race_results_archive
            (race_id, season, round_number, league_id, track_name, tick, player_team_name,
             player_drivers_json, finish_positions_json, grid_position, prize_money,
             fastest_lap_holder, incidents_json, championship_position_after, points_after, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            race_record['race_id'],
            race_record['season'],
            race_record['round_number'],
            race_record['league_id'],
            race_record['track_name'],
            race_record['tick'],
            race_record['player_team_name'],
            race_record['player_drivers_json'],
            race_record['finish_positions_json'],
            race_record.get('grid_position'),
            race_record.get('prize_money', 0.0),
            race_record.get('fastest_lap_holder'),
            race_record.get('incidents_json'),
            race_record.get('championship_position_after'),
            race_record.get('points_after'),
            race_record.get('metadata_json')
        ))


def write_financial_transaction(db_path: str, transaction: Dict[str, Any]) -> None:
    """Log a financial transaction (income or expense).
    
    Args:
        db_path: Database path
        transaction: Dict containing transaction details
            Required keys: tick, season, game_day, type, category, amount, balance_after, description
            Optional keys: related_entity, metadata_json
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO financial_transactions
            (tick, season, game_day, type, category, amount, balance_after, description, related_entity, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction['tick'],
            transaction['season'],
            transaction['game_day'],
            transaction['type'],
            transaction['category'],
            transaction['amount'],
            transaction['balance_after'],
            transaction['description'],
            transaction.get('related_entity'),
            transaction.get('metadata_json')
        ))


def write_season_summary(db_path: str, summary: Dict[str, Any]) -> None:
    """Record end-of-season performance summary.
    
    Args:
        db_path: Database path
        summary: Dict containing season summary details
            Required keys: season, team_name, tier, league_id
            Optional keys: championship_position, total_points, races_entered, wins, podiums,
                          poles, season_prize_money, season_sponsor_income, season_expenses,
                          starting_balance, ending_balance, promoted, relegated, metadata_json
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO season_summaries
            (season, team_name, tier, league_id, championship_position, total_points, races_entered,
             wins, podiums, poles, season_prize_money, season_sponsor_income, season_expenses,
             starting_balance, ending_balance, promoted, relegated, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            summary['season'],
            summary['team_name'],
            summary['tier'],
            summary['league_id'],
            summary.get('championship_position'),
            summary.get('total_points', 0.0),
            summary.get('races_entered', 0),
            summary.get('wins', 0),
            summary.get('podiums', 0),
            summary.get('poles', 0),
            summary.get('season_prize_money', 0.0),
            summary.get('season_sponsor_income', 0.0),
            summary.get('season_expenses', 0.0),
            summary.get('starting_balance', 0.0),
            summary.get('ending_balance', 0.0),
            summary.get('promoted', 0),
            summary.get('relegated', 0),
            summary.get('metadata_json')
        ))


# ============================================================================
# READ OPERATIONS (Called by narrator/delegate AI)
# ============================================================================

def query_player_state(db_path: str) -> Optional[Dict[str, Any]]:
    """Get current player state snapshot.
    
    Returns:
        Dict with player team info, budget, standings, etc.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM player_state WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            return {
                'team_name': row['team_name'],
                'budget': row['budget'],
                'championship_position': row['championship_position'],
                'points': row['points'],
                'morale': row['morale'],
                'reputation': row['reputation'],
                'tier': row['tier'],
                'league_id': row['league_id'],
                'focus': row['focus'],
                'identity': json.loads(row['identity_json']),
                'ownership_type': row['ownership_type']
            }
        return None


def query_game_state(db_path: str) -> Optional[Dict[str, Any]]:
    """Get current game state snapshot.
    
    Returns:
        Dict with tick, phase, season, day, modes, etc.
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM game_state_snapshot WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            # Handle seed as either int or str for backward compatibility
            seed_value = row['seed']
            if isinstance(seed_value, str):
                try:
                    seed_value = int(seed_value)
                except (ValueError, TypeError):
                    seed_value = 0  # Fallback for invalid seeds
            
            return {
                'tick': row['tick'],
                'phase': row['phase'],
                'season': row['season'],
                'day': row['day_of_year'],
                'time_mode': row['time_mode'],
                'control_mode': row['control_mode'],
                'active_tab': row['active_tab'],
                'seed': seed_value,
                'races_completed_this_season': row['races_completed_this_season'] if 'races_completed_this_season' in row.keys() else 0
            }
        return None


def query_entities_by_team(db_path: str, team_name: str) -> List[Dict[str, Any]]:
    """Get all entities (roster) for a team.
    
    Args:
        team_name: Name of team
        
    Returns:
        List of entity dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT entity_id, entity_type, name, age, overall_rating, stats_json, contract_end_day, salary
            FROM entities
            WHERE team_name = ? AND is_free_agent = 0
        """, (team_name,))
        
        entities = []
        for row in cursor.fetchall():
            entities.append({
                'entity_id': row['entity_id'],
                'type': row['entity_type'],
                'name': row['name'],
                'age': row['age'],
                'overall': row['overall_rating'],
                'stats': json.loads(row['stats_json']),
                'contract_end': row['contract_end_day'],
                'salary': row['salary']
            })
        
        return entities


def query_sponsorships(db_path: str, team_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get sponsorship deals, optionally filtered by team.
    
    Args:
        db_path: Database path
        team_name: Optional team name filter
        
    Returns:
        List of sponsorship dicts with full profile data
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        if team_name:
            cursor.execute("""
                SELECT * FROM sponsorships WHERE team_name = ?
            """, (team_name,))
        else:
            cursor.execute("SELECT * FROM sponsorships")
        
        def _safe_json_loads(raw: Optional[str], fallback: Any) -> Any:
            if not raw:
                return fallback
            try:
                return json.loads(raw)
            except Exception:
                return fallback

        sponsorships = []
        for row in cursor.fetchall():
            sponsorships.append({
                'sponsor_name': row['sponsor_name'],
                'sponsor_id': row['sponsor_id'],
                'team_name': row['team_name'],
                'tier': row['tier'],
                'financial_tier': row['financial_tier'],
                'industry': row['industry'],
                'sub_industry': row['sub_industry'],
                'base_payment_per_season': row['base_payment_per_season'],
                'duration_seasons': row['duration_seasons'],
                'seasons_active': row['seasons_active'],
                'confidence': row['confidence'],
                'contract_type': row['contract_type'],
                'warning_issued': bool(row['warning_issued']),
                'brand_profile': _safe_json_loads(row['brand_profile_json'], {}),
                'contract_behavior': _safe_json_loads(row['contract_behavior_json'], {}),
                'activation_style': _safe_json_loads(row['activation_style_json'], {}),
                'narrative_hooks': _safe_json_loads(row['narrative_hooks_json'], {}),
                'exclusivity_clauses': _safe_json_loads(row['exclusivity_clauses_json'], []),
                'performance_history': _safe_json_loads(row['performance_history_json'], [])
            })
        
        return sponsorships


def _write_penalties(cursor, state: Any) -> None:
    """Write penalties to database."""
    cursor.execute("DELETE FROM penalties")
    if hasattr(state, 'penalties'):
        for penalty in state.penalties:
            cursor.execute("""
                INSERT INTO penalties (
                    race_id, team_name, driver_name, penalty_type, magnitude,
                    reason, game_day, tier, issued_by, appealable, applied, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                getattr(penalty, 'race_id', 0),
                penalty.team_name,
                getattr(penalty, 'driver_name', ''),
                penalty.penalty_type,
                penalty.magnitude,
                penalty.reason,
                getattr(state, 'current_day', 0),
                getattr(state, 'current_tier', 1),
                getattr(penalty, 'issued_by', 'Stewards'),
                1 if getattr(penalty, 'appealable', False) else 0,
                1 if getattr(penalty, 'applied', False) else 0,
                json.dumps(getattr(penalty, 'metadata', {}))
            ))


def query_penalties(db_path: str, team_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Get penalties, optionally filtered by team.
    
    Args:
        db_path: Database path
        team_name: Optional team name filter
        limit: Max penalties to return
        
    Returns:
        List of penalty dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        if team_name:
            cursor.execute("""
                SELECT * FROM penalties 
                WHERE team_name = ?
                ORDER BY game_day DESC, penalty_id DESC
                LIMIT ?
            """, (team_name, limit))
        else:
            cursor.execute("""
                SELECT * FROM penalties
                ORDER BY game_day DESC, penalty_id DESC
                LIMIT ?
            """, (limit,))
        
        penalties = []
        for row in cursor.fetchall():
            penalties.append({
                'penalty_id': row['penalty_id'],
                'race_id': row['race_id'],
                'team_name': row['team_name'],
                'driver_name': row['driver_name'],
                'penalty_type': row['penalty_type'],
                'magnitude': row['magnitude'],
                'reason': row['reason'],
                'game_day': row['game_day'],
                'tier': row['tier'],
                'issued_by': row['issued_by'],
                'appealable': bool(row['appealable']),
                'applied': bool(row['applied']),
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {}
            })
        
        return penalties


def query_team_penalty_history(db_path: str, team_name: str, days_back: int = 90) -> Dict[str, Any]:
    """Get penalty accumulation stats for a team over recent period.
    
    Args:
        db_path: Database path  
        team_name: Team name
        days_back: How many game days back to analyze
        
    Returns:
        Dict with penalty counts by type and warning accumulation
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get current game day
        cursor.execute("SELECT current_day FROM game_state LIMIT 1")
        row = cursor.fetchone()
        current_day = row['current_day'] if row else 0
        
        cutoff_day = max(0, current_day - days_back)
        
        cursor.execute("""
            SELECT penalty_type, COUNT(*) as count
            FROM penalties
            WHERE team_name = ? AND game_day >= ?
            GROUP BY penalty_type
        """, (team_name, cutoff_day))
        
        penalty_counts = {}
        for row in cursor.fetchall():
            penalty_counts[row['penalty_type']] = row['count']
        
        return {
            'team_name': team_name,
            'days_analyzed': days_back,
            'cutoff_day': cutoff_day,
            'current_day': current_day,
            'penalty_counts': penalty_counts,
            'total_penalties': sum(penalty_counts.values()),
            'warnings': penalty_counts.get('warning', 0),
            'grid_penalties': penalty_counts.get('grid_penalty', 0),
            'fines': penalty_counts.get('fine', 0),
            'points_deductions': penalty_counts.get('points_deduction', 0)
        }


def query_unseen_events(db_path: str, mark_seen: bool = True, limit: int = 100) -> List[Dict[str, Any]]:
    """Get events not yet consumed by narrator.
    
    Args:
        mark_seen: Whether to mark events as emitted
        limit: Max events to return
        
    Returns:
        List of event dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT event_id, tick, event_type, category, priority, severity, team, data_json
            FROM events_buffer
            WHERE emitted_to_narrator = 0
            ORDER BY tick DESC, priority DESC
            LIMIT ?
        """, (limit,))
        
        events = []
        event_ids = []
        
        for row in cursor.fetchall():
            events.append({
                'event_id': row['event_id'],
                'tick': row['tick'],
                'event_type': row['event_type'],
                'category': row['category'],
                'priority': row['priority'],
                'severity': row['severity'],
                'team': row['team'],
                'data': json.loads(row['data_json'])
            })
            event_ids.append(row['event_id'])
        
        if mark_seen and event_ids:
            placeholders = ','.join('?' * len(event_ids))
            cursor.execute(f"""
                UPDATE events_buffer
                SET emitted_to_narrator = 1
                WHERE event_id IN ({placeholders})
            """, event_ids)
        
        return events


def _event_matches_tier(event_data: Dict[str, Any], tier: int) -> bool:
    if event_data.get("tier") == tier:
        return True
    if event_data.get("league_tier") == tier:
        return True

    league_name = str(event_data.get("league_name", "")).lower()
    if league_name:
        normalized = league_name.replace("_", " ")
        if tier == 5 and "formula z" in normalized:
            return True

    return False


def query_tier_events(db_path: str, tier: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Get recent events for a specific tier (non-destructive).

    Args:
        tier: Tier number (1-5)
        limit: Max events to return after filtering

    Returns:
        List of event dicts
    """
    fetch_limit = max(limit * 5, 100)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT event_id, tick, event_type, category, priority, severity, team, data_json
            FROM events_buffer
            ORDER BY tick DESC, priority DESC
            LIMIT ?
        """, (fetch_limit,))

        events = []
        for row in cursor.fetchall():
            data = json.loads(row['data_json'])
            if not _event_matches_tier(data, tier):
                continue
            events.append({
                'event_id': row['event_id'],
                'tick': row['tick'],
                'event_type': row['event_type'],
                'category': row['category'],
                'priority': row['priority'],
                'severity': row['severity'],
                'team': row['team'],
                'data': data
            })

            if len(events) >= limit:
                break

        return events


def query_league_standings(db_path: str, tier: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get league standings, optionally filtered by tier.
    
    Args:
        tier: Filter by tier (1-5), or None for all
        
    Returns:
        List of league standings dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        if tier:
            cursor.execute("""
                SELECT league_id, tier, league_name, standings_json
                FROM league_standings
                WHERE tier = ?
            """, (tier,))
        else:
            cursor.execute("SELECT league_id, tier, league_name, standings_json FROM league_standings")
        
        leagues = []
        for row in cursor.fetchall():
            leagues.append({
                'league_id': row['league_id'],
                'tier': row['tier'],
                'name': row['league_name'],
                'standings': json.loads(row['standings_json'])
            })
        
        return leagues


def query_job_board(db_path: str, tier: Optional[int] = None, role: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get job board listings.
    
    Args:
        tier: Filter by tier
        role: Filter by role (e.g., "Driver", "Manager")
        
    Returns:
        List of job listing dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM job_board WHERE 1=1"
        params = []
        
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        
        if role:
            query += " AND role = ?"
            params.append(role)
        
        cursor.execute(query, params)
        
        listings = []
        for row in cursor.fetchall():
            listings.append({
                'listing_id': row['listing_id'],
                'team_name': row['team_name'],
                'role': row['role'],
                'tier': row['tier'],
                'salary': row['salary'],
                'visibility_threshold': row['visibility_threshold'],
                'created_tick': row['created_tick']
            })
        
        return listings


def query_free_agents(db_path: str, role: Optional[str] = None, tier: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
    """Get free agents from pool.
    
    Args:
        role: Filter by role type
        tier: Filter by tier
        limit: Max results
        
    Returns:
        List of free agent dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM free_agents WHERE exit_reason IS NULL"
        params = []
        
        if role:
            query += " AND role = ?"
            params.append(role)
        
        if tier:
            query += " AND tier <= ?"
            params.append(tier)
        
        query += " ORDER BY overall_rating DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        
        agents = []
        for row in cursor.fetchall():
            agents.append({
                'entity_id': row['entity_id'],
                'role': row['role'],
                'age': row['age'],
                'tier': row['tier'],
                'overall': row['overall_rating'],
                'salary': row['asking_salary'],
                'time_in_pool': row['time_in_pool_days']
            })
        
        return agents


def query_ui_context(db_path: str) -> Optional[Dict[str, Any]]:
    """Get current UI context (active tab).
    
    Returns:
        Dict with active_tab and last_tab_change_tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM ui_context WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            return {
                'active_tab': row['active_tab'],
                'last_tab_change_tick': row['last_tab_change_tick']
            }
        return None


def query_team_by_name(db_path: str, team_name: str) -> Optional[Dict[str, Any]]:
    """Get team info by name.
    
    Args:
        team_name: Name of team
        
    Returns:
        Dict with team info
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM teams WHERE team_name = ?", (team_name,))
        row = cursor.fetchone()
        
        if row:
            infrastructure_summary = {}
            if 'infrastructure_summary_json' in row.keys():
                try:
                    infrastructure_summary = json.loads(row['infrastructure_summary_json']) if row['infrastructure_summary_json'] else {}
                except Exception:
                    infrastructure_summary = {}
            return {
                'name': row['team_name'],
                'tier': row['tier'],
                'league_id': row['league_id'],
                'budget': row['budget'],
                'position': row['championship_position'],
                'points': row['points'],
                'is_player': bool(row['is_player_team']),
                'principal': row['principal_name'],
                'ownership_type': row['ownership_type'],
                'standing_metrics': json.loads(row['standing_metrics_json']) if row['standing_metrics_json'] else {},
                'infrastructure_summary': infrastructure_summary
            }
        return None


def query_all_teams(db_path: str, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all teams in database, optionally filtered by league.
    
    Args:
        db_path: Path to database
        league_id: Optional league ID to filter teams by specific league
        
    Returns:
        List of dicts with team info
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        if league_id:
            cursor.execute("SELECT * FROM teams WHERE league_id = ?", (league_id,))
        else:
            cursor.execute("SELECT * FROM teams")
        teams = []
        
        for row in cursor.fetchall():
            infrastructure_summary = {}
            if 'infrastructure_summary_json' in row.keys():
                try:
                    infrastructure_summary = json.loads(row['infrastructure_summary_json']) if row['infrastructure_summary_json'] else {}
                except Exception:
                    infrastructure_summary = {}
            teams.append({
                'name': row['team_name'],
                'tier': row['tier'],
                'league_id': row['league_id'],
                'budget': row['budget'],
                'position': row['championship_position'],
                'points': row['points'],
                'is_player': bool(row['is_player_team']),
                'principal': row['principal_name'],
                'ownership_type': row['ownership_type'],
                'standing_metrics': json.loads(row['standing_metrics_json']) if row['standing_metrics_json'] else {},
                'infrastructure_summary': infrastructure_summary
            })
        
        return teams


# ============================================================================
# NARRATOR CONTEXT PERSISTENCE (CONTINUITY-FIRST)
# ============================================================================

def save_narrator_context(db_path: str, context: Dict[str, Any]):
    """Save narrator context including Show Bible fields.
    
    Args:
        db_path: Path to database
        context: Narrator context dict with Show Bible fields
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Convert lists/deques to JSON
        topics_json = json.dumps(list(context.get('last_topics_discussed', [])))
        themes_json = json.dumps(context.get('active_themes', []))
        streak_json = json.dumps({
            'races_since_points': context.get('races_since_points', 0),
            'consecutive_dnfs': context.get('consecutive_dnfs', 0),
            'races_since_win': context.get('races_since_win', 0)
        })
        segment_history_json = json.dumps(context.get('segment_history', {}))
        claim_tags_json = json.dumps(list(context.get('claim_tags', [])))
        
        cursor.execute("""
            INSERT OR REPLACE INTO narrator_context (
                id, last_commentary_time, topics_discussed_json, active_themes_json,
                player_streak_data_json, segment_history_json, player_team, save_timestamp,
                current_motif, open_loop, named_focus, stakes_axis, tone,
                last_generated_spine, last_generated_beat, claim_tags_json,
                segments_since_motif_change
            ) VALUES (
                1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            context.get('last_commentary_time', 0),
            topics_json,
            themes_json,
            streak_json,
            segment_history_json,
            context.get('player_team', ''),
            context.get('save_timestamp', 0),
            context.get('current_motif', 'quiet climb'),
            context.get('open_loop', ''),
            context.get('named_focus', ''),
            context.get('stakes_axis', 'budget'),
            context.get('tone', 'wry'),
            context.get('last_generated_spine', ''),
            context.get('last_generated_beat', ''),
            claim_tags_json,
            context.get('segments_since_motif_change', 0)
        ))


def load_narrator_context(db_path: str) -> Optional[Dict[str, Any]]:
    """Load narrator context including Show Bible fields.
    
    Args:
        db_path: Path to database
        
    Returns:
        Dict with narrator context or None if not found
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM narrator_context WHERE id = 1")
        row = cursor.fetchone()
        
        if row:
            return {
                'last_commentary_time': row['last_commentary_time'],
                'last_topics_discussed': json.loads(row['topics_discussed_json']) if row['topics_discussed_json'] else [],
                'active_themes': json.loads(row['active_themes_json']) if row['active_themes_json'] else [],
                'player_streak_data': json.loads(row['player_streak_data_json']) if row['player_streak_data_json'] else {},
                'segment_history': json.loads(row['segment_history_json']) if row['segment_history_json'] else {},
                'player_team': row['player_team'],
                'save_timestamp': row['save_timestamp'],
                # Show Bible fields
                'current_motif': row['current_motif'] if 'current_motif' in row.keys() else 'quiet climb',
                'open_loop': row['open_loop'] if 'open_loop' in row.keys() else '',
                'named_focus': row['named_focus'] if 'named_focus' in row.keys() else '',
                'stakes_axis': row['stakes_axis'] if 'stakes_axis' in row.keys() else 'budget',
                'tone': row['tone'] if 'tone' in row.keys() else 'wry',
                'last_generated_spine': row['last_generated_spine'] if 'last_generated_spine' in row.keys() else '',
                'last_generated_beat': row['last_generated_beat'] if 'last_generated_beat' in row.keys() else '',
                'claim_tags': json.loads(row['claim_tags_json']) if ('claim_tags_json' in row.keys() and row['claim_tags_json']) else [],
                'segments_since_motif_change': row['segments_since_motif_change'] if 'segments_since_motif_change' in row.keys() else 0
            }
        return None


# ============================================================================
# CALENDAR OPERATIONS
# ============================================================================

def write_calendar_projection(db_path: str, projection: List[Dict[str, Any]]) -> None:
    """Write calendar projection to database (overwrites non-player-authored entries).
    
    Args:
        db_path: Path to SQLite database
        projection: List of calendar entry dicts from state.get_calendar_projection()
    """
    import time
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Remove old system-generated entries (keep player notes)
        cursor.execute("DELETE FROM calendar_entries WHERE is_player_authored = 0")
        
        # Insert new projection
        for entry in projection:
            cursor.execute("""
                INSERT INTO calendar_entries 
                (entry_day, entry_type, category, entity_id, title, description, 
                 priority, action_required, metadata_json, created_at, is_player_authored)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """, (
                entry['entry_day'],
                entry['entry_type'],
                entry['category'],
                entry.get('metadata', {}).get('entity_id'),
                entry['title'],
                entry['description'],
                entry.get('priority', 50),
                1 if entry.get('action_required', False) else 0,
                json.dumps(entry.get('metadata', {})),
                time.time()
            ))


def query_calendar_window(
    db_path: str,
    start_day: int,
    window_days: int = 30,
    include_player_authored: bool = True
) -> List[Dict[str, Any]]:
    """
    Query calendar entries in a time window.
    
    Args:
        db_path: Path to database
        start_day: Start day of window
        window_days: Number of days to look ahead
        include_player_authored: Whether to include user-created entries
    
    Returns:
        List of calendar entries as dicts
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        end_day = start_day + window_days
        
        query = """
            SELECT * FROM calendar_entries
            WHERE entry_day BETWEEN ? AND ?
        """
        
        params = [start_day, end_day]
        
        if not include_player_authored:
            query += " AND is_player_authored = 0"
        
        query += " ORDER BY entry_day ASC, priority DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[FTB State DB] Error querying calendar: {e}")
        return []


def query_folded_teams(db_path: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Query recently folded teams for historical context.
    
    Args:
        db_path: Path to database
        limit: Maximum number of folded teams to return (default 10)
    
    Returns:
        List of folded team records as dicts
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM folded_teams
            ORDER BY fold_tick DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"[FTB State DB] Error querying folded teams: {e}")
        return []


def query_league_economic_state(db_path: str, season: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Query league economic state for current or specific season.
    
    Args:
        db_path: Path to database
        season: Specific season to query, or None for latest
    
    Returns:
        Economic state dict or None if not found
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if season is not None:
            cursor.execute("""
                SELECT * FROM league_economic_state
                WHERE season = ?
            """, (season,))
        else:
            cursor.execute("""
                SELECT * FROM league_economic_state
                ORDER BY season DESC
                LIMIT 1
            """)
        
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    except Exception as e:
        print(f"[FTB State DB] Error querying economic state: {e}")
        return None


def query_calendar_window(
    db_path: str, 
    start_day: int, 
    end_day: int,
    categories: Optional[List[str]] = None,
    action_required_only: Optional[bool] = None,
    search_text: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Query calendar entries within date range with optional filters.
    
    Args:
        db_path: Path to SQLite database
        start_day: Start of window (inclusive)
        end_day: End of window (inclusive)
        categories: Optional list of categories to filter (competition, personnel, financial, pressure, player)
        action_required_only: If True, only return entries requiring action; if False, exclude action items; if None, all
        search_text: Optional text to search in title or description (case-insensitive)
        
    Returns:
        List of calendar entry dicts
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Build query dynamically based on filters
        query = "SELECT * FROM calendar_entries WHERE entry_day >= ? AND entry_day <= ?"
        params = [start_day, end_day]
        
        # Category filter
        if categories:
            placeholders = ','.join('?' * len(categories))
            query += f" AND category IN ({placeholders})"
            params.extend(categories)
        
        # Action required filter
        if action_required_only is True:
            query += " AND action_required = 1"
        elif action_required_only is False:
            query += " AND action_required = 0"
        
        # Text search filter
        if search_text:
            query += " AND (title LIKE ? OR description LIKE ?)"
            search_pattern = f"%{search_text}%"
            params.extend([search_pattern, search_pattern])
        
        query += " ORDER BY entry_day ASC, priority DESC"
        
        cursor.execute(query, params)
        
        rows = cursor.fetchall()
        entries = []
        for row in rows:
            entries.append({
                'id': row['id'],
                'entry_day': row['entry_day'],
                'entry_type': row['entry_type'],
                'category': row['category'],
                'entity_id': row['entity_id'],
                'title': row['title'],
                'description': row['description'],
                'is_player_authored': bool(row['is_player_authored']),
                'priority': row['priority'],
                'action_required': bool(row['action_required']),
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {},
                'created_at': row['created_at']
            })
        return entries


def query_decision_inbox(db_path: str) -> List[Dict[str, Any]]:
    """Query calendar entries requiring player action.
    
    Returns:
        List of entries with action_required=1, sorted by urgency
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM calendar_entries
            WHERE action_required = 1
            ORDER BY entry_day ASC, priority DESC
        """)
        
        rows = cursor.fetchall()
        entries = []
        for row in rows:
            entries.append({
                'id': row['id'],
                'entry_day': row['entry_day'],
                'entry_type': row['entry_type'],
                'category': row['category'],
                'title': row['title'],
                'description': row['description'],
                'priority': row['priority'],
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {}
            })
        return entries


def add_player_note(db_path: str, entry_day: int, title: str, description: str = "") -> int:
    """Add player-authored calendar note.
    
    Args:
        db_path: Path to SQLite database
        entry_day: Day when note/reminder applies
        title: Short note title
        description: Optional longer description
        
    Returns:
        ID of created entry
    """
    import time
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO calendar_entries
            (entry_day, entry_type, category, title, description, 
             is_player_authored, priority, action_required, created_at)
            VALUES (?, 'player_note', 'player', ?, ?, 1, 60, 0, ?)
        """, (entry_day, title, description, time.time()))
        
        return cursor.lastrowid


def delete_player_note(db_path: str, note_id: int) -> bool:
    """Delete player-authored note.
    
    Args:
        db_path: Path to SQLite database
        note_id: ID of note to delete
        
    Returns:
        True if deleted, False if not found or not player-authored
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM calendar_entries
            WHERE id = ? AND is_player_authored = 1
        """, (note_id,))
        
        return cursor.rowcount > 0


def query_decision_history(
    db_path: str,
    limit: Optional[int] = None,
    categories: Optional[List[str]] = None,
    seasons: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """Query player/delegate decision history.
    
    Args:
        db_path: Path to database
        limit: Maximum number of decisions to return (default: all)
        categories: Filter by decision categories (e.g., ["hire", "fire", "contract"])
        seasons: Filter by specific seasons
        
    Returns:
        List of decision records, newest first
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM decision_history WHERE 1=1"
        params = []
        
        if categories:
            placeholders = ','.join('?' * len(categories))
            query += f" AND category IN ({placeholders})"
            params.extend(categories)
        
        if seasons:
            placeholders = ','.join('?' * len(seasons))
            query += f" AND season IN ({placeholders})"
            params.extend(seasons)
        
        query += " ORDER BY tick DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'decision_id': row['decision_id'],
                'tick': row['tick'],
                'season': row['season'],
                'game_day': row['game_day'],
                'category': row['category'],
                'decision_text': row['decision_text'],
                'options': json.loads(row['options_json']) if row['options_json'] else [],
                'chosen_option_id': row['chosen_option_id'],
                'chosen_option_label': row['chosen_option_label'],
                'immediate_cost': row['immediate_cost'],
                'rationale': row['rationale'],
                'resolved_by': row['resolved_by'],
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {}
            })
        
        return results


def query_race_results(
    db_path: str,
    seasons: Optional[List[int]] = None,
    league_ids: Optional[List[str]] = None,
    tracks: Optional[List[str]] = None,
    min_position: Optional[int] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Query historical race results.
    
    Args:
        db_path: Path to database
        seasons: Filter by specific seasons
        league_ids: Filter by league ids
        tracks: Filter by track names
        min_position: Only return races where finish position <= this value (e.g., 3 for podiums)
        limit: Maximum number of results to return (default: all)
        
    Returns:
        List of race result records, newest first
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM race_results_archive WHERE 1=1"
        params = []
        
        if seasons:
            placeholders = ','.join('?' * len(seasons))
            query += f" AND season IN ({placeholders})"
            params.extend(seasons)

        if league_ids:
            placeholders = ','.join('?' * len(league_ids))
            query += f" AND league_id IN ({placeholders})"
            params.extend(league_ids)
        
        if tracks:
            placeholders = ','.join('?' * len(tracks))
            query += f" AND track_name IN ({placeholders})"
            params.extend(tracks)
        
        query += " ORDER BY season DESC, round_number DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'race_id': row['race_id'],
                'season': row['season'],
                'round_number': row['round_number'],
                'league_id': row['league_id'],
                'track_name': row['track_name'],
                'tick': row['tick'],
                'player_team_name': row['player_team_name'],
                'player_drivers': json.loads(row['player_drivers_json']) if row['player_drivers_json'] else [],
                'finish_positions': json.loads(row['finish_positions_json']) if row['finish_positions_json'] else [],
                'grid_position': row['grid_position'],
                'prize_money': row['prize_money'],
                'fastest_lap_holder': row['fastest_lap_holder'],
                'incidents': json.loads(row['incidents_json']) if row['incidents_json'] else [],
                'championship_position_after': row['championship_position_after'],
                'points_after': row['points_after'],
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {}
            })

        if min_position is not None:
            results = [
                r for r in results
                if any(p.get('position', 99) <= min_position for p in r.get('finish_positions', []))
            ]
        
        return results


def query_race_stats(
    db_path: str,
    seasons: Optional[List[int]] = None,
    league_ids: Optional[List[str]] = None,
    team_names: Optional[List[str]] = None,
    driver_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Aggregate race statistics from archived results.

    Args:
        db_path: Path to database
        seasons: Filter by specific seasons
        league_ids: Filter by league ids
        team_names: Filter to specific teams
        driver_names: Filter to specific drivers

    Returns:
        Dict with team_stats, driver_stats, race_count, seasons_tracked
    """
    results = query_race_results(
        db_path,
        seasons=seasons,
        league_ids=league_ids
    )

    team_filter = set(team_names) if team_names else None
    driver_filter = set(driver_names) if driver_names else None

    team_stats: Dict[str, Dict[str, Any]] = {}
    driver_stats: Dict[str, Dict[str, Any]] = {}
    seasons_tracked = set()

    for result in results:
        season = result.get('season')
        if season is not None:
            seasons_tracked.add(season)

        team_best_positions: Dict[str, int] = {}
        team_dnf_flags: Dict[str, bool] = {}

        for entry in result.get('finish_positions', []):
            team = entry.get('team')
            driver = entry.get('driver')
            position = entry.get('position', 99)
            status = entry.get('status', 'finished')

            if team:
                if team_filter is None or team in team_filter:
                    current_best = team_best_positions.get(team)
                    if current_best is None or position < current_best:
                        team_best_positions[team] = position
                    if status != 'finished':
                        team_dnf_flags[team] = True

            if driver:
                if driver_filter is None or driver in driver_filter:
                    stats = driver_stats.setdefault(driver, {
                        'wins': 0,
                        'podiums': 0,
                        'races': 0,
                        'dnfs': 0,
                        'best_finish': None
                    })
                    stats['races'] += 1
                    if position == 1:
                        stats['wins'] += 1
                    if position <= 3:
                        stats['podiums'] += 1
                    if status != 'finished':
                        stats['dnfs'] += 1
                    if stats['best_finish'] is None or position < stats['best_finish']:
                        stats['best_finish'] = position

        for team, best_position in team_best_positions.items():
            stats = team_stats.setdefault(team, {
                'wins': 0,
                'podiums': 0,
                'races': 0,
                'dnfs': 0,
                'best_finish': None
            })
            stats['races'] += 1
            if best_position == 1:
                stats['wins'] += 1
            if best_position <= 3:
                stats['podiums'] += 1
            if team_dnf_flags.get(team, False):
                stats['dnfs'] += 1
            if stats['best_finish'] is None or best_position < stats['best_finish']:
                stats['best_finish'] = best_position

    return {
        'team_stats': team_stats,
        'driver_stats': driver_stats,
        'race_count': len(results),
        'seasons_tracked': sorted(seasons_tracked)
    }


def query_financial_transactions(
    db_path: str,
    type: Optional[str] = None,
    categories: Optional[List[str]] = None,
    seasons: Optional[List[int]] = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Query financial transaction history.
    
    Args:
        db_path: Path to database
        type: Filter by "income" or "expense"
        categories: Filter by categories (e.g., ["salary", "prize_money", "sponsor_payment"])
        seasons: Filter by specific seasons
        limit: Maximum number of transactions to return (default: all)
        
    Returns:
        List of transaction records, newest first
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM financial_transactions WHERE 1=1"
        params = []
        
        if type:
            query += " AND type = ?"
            params.append(type)
        
        if categories:
            placeholders = ','.join('?' * len(categories))
            query += f" AND category IN ({placeholders})"
            params.extend(categories)
        
        if seasons:
            placeholders = ','.join('?' * len(seasons))
            query += f" AND season IN ({placeholders})"
            params.extend(seasons)
        
        query += " ORDER BY tick DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'transaction_id': row['transaction_id'],
                'tick': row['tick'],
                'season': row['season'],
                'game_day': row['game_day'],
                'type': row['type'],
                'category': row['category'],
                'amount': row['amount'],
                'balance_after': row['balance_after'],
                'description': row['description'],
                'related_entity': row['related_entity'],
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {}
            })
        
        return results


def query_season_summaries(
    db_path: str,
    seasons: Optional[List[int]] = None
) -> List[Dict[str, Any]]:
    """Query season performance summaries.
    
    Args:
        db_path: Path to database
        seasons: Filter by specific seasons (default: all seasons)
        
    Returns:
        List of season summary records, newest first
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM season_summaries WHERE 1=1"
        params = []
        
        if seasons:
            placeholders = ','.join('?' * len(seasons))
            query += f" AND season IN ({placeholders})"
            params.extend(seasons)
        
        query += " ORDER BY season DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'season': row['season'],
                'team_name': row['team_name'],
                'tier': row['tier'],
                'league_id': row['league_id'],
                'championship_position': row['championship_position'],
                'total_points': row['total_points'],
                'races_entered': row['races_entered'],
                'wins': row['wins'],
                'podiums': row['podiums'],
                'poles': row['poles'],
                'season_prize_money': row['season_prize_money'],
                'season_sponsor_income': row['season_sponsor_income'],
                'season_expenses': row['season_expenses'],
                'starting_balance': row['starting_balance'],
                'ending_balance': row['ending_balance'],
                'promoted': bool(row['promoted']),
                'relegated': bool(row['relegated']),
                'metadata': json.loads(row['metadata_json']) if row['metadata_json'] else {}
            })
        
        return results


# ============================================================================
# ML TRAINING: AI DECISION LOGGING
# ============================================================================

def log_ai_decision(
    db_path: str,
    tick: int,
    season: int,
    team_id: str,
    team_name: str,
    state_vector: Dict[str, Any],
    action_chosen: Dict[str, Any],
    action_scores: Optional[Dict[str, float]],
    principal_stats: Dict[str, float],
    budget_before: float,
    budget_after: float,
    championship_position: int
) -> None:
    """Log an AI team decision for ML training.
    
    Args:
        db_path: Path to database
        tick: Current simulation tick
        season: Current season number
        team_id: Unique team identifier
        team_name: Team name
        state_vector: Dict of team state features (budget_ratio, roster_quality, etc.)
        action_chosen: Dict describing the action taken
        action_scores: Dict mapping action names to evaluation scores (optional)
        principal_stats: Dict of team principal's 25 attributes
        budget_before: Team budget before action
        budget_after: Team budget after action
        championship_position: Team's current championship standing
    """
    import time
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ai_decisions (
                tick, season, team_id, team_name,
                state_vector_json, action_chosen_json, action_scores_json,
                principal_stats_json, budget_before, budget_after,
                championship_position, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tick, season, team_id, team_name,
            json.dumps(state_vector),
            json.dumps(action_chosen),
            json.dumps(action_scores) if action_scores else None,
            json.dumps(principal_stats),
            budget_before, budget_after,
            championship_position, time.time()
        ))
        
        conn.commit()


def log_team_outcome(
    db_path: str,
    team_id: str,
    team_name: str,
    season: int,
    championship_position: int,
    total_points: float,
    starting_budget: float,
    ending_budget: float,
    survival_flag: bool = True,
    folded_tick: Optional[int] = None,
    seasons_survived: int = 1
) -> None:
    """Log end-of-season team outcome metrics for ML success scoring.
    
    Args:
        db_path: Path to database
        team_id: Unique team identifier
        team_name: Team name
        season: Season number
        championship_position: Final championship standing
        total_points: Championship points earned
        starting_budget: Budget at season start
        ending_budget: Budget at season end
        survival_flag: True if team still exists
        folded_tick: Tick when team folded (if applicable)
        seasons_survived: Total seasons team has existed
    """
    import time
    
    # Calculate success metrics
    budget_delta = ending_budget - starting_budget
    budget_health_score = min(100.0, max(0.0, 
        50.0 + (ending_budget / max(starting_budget, 1.0) - 1.0) * 50.0
    ))
    
    # ROI: points earned per $100k spent (or gained)
    budget_spent = max(1.0, starting_budget - ending_budget) if ending_budget < starting_budget else 1.0
    roi_score = (total_points / (budget_spent / 100000.0)) if budget_spent > 0 else total_points
    roi_score = min(100.0, roi_score)  # Cap at 100
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO team_outcomes (
                team_id, team_name, season,
                championship_position, total_points,
                starting_budget, ending_budget,
                budget_health_score, roi_score,
                survival_flag, folded_tick, seasons_survived,
                created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            team_id, team_name, season,
            championship_position, total_points,
            starting_budget, ending_budget,
            budget_health_score, roi_score,
            1 if survival_flag else 0, folded_tick, seasons_survived,
            time.time()
        ))
        
        conn.commit()


def query_ai_decisions(
    db_path: str,
    team_id: Optional[str] = None,
    season: Optional[int] = None,
    min_tick: Optional[int] = None,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Query logged AI decisions for ML training.
    
    Args:
        db_path: Path to database
        team_id: Filter by specific team (optional)
        season: Filter by season (optional)
        min_tick: Filter by minimum tick (optional)
        limit: Maximum results to return
        
    Returns:
        List of AI decision records
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM ai_decisions WHERE 1=1"
        params = []
        
        if team_id:
            query += " AND team_id = ?"
            params.append(team_id)
        if season is not None:
            query += " AND season = ?"
            params.append(season)
        if min_tick is not None:
            query += " AND tick >= ?"
            params.append(min_tick)
        
        query += " ORDER BY tick DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'decision_id': row['decision_id'],
                'tick': row['tick'],
                'season': row['season'],
                'team_id': row['team_id'],
                'team_name': row['team_name'],
                'state_vector': json.loads(row['state_vector_json']),
                'action_chosen': json.loads(row['action_chosen_json']),
                'action_scores': json.loads(row['action_scores_json']) if row['action_scores_json'] else None,
                'principal_stats': json.loads(row['principal_stats_json']),
                'budget_before': row['budget_before'],
                'budget_after': row['budget_after'],
                'championship_position': row['championship_position'],
                'created_ts': row['created_ts']
            })
        
        return results


def query_team_outcomes(
    db_path: str,
    team_id: Optional[str] = None,
    min_budget_health: Optional[float] = None,
    min_roi: Optional[float] = None,
    survived_only: bool = False,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """Query team outcome metrics, optionally filtering for successful teams.
    
    Args:
        db_path: Path to database
        team_id: Filter by specific team (optional)
        min_budget_health: Minimum budget health score (optional)
        min_roi: Minimum ROI score (optional)
        survived_only: Only return teams that survived (optional)
        limit: Maximum results to return
        
    Returns:
        List of team outcome records
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        query = "SELECT * FROM team_outcomes WHERE 1=1"
        params = []
        
        if team_id:
            query += " AND team_id = ?"
            params.append(team_id)
        if min_budget_health is not None:
            query += " AND budget_health_score >= ?"
            params.append(min_budget_health)
        if min_roi is not None:
            query += " AND roi_score >= ?"
            params.append(min_roi)
        if survived_only:
            query += " AND survival_flag = 1"
        
        query += " ORDER BY season DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                'outcome_id': row['outcome_id'],
                'team_id': row['team_id'],
                'team_name': row['team_name'],
                'season': row['season'],
                'championship_position': row['championship_position'],
                'total_points': row['total_points'],
                'starting_budget': row['starting_budget'],
                'ending_budget': row['ending_budget'],
                'budget_health_score': row['budget_health_score'],
                'roi_score': row['roi_score'],
                'survival_flag': bool(row['survival_flag']),
                'folded_tick': row['folded_tick'],
                'seasons_survived': row['seasons_survived'],
                'created_ts': row['created_ts']
            })
        
        return results


# ============================================================================
# HISTORICAL DATA UPDATES - Phase 1 Implementation
# ============================================================================

def update_team_career_totals(db_path: str, team_name: str, tick: int) -> None:
    """Update team career totals from season summaries and race results.
    
    Args:
        db_path: Path to database
        team_name: Team to update
        tick: Current game tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Aggregate from season_summaries
        cursor.execute("""
            SELECT 
                COUNT(*) as seasons,
                SUM(races_entered) as races,
                SUM(wins) as wins,
                SUM(podiums) as podiums,
                SUM(poles) as poles,
                SUM(total_points) as points
            FROM season_summaries
            WHERE team_name = ?
        """, (team_name,))
        
        row = cursor.fetchone()
        if not row or row['seasons'] == 0:
            # Initialize with zeros
            cursor.execute("""
                INSERT OR REPLACE INTO team_career_totals 
                (team_name, seasons_entered, races_entered, wins_total, podiums_total, 
                 poles_total, points_total, last_updated_tick)
                VALUES (?, 0, 0, 0, 0, 0, 0.0, ?)
            """, (team_name, tick))
            return
        
        seasons = row['seasons'] or 0
        races = row['races'] or 0
        wins = row['wins'] or 0
        podiums = row['podiums'] or 0
        poles = row['poles'] or 0
        points = row['points'] or 0.0
        
        # Calculate derived metrics
        win_rate = (wins / races * 100.0) if races > 0 else 0.0
        podium_rate = (podiums / races * 100.0) if races > 0 else 0.0
        points_per_race = (points / races) if races > 0 else 0.0
        
        # Count championships (P1 finishes)
        cursor.execute("""
            SELECT COUNT(*) as titles
            FROM season_summaries
            WHERE team_name = ? AND championship_position = 1
        """, (team_name,))
        championships = cursor.fetchone()['titles']
        
        # Count runner-up finishes
        cursor.execute("""
            SELECT COUNT(*) as runner_ups
            FROM season_summaries
            WHERE team_name = ? AND championship_position = 2
        """, (team_name,))
        runner_ups = cursor.fetchone()['runner_ups']
        
        # Insert or update
        cursor.execute("""
            INSERT OR REPLACE INTO team_career_totals 
            (team_name, seasons_entered, races_entered, wins_total, podiums_total, 
             poles_total, points_total, championships_won, runner_up_finishes,
             win_rate, podium_rate, points_per_race_career, last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (team_name, seasons, races, wins, podiums, poles, points,
              championships, runner_ups, win_rate, podium_rate, points_per_race, tick))


def update_team_peak_valley(db_path: str, team_name: str, tick: int) -> None:
    """Update team peak and valley metrics.
    
    Args:
        db_path: Path to database
        team_name: Team to update
        tick: Current game tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get best season finish
        cursor.execute("""
            SELECT championship_position, season, total_points
            FROM season_summaries
            WHERE team_name = ? AND championship_position IS NOT NULL
            ORDER BY championship_position ASC, total_points DESC
            LIMIT 1
        """, (team_name,))
        best = cursor.fetchone()
        
        # Get worst season finish
        cursor.execute("""
            SELECT championship_position, season, total_points
            FROM season_summaries
            WHERE team_name = ? AND championship_position IS NOT NULL
            ORDER BY championship_position DESC, total_points ASC
            LIMIT 1
        """, (team_name,))
        worst = cursor.fetchone()
        
        # Get best points season
        cursor.execute("""
            SELECT total_points, season
            FROM season_summaries
            WHERE team_name = ?
            ORDER BY total_points DESC
            LIMIT 1
        """, (team_name,))
        best_points = cursor.fetchone()
        
        # Calculate droughts
        cursor.execute("""
            SELECT season
            FROM season_summaries
            WHERE team_name = ? AND wins > 0
            ORDER BY season DESC
            LIMIT 1
        """, (team_name,))
        last_win_season = cursor.fetchone()
        
        cursor.execute("""
            SELECT MAX(season) as current_season FROM season_summaries
        """)
        current_season = cursor.fetchone()['current_season'] or 0
        
        current_win_drought = 0
        if last_win_season:
            current_win_drought = current_season - last_win_season['season']
        else:
            cursor.execute("""
                SELECT COUNT(*) as seasons FROM season_summaries WHERE team_name = ?
            """, (team_name,))
            current_win_drought = cursor.fetchone()['seasons']
        
        # Insert or update
        cursor.execute("""
            INSERT OR REPLACE INTO team_peak_valley
            (team_name, best_season_finish, best_season_finish_year,
             worst_season_finish, worst_season_finish_year,
             best_single_season_points, best_season_points_year,
             current_win_drought, last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            team_name,
            best['championship_position'] if best else None,
            best['season'] if best else None,
            worst['championship_position'] if worst else None,
            worst['season'] if worst else None,
            best_points['total_points'] if best_points else 0.0,
            best_points['season'] if best_points else None,
            current_win_drought,
            tick
        ))


def update_active_streaks_after_race(
    db_path: str, 
    team_name: str, 
    finish_position: int,
    race_id: str,
    season: int,
    tick: int,
    scored_points: bool = True,
    was_dnf: bool = False
) -> None:
    """Update team active streaks after a race.
    
    Args:
        db_path: Path to database
        team_name: Team name
        finish_position: Race finish position
        race_id: Race identifier
        season: Season number
        tick: Current game tick
        scored_points: Whether team scored points
        was_dnf: Whether team had a DNF
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get current streaks or initialize
        cursor.execute("""
            SELECT * FROM active_streaks WHERE team_name = ?
        """, (team_name,))
        current = cursor.fetchone()
        
        if current:
            points_streak = current['current_points_streak']
            podium_streak = current['current_podium_streak']
            win_streak = current['current_win_streak']
            dnf_streak = current['current_dnf_streak']
            top5_streak = current['consecutive_top5_finishes']
            longest_points = current['longest_points_streak_ever']
            longest_win = current['longest_win_streak_ever']
            longest_podium = current['longest_podium_streak_ever']
        else:
            points_streak = podium_streak = win_streak = dnf_streak = top5_streak = 0
            longest_points = longest_win = longest_podium = 0
        
        # Update streaks based on race result
        if scored_points:
            points_streak += 1
            dnf_streak = 0
            longest_points = max(longest_points, points_streak)
        else:
            points_streak = 0
        
        if finish_position == 1:
            win_streak += 1
            podium_streak += 1
            longest_win = max(longest_win, win_streak)
            longest_podium = max(longest_podium, podium_streak)
        else:
            win_streak = 0
            if finish_position <= 3:
                podium_streak += 1
                longest_podium = max(longest_podium, podium_streak)
            else:
                podium_streak = 0
        
        if was_dnf:
            dnf_streak += 1
        else:
            dnf_streak = 0
        
        if finish_position <= 5:
            top5_streak += 1
        else:
            top5_streak = 0
        
        # Update database
        cursor.execute("""
            INSERT OR REPLACE INTO active_streaks
            (team_name, current_points_streak, current_podium_streak, current_win_streak,
             current_dnf_streak, consecutive_top5_finishes,
             longest_points_streak_ever, longest_win_streak_ever, longest_podium_streak_ever,
             last_points_finish_race, last_points_finish_season,
             last_win_race, last_win_season,
             last_podium_race, last_podium_season,
             last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            team_name, points_streak, podium_streak, win_streak, dnf_streak, top5_streak,
            longest_points, longest_win, longest_podium,
            race_id if scored_points else (current['last_points_finish_race'] if current else None),
            season if scored_points else (current['last_points_finish_season'] if current else None),
            race_id if finish_position == 1 else (current['last_win_race'] if current else None),
            season if finish_position == 1 else (current['last_win_season'] if current else None),
            race_id if finish_position <= 3 else (current['last_podium_race'] if current else None),
            season if finish_position <= 3 else (current['last_podium_season'] if current else None),
            tick
        ))


def update_team_pulse_metrics(
    db_path: str,
    team_name: str,
    tick: int,
    performance_trend: float = 0.0,
    financial_stability: float = 50.0,
    development_speed: float = 50.0,
    league_percentile: float = 50.0
) -> None:
    """Update team pulse composite metrics.
    
    Args:
        db_path: Path to database
        team_name: Team name
        tick: Current game tick
        performance_trend: Performance trend component (0-100)
        financial_stability: Financial stability component (0-100)
        development_speed: Development speed component (0-100)
        league_percentile: League percentile component (0-100)
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Calculate team pulse (weighted average)
        team_pulse = (
            performance_trend * 0.35 +
            financial_stability * 0.25 +
            development_speed * 0.20 +
            league_percentile * 0.20
        )
        
        # Determine competitive tier
        if league_percentile >= 95:
            competitive_tier = "dominant"
        elif league_percentile >= 80:
            competitive_tier = "contender"
        elif league_percentile >= 60:
            competitive_tier = "upper_midfield"
        elif league_percentile >= 40:
            competitive_tier = "midfield"
        elif league_percentile >= 20:
            competitive_tier = "lower_midfield"
        elif league_percentile >= 5:
            competitive_tier = "backmarker"
        else:
            competitive_tier = "crisis"
        
        # Determine narrative temperature
        if team_pulse >= 80:
            narrative_temp = "surging"
        elif team_pulse >= 65:
            narrative_temp = "tense"
        elif team_pulse >= 35:
            narrative_temp = "stable"
        elif team_pulse >= 20:
            narrative_temp = "fragile"
        elif team_pulse >= 10:
            narrative_temp = "volatile"
        else:
            narrative_temp = "desperate"
        
        cursor.execute("""
            INSERT OR REPLACE INTO team_pulse_metrics
            (team_name, team_pulse, performance_trend_component,
             financial_stability_component, development_speed_component,
             league_percentile_component, competitive_tier, narrative_temperature,
             last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            team_name, team_pulse, performance_trend, financial_stability,
            development_speed, league_percentile, competitive_tier, narrative_temp, tick
        ))


def update_momentum_metrics(db_path: str, team_name: str, tick: int) -> None:
    """Update momentum metrics based on recent race results.
    
    Args:
        db_path: Path to database
        team_name: Team name
        tick: Current game tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get last 5 race finishes
        cursor.execute("""
            SELECT championship_position_after, round_number
            FROM race_results_archive
            WHERE player_team_name = ?
            ORDER BY season DESC, round_number DESC
            LIMIT 5
        """, (team_name,))
        
        recent_finishes = [row['championship_position_after'] for row in cursor.fetchall() if row['championship_position_after']]
        
        if len(recent_finishes) < 2:
            # Not enough data
            return
        
        # Calculate form (inverse of average finish position, normalized)
        form_last_3 = 100.0 - (sum(recent_finishes[:3]) / len(recent_finishes[:3]) * 5) if len(recent_finishes) >= 3 else 50.0
        form_last_5 = 100.0 - (sum(recent_finishes) / len(recent_finishes) * 5) if len(recent_finishes) >= 5 else 50.0
        
        # Calculate momentum slope (simple linear regression)
        if len(recent_finishes) >= 3:
            # Reverse order for time series (oldest to newest)
            finishes_reversed = list(reversed(recent_finishes))
            n = len(finishes_reversed)
            x_mean = (n - 1) / 2
            y_mean = sum(finishes_reversed) / n
            
            numerator = sum((i - x_mean) * (finishes_reversed[i] - y_mean) for i in range(n))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            
            slope = numerator / denominator if denominator != 0 else 0.0
            
            # Negative slope = improving (lower positions), positive = declining
            momentum_slope = -slope  # Invert so positive = improving
        else:
            momentum_slope = 0.0
        
        # Determine momentum state
        if momentum_slope > 2.0:
            momentum_state = "surging"
        elif momentum_slope > 0.5:
            momentum_state = "rising"
        elif momentum_slope < -2.0:
            momentum_state = "collapsing"
        elif momentum_slope < -0.5:
            momentum_state = "declining"
        else:
            momentum_state = "stable"
        
        cursor.execute("""
            INSERT OR REPLACE INTO momentum_metrics
            (team_name, form_last_3_races, form_last_5_races, momentum_slope,
             momentum_state, last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (team_name, form_last_3, form_last_5, momentum_slope, momentum_state, tick))


def update_driver_career_stats(db_path: str, driver_name: str, tick: int) -> None:
    """Update driver career statistics.
    
    Args:
        db_path: Path to database
        driver_name: Driver name
        tick: Current game tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get driver's race results from race_results_archive
        cursor.execute("""
            SELECT season, finish_positions_json
            FROM race_results_archive
            ORDER BY season, round_number
        """)
        
        career_starts = 0
        career_wins = 0
        career_podiums = 0
        career_points = 0.0
        seasons_active = set()
        teams_driven = set()
        
        for row in cursor.fetchall():
            try:
                finishes = json.loads(row['finish_positions_json'])
                for result in finishes:
                    if result.get('driver_name') == driver_name:
                        career_starts += 1
                        position = result.get('position', 99)
                        seasons_active.add(row['season'])
                        
                        if result.get('team'):
                            teams_driven.add(result['team'])
                        
                        if position == 1:
                            career_wins += 1
                        if position <= 3:
                            career_podiums += 1
                        
                        # Simplified points (you may want actual points from data)
                        if position <= 10:
                            career_points += max(0, 25 - (position - 1) * 2)
            except (json.JSONDecodeError, KeyError):
                continue
        
        if career_starts == 0:
            return
        
        win_rate = (career_wins / career_starts * 100.0) if career_starts > 0 else 0.0
        podium_rate = (career_podiums / career_starts * 100.0) if career_starts > 0 else 0.0
        points_per_race = (career_points / career_starts) if career_starts > 0 else 0.0
        
        cursor.execute("""
            INSERT OR REPLACE INTO driver_career_stats
            (driver_name, career_starts, career_wins, career_podiums, career_points,
             career_teams_driven_for, win_rate_career, podium_rate_career,
             points_per_race_career, seasons_active, last_updated_tick)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            driver_name, career_starts, career_wins, career_podiums, career_points,
            len(teams_driven), win_rate, podium_rate, points_per_race,
            len(seasons_active), tick
        ))


def bulk_update_historical_data(db_path: str, tick: int) -> None:
    """Bulk update all historical data tables.
    
    Should be called after significant game events (race completion, season end).
    
    Args:
        db_path: Path to database
        tick: Current game tick
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get all teams that have season summaries
        cursor.execute("""
            SELECT DISTINCT team_name FROM season_summaries
        """)
        teams = [row['team_name'] for row in cursor.fetchall()]
        
        print(f"[FTB Historical] Updating {len(teams)} teams...")
        
        for team in teams:
            try:
                update_team_career_totals(db_path, team, tick)
                update_team_peak_valley(db_path, team, tick)
                update_momentum_metrics(db_path, team, tick)
            except Exception as e:
                print(f"[FTB Historical] Error updating {team}: {e}")
        
        # Get all drivers from entities
        cursor.execute("""
            SELECT DISTINCT name FROM entities WHERE entity_type = 'driver'
        """)
        drivers = [row['name'] for row in cursor.fetchall()]
        
        print(f"[FTB Historical] Updating {len(drivers)} drivers...")
        
        for driver in drivers:
            try:
                update_driver_career_stats(db_path, driver, tick)
            except Exception as e:
                print(f"[FTB Historical] Error updating driver {driver}: {e}")
        
        print("[FTB Historical] Bulk update complete")


# ============================================================================
# CLEANUP
# ============================================================================

def cleanup_old_events(db_path: str, keep_recent_ticks: int = 1000):
    """Remove old events to prevent database bloat.
    
    Args:
        keep_recent_ticks: Keep events from last N ticks
    """
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM events_buffer
            WHERE tick < (SELECT MAX(tick) FROM events_buffer) - ?
        """, (keep_recent_ticks,))
        
        deleted = cursor.rowcount
        if deleted > 0:
            print(f"[FTB State DB] Cleaned up {deleted} old events")


if __name__ == "__main__":
    # Test harness
    import tempfile
    import os
    
    test_db = os.path.join(tempfile.gettempdir(), "ftb_test.db")
    print(f"Testing FTB State DB at {test_db}")
    
    init_db(test_db)
    print("✓ Database initialized")
    
    # Test write/read cycle
    write_ui_context(test_db, "Team", 100)
    ui_ctx = query_ui_context(test_db)
    assert ui_ctx['active_tab'] == "Team"
    print("✓ UI context write/read")
    
    print("\nAll tests passed!")
    os.remove(test_db)
