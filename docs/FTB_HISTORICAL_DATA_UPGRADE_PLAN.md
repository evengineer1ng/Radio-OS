# From The Backmarker - Historical Data System Upgrade Plan

**Version:** 2.0  
**Target Release:** v1.06+  
**Status:** Planning Phase  

---

## Executive Summary

This document outlines a comprehensive upgrade to FTB's data architecture to support **massively expanded narrator capabilities** through rich historical tracking, advanced analytics, and real-time composite metrics. The goal is to transform the narrator from "reactive commentator" to "sports historian with perfect memory."

**Key Deliverables:**
1. **Extended database schema** with 40+ new tables for historical tracking
2. **Computed analytics layer** providing 100+ derived metrics
3. **FTB DB Explorer widget** for real-time data visualization
4. **Master meta-plugin** orchestrating all analytics systems

---

## I. TEAM HISTORICAL RECORDS

### A. Career Totals (All-Time)

**New Table: `team_career_totals`**

```sql
CREATE TABLE team_career_totals (
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
```

**Implementation Notes:**
- Updated after every race completion
- Derived metrics recomputed on every update
- Historical teams (folded) maintain their records
- Used for: "This is their 47th career podium" / "Best win rate in tier history"

---

### B. Era-Specific Performance

**New Table: `team_era_performance`**

Eras defined by regulation cycles or calendar blocks (e.g., "Season 1-3", "Season 4-7").

```sql
CREATE TABLE team_era_performance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    era_id TEXT NOT NULL, -- e.g., "s1_s3_regs_a", "s4_s7_regs_b"
    era_label TEXT NOT NULL, -- "Early Era", "Mid Regulation Cycle"
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
    
    UNIQUE(team_name, era_id)
);
```

**New Table: `regulation_eras`**

```sql
CREATE TABLE regulation_eras (
    era_id TEXT PRIMARY KEY,
    era_label TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season INTEGER,
    major_regulation_changes TEXT, -- JSON list
    description TEXT
);
```

**Implementation Notes:**
- Eras defined manually or auto-generated every 3-4 seasons
- Enables: "They dominated the early regulation cycle but struggled after the 2023 aero changes"
- `adaptability_score` = performance delta across regulation boundaries

---

### C. Peak & Valley Metrics

**New Table: `team_peak_valley`**

```sql
CREATE TABLE team_peak_valley (
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
    biggest_season_overperformance REAL DEFAULT 0.0, -- vs expectation
    biggest_season_collapse REAL DEFAULT 0.0,
    volatility_index REAL DEFAULT 0.0, -- std dev of season finishes
    
    -- Golden era
    golden_era_start INTEGER,
    golden_era_end INTEGER,
    golden_era_avg_finish REAL,
    consecutive_top3_seasons INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL
);
```

**Implementation Notes:**
- Updated at end of each season
- Enables: "Their longest win drought since Season 4" / "This is their best 3-season stretch"
- Golden era = longest window of top-3 finishes or percentile dominance

---

## II. DRIVER HISTORICAL ARCHIVES

### A. Career Stats

**New Table: `driver_career_stats`**

```sql
CREATE TABLE driver_career_stats (
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
    clutch_index REAL DEFAULT 0.0, -- points in final 3 rounds / total
    
    -- Career arc
    debut_season INTEGER,
    debut_team TEXT,
    current_team TEXT,
    seasons_active INTEGER DEFAULT 0,
    
    last_updated_tick INTEGER NOT NULL
);
```

**Implementation Notes:**
- Updated after every race
- Persists after driver retirement (becomes historical record)
- Enables: "In 47 career starts, this is his first pole"

---

### B. Team-Specific History

**New Table: `driver_team_stints`**

```sql
CREATE TABLE driver_team_stints (
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
    
    UNIQUE(driver_name, team_name, start_season)
);
```

**Implementation Notes:**
- New row created when driver joins team
- `end_season` is NULL for current stint
- Enables: "He outscored three teammates over four seasons at Apex Racing"

---

### C. Development Curve

**New Table: `driver_development_curve`**

```sql
CREATE TABLE driver_development_curve (
    driver_name TEXT PRIMARY KEY,
    
    -- Peak identification
    peak_rating REAL DEFAULT 0.0,
    peak_rating_age INTEGER,
    peak_performance_season INTEGER,
    peak_performance_metric REAL DEFAULT 0.0, -- composite score
    
    -- Age curve
    age_curve_json TEXT, -- {"25": 82.5, "26": 84.1, ...}
    
    -- Pressure performance
    mettle_under_pressure_index REAL DEFAULT 0.0,
    performance_when_championship_close REAL DEFAULT 0.0, -- within 25pts
    post_crash_recovery_performance REAL DEFAULT 0.0,
    
    -- Career trajectory
    improvement_rate REAL DEFAULT 0.0, -- linear regression slope
    consistency_index REAL DEFAULT 0.0,
    volatility_score REAL DEFAULT 0.0,
    
    last_updated_tick INTEGER NOT NULL
);
```

**Implementation Notes:**
- Updated at end of season
- Enables: "Peaked at age 27 in Season 6" / "Historically weak under championship pressure"

---

## III. LEAGUE & CHAMPIONSHIP HISTORY

### A. Competitive Landscape

**New Table: `championship_history`**

```sql
CREATE TABLE championship_history (
    season INTEGER PRIMARY KEY,
    league_id TEXT NOT NULL,
    tier INTEGER NOT NULL,
    
    champion_team TEXT NOT NULL,
    champion_points REAL NOT NULL,
    runner_up_team TEXT NOT NULL,
    runner_up_points REAL NOT NULL,
    third_place_team TEXT NOT NULL,
    third_place_points REAL NOT NULL,
    
    -- Competition metrics
    title_margin REAL NOT NULL, -- P1 - P2 points
    title_decided_round INTEGER, -- when mathematically decided
    avg_points_to_win REAL DEFAULT 0.0,
    most_dominant_season REAL DEFAULT 0.0, -- margin as % of total
    closest_title_fight REAL DEFAULT 0.0,
    
    -- Dynasty tracking
    is_repeat_champion INTEGER DEFAULT 0,
    consecutive_titles_for_winner INTEGER DEFAULT 0,
    
    -- Parity metrics
    parity_index REAL DEFAULT 0.0, -- std dev of team CPI
    championship_compression_score REAL DEFAULT 0.0, -- gap P1 to P3
    
    last_updated_tick INTEGER NOT NULL
);
```

**Implementation Notes:**
- Written at end of season
- Enables: "Closest title fight in 4 seasons" / "They're chasing their third consecutive title"

---

### B. Historical Tier Mapping

**New Table: `team_tier_history`**

```sql
CREATE TABLE team_tier_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    
    -- Performance tier classification
    performance_tier TEXT NOT NULL, -- "dominant", "contender", "upper_mid", "mid", "lower_mid", "backmarker"
    tier_percentile REAL DEFAULT 0.0,
    
    -- Tier duration tracking
    seasons_in_tier INTEGER DEFAULT 0, -- consecutive
    total_seasons_in_tier INTEGER DEFAULT 0, -- all-time
    
    -- Promotion/relegation
    promoted_from_tier INTEGER,
    relegated_from_tier INTEGER,
    tier_change_reason TEXT,
    
    UNIQUE(team_name, season)
);
```

**New Table: `tier_definitions`**

```sql
CREATE TABLE tier_definitions (
    season INTEGER NOT NULL,
    performance_tier TEXT NOT NULL,
    min_percentile REAL NOT NULL,
    max_percentile REAL NOT NULL,
    
    PRIMARY KEY (season, performance_tier)
);
```

**Implementation Notes:**
- Performance tiers != competitive tiers
- Dominant = top 10%, Contender = 10-30%, etc.
- Enables: "They've spent 9 of 12 seasons in the lower midfield"

---

## IV. TECH & ARMS RACE HISTORY

### A. Innovation Timeline

**New Table: `team_innovation_history`**

```sql
CREATE TABLE team_innovation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    game_day INTEGER NOT NULL,
    
    innovation_type TEXT NOT NULL, -- "first_to_new_part", "breakthrough", "revolution"
    part_type TEXT,
    part_name TEXT,
    innovation_description TEXT,
    
    -- Impact tracking
    cpi_before REAL DEFAULT 0.0,
    cpi_after REAL DEFAULT 0.0,
    cpi_delta REAL DEFAULT 0.0,
    innovation_success REAL DEFAULT 0.0, -- 0-100 score
    
    league_impact TEXT, -- "minor", "major", "game_changing"
    
    created_tick INTEGER NOT NULL
);
```

**New Table: `team_development_arms_race`**

```sql
CREATE TABLE team_development_arms_race (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    
    -- Development metrics
    upgrade_frequency REAL DEFAULT 0.0, -- upgrades per race
    development_spend_rank INTEGER,
    development_budget_pct REAL DEFAULT 0.0, -- % of budget on R&D
    
    -- Arms race positioning
    catch_up_success_rate REAL DEFAULT 0.0,
    seasons_starting_below_avg INTEGER DEFAULT 0,
    seasons_finishing_above_avg INTEGER DEFAULT 0,
    
    -- Innovation stats
    breakthrough_upgrades INTEGER DEFAULT 0,
    failed_upgrades INTEGER DEFAULT 0,
    innovation_success_rate REAL DEFAULT 0.0,
    
    UNIQUE(team_name, season)
);
```

**Implementation Notes:**
- Enables: "First team to develop active suspension" / "48% innovation success rate"
- Arms race tracking identifies catch-up stories

---

## V. ECONOMIC HISTORY

### A. Financial Cycles

**New Table: `team_financial_history`**

```sql
CREATE TABLE team_financial_history (
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
    lowest_cash REAL DEFAULT 0.0, -- low water mark
    highest_cash REAL DEFAULT 0.0, -- high water mark
    near_bankruptcy_events INTEGER DEFAULT 0,
    
    -- Derived metrics
    financial_resilience_score REAL DEFAULT 0.0,
    spending_efficiency REAL DEFAULT 0.0, -- points per dollar
    investment_aggression REAL DEFAULT 0.0,
    runway_weeks_avg REAL DEFAULT 0.0,
    
    UNIQUE(team_name, season)
);
```

**Implementation Notes:**
- Updated at end of season
- Enables: "Ran at a loss for three consecutive seasons" / "Lowest cash position in team history"

---

### B. Sponsorship Legacy

**New Table: `sponsorship_legacy`**

```sql
CREATE TABLE sponsorship_legacy (
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
    
    -- Loyalty metrics
    longest_sponsor_partnership INTEGER DEFAULT 0, -- team-wide
    sponsor_turnover_rate REAL DEFAULT 0.0,
    
    UNIQUE(team_name, sponsor_name, start_season)
);
```

**Implementation Notes:**
- Enables: "TechCorp has backed them for 7 seasons" / "High sponsor turnover rate"

---

## VI. STREAK TRACKING (CRUCIAL FOR RADIO)

### New Table: `active_streaks`

```sql
CREATE TABLE active_streaks (
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
    last_podium_race TEXT,
    last_win_race TEXT,
    last_dnf_race TEXT,
    
    last_updated_tick INTEGER NOT NULL
);
```

**Implementation Notes:**
- Updated after EVERY race
- Real-time urgency driver: "They've scored points in 8 consecutive races"
- Historical comparisons: "Longest win streak since Season 2"

---

## VII. EXPECTATION VS HISTORY MODELS

### New Table: `expectation_models`

```sql
CREATE TABLE expectation_models (
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Expectation metrics
    expected_finish REAL DEFAULT 0.0,
    actual_finish INTEGER,
    expectation_gap REAL DEFAULT 0.0, -- actual - expected
    
    historical_baseline_finish REAL DEFAULT 0.0, -- career avg
    regression_to_mean_indicator REAL DEFAULT 0.0,
    sustainable_performance_score REAL DEFAULT 0.0,
    overachieving_vs_history_index REAL DEFAULT 0.0,
    
    -- Context
    strongest_start_comparison TEXT, -- "Best since Season 3"
    performance_vs_career_avg REAL DEFAULT 0.0,
    
    PRIMARY KEY (team_name, season, round_number)
);
```

**Implementation Notes:**
- Computed after every race
- Enables: "This is their strongest start since Season 3" / "Overperforming expectations by 3.2 positions"

---

## VIII. LEGACY & PRESTIGE SCORES

### New Table: `team_prestige`

```sql
CREATE TABLE team_prestige (
    team_name TEXT PRIMARY KEY,
    
    -- Prestige score (0-100 composite)
    prestige_index REAL DEFAULT 50.0,
    
    -- Components
    championship_prestige REAL DEFAULT 0.0, -- from titles
    wins_prestige REAL DEFAULT 0.0,
    longevity_prestige REAL DEFAULT 0.0,
    era_dominance_prestige REAL DEFAULT 0.0,
    financial_resilience_prestige REAL DEFAULT 0.0,
    
    -- Historical tier
    legacy_tier TEXT, -- "legendary", "storied", "established", "emerging", "new"
    
    last_updated_tick INTEGER NOT NULL
);
```

### New Table: `driver_legacy`

```sql
CREATE TABLE driver_legacy (
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
    legacy_tier TEXT, -- "legend", "great", "solid", "journeyman", "developing"
    
    last_updated_tick INTEGER NOT NULL
);
```

**Implementation Notes:**
- Computed at end of season
- Weights adjust by tier and era
- Enables: "A legendary team facing their toughest challenge"

---

## IX. HEAD-TO-HEAD ARCHIVES

### New Table: `driver_head_to_head`

```sql
CREATE TABLE driver_head_to_head (
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
    
    PRIMARY KEY (driver_a, driver_b),
    CHECK (driver_a < driver_b) -- Ensure alphabetical ordering
);
```

### New Table: `team_head_to_head`

```sql
CREATE TABLE team_head_to_head (
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    
    -- Competition records
    wins_differential INTEGER DEFAULT 0, -- team_a - team_b
    podiums_differential INTEGER DEFAULT 0,
    points_differential REAL DEFAULT 0.0,
    
    -- Championship context
    title_fights_contested INTEGER DEFAULT 0,
    seasons_in_same_tier INTEGER DEFAULT 0,
    era_overlaps TEXT, -- JSON: ["s1_s3", "s5_s9"]
    
    PRIMARY KEY (team_a, team_b),
    CHECK (team_a < team_b)
);
```

**Implementation Notes:**
- Enables rivalry segments: "Leading the head-to-head 47-23" / "Fourth title fight in six seasons"

---

## X. HISTORICAL TREND ANALYTICS

### New Table: `rolling_performance_metrics`

```sql
CREATE TABLE rolling_performance_metrics (
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Rolling windows
    rolling_5season_avg_finish REAL DEFAULT 0.0,
    rolling_10race_points_avg REAL DEFAULT 0.0,
    rolling_3race_form REAL DEFAULT 0.0,
    
    -- Regression analysis
    performance_regression_slope REAL DEFAULT 0.0,
    performance_trend TEXT, -- "rising", "stable", "declining"
    
    -- Pattern detection
    cyclical_rise_fall_pattern TEXT,
    title_probability_given_history REAL DEFAULT 0.0,
    
    PRIMARY KEY (team_name, season, round_number)
);
```

**Implementation Notes:**
- Computed after every race
- Enables: "Performance has declined 12% over last 10 races" / "On upward trajectory"

---

## TIME-BASED SYSTEM METRICS

### A. Enhanced Time Tracking

**Extensions to existing `game_state_snapshot` table:**

```sql
ALTER TABLE game_state_snapshot ADD COLUMN season_progress_pct REAL DEFAULT 0.0;
ALTER TABLE game_state_snapshot ADD COLUMN rounds_remaining INTEGER DEFAULT 0;
ALTER TABLE game_state_snapshot ADD COLUMN days_to_next_race INTEGER DEFAULT 0;
ALTER TABLE game_state_snapshot ADD COLUMN days_since_last_race INTEGER DEFAULT 0;
```

### B. Contract Timelines

**New Table: `contract_pressure_index`**

```sql
CREATE TABLE contract_pressure_index (
    entity_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    team_name TEXT NOT NULL,
    
    contract_days_left INTEGER NOT NULL,
    contract_pressure_score REAL DEFAULT 0.0, -- weighted by importance
    
    -- Context
    is_critical_personnel INTEGER DEFAULT 0,
    replacement_difficulty TEXT, -- "easy", "moderate", "difficult"
    
    last_updated_tick INTEGER NOT NULL
);
```

---

### C. Development Timelines

**New Table: `development_timelines`**

```sql
CREATE TABLE development_timelines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    
    part_name TEXT NOT NULL,
    part_type TEXT NOT NULL,
    
    -- ETA tracking
    build_eta_days INTEGER NOT NULL,
    research_completion_days INTEGER DEFAULT 0,
    upgrade_lag_vs_league REAL DEFAULT 0.0, -- days behind median
    
    -- Status
    status TEXT DEFAULT 'in_progress', -- "in_progress", "completed", "cancelled"
    
    created_tick INTEGER NOT NULL,
    completed_tick INTEGER
);
```

---

### D. Momentum Windows

**New Table: `momentum_metrics`**

```sql
CREATE TABLE momentum_metrics (
    team_name TEXT PRIMARY KEY,
    
    -- Form metrics
    form_last_3_races REAL DEFAULT 0.0,
    form_last_5_races REAL DEFAULT 0.0,
    momentum_slope REAL DEFAULT 0.0, -- linear regression over last N finishes
    
    -- Momentum classification
    momentum_state TEXT DEFAULT 'stable', -- "surging", "stable", "declining", "collapsing"
    
    last_updated_tick INTEGER NOT NULL
);
```

---

### E. Narrative Heat

**New Table: `narrative_heat_scores`**

```sql
CREATE TABLE narrative_heat_scores (
    team_name TEXT NOT NULL,
    story_type TEXT NOT NULL,
    
    -- Heat tracking (0-100 with decay)
    heat_score REAL DEFAULT 0.0,
    peak_heat REAL DEFAULT 0.0,
    decay_rate REAL DEFAULT 5.0, -- points per day
    
    -- Story context
    story_start_tick INTEGER NOT NULL,
    last_boosted_tick INTEGER NOT NULL,
    days_since_last_boost INTEGER DEFAULT 0,
    
    -- Story metadata
    story_description TEXT,
    key_players TEXT, -- JSON array
    
    PRIMARY KEY (team_name, story_type)
);
```

**Story types:**
- `rivalry_heat`
- `financial_crisis_heat`
- `breakthrough_heat`
- `collapse_heat`
- `comeback_heat`

**Implementation Notes:**
- Heat decays daily unless refreshed by events
- Drives urgency: "Championship battle intensity at season high"

---

## MOTORSPORT PERFORMANCE METRICS

Most already exist in current schema. **Enhancements:**

### New Computed Views

```sql
CREATE VIEW team_performance_summary AS
SELECT 
    t.team_name,
    t.tier,
    t.championship_position,
    t.points,
    
    -- Car metrics
    (SELECT value FROM team_car_performance WHERE team = t.team_name LIMIT 1) as cpi,
    
    -- Derived
    (t.points * 1.0 / NULLIF(races_completed, 0)) as points_per_race,
    (t.championship_position * 1.0 / league_size) as championship_percentile,
    
    -- Overperformance
    (expected_finish - actual_finish) as overperformance_index
FROM teams t;
```

---

## INFRASTRUCTURE & DEVELOPMENT

### Extensions to existing infrastructure tracking:

**New Table: `team_infrastructure_evolution`**

```sql
CREATE TABLE team_infrastructure_evolution (
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
    
    UNIQUE(team_name, season)
);
```

---

## ECONOMIC METRICS

Most exist. **Enhancement:**

### New View: `team_financial_health`

```sql
CREATE VIEW team_financial_health AS
SELECT
    team_name,
    budget as cash_on_hand,
    
    -- Burn rate (computed from transactions)
    (SELECT AVG(daily_expenses) FROM financial_summary WHERE team = team_name) as burn_rate_weekly,
    
    -- Runway
    (budget / NULLIF(burn_rate_weekly, 0)) as runway_weeks,
    
    -- Stability
    CASE
        WHEN runway_weeks > 20 THEN 'stable'
        WHEN runway_weeks > 10 THEN 'moderate'
        WHEN runway_weeks > 5 THEN 'concerning'
        ELSE 'crisis'
    END as financial_stability,
    
    -- Investment confidence
    (development_spend / NULLIF(total_spend, 0)) as investment_confidence_index
    
FROM teams;
```

---

## LEAGUE ECONOMY & LANDSCAPE

### New Table: `league_baselines`

```sql
CREATE TABLE league_baselines (
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
    league_parity_score REAL DEFAULT 0.0, -- std dev of CPI
    dominance_index REAL DEFAULT 0.0, -- P1 CPI vs avg
    midfield_compression_score REAL DEFAULT 0.0, -- CPI spread P5-P10
    
    PRIMARY KEY (league_id, season, round_number)
);
```

**Implementation Notes:**
- Computed after every race
- Enables: "23% above league average CPI" / "Highest parity season in history"

---

## META-ANALYTICS FOR NARRATIVE CONTROL

### New Table: `expectation_calibration`

```sql
CREATE TABLE expectation_calibration (
    team_name TEXT NOT NULL,
    season INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    
    -- Expectation modeling
    expected_model_finish REAL DEFAULT 0.0,
    expectation_gap REAL DEFAULT 0.0,
    narrative_bias_correction REAL DEFAULT 0.0,
    
    -- Hope/doom metrics
    hope_index REAL DEFAULT 50.0, -- based on dev velocity vs gap
    trajectory_projection TEXT, -- "title_contention", "midfield_stability", "relegation_risk"
    
    -- 5-race forecast
    simulated_forecast_json TEXT, -- Monte Carlo projection
    
    PRIMARY KEY (team_name, season, round_number)
);
```

---

## SPECIAL SITUATIONAL TRIGGERS

### New Table: `situational_triggers`

```sql
CREATE TABLE situational_triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_name TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    
    -- Trigger state
    is_active INTEGER DEFAULT 0,
    severity REAL DEFAULT 0.0, -- 0-100
    activated_tick INTEGER,
    resolved_tick INTEGER,
    
    -- Context
    description TEXT,
    narrative_priority INTEGER DEFAULT 50,
    
    UNIQUE(team_name, trigger_type, activated_tick)
);
```

**Trigger types:**
- `contract_cliff`
- `financial_cliff`
- `championship_elimination`
- `promotion_threat`
- `relegation_threat`
- `breakout_performance`
- `collapse_event`
- `reliability_spiral`
- `sponsor_risk`

---

## COMPOSITE SCORES FOR RADIO OS INJECTION

### New Table: `team_pulse_metrics`

```sql
CREATE TABLE team_pulse_metrics (
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
```

**Competitive tier labels:**
- Dominant (top 5%)
- Contender (5-20%)
- Upper Midfield (20-40%)
- Midfield (40-60%)
- Lower Midfield (60-80%)
- Backmarker (80-95%)
- Crisis Mode (95-100%)

**Narrative temperature labels:**
- Stable
- Tense
- Surging
- Fragile
- Volatile
- Desperate

---

## FTB DB EXPLORER WIDGET

### Implementation Plan

**New plugin: `ftb_db_explorer.py`**

**Features:**
1. **Team Historical Dashboard**
   - Career totals visualization
   - Era performance comparison charts
   - Peak/valley timeline
   - Financial history graph

2. **Driver Archives**
   - Career stats grid
   - Team stint breakdown
   - Development curve visualization
   - Head-to-head records matrix

3. **League History Browser**
   - Championship history table
   - Tier evolution heatmap
   - Competitive landscape timeline
   - Parity index trends

4. **Analytics Dashboard**
   - Real-time composite scores
   - Streak tracker
   - Momentum gauges
   - Situational triggers panel

5. **Query Console**
   - SQL query builder
   - Custom metric calculator
   - Export to JSON/CSV

**UI Structure:**

```
┌─ FTB DB Explorer ────────────────────────────────┐
│                                                   │
│  [Teams] [Drivers] [League] [Analytics] [Query]  │
│                                                   │
│  ┌─ Selected: Apex Racing ─────────────────────┐ │
│  │                                              │ │
│  │  Career: 47 wins, 3 titles (12 seasons)     │ │
│  │  Win Rate: 24.1% │ Current Streak: 3 races  │ │
│  │                                              │ │
│  │  [Era Performance Chart]                     │ │
│  │  [Financial History Graph]                   │ │
│  │  [Peak Season: S6 - 18 wins, 412 pts]       │ │
│  │                                              │ │
│  └──────────────────────────────────────────────┘ │
│                                                   │
└───────────────────────────────────────────────────┘
```

---

## MASTER META PLUGIN

**New plugin: `ftb_meta_orchestrator.py`**

**Responsibilities:**
1. **Data Aggregation Pipeline**
   - Ingest game events from `ftb_game.py`
   - Update all historical tables
   - Compute derived metrics
   - Maintain streak tracking

2. **Analytics Engine**
   - Run expectation models
   - Compute composite scores
   - Update prestige indices
   - Detect situational triggers

3. **Narrator Interface**
   - Expose rich query API
   - Provide contextual data packets
   - Supply comparative metrics
   - Generate narrative suggestions

4. **Performance Optimization**
   - Batch database updates
   - Cache frequent queries
   - Lazy computation of expensive metrics
   - Async processing for non-critical updates

**API Example:**

```python
# Get rich context for narrator
context = ftb_meta.get_narrator_context(
    team_name="Apex Racing",
    context_depth="full"
)

# Returns:
{
    "team_pulse": 73.2,
    "competitive_tier": "upper_midfield",
    "narrative_temperature": "surging",
    "active_streaks": {
        "points": 8,
        "approaching_record": "longest_points_streak_ever (12)"
    },
    "historical_context": "Best 5-race stretch since Season 3",
    "expectation_gap": +2.4,  # overperforming
    "momentum": "rising",
    "hot_narratives": [
        {"type": "breakout_performance", "heat": 82},
        {"type": "financial_recovery", "heat": 67}
    ]
}
```

---

## IMPLEMENTATION PHASES

### Phase 1: Foundation (Sprint 1-2)
- [ ] Create all new database tables
- [ ] Implement basic update triggers
- [ ] Test data persistence across saves

### Phase 2: Historical Tracking (Sprint 3-5)
- [ ] Career totals tracking
- [ ] Era performance system
- [ ] Peak/valley metrics
- [ ] Driver career stats
- [ ] Team stint records

### Phase 3: Advanced Analytics (Sprint 6-8)
- [ ] Expectation models
- [ ] Prestige scoring
- [ ] Head-to-head archives
- [ ] Rolling performance metrics
- [ ] Narrative heat system

### Phase 4: Time Systems (Sprint 9-10)
- [ ] Enhanced time tracking
- [ ] Contract pressure index
- [ ] Development timelines
- [ ] Momentum metrics

### Phase 5: Meta Plugin (Sprint 11-13)
- [ ] Data aggregation pipeline
- [ ] Analytics engine
- [ ] Narrator interface API
- [ ] Performance optimization

### Phase 6: DB Explorer Widget (Sprint 14-16)
- [ ] Team dashboard
- [ ] Driver archives browser
- [ ] League history viewer
- [ ] Analytics dashboard
- [ ] Query console

### Phase 7: Integration & Polish (Sprint 17-18)
- [ ] Connect to narrator plugin
- [ ] Performance tuning
- [ ] Documentation
- [ ] Example narratives

---

## DATA VOLUME ESTIMATES

**After 20 seasons of simulation:**

| Table | Estimated Rows |
|-------|----------------|
| team_career_totals | ~40 teams |
| team_era_performance | ~160 (40 teams × 4 eras) |
| driver_career_stats | ~200 drivers |
| driver_team_stints | ~400 stints |
| championship_history | 20 seasons |
| team_tier_history | ~800 (40 teams × 20 seasons) |
| race_results_archive | ~400 races |
| active_streaks | ~40 teams |
| rolling_performance_metrics | ~8,000 (40 teams × 20 seasons × 10 rounds) |
| narrative_heat_scores | ~200 active stories |

**Total estimated DB size:** ~50-100 MB (well within SQLite comfort zone)

---

## NARRATIVE EXAMPLES ENABLED

With this system, your narrator can say:

> "Apex Racing has now scored points in 14 consecutive races—their longest streak **since Season 4** and just 3 shy of their all-time record. They've climbed from **lower midfield to contender tier** over the past 18 months, a trajectory we haven't seen since the legendary **Velocity Era champions** of Seasons 6-8. Their **team pulse is at 82**—the highest in franchise history—and they're **overperforming expectations by 2.7 positions**. Financial stability has improved dramatically: they're operating with a **19-week runway**, up from **4 weeks** this time last year. The **breakthrough heat** surrounding their aero package innovation is still at **91**—it's the story of the season. If they maintain this form, our models give them a **34% title probability**—fourth-best odds, but rising. This is no longer a fluke. This is a **resurgence**."

---

## MIGRATION STRATEGY

For existing saves:

1. **Bootstrap historical data** from `race_results_archive` and `season_summaries`
2. **Recompute career totals** from existing records
3. **Generate synthetic era definitions** based on season blocks
4. **Populate streak tracking** from recent race history
5. **Initialize prestige scores** using current standings + career data
6. **Set baseline expectations** using league averages

Script: `tools/ftb_historical_data_bootstrap.py`

---

## SUCCESS METRICS

- [ ] Narrator can access 100+ historical data points per team
- [ ] DB Explorer widget loads <500ms for any team
- [ ] All derived metrics compute in <100ms
- [ ] Zero narrator hallucinations about team history
- [ ] Streaks and records update in real-time
- [ ] Financial doom only when numbers justify (runway < 6 weeks)
- [ ] Narratives cite specific historical comparisons

---

## NEXT STEPS

1. **Review this plan** with team
2. **Prioritize tables** (which are MVP vs nice-to-have?)
3. **Create detailed schema SQL file** (`schema/ftb_historical_tables.sql`)
4. **Implement Phase 1** (database foundation)
5. **Build test harness** to validate historical accuracy
6. **Prototype DB Explorer** basic views

---

**Document Version:** 2.0  
**Last Updated:** 2026-02-12  
**Owner:** FTB Core Team  
**Status:** Ready for Implementation Review
