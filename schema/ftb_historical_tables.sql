-- ============================================================================
-- FTB Historical Data System - Complete Schema
-- ============================================================================
-- Version: 2.0
-- Target: SQLite 3.x
-- Purpose: Extended historical tracking for narrator enhancement
-- ============================================================================

-- ============================================================================
-- I. TEAM HISTORICAL RECORDS
-- ============================================================================

-- A. Career Totals (All-Time)
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
    
    -- Derived metrics (computed on update)
    win_rate REAL DEFAULT 0.0,
    podium_rate REAL DEFAULT 0.0,
    points_per_race_career REAL DEFAULT 0.0,
    reliability_career REAL DEFAULT 0.0,
    championship_conversion_rate REAL DEFAULT 0.0,
    titles_per_top3_season REAL DEFAULT 0.0,
    
    last_updated_tick INTEGER NOT NULL
);

CREATE INDEX idx_team_career_championships ON team_career_totals(championships_won DESC);
CREATE INDEX idx_team_career_wins ON team_career_totals(wins_total DESC);

-- B. Era-Specific Performance
CREATE TABLE IF NOT EXISTS regulation_eras (
    era_id TEXT PRIMARY KEY,
    era_label TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season INTEGER,
    major_regulation_changes TEXT, -- JSON list
    description TEXT,
    created_tick INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS team_era_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    era_id TEXT NOT NULL,
    era_label TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season INTEGER NOT NULL,
    
    -- Performance in era
    races_entered INTEGER DEFAULT 0,
    avg_finish REAL DEFAULT 0.0,
    avg_cpi REAL DEFAULT 0.0,
    cpi_percentile REAL DEFAULT 0.0,
    championships INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    podiums INTEGER DEFAULT 0,
    
    -- Adaptability metrics
    performance_vs_previous_era REAL DEFAULT 0.0,
    decline_after_rule_change REAL DEFAULT 0.0,
    adaptability_score REAL DEFAULT 50.0,
    
    last_updated_tick INTEGER NOT NULL,
    
    UNIQUE(team_name, era_id),
    FOREIGN KEY (era_id) REFERENCES regulation_eras(era_id)
);

CREATE INDEX idx_era_performance_team ON team_era_performance(team_name);
CREATE INDEX idx_era_performance_era ON team_era_performance(era_id);

-- C. Peak & Valley Metrics
CREATE TABLE IF NOT EXISTS team_peak_valley (
    team_name TEXT PRIMARY KEY,
    
    -- Peak performance
    best_season_finish INTEGER,
    best_season_finish_year INTEGER,
    worst_season_finish INTEGER,
    worst_season_finish_year INTEGER,
    best_single_season_points REAL DEFAULT 0.0,
    best_season_points_year INTEGER,
    worst_season_points REAL DEFAULT 0.0,
    worst_season_points_year INTEGER,
    
    -- Drought tracking
    longest_title_drought INTEGER DEFAULT 0,
    longest_win_drought INTEGER DEFAULT 0,
    longest_podium_drought INTEGER DEFAULT 0,
    current_title_drought INTEGER DEFAULT 0,
    current_win_drought INTEGER DEFAULT 0,
    current_podium_drought INTEGER DEFAULT 0,
    
    -- Volatility
    biggest_season_overperformance REAL DEFAULT 0.0,
    biggest_season_collapse REAL DEFAULT 0.0,
    volatility_index REAL DEFAULT 0.0,
    
    -- Golden era
    golden_era_start INTEGER,
    golden_era_end INTEGER,
    golden_era_avg_finish REAL,
    consecutive_top3_seasons INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL
);

-- ============================================================================
-- II. DRIVER HISTORICAL ARCHIVES
-- ============================================================================

-- A. Career Stats
CREATE TABLE IF NOT EXISTS driver_career_stats (
    driver_name TEXT PRIMARY KEY,
    
    -- Core career totals
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
    
    -- Derived metrics
    win_rate_career REAL DEFAULT 0.0,
    podium_rate_career REAL DEFAULT 0.0,
    points_per_race_career REAL DEFAULT 0.0,
    reliability_career REAL DEFAULT 0.0,
    clutch_index REAL DEFAULT 0.0,
    
    -- Career arc
    debut_season INTEGER,
    debut_team TEXT,
    current_team TEXT,
    seasons_active INTEGER DEFAULT 0,
    is_retired INTEGER DEFAULT 0,
    retirement_season INTEGER,
    
    last_updated_tick INTEGER NOT NULL
);

CREATE INDEX idx_driver_career_championships ON driver_career_stats(championships_won DESC);
CREATE INDEX idx_driver_career_wins ON driver_career_stats(career_wins DESC);

-- B. Team-Specific History
CREATE TABLE IF NOT EXISTS driver_team_stints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    driver_name TEXT NOT NULL,
    team_name TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season INTEGER,
    
    -- Performance at team
    races INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    podiums INTEGER DEFAULT 0,
    points REAL DEFAULT 0.0,
    years_at_team INTEGER DEFAULT 0,
    
    -- Teammate battles
    teammate_name TEXT,
    performance_delta_vs_teammate REAL DEFAULT 0.0,
    teammate_comparison_index REAL DEFAULT 0.0,
    quali_head_to_head_wins INTEGER DEFAULT 0,
    quali_head_to_head_losses INTEGER DEFAULT 0,
    race_head_to_head_wins INTEGER DEFAULT 0,
    race_head_to_head_losses INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL,
    
    UNIQUE(driver_name, team_name, start_season)
);

CREATE INDEX idx_driver_stints_driver ON driver_team_stints(driver_name);
CREATE INDEX idx_driver_stints_team ON driver_team_stints(team_name);

-- C. Development Curve
CREATE TABLE IF NOT EXISTS driver_development_curve (
    driver_name TEXT PRIMARY KEY,
    
    -- Peak identification
    peak_rating REAL DEFAULT 0.0,
    peak_rating_age INTEGER,
    peak_performance_season INTEGER,
    peak_performance_metric REAL DEFAULT 0.0,
    
    -- Age curve (JSON: {"25": 82.5, "26": 84.1, ...})
    age_curve_json TEXT,
    
    -- Pressure performance
    mettle_under_pressure_index REAL DEFAULT 0.0,
    performance_when_championship_close REAL DEFAULT 0.0,
    post_crash_recovery_performance REAL DEFAULT 0.0,
    
    -- Career trajectory
    improvement_rate REAL DEFAULT 0.0,
    consistency_index REAL DEFAULT 0.0,
    volatility_score REAL DEFAULT 0.0,
    
    last_updated_tick INTEGER NOT NULL
);

-- ============================================================================
-- III. LEAGUE & CHAMPIONSHIP HISTORY
-- ============================================================================

-- A. Competitive Landscape
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
    
    -- Competition metrics
    title_margin REAL NOT NULL,
    title_decided_round INTEGER,
    avg_points_to_win REAL DEFAULT 0.0,
    most_dominant_season REAL DEFAULT 0.0,
    closest_title_fight REAL DEFAULT 0.0,
    
    -- Dynasty tracking
    is_repeat_champion INTEGER DEFAULT 0,
    consecutive_titles_for_winner INTEGER DEFAULT 0,
    
    -- Parity metrics
    parity_index REAL DEFAULT 0.0,
    championship_compression_score REAL DEFAULT 0.0,
    
    last_updated_tick INTEGER NOT NULL,
    
    PRIMARY KEY (season, league_id)
);

CREATE INDEX idx_championship_history_season ON championship_history(season);
CREATE INDEX idx_championship_history_champion ON championship_history(champion_team);

-- B. Historical Tier Mapping
CREATE TABLE IF NOT EXISTS tier_definitions (
    season INTEGER NOT NULL,
    performance_tier TEXT NOT NULL,
    min_percentile REAL NOT NULL,
    max_percentile REAL NOT NULL,
    
    PRIMARY KEY (season, performance_tier)
);

CREATE TABLE IF NOT EXISTS team_tier_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    
    -- Performance tier classification
    performance_tier TEXT NOT NULL,
    tier_percentile REAL DEFAULT 0.0,
    
    -- Tier duration tracking
    seasons_in_tier INTEGER DEFAULT 0,
    total_seasons_in_tier INTEGER DEFAULT 0,
    
    -- Promotion/relegation
    promoted_from_tier INTEGER,
    relegated_from_tier INTEGER,
    tier_change_reason TEXT,
    
    last_updated_tick INTEGER NOT NULL,
    
    UNIQUE(team_name, season)
);

CREATE INDEX idx_team_tier_history_team ON team_tier_history(team_name);
CREATE INDEX idx_team_tier_history_season ON team_tier_history(season);

-- ============================================================================
-- IV. TECH & ARMS RACE HISTORY
-- ============================================================================

-- A. Innovation Timeline
CREATE TABLE IF NOT EXISTS team_innovation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    game_day INTEGER NOT NULL,
    
    innovation_type TEXT NOT NULL,
    part_type TEXT,
    part_name TEXT,
    innovation_description TEXT,
    
    -- Impact tracking
    cpi_before REAL DEFAULT 0.0,
    cpi_after REAL DEFAULT 0.0,
    cpi_delta REAL DEFAULT 0.0,
    innovation_success REAL DEFAULT 0.0,
    
    league_impact TEXT,
    
    created_tick INTEGER NOT NULL
);

CREATE INDEX idx_innovation_team ON team_innovation_history(team_name);
CREATE INDEX idx_innovation_season ON team_innovation_history(season);

-- B. Development Arms Race
CREATE TABLE IF NOT EXISTS team_development_arms_race (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    
    -- Development metrics
    upgrade_frequency REAL DEFAULT 0.0,
    development_spend_rank INTEGER,
    development_budget_pct REAL DEFAULT 0.0,
    
    -- Arms race positioning
    catch_up_success_rate REAL DEFAULT 0.0,
    seasons_starting_below_avg INTEGER DEFAULT 0,
    seasons_finishing_above_avg INTEGER DEFAULT 0,
    
    -- Innovation stats
    breakthrough_upgrades INTEGER DEFAULT 0,
    failed_upgrades INTEGER DEFAULT 0,
    innovation_success_rate REAL DEFAULT 0.0,
    
    last_updated_tick INTEGER NOT NULL,
    
    UNIQUE(team_name, season)
);

-- ============================================================================
-- V. ECONOMIC HISTORY
-- ============================================================================

-- A. Financial Cycles
CREATE TABLE IF NOT EXISTS team_financial_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    
    -- Season financials
    total_revenue REAL DEFAULT 0.0,
    total_expenses REAL DEFAULT 0.0,
    net_income REAL DEFAULT 0.0,
    profitable INTEGER DEFAULT 0,
    
    -- Cash position
    starting_cash REAL DEFAULT 0.0,
    ending_cash REAL DEFAULT 0.0,
    lowest_cash REAL DEFAULT 0.0,
    highest_cash REAL DEFAULT 0.0,
    near_bankruptcy_events INTEGER DEFAULT 0,
    
    -- Derived metrics
    financial_resilience_score REAL DEFAULT 0.0,
    spending_efficiency REAL DEFAULT 0.0,
    investment_aggression REAL DEFAULT 0.0,
    runway_weeks_avg REAL DEFAULT 0.0,
    
    last_updated_tick INTEGER NOT NULL,
    
    UNIQUE(team_name, season)
);

CREATE INDEX idx_financial_history_team ON team_financial_history(team_name);
CREATE INDEX idx_financial_history_season ON team_financial_history(season);

-- B. Sponsorship Legacy
CREATE TABLE IF NOT EXISTS sponsorship_legacy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    sponsor_name TEXT NOT NULL,
    
    -- Partnership duration
    start_season INTEGER NOT NULL,
    end_season INTEGER,
    seasons_duration INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    
    -- Financial impact
    total_revenue REAL DEFAULT 0.0,
    avg_payment_per_season REAL DEFAULT 0.0,
    
    -- Partnership quality
    renewals INTEGER DEFAULT 0,
    bailouts INTEGER DEFAULT 0,
    early_terminations INTEGER DEFAULT 0,
    end_reason TEXT,
    
    -- Metadata
    created_tick INTEGER NOT NULL,
    ended_tick INTEGER,
    
    UNIQUE(team_name, sponsor_name, start_season)
);

CREATE INDEX idx_sponsorship_legacy_team ON sponsorship_legacy(team_name);
CREATE INDEX idx_sponsorship_legacy_active ON sponsorship_legacy(is_active);

-- ============================================================================
-- VI. STREAK TRACKING
-- ============================================================================

CREATE TABLE IF NOT EXISTS active_streaks (
    team_name TEXT PRIMARY KEY,
    
    -- Current active streaks
    current_points_streak INTEGER DEFAULT 0,
    current_podium_streak INTEGER DEFAULT 0,
    current_dnf_streak INTEGER DEFAULT 0,
    current_win_streak INTEGER DEFAULT 0,
    consecutive_points_finishes INTEGER DEFAULT 0,
    consecutive_outqualified_teammate INTEGER DEFAULT 0,
    consecutive_mechanical_failures INTEGER DEFAULT 0,
    consecutive_top5_finishes INTEGER DEFAULT 0,
    consecutive_outside_top10 INTEGER DEFAULT 0,
    
    -- Historical records
    longest_points_streak_ever INTEGER DEFAULT 0,
    longest_win_streak_ever INTEGER DEFAULT 0,
    longest_dnf_streak_ever INTEGER DEFAULT 0,
    longest_podium_streak_ever INTEGER DEFAULT 0,
    
    -- Streak context
    last_points_finish_race TEXT,
    last_points_finish_season INTEGER,
    last_podium_race TEXT,
    last_podium_season INTEGER,
    last_win_race TEXT,
    last_win_season INTEGER,
    last_dnf_race TEXT,
    last_dnf_season INTEGER,
    
    last_updated_tick INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_active_streaks (
    driver_name TEXT PRIMARY KEY,
    
    -- Current streaks
    current_points_streak INTEGER DEFAULT 0,
    current_podium_streak INTEGER DEFAULT 0,
    current_dnf_streak INTEGER DEFAULT 0,
    current_win_streak INTEGER DEFAULT 0,
    consecutive_outqualified_teammate INTEGER DEFAULT 0,
    
    -- Historical records
    longest_points_streak_ever INTEGER DEFAULT 0,
    longest_win_streak_ever INTEGER DEFAULT 0,
    longest_podium_streak_ever INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL
);

-- ============================================================================
-- VII. EXPECTATION VS HISTORY MODELS
-- ============================================================================

CREATE TABLE IF NOT EXISTS expectation_models (
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Expectation metrics
    expected_finish REAL DEFAULT 0.0,
    actual_finish INTEGER,
    expectation_gap REAL DEFAULT 0.0,
    
    historical_baseline_finish REAL DEFAULT 0.0,
    regression_to_mean_indicator REAL DEFAULT 0.0,
    sustainable_performance_score REAL DEFAULT 0.0,
    overachieving_vs_history_index REAL DEFAULT 0.0,
    
    -- Context
    strongest_start_comparison TEXT,
    performance_vs_career_avg REAL DEFAULT 0.0,
    
    created_tick INTEGER NOT NULL,
    
    PRIMARY KEY (team_name, season, round_number)
);

CREATE INDEX idx_expectation_team_season ON expectation_models(team_name, season);

-- ============================================================================
-- VIII. LEGACY & PRESTIGE SCORES
-- ============================================================================

CREATE TABLE IF NOT EXISTS team_prestige (
    team_name TEXT PRIMARY KEY,
    
    -- Prestige score (0-100 composite)
    prestige_index REAL DEFAULT 50.0,
    
    -- Components
    championship_prestige REAL DEFAULT 0.0,
    wins_prestige REAL DEFAULT 0.0,
    longevity_prestige REAL DEFAULT 0.0,
    era_dominance_prestige REAL DEFAULT 0.0,
    financial_resilience_prestige REAL DEFAULT 0.0,
    
    -- Historical tier
    legacy_tier TEXT DEFAULT 'emerging',
    
    last_updated_tick INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS driver_legacy (
    driver_name TEXT PRIMARY KEY,
    
    -- Legacy score (0-100 composite)
    legacy_score REAL DEFAULT 50.0,
    
    -- Components
    titles_legacy REAL DEFAULT 0.0,
    win_rate_legacy REAL DEFAULT 0.0,
    teammate_dominance_legacy REAL DEFAULT 0.0,
    clutch_index_legacy REAL DEFAULT 0.0,
    peak_rating_legacy REAL DEFAULT 0.0,
    longevity_legacy REAL DEFAULT 0.0,
    
    -- Historical tier
    legacy_tier TEXT DEFAULT 'developing',
    
    last_updated_tick INTEGER NOT NULL
);

-- ============================================================================
-- IX. HEAD-TO-HEAD ARCHIVES
-- ============================================================================

CREATE TABLE IF NOT EXISTS driver_head_to_head (
    driver_a TEXT NOT NULL,
    driver_b TEXT NOT NULL,
    
    -- All-time records
    quali_record_a_wins INTEGER DEFAULT 0,
    quali_record_b_wins INTEGER DEFAULT 0,
    race_finish_record_a_wins INTEGER DEFAULT 0,
    race_finish_record_b_wins INTEGER DEFAULT 0,
    
    -- Points comparison
    total_points_a REAL DEFAULT 0.0,
    total_points_b REAL DEFAULT 0.0,
    
    -- Championship battles
    championship_battles INTEGER DEFAULT 0,
    title_deciders INTEGER DEFAULT 0,
    
    -- Context
    races_contested_together INTEGER DEFAULT 0,
    seasons_as_teammates INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL,
    
    PRIMARY KEY (driver_a, driver_b),
    CHECK (driver_a < driver_b)
);

CREATE INDEX idx_driver_h2h_a ON driver_head_to_head(driver_a);
CREATE INDEX idx_driver_h2h_b ON driver_head_to_head(driver_b);

CREATE TABLE IF NOT EXISTS team_head_to_head (
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    
    -- Competition records
    wins_differential INTEGER DEFAULT 0,
    podiums_differential INTEGER DEFAULT 0,
    points_differential REAL DEFAULT 0.0,
    
    -- Championship context
    title_fights_contested INTEGER DEFAULT 0,
    seasons_in_same_tier INTEGER DEFAULT 0,
    era_overlaps TEXT,
    
    last_updated_tick INTEGER NOT NULL,
    
    PRIMARY KEY (team_a, team_b),
    CHECK (team_a < team_b)
);

-- ============================================================================
-- X. HISTORICAL TREND ANALYTICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS rolling_performance_metrics (
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Rolling windows
    rolling_5season_avg_finish REAL DEFAULT 0.0,
    rolling_10race_points_avg REAL DEFAULT 0.0,
    rolling_3race_form REAL DEFAULT 0.0,
    
    -- Regression analysis
    performance_regression_slope REAL DEFAULT 0.0,
    performance_trend TEXT DEFAULT 'stable',
    
    -- Pattern detection
    cyclical_rise_fall_pattern TEXT,
    title_probability_given_history REAL DEFAULT 0.0,
    
    created_tick INTEGER NOT NULL,
    
    PRIMARY KEY (team_name, season, round_number)
);

CREATE INDEX idx_rolling_perf_team ON rolling_performance_metrics(team_name);

-- ============================================================================
-- TIME-BASED SYSTEM METRICS
-- ============================================================================

CREATE TABLE IF NOT EXISTS contract_pressure_index (
    entity_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    team_name TEXT NOT NULL,
    
    contract_days_left INTEGER NOT NULL,
    contract_pressure_score REAL DEFAULT 0.0,
    
    -- Context
    is_critical_personnel INTEGER DEFAULT 0,
    replacement_difficulty TEXT DEFAULT 'moderate',
    
    last_updated_tick INTEGER NOT NULL
);

CREATE INDEX idx_contract_pressure_team ON contract_pressure_index(team_name);

CREATE TABLE IF NOT EXISTS development_timelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    
    part_name TEXT NOT NULL,
    part_type TEXT NOT NULL,
    
    -- ETA tracking
    build_eta_days INTEGER NOT NULL,
    research_completion_days INTEGER DEFAULT 0,
    upgrade_lag_vs_league REAL DEFAULT 0.0,
    
    -- Status
    status TEXT DEFAULT 'in_progress',
    
    created_tick INTEGER NOT NULL,
    completed_tick INTEGER
);

CREATE INDEX idx_dev_timelines_team ON development_timelines(team_name);
CREATE INDEX idx_dev_timelines_status ON development_timelines(status);

CREATE TABLE IF NOT EXISTS momentum_metrics (
    team_name TEXT PRIMARY KEY,
    
    -- Form metrics
    form_last_3_races REAL DEFAULT 0.0,
    form_last_5_races REAL DEFAULT 0.0,
    momentum_slope REAL DEFAULT 0.0,
    
    -- Momentum classification
    momentum_state TEXT DEFAULT 'stable',
    
    last_updated_tick INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS narrative_heat_scores (
    team_name TEXT NOT NULL,
    story_type TEXT NOT NULL,
    
    -- Heat tracking (0-100 with decay)
    heat_score REAL DEFAULT 0.0,
    peak_heat REAL DEFAULT 0.0,
    decay_rate REAL DEFAULT 5.0,
    
    -- Story context
    story_start_tick INTEGER NOT NULL,
    last_boosted_tick INTEGER NOT NULL,
    days_since_last_boost INTEGER DEFAULT 0,
    
    -- Story metadata
    story_description TEXT,
    key_players TEXT,
    
    PRIMARY KEY (team_name, story_type)
);

CREATE INDEX idx_narrative_heat_team ON narrative_heat_scores(team_name);
CREATE INDEX idx_narrative_heat_score ON narrative_heat_scores(heat_score DESC);

-- ============================================================================
-- INFRASTRUCTURE & DEVELOPMENT
-- ============================================================================

CREATE TABLE IF NOT EXISTS team_infrastructure_evolution (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    
    -- Infrastructure levels
    facility_level INTEGER DEFAULT 1,
    factory_output_rate REAL DEFAULT 0.0,
    design_staff_rating REAL DEFAULT 0.0,
    engineering_rating REAL DEFAULT 0.0,
    
    -- Investment
    development_budget_pct REAL DEFAULT 0.0,
    wind_tunnel_efficiency REAL DEFAULT 0.0,
    parts_pipeline_depth INTEGER DEFAULT 0,
    
    -- Innovation metrics
    innovation_index REAL DEFAULT 0.0,
    regulation_adaptability REAL DEFAULT 0.0,
    spec_compliance_risk REAL DEFAULT 0.0,
    
    -- Derived
    arms_race_intensity REAL DEFAULT 0.0,
    tech_gap_to_top_team REAL DEFAULT 0.0,
    development_catchup_time_days INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL,
    
    UNIQUE(team_name, season)
);

-- ============================================================================
-- LEAGUE ECONOMY & LANDSCAPE
-- ============================================================================

CREATE TABLE IF NOT EXISTS league_baselines (
    league_id TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Dynamic league averages
    league_avg_cpi REAL DEFAULT 0.0,
    league_avg_reliability REAL DEFAULT 0.0,
    league_avg_cash REAL DEFAULT 0.0,
    league_avg_burn REAL DEFAULT 0.0,
    league_avg_driver_rating REAL DEFAULT 0.0,
    league_development_velocity REAL DEFAULT 0.0,
    league_financial_health_index REAL DEFAULT 0.0,
    
    -- Competitive distribution
    league_parity_score REAL DEFAULT 0.0,
    dominance_index REAL DEFAULT 0.0,
    midfield_compression_score REAL DEFAULT 0.0,
    
    created_tick INTEGER NOT NULL,
    
    PRIMARY KEY (league_id, season, round_number)
);

CREATE INDEX idx_league_baselines_season ON league_baselines(season, round_number);

-- ============================================================================
-- META-ANALYTICS FOR NARRATIVE CONTROL
-- ============================================================================

CREATE TABLE IF NOT EXISTS expectation_calibration (
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Expectation modeling
    expected_model_finish REAL DEFAULT 0.0,
    expectation_gap REAL DEFAULT 0.0,
    narrative_bias_correction REAL DEFAULT 0.0,
    
    -- Hope/doom metrics
    hope_index REAL DEFAULT 50.0,
    trajectory_projection TEXT DEFAULT 'midfield_stability',
    
    -- 5-race forecast (JSON)
    simulated_forecast_json TEXT,
    
    created_tick INTEGER NOT NULL,
    
    PRIMARY KEY (team_name, season, round_number)
);

-- ============================================================================
-- SPECIAL SITUATIONAL TRIGGERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS situational_triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    
    -- Trigger state
    is_active INTEGER DEFAULT 0,
    severity REAL DEFAULT 0.0,
    activated_tick INTEGER,
    resolved_tick INTEGER,
    
    -- Context
    description TEXT,
    narrative_priority INTEGER DEFAULT 50,
    
    created_tick INTEGER NOT NULL,
    
    UNIQUE(team_name, trigger_type, activated_tick)
);

CREATE INDEX idx_triggers_active ON situational_triggers(is_active, team_name);
CREATE INDEX idx_triggers_team ON situational_triggers(team_name);

-- ============================================================================
-- COMPOSITE SCORES FOR RADIO OS INJECTION
-- ============================================================================

CREATE TABLE IF NOT EXISTS team_pulse_metrics (
    team_name TEXT PRIMARY KEY,
    
    -- Team Pulse (0-100 composite)
    team_pulse REAL DEFAULT 50.0,
    
    -- Components
    performance_trend_component REAL DEFAULT 0.0,
    financial_stability_component REAL DEFAULT 0.0,
    development_speed_component REAL DEFAULT 0.0,
    league_percentile_component REAL DEFAULT 0.0,
    
    -- Classification labels
    competitive_tier TEXT DEFAULT 'midfield',
    narrative_temperature TEXT DEFAULT 'stable',
    
    last_updated_tick INTEGER NOT NULL
);

-- ============================================================================
-- VIEWS FOR CONVENIENCE
-- ============================================================================

-- Team performance summary view
CREATE VIEW IF NOT EXISTS v_team_performance_summary AS
SELECT 
    t.team_name,
    t.tier,
    t.championship_position,
    t.points,
    tpm.team_pulse,
    tpm.competitive_tier,
    tpm.narrative_temperature,
    tp.prestige_index,
    tp.legacy_tier,
    mm.momentum_state,
    tct.win_rate,
    tct.championships_won
FROM teams t
LEFT JOIN team_pulse_metrics tpm ON t.team_name = tpm.team_name
LEFT JOIN team_prestige tp ON t.team_name = tp.team_name
LEFT JOIN momentum_metrics mm ON t.team_name = mm.team_name
LEFT JOIN team_career_totals tct ON t.team_name = tct.team_name;

-- Driver performance summary view
CREATE VIEW IF NOT EXISTS v_driver_performance_summary AS
SELECT
    e.name as driver_name,
    e.age,
    e.team_name,
    e.overall_rating,
    dcs.career_wins,
    dcs.career_podiums,
    dcs.championships_won,
    dcs.win_rate_career,
    dl.legacy_score,
    dl.legacy_tier,
    ddc.peak_rating,
    ddc.mettle_under_pressure_index
FROM entities e
LEFT JOIN driver_career_stats dcs ON e.name = dcs.driver_name
LEFT JOIN driver_legacy dl ON e.name = dl.driver_name
LEFT JOIN driver_development_curve ddc ON e.name = ddc.driver_name
WHERE e.entity_type = 'driver';

-- Active streaks summary
CREATE VIEW IF NOT EXISTS v_active_streaks_summary AS
SELECT
    team_name,
    current_points_streak,
    current_win_streak,
    current_podium_streak,
    longest_points_streak_ever,
    longest_win_streak_ever,
    CASE
        WHEN current_points_streak >= longest_points_streak_ever * 0.8 THEN 'approaching_record'
        WHEN current_points_streak > 5 THEN 'hot_streak'
        ELSE 'normal'
    END as streak_status
FROM active_streaks;

-- ============================================================================
-- INITIALIZATION DATA
-- ============================================================================

-- Insert default tier definitions
INSERT OR IGNORE INTO tier_definitions (season, performance_tier, min_percentile, max_percentile) VALUES
(0, 'dominant', 0.0, 5.0),
(0, 'contender', 5.0, 20.0),
(0, 'upper_midfield', 20.0, 40.0),
(0, 'midfield', 40.0, 60.0),
(0, 'lower_midfield', 60.0, 80.0),
(0, 'backmarker', 80.0, 95.0),
(0, 'crisis', 95.0, 100.0);

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
