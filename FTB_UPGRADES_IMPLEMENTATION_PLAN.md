# From The Backmarker - Upgrades Implementation Plan

**Version:** 1.0  
**Date:** February 13, 2026  
**Scope:** 9 major feature upgrades for FTB racing management game

---

## 📋 Executive Summary

This document provides a phased, technically detailed implementation plan for upgrading the From The Backmarker (FTB) game plugin. All variable names, file paths, and implementation details have been verified against the current codebase structure.

**Key Files:**
- Main game logic: `/plugins/ftb_game.py` (29,841 lines)
- State database: `/plugins/ftb_state_db.py` (3,921 lines)
- Narrator system: `/plugins/meta/ftb_narrator_plugin.py` (3,454 lines)
- Components library: `/plugins/ftb_components.py`

---

## 🎯 Feature Priority Matrix

| Priority | Feature | Complexity | Impact | Dependencies |
|----------|---------|------------|--------|--------------|
| **P0** | Recent Race Results Bug Fix | Low | High | None |
| **P0** | Contract Expiry Dashboard Alerts | Low | High | None |
| **P1** | Morale System Stabilization | Medium | High | None |
| **P1** | UI Refresh Controls | Low | Medium | None |
| **P2** | Driver Poaching & Compensation | High | High | Morale fix |
| **P2** | Narrator Tick Alignment | Medium | High | None |
| **P3** | Sponsor Page Refresh | Low | Low | Refresh controls |

---

## 🔴 PHASE 0: Critical Bug Fixes (Week 1)

### 6. Recent Race Results Bug Fix

**Problem:** Dashboard shows "No recent races" despite races being completed past Race 4.

**Root Cause Analysis:**
```python
# Current code at line ~22847-22850
race_results = [
    e for e in self.sim_state.event_history[-50:]
    if e.category == "race_result" and e.data.get("team") == self.sim_state.player_team.name
]
```

**Issues:**
1. ✅ Filter looks correct - searches for `category == "race_result"`
2. ❌ Possible issue: `event_history` may not be populated correctly
3. ❌ Possible issue: `e.category` vs `e.event_type` naming inconsistency
4. ❌ Check if events are using `data.get("team")` or `data.get("team_name")`

**Implementation Steps:**

#### Step 1: Verify Event Structure
```python
# Location: ftb_game.py, around line 8200-8300 (_apply_performance_morale_changes)
# Check how race result events are created

# Search for: SimEvent creation with category="race_result"
# Expected structure:
SimEvent(
    event_type="outcome",           # ← Check this
    category="race_result",         # ← Must match dashboard filter
    ts=state.tick,
    priority=80.0,
    severity="info",
    data={
        'team': team_name,          # ← Check exact key name
        'driver': driver_name,
        'position': position,
        'points': points,
        'grid_position': grid_pos
    }
)
```

#### Step 2: Fix Dashboard Query
```python
# Location: ftb_game.py, line ~22847
# File: plugins/ftb_game.py
# Method: _refresh_race_ops

def _refresh_race_ops(self):
    # ... existing code ...
    
    # BEFORE (potentially broken):
    race_results = [
        e for e in self.sim_state.event_history[-50:]
        if e.category == "race_result" and e.data.get("team") == self.sim_state.player_team.name
    ]
    
    # AFTER (robust version):
    race_results = []
    for e in self.sim_state.event_history[-100:]:  # Check more events
        # Handle both category and event_type naming
        event_cat = getattr(e, 'category', None) or getattr(e, 'event_type', '')
        
        if event_cat == "race_result":
            # Check all possible team key names
            event_team = (e.data.get("team") or 
                         e.data.get("team_name") or 
                         e.data.get("team_id"))
            
            if event_team == self.sim_state.player_team.name:
                race_results.append(e)
    
    # Add debug logging
    if not race_results and self.sim_state.races_completed_this_season > 0:
        print(f"[FTB Debug] No race results found despite {self.sim_state.races_completed_this_season} races completed")
        print(f"[FTB Debug] Event history size: {len(self.sim_state.event_history)}")
        print(f"[FTB Debug] Sample events: {[e.category if hasattr(e, 'category') else e.event_type for e in self.sim_state.event_history[-10:]]}")
```

#### Step 3: Verify Event Persistence
```python
# Check if events are being cleared prematurely
# Location: SimState class initialization and tick processing

# Ensure event_history has sufficient retention:
self.event_history: List[SimEvent] = []  # Current
self.max_event_history = 500  # Add this limit

# In tick processing, trim intelligently:
if len(self.event_history) > self.max_event_history:
    # Keep all race_result events + recent 200 events
    race_events = [e for e in self.event_history if getattr(e, 'category', '') == 'race_result']
    recent_events = self.event_history[-200:]
    self.event_history = race_events + [e for e in recent_events if e not in race_events]
```

#### Step 4: Add Dashboard Display for Multiple Drivers
```python
# Location: _refresh_race_ops, after race_results query

if not race_results:
    ctk.CTkLabel(
        self.race_results_container,
        text="No races completed yet",
        font=("Arial", 11),
        text_color=FTBTheme.TEXT_MUTED
    ).pack(pady=20)
else:
    # Group by race (handle both drivers)
    races_dict = {}
    for result_event in race_results[-10:]:  # Last 10 results (5 races if 2 drivers)
        race_id = result_event.data.get('race_id', result_event.data.get('race_name', f"Race_{result_event.ts}"))
        if race_id not in races_dict:
            races_dict[race_id] = []
        races_dict[race_id].append(result_event)
    
    # Display last 5 races
    for race_id in list(races_dict.keys())[-5:]:
        race_frame = ctk.CTkFrame(
            self.race_results_container,
            fg_color=FTBTheme.SURFACE,
            corner_radius=6
        )
        race_frame.pack(fill=tk.X, pady=5)
        
        # Race header
        ctk.CTkLabel(
            race_frame,
            text=f"Race: {race_id}",
            font=("Arial", 11, "bold"),
            text_color=FTBTheme.TEXT
        ).pack(anchor="w", padx=10, pady=(8, 4))
        
        # Each driver result
        for result_event in races_dict[race_id]:
            data = result_event.data
            driver = data.get('driver', 'Unknown')
            position = data.get('position', '--')
            points = data.get('points', 0)
            grid_pos = data.get('grid_position', '--')
            
            pos_color = (FTBTheme.SUCCESS if position <= 3 else 
                        FTBTheme.ACCENT if position <= 10 else 
                        FTBTheme.TEXT_MUTED)
            
            driver_row = ctk.CTkFrame(race_frame, fg_color="transparent")
            driver_row.pack(fill=tk.X, padx=10, pady=2)
            
            ctk.CTkLabel(
                driver_row,
                text=f"  {driver}: P{position} ({grid_pos} → {position}) - {points} pts",
                font=("Arial", 10),
                text_color=pos_color
            ).pack(anchor="w")
```

**Testing Checklist:**
- [ ] Complete 5+ races in a season
- [ ] Check dashboard shows correct results for both drivers
- [ ] Verify results persist after game save/load
- [ ] Test with DNFs and various finishing positions
- [ ] Confirm no duplicate entries

---

### 5. Contract Expiry Dashboard Alerts

**Current State:**
- Dashboard exists at line ~17893 (`_build_dashboard_tab`)
- Contract alerts label exists at line ~18163: `self.contract_alerts_label`
- No active alert system implemented

**Implementation:**

#### Step 1: Add Dashboard Widget (Already Partially Exists)
```python
# Location: _build_dashboard_tab, line ~18163
# Currently shows: "📋 Contracts: --"

# ENHANCE existing widget:
self.contract_alerts_label = ctk.CTkLabel(
    status_panel,
    text="📋 Contracts: --",
    font=("Arial", 11),
    text_color=FTBTheme.TEXT,
    anchor="w",
    justify="left"  # Allow multi-line
)
self.contract_alerts_label.pack(padx=15, pady=(0, 15), anchor="w")
```

#### Step 2: Create Contract Alert System
```python
# Location: Add new method in FTBWidget class, around line ~26500

def _update_contract_alerts(self):
    """Update contract expiry alerts on dashboard"""
    if not self.sim_state or not self.sim_state.player_team:
        self.contract_alerts_label.configure(text="📋 Contracts: --")
        return
    
    team = self.sim_state.player_team
    current_day = self.sim_state.sim_day_of_year
    
    expiring_soon = []
    
    # Check all active contracts
    all_entities = (
        team.drivers + 
        team.engineers + 
        team.mechanics + 
        ([team.strategist] if team.strategist else [])
    )
    
    for entity in all_entities:
        if not entity or not hasattr(entity, 'contract'):
            continue
        
        contract = entity.contract
        if not contract:
            continue
        
        days_remaining = contract.days_remaining(current_day)
        
        if days_remaining <= 0:
            continue  # Already expired
        
        # Categorize by urgency
        if days_remaining <= 7:
            urgency = "🔴 CRITICAL"
            color = FTBTheme.ERROR
        elif days_remaining <= 14:
            urgency = "🟡 URGENT"
            color = FTBTheme.WARNING
        elif days_remaining <= 30:
            urgency = "🟢 Soon"
            color = FTBTheme.ACCENT
        else:
            continue  # Not soon enough to alert
        
        expiring_soon.append({
            'name': entity.name,
            'role': contract.role,
            'days': days_remaining,
            'urgency': urgency,
            'color': color
        })
    
    # Sort by urgency (days remaining, ascending)
    expiring_soon.sort(key=lambda x: x['days'])
    
    # Build alert text
    if not expiring_soon:
        self.contract_alerts_label.configure(
            text="📋 Contracts: All stable",
            text_color=FTBTheme.TEXT_MUTED
        )
    else:
        alert_lines = ["📋 Contracts Expiring:"]
        for item in expiring_soon[:5]:  # Show max 5
            alert_lines.append(
                f"  {item['urgency']} {item['name']} ({item['role']}) - {item['days']}d"
            )
        
        if len(expiring_soon) > 5:
            alert_lines.append(f"  ... and {len(expiring_soon) - 5} more")
        
        # Use the most urgent color
        primary_color = expiring_soon[0]['color']
        
        self.contract_alerts_label.configure(
            text="\n".join(alert_lines),
            text_color=primary_color
        )
```

#### Step 3: Integrate into Dashboard Refresh
```python
# Location: _periodic_tick_update, around line 26250

elif current_tab == "Dashboard":
    # Dashboard pressure indicators need regular updates
    self._update_pressure_indicators()
    self._update_contract_alerts()  # ← ADD THIS
```

#### Step 4: Add Notification System Integration
```python
# Location: SimState class tick processing, around line 4400

def _check_contract_expiry_notifications(self):
    """Generate notifications for expiring contracts"""
    current_day = self.sim_day_of_year
    team = self.player_team
    
    if not team:
        return
    
    all_entities = (
        team.drivers + 
        team.engineers + 
        team.mechanics + 
        ([team.strategist] if team.strategist else [])
    )
    
    for entity in all_entities:
        if not entity or not hasattr(entity, 'contract'):
            continue
        
        contract = entity.contract
        if not contract:
            continue
        
        days_remaining = contract.days_remaining(current_day)
        
        # Trigger notifications at specific thresholds
        # Use contract._last_notified_at to avoid spam
        if not hasattr(contract, '_last_notified_at'):
            contract._last_notified_at = {}
        
        notify_thresholds = [30, 14, 7]
        
        for threshold in notify_thresholds:
            if days_remaining == threshold:
                # Check if we already notified at this threshold
                notification_key = f"{entity.name}_{threshold}"
                if notification_key not in contract._last_notified_at:
                    contract._last_notified_at[notification_key] = self.tick
                    
                    # Create notification event
                    severity = "critical" if threshold <= 7 else "warning" if threshold <= 14 else "info"
                    
                    self.event_history.append(SimEvent(
                        event_type="notification",
                        category="contract_expiry",
                        ts=self.tick,
                        priority=90.0 if threshold <= 7 else 70.0,
                        severity=severity,
                        data={
                            'entity': entity.name,
                            'role': contract.role,
                            'days_remaining': days_remaining,
                            'threshold': threshold,
                            'message': f"{entity.name}'s contract expires in {days_remaining} days"
                        }
                    ))

# Add to main tick processing:
def tick(self, delegate_mode=False):
    # ... existing tick logic ...
    
    # Add after phase transitions, before event processing:
    self._check_contract_expiry_notifications()
```

#### Step 5: Add Quick Renewal Shortcut (Optional Enhancement)
```python
# In dashboard contract alert display, add clickable buttons

for item in expiring_soon[:5]:
    item_frame = ctk.CTkFrame(status_panel, fg_color=FTBTheme.SURFACE, corner_radius=4)
    item_frame.pack(fill=tk.X, padx=15, pady=2)
    
    # Alert text
    ctk.CTkLabel(
        item_frame,
        text=f"{item['urgency']} {item['name']} ({item['role']}) - {item['days']}d",
        font=("Arial", 10),
        text_color=item['color']
    ).pack(side=tk.LEFT, padx=10, pady=5)
    
    # Quick renew button
    renew_btn = ctk.CTkButton(
        item_frame,
        text="Renew",
        width=60,
        height=24,
        fg_color=FTBTheme.ACCENT,
        command=lambda e=item: self._quick_renew_contract(e['name'])
    )
    renew_btn.pack(side=tk.RIGHT, padx=10, pady=5)
```

**Testing Checklist:**
- [ ] Contracts show correct days remaining
- [ ] Colors change appropriately (green → yellow → red)
- [ ] Notifications trigger at 30d, 14d, 7d
- [ ] No duplicate notifications for same contract
- [ ] Dashboard updates in real-time during gameplay
- [ ] Quick renew button works (if implemented)

---

## 🟡 PHASE 1: Stability & UX Improvements (Week 2-3)

### 4. Morale System Stabilization

**Problem:** Morale trends excessively in one direction without natural regression (runaway drift bug).

**Current Implementation:**
```python
# Location: line ~8288-8400
def _apply_performance_morale_changes(state, league, race_result, qualifying_scores):
    # Current logic applies morale changes based on performance delta
    # NO mean reversion mechanism
    # NO diminishing returns
```

**Verified Variables:**
- ✅ `driver.morale` exists (line 8336: `driver.morale`)
- ✅ `driver.mettle` exists (line 8329: `driver_mettle = getattr(driver, 'mettle', 55.0)`)
- ✅ `team.standing_metrics['morale']` exists (line 8360)
- ⚠️ Need to add `morale_baseline` to entities

#### Implementation:

**Step 1: Add Baseline to Entity Initialization**
```python
# Location: Driver class initialization, around line 1568-1700

class Driver(Entity):
    def __init__(self, ...):
        super().__init__(...)
        # ... existing initialization ...
        
        # ADD THESE:
        self.morale = 50.0  # Current morale (already exists)
        self.morale_baseline = self._calculate_baseline()  # NEW
        self.morale_last_updated = 0  # NEW - track when last modified
    
    def _calculate_baseline(self) -> float:
        """Calculate personality-driven morale baseline
        
        Factors:
        - Mettle: Higher mettle = higher baseline resilience
        - Composure: Emotional stability
        - Ambition: Some drivers need success to be happy
        """
        mettle = getattr(self, 'mettle', 55.0)
        composure = getattr(self, 'composure', 50.0)
        
        # Baseline ranges from 40-60 based on personality
        baseline = 45.0 + (mettle / 10.0) + (composure / 20.0)
        return max(40.0, min(60.0, baseline))
```

**Step 2: Implement Mean Reversion System**
```python
# Location: Add new method in SimState class, around line 8500

def _apply_morale_mean_reversion(self, team: Team) -> None:
    """Apply daily morale regression toward baseline
    
    This prevents runaway morale drift by creating elastic pull
    toward a personality-driven equilibrium point.
    
    Called daily for all entities.
    """
    current_day = self.sim_day_of_year
    
    # Reversion strength (tunable)
    DAILY_REVERSION_FACTOR = 0.08  # 8% daily pull toward baseline
    
    all_entities = (
        team.drivers + 
        team.engineers + 
        team.mechanics + 
        ([team.strategist] if team.strategist else [])
    )
    
    for entity in all_entities:
        if not entity or not hasattr(entity, 'morale'):
            continue
        
        # Ensure baseline exists
        if not hasattr(entity, 'morale_baseline'):
            entity.morale_baseline = 50.0
        
        current_morale = entity.morale
        baseline = entity.morale_baseline
        
        # Calculate regression amount
        morale_delta = baseline - current_morale
        reversion_amount = morale_delta * DAILY_REVERSION_FACTOR
        
        # Apply reversion
        entity.morale += reversion_amount
        
        # Clamp to valid range
        entity.morale = max(0.0, min(100.0, entity.morale))
        
        # Log significant changes (for debugging)
        if abs(reversion_amount) > 0.5:
            self.event_history.append(SimEvent(
                event_type="internal",
                category="morale_reversion",
                ts=self.tick,
                priority=20.0,
                severity="debug",
                data={
                    'entity': entity.name,
                    'team': team.name,
                    'old_morale': current_morale,
                    'new_morale': entity.morale,
                    'baseline': baseline,
                    'reversion': reversion_amount
                }
            ))
```

**Step 3: Add Diminishing Returns Curve**
```python
# Location: Modify _apply_performance_morale_changes, around line 8288

def _apply_performance_morale_changes(state, league, race_result, qualifying_scores):
    """Apply morale changes with diminishing returns"""
    events = []
    
    # ... existing position calculation logic ...
    
    # Calculate BASE morale change
    if position_delta > 2:
        base_morale_change = min(12.0, position_delta * 3.5)
    elif position_delta > 0:
        base_morale_change = position_delta * 2.5
    elif position_delta == 0:
        base_morale_change = 0.5
    elif position_delta >= -2:
        driver_mettle = getattr(driver, 'mettle', 55.0)
        mettle_multiplier = (100.0 - driver_mettle) / 100.0
        base_morale_change = position_delta * 4.0 * mettle_multiplier
    else:
        driver_mettle = getattr(driver, 'mettle', 55.0)
        mettle_multiplier = (100.0 - driver_mettle) / 100.0
        base_morale_change = max(-20.0, position_delta * 5.0 * mettle_multiplier)
    
    # NEW: Apply diminishing returns curve
    current_morale = getattr(driver, 'morale', 50.0)
    diminishing_factor = calculate_morale_diminishing_returns(current_morale, base_morale_change)
    
    final_morale_change = base_morale_change * diminishing_factor
    
    # Apply to driver
    if hasattr(driver, 'morale') and abs(final_morale_change) >= 0.5:
        old_morale = driver.morale
        driver.morale = max(0.0, min(100.0, driver.morale + final_morale_change))
        # ... rest of existing logic ...


def calculate_morale_diminishing_returns(current_morale: float, proposed_change: float) -> float:
    """Calculate diminishing returns multiplier for morale changes
    
    Prevents runaway high/low morale by reducing effectiveness of
    changes when morale is already extreme.
    
    Args:
        current_morale: Current morale value (0-100)
        proposed_change: Proposed morale change amount
    
    Returns:
        Multiplier between 0.0 and 1.0
    """
    # Distance from center (50)
    distance_from_center = abs(current_morale - 50.0)
    
    # If change would push further from center, apply diminishing returns
    if (current_morale > 50.0 and proposed_change > 0) or \
       (current_morale < 50.0 and proposed_change < 0):
        
        # Stronger diminishing returns as you get further from 50
        # At 80 morale: 60% effectiveness
        # At 90 morale: 20% effectiveness
        # At 20 morale: 60% effectiveness (for negative changes)
        # At 10 morale: 20% effectiveness (for negative changes)
        
        if distance_from_center < 20:
            return 1.0  # Full effect within normal range
        elif distance_from_center < 30:
            return 0.8  # 80% effect
        elif distance_from_center < 40:
            return 0.5  # 50% effect
        else:
            return 0.2  # 20% effect at extremes
    
    else:
        # Change brings morale back toward center - allow full effect
        return 1.0
```

**Step 4: Context-Aware Event Scaling**
```python
# Location: Add to _apply_performance_morale_changes, around line 8320

def _calculate_expected_position(team: Team, league: League) -> int:
    """Calculate expected finishing position based on:
    - Car rating
    - Driver rating  
    - Budget tier
    - Recent form
    """
    # Get team's overall strength relative to league
    team_strength = calculate_team_strength(team)
    
    # Rank all teams by strength
    team_rankings = sorted(
        [(t, calculate_team_strength(t)) for t in league.teams],
        key=lambda x: x[1],
        reverse=True
    )
    
    # Find team's position in rankings
    for idx, (ranked_team, strength) in enumerate(team_rankings, 1):
        if ranked_team.name == team.name:
            return idx
    
    return len(league.teams) // 2  # Default to midfield


def calculate_team_strength(team: Team) -> float:
    """Composite strength score"""
    car_rating = getattr(team, 'overall_car_rating', 50.0)
    driver_avg = sum(d.overall_rating for d in team.drivers if d) / max(len([d for d in team.drivers if d]), 1)
    budget_factor = (team.budget.current_cash / 1000000) * 0.1  # Slight budget advantage
    
    return car_rating * 0.5 + driver_avg * 0.4 + budget_factor


# Then use this in morale calculation:
expected_pos = _calculate_expected_position(team, league)
position_delta = expected_pos - position  # Positive = better than expected

# Scale morale impact by magnitude of surprise
if position_delta > 5:
    # Huge overperformance - major morale boost
    base_morale_change *= 1.5
elif position_delta < -5:
    # Huge underperformance - major morale hit
    base_morale_change *= 1.5
```

**Step 5: Daily Morale Tick Integration**
```python
# Location: Main tick processing in SimState, around line 4400

def tick(self, delegate_mode=False):
    # ... existing tick logic ...
    
    # Add daily morale processing (NON-race days)
    if self.phase != "race_weekend":
        # Apply mean reversion for all teams
        for league in self.leagues:
            for team in league.teams:
                self._apply_morale_mean_reversion(team)
    
    # ... rest of tick logic ...
```

**Testing & Tuning:**

```python
# Add debug command to test morale system
def _debug_morale_simulation(self):
    """Run 100-tick morale simulation to test stability"""
    test_driver = self.sim_state.player_team.drivers[0]
    initial_morale = test_driver.morale
    
    history = []
    
    # Simulate 100 days with no events (pure reversion)
    for i in range(100):
        self.sim_state._apply_morale_mean_reversion(self.sim_state.player_team)
        history.append(test_driver.morale)
    
    # Plot results
    print(f"Initial: {initial_morale:.1f}")
    print(f"Final: {test_driver.morale:.1f}")
    print(f"Baseline: {test_driver.morale_baseline:.1f}")
    print(f"Convergence: {abs(test_driver.morale - test_driver.morale_baseline):.1f}")
    
    # Should converge to baseline within ~30 days
    assert abs(test_driver.morale - test_driver.morale_baseline) < 5.0, "Morale didn't converge"
```

**Configuration Constants:**
```python
# Add to top of ftb_game.py with other constants

# Morale System Configuration
MORALE_CONFIG = {
    'daily_reversion_factor': 0.08,      # 8% daily pull toward baseline
    'baseline_range': (40.0, 60.0),      # Min/max personality baselines
    'diminishing_returns_threshold': 20, # Distance from 50 before diminishing returns kick in
    'extreme_morale_cap': 0.2,           # Max 20% effectiveness at extremes (>40 distance from 50)
    'dnf_base_penalty': -15.0,           # Base morale loss for DNF
    'max_single_change': 20.0,           # Maximum morale change in single event
}
```

**Testing Checklist:**
- [ ] Morale converges to baseline over 30-50 days with no events
- [ ] High morale (>80) becomes harder to increase further
- [ ] Low morale (<20) becomes harder to decrease further
- [ ] Series of wins doesn't push morale above ~90
- [ ] Series of losses doesn't push morale below ~10
- [ ] Different personality types (high mettle vs low mettle) have different baselines
- [ ] Context matters: P10 when expected P15 = positive; P10 when expected P5 = negative
- [ ] No infinite loops or NaN values

---

### 2. UI Refresh Controls

**Current State:**
- Many `_refresh_*` methods already exist (18+ methods)
- Methods reload data from `self.sim_state`
- No explicit refresh buttons in UI

**Strategy:** Add consistent "↻ Refresh" button to each major tab.

#### Implementation Template:

```python
# Standard refresh button pattern
# Add to each tab's build method

def _build_[TAB_NAME]_tab(self):
    tab = self.tab_[TAB_NAME]
    
    # Header with refresh button
    header = ctk.CTkFrame(tab, fg_color="transparent")
    header.pack(fill=tk.X, padx=10, pady=10)
    
    ctk.CTkLabel(
        header,
        text="[TAB TITLE]",
        font=("Arial", 16, "bold"),
        text_color=FTBTheme.TEXT
    ).pack(side=tk.LEFT)
    
    # REFRESH BUTTON (standardized)
    refresh_btn = ctk.CTkButton(
        header,
        text="↻ Refresh",
        width=100,
        height=28,
        fg_color=FTBTheme.ACCENT,
        hover_color=FTBTheme.ACCENT_HOVER,
        command=self._refresh_[TAB_NAME]
    )
    refresh_btn.pack(side=tk.RIGHT)
    
    # ... rest of tab content ...
```

#### Tabs Requiring Refresh Buttons:

**2.1 Roster Tab** (line ~18612)
```python
# File: plugins/ftb_game.py
# Method: _build_people_tab
# Existing refresh: _refresh_roster (line 18612)

# Add button to header section, around line 18550:
refresh_btn = ctk.CTkButton(
    self.tab_people,  # Or appropriate parent frame
    text="↻ Refresh Roster",
    width=120,
    command=self._refresh_roster
)
refresh_btn.pack(side=tk.TOP, anchor="e", padx=10, pady=5)

# Refresh method already exists and works correctly
```

**2.2 Car Equipped Parts Tab** (line ~20899)
```python
# File: plugins/ftb_game.py
# Method: _build_car_tab
# Existing refresh: _refresh_car_parts_visual (line 20899)

# Add to car tab header:
refresh_btn = ctk.CTkButton(
    header_frame,  # Top section of car tab
    text="↻ Refresh Parts",
    width=120,
    command=self._refresh_car_equipped_parts
)

# The refresh method may need to be enhanced:
def _refresh_car_equipped_parts(self):
    """Refresh equipped parts and recalculate car performance"""
    # Reload from state
    self._refresh_car_parts_visual()
    
    # Recalculate aggregate performance
    if self.sim_state and self.sim_state.player_team:
        team = self.sim_state.player_team
        # Trigger car rating recalculation
        if hasattr(team, 'recalculate_car_rating'):
            team.recalculate_car_rating()
    
    # Update display
    self._refresh_car_overview()
```

**2.3 Parts Marketplace Tab** (line ~21866)
```python
# File: plugins/ftb_game.py
# Method: _build_parts_marketplace_tab
# Existing refresh: _refresh_parts_marketplace (line 21866)

# Add button:
refresh_btn = ctk.CTkButton(
    market_header,
    text="↻ Refresh Market",
    width=120,
    command=self._refresh_parts_marketplace_enhanced
)

# Enhanced refresh with optional market volatility:
def _refresh_parts_marketplace_enhanced(self):
    """Refresh marketplace with optional price fluctuation"""
    if not self.sim_state:
        return
    
    # Reload existing market
    self._refresh_parts_marketplace()
    
    # Optional: Small chance of market event on manual refresh
    if random.random() < 0.1:  # 10% chance
        self._trigger_market_fluctuation_event()

def _trigger_market_fluctuation_event(self):
    """Random market event (price change, new parts available, etc.)"""
    event_types = [
        "price_drop",      # 10-20% discount on random part category
        "premium_arrival", # High-end part becomes available
        "clearance_sale",  # Multiple parts discounted
        "supply_shortage"  # Prices increase
    ]
    
    event = random.choice(event_types)
    
    # Implement market event logic
    # This adds dynamic economy feel to manual refreshes
```

**2.4 Infrastructure Tab** (line ~21689)
```python
# File: plugins/ftb_game.py
# Method: _build_infrastructure_tab
# Existing refresh: _refresh_infrastructure (line 21689)

refresh_btn = ctk.CTkButton(
    infra_header,
    text="↻ Refresh Infrastructure",
    width=150,
    command=self._refresh_infrastructure_enhanced
)

def _refresh_infrastructure_enhanced(self):
    """Refresh infrastructure with cost/efficiency recalc"""
    self._refresh_infrastructure()
    
    # Recalculate efficiency bonuses
    if self.sim_state and self.sim_state.player_team:
        team = self.sim_state.player_team
        # Update maintenance cost projections
        self._update_infrastructure_maintenance_display()
```

**2.5 Active Projects Tab** (line ~21514)
```python
# File: plugins/ftb_game.py
# Method: _build_development_tab
# Existing refresh: _refresh_development_projects (line 21514)

refresh_btn = ctk.CTkButton(
    projects_header,
    text="↻ Refresh Projects",
    width=130,
    command=self._refresh_development_projects_enhanced
)

def _refresh_development_projects_enhanced(self):
    """Refresh projects with progress sync"""
    self._refresh_development_projects()
    
    # Sync progress with current game day
    if self.sim_state:
        current_day = self.sim_state.sim_day_of_year
        
        for project in self.sim_state.active_projects:
            # Recalculate progress percentage
            if hasattr(project, 'start_day') and hasattr(project, 'duration_days'):
                elapsed = current_day - project.start_day
                progress_pct = min(100.0, (elapsed / project.duration_days) * 100)
                project.progress = progress_pct
        
        # Check for newly completed projects
        self._check_project_completion()
```

**2.6 Sponsors Tab** (line ~24778)
```python
# File: plugins/ftb_game.py  
# Method: _build_sponsors_tab
# Existing refresh: _refresh_sponsors (line 24778)

refresh_btn = ctk.CTkButton(
    sponsors_header,
    text="↻ Refresh Sponsors",
    width=130,
    command=self._refresh_sponsors_enhanced
)

def _refresh_sponsors_enhanced(self):
    """Refresh sponsor state with satisfaction recalc"""
    self._refresh_sponsors()
    
    # Recalculate sponsor satisfaction
    if self.sim_state and self.sim_state.player_team:
        team = self.sim_state.player_team
        
        for sponsor in getattr(team, 'sponsors', []):
            if hasattr(sponsor, 'recalculate_satisfaction'):
                sponsor.recalculate_satisfaction(
                    team_performance=getattr(team, 'championship_position', 10),
                    morale=team.standing_metrics.get('morale', 50.0),
                    reputation=team.standing_metrics.get('reputation', 50.0)
                )
    
    # Update payout projections
    self._update_sponsor_payout_display()
```

#### Standardized Refresh Method Pattern:

```python
# Template for adding new refresh functionality

def _refresh_[TAB_NAME](self):
    """Refresh [TAB NAME] - reload from DB, recompute derived values, update UI"""
    
    # Step 1: Guard clause
    if not self.sim_state:
        return
    
    # Step 2: Reload from authoritative source (SimState)
    # Access self.sim_state.[data_structure]
    
    # Step 3: Recompute derived values
    # Calculate aggregates, ratings, projections
    
    # Step 4: Update widgets
    # Clear old display
    # Rebuild UI elements with fresh data
    
    # Step 5: Optional feedback
    # Play subtle audio click
    # Flash button briefly
```

#### UX Consistency Guidelines:

1. **Button Placement:** Top-right of each tab header
2. **Button Style:**
   ```python
   width=100-150  # Based on text length
   height=28
   fg_color=FTBTheme.ACCENT
   hover_color=FTBTheme.ACCENT_HOVER
   ```
3. **Icon:** Use "↻" (U+21BB) consistently
4. **Feedback:** Optional subtle confirmation (audio or brief color change)
5. **Cooldown:** Optional 1-second cooldown to prevent spam

**Testing Checklist:**
- [ ] Each refresh button reloads latest data from SimState
- [ ] No UI lag or freezing during refresh
- [ ] Derived values (ratings, costs, projections) recalculate correctly
- [ ] Refresh works correctly when external changes occur (AI actions, tick progression)
- [ ] No duplicate entries or memory leaks from repeated refreshes
- [ ] Buttons are consistently positioned across all tabs
- [ ] Keyboard shortcut support (F5 refreshes current tab)

---

## 🟢 PHASE 2: Advanced Features (Week 4-6)

### 1. Driver Poaching & Compensation System

**Current Contract System:**
- ✅ `Contract` class exists (dataclass with base_salary, duration, exit_clauses)
- ✅ `calculate_contract_buyout()` function exists (line 2602)
- ✅ `apply_contract_buyout()` method exists in SimState (line 4180)
- ✅ Job Board system exists (`JobBoard` class at line 3215)
- ✅ Free agent system exists (`FreeAgent` class at line 3310)

**Missing:** Driver poaching from contracted drivers via Job Board.

#### Architecture Overview:

```
Job Board
├── Free Agents (current ✓)
│   ├── Drivers
│   ├── Engineers
│   ├── Mechanics
│   └── Strategists
│
└── Contracted Personnel (NEW)
    ├── Available for Poaching
    │   ├── Contract status: "Under Contract"
    │   ├── Buyout clause visible
    │   ├── Morale indicator
    │   └── "Open to Offers" flag
    │
    └── Protected
        ├── Recently signed (< 30 days)
        ├── Team financial distress flag
        └── Player opt-out
```

#### Step 1: Add Contract Status Fields

```python
# Location: Contract dataclass, around line 2550

@dataclass
class Contract:
    role: str
    team_name: str
    base_salary: int
    start_day: int
    duration_days: int
    exit_clauses: Optional[Dict[str, Any]] = None
    performance_bonuses: Optional[Dict[str, int]] = None
    
    # NEW FIELDS for poaching system:
    open_to_offers: bool = False          # Set by morale, team performance
    poaching_protection_until: int = 0     # Lock period after signing
    buyout_clause_fixed: Optional[int] = None  # Explicit buyout amount (overrides calculated)
    loyalty_factor: float = 1.0            # Affects buyout acceptance chance
    
    def is_poachable(self, current_day: int) -> bool:
        """Check if contract allows poaching attempts"""
        # Protected period still active
        if current_day < self.poaching_protection_until:
            return False
        
        # Contract nearly expired (< 14 days) - just wait it out
        if self.days_remaining(current_day) < 14:
            return False
        
        return True
    
    def calculate_buyout_amount(self, team_tier: int, current_day: int) -> int:
        """Calculate buyout amount for this contract"""
        # Use fixed clause if exists
        if self.buyout_clause_fixed:
            return self.buyout_clause_fixed
        
        # Otherwise use standard calculation
        return calculate_contract_buyout(self, team_tier, current_day)
```

#### Step 2: Add Morale-Driven "Open to Offers" System

```python
# Location: Add to SimState daily tick processing, around line 4500

def _update_contract_openness_flags(self):
    """Update whether contracted personnel are open to offers
    
    Driven by:
    - Low morale
    - Team underperformance  
    - Better opportunities available
    """
    for league in self.leagues:
        for team in league.teams:
            all_entities = (
                team.drivers + 
                team.engineers + 
                team.mechanics + 
                ([team.strategist] if team.strategist else [])
            )
            
            for entity in all_entities:
                if not entity or not hasattr(entity, 'contract'):
                    continue
                
                contract = entity.contract
                if not contract:
                    continue
                
                # Calculate "openness" score
                openness_factors = []
                
                # Factor 1: Personal morale
                if hasattr(entity, 'morale'):
                    morale = entity.morale
                    if morale < 40:
                        openness_factors.append(('low_morale', 0.7))
                    elif morale < 50:
                        openness_factors.append(('below_avg_morale', 0.4))
                
                # Factor 2: Team performance
                team_position = getattr(team, 'championship_position', 10)
                league_size = len(league.teams)
                
                if team_position > league_size * 0.75:
                    openness_factors.append(('backmarker_team', 0.5))
                
                # Factor 3: Financial instability
                if team.budget.current_cash < team.budget.minimum_operating_cash * 1.5:
                    openness_factors.append(('financial_distress', 0.6))
                
                # Factor 4: Underutilization (high skill, low tier)
                entity_rating = entity.overall_rating
                if entity_rating > 75 and team.tier <= 2:
                    openness_factors.append(('underutilized', 0.5))
                
                # Calculate aggregate openness
                if openness_factors:
                    openness_score = sum(weight for _, weight in openness_factors) / len(openness_factors)
                    contract.open_to_offers = openness_score > 0.4
                else:
                    contract.open_to_offers = False
```

#### Step 3: Enhance Job Board to Show Contracted Drivers

```python
# Location: Modify _refresh_job_board method, around line 18890

def _refresh_job_board(self):
    """Show both free agents AND poachable contracted drivers"""
    for widget in self.job_board_container.winfo_children():
        widget.destroy()
    
    if not self.sim_state:
        return
    
    # Section 1: Free Agents (existing functionality)
    free_agents_frame = ctk.CTkFrame(
        self.job_board_container,
        fg_color=FTBTheme.CARD,
        corner_radius=8
    )
    free_agents_frame.pack(fill=tk.X, pady=5)
    
    ctk.CTkLabel(
        free_agents_frame,
        text="🟢 Free Agents",
        font=("Arial", 13, "bold"),
        text_color=FTBTheme.SUCCESS
    ).pack(padx=10, pady=10, anchor="w")
    
    # ... existing free agent display code ...
    
    # Section 2: Under Contract - Open to Offers (NEW)
    poachable_frame = ctk.CTkFrame(
        self.job_board_container,
        fg_color=FTBTheme.CARD,
        corner_radius=8
    )
    poachable_frame.pack(fill=tk.X, pady=5)
    
    ctk.CTkLabel(
        poachable_frame,
        text="🟡 Under Contract - Open to Offers",
        font=("Arial", 13, "bold"),
        text_color=FTBTheme.WARNING
    ).pack(padx=10, pady=10, anchor="w")
    
    # Find all poachable contracted drivers
    poachable_drivers = []
    current_day = self.sim_state.sim_day_of_year
    
    for league in self.sim_state.leagues:
        for team in league.teams:
            # Don't show own team's drivers
            if team.name == self.sim_state.player_team.name:
                continue
            
            for driver in team.drivers:
                if not driver or not hasattr(driver, 'contract'):
                    continue
                
                contract = driver.contract
                if not contract:
                    continue
                
                # Check if poachable
                if contract.is_poachable(current_day) and contract.open_to_offers:
                    buyout = contract.calculate_buyout_amount(team.tier, current_day)
                    
                    poachable_drivers.append({
                        'entity': driver,
                        'team': team,
                        'contract': contract,
                        'buyout': buyout,
                        'morale': getattr(driver, 'morale', 50.0)
                    })
    
    # Display poachable drivers
    if not poachable_drivers:
        ctk.CTkLabel(
            poachable_frame,
            text="No drivers currently open to offers",
            font=("Arial", 10),
            text_color=FTBTheme.TEXT_MUTED
        ).pack(padx=15, pady=10)
    else:
        for item in poachable_drivers:
            self._display_poachable_driver_card(poachable_frame, item)

def _display_poachable_driver_card(self, parent, item):
    """Display a driver available for poaching"""
    driver = item['entity']
    team = item['team']
    contract = item['contract']
    buyout = item['buyout']
    morale = item['morale']
    
    card = ctk.CTkFrame(parent, fg_color=FTBTheme.SURFACE, corner_radius=6)
    card.pack(fill=tk.X, padx=15, pady=5)
    
    # Top row: Name, rating, current team
    header = ctk.CTkFrame(card, fg_color="transparent")
    header.pack(fill=tk.X, padx=10, pady=(10, 5))
    
    ctk.CTkLabel(
        header,
        text=f"{driver.name}",
        font=("Arial", 12, "bold"),
        text_color=FTBTheme.TEXT
    ).pack(side=tk.LEFT)
    
    ctk.CTkLabel(
        header,
        text=f"OVR {driver.overall_rating:.0f}",
        font=("Arial", 11),
        text_color=FTBTheme.ACCENT
    ).pack(side=tk.LEFT, padx=(10, 0))
    
    ctk.CTkLabel(
        header,
        text=f"({team.name})",
        font=("Arial", 10),
        text_color=FTBTheme.TEXT_MUTED
    ).pack(side=tk.LEFT, padx=(10, 0))
    
    # Middle row: Contract details
    details = ctk.CTkFrame(card, fg_color="transparent")
    details.pack(fill=tk.X, padx=10, pady=5)
    
    days_remaining = contract.days_remaining(self.sim_state.sim_day_of_year)
    
    ctk.CTkLabel(
        details,
        text=f"💼 Contract: {days_remaining} days | ${contract.base_salary:,}/yr",
        font=("Arial", 9),
        text_color=FTBTheme.TEXT
    ).pack(side=tk.LEFT)
    
    # Morale indicator
    morale_color = (FTBTheme.ERROR if morale < 40 else 
                    FTBTheme.WARNING if morale < 50 else 
                    FTBTheme.TEXT_MUTED)
    
    ctk.CTkLabel(
        details,
        text=f"😐 Morale: {morale:.0f}",
        font=("Arial", 9),
        text_color=morale_color
    ).pack(side=tk.LEFT, padx=(15, 0))
    
    # Bottom row: Buyout and action button
    actions = ctk.CTkFrame(card, fg_color="transparent")
    actions.pack(fill=tk.X, padx=10, pady=(5, 10))
    
    ctk.CTkLabel(
        actions,
        text=f"💰 Buyout: ${buyout:,}",
        font=("Arial", 11, "bold"),
        text_color=FTBTheme.WARNING
    ).pack(side=tk.LEFT)
    
    # Trigger buyout button
    trigger_btn = ctk.CTkButton(
        actions,
        text="Trigger Buyout",
        width=120,
        height=28,
        fg_color=FTBTheme.ACCENT,
        hover_color=FTBTheme.ACCENT_HOVER,
        command=lambda: self._attempt_driver_poach(driver, team, contract, buyout)
    )
    trigger_btn.pack(side=tk.RIGHT)
```

#### Step 4: Implement Poaching Transaction Logic

```python
# Location: Add new method in FTBWidget class, around line 19500

def _attempt_driver_poach(self, driver: Driver, original_team: Team, contract: Contract, buyout_amount: int):
    """Attempt to poach a driver from another team via buyout
    
    Process:
    1. Confirm player has sufficient funds (buyout + signing bonus)
    2. Execute buyout payment to original team
    3. Terminate old contract
    4. Negotiate new contract with player
    5. Add driver to player team
    6. Generate events and notifications
    """
    player_team = self.sim_state.player_team
    current_day = self.sim_state.sim_day_of_year
    
    # Step 1: Validation checks
    errors = []
    
    # Check roster space
    max_drivers = TIER_FEATURES.get(player_team.tier, {}).get('max_drivers', 2)
    current_drivers = len([d for d in player_team.drivers if d])
    
    if current_drivers >= max_drivers:
        errors.append(f"Roster full ({current_drivers}/{max_drivers} drivers)")
    
    # Check financial capacity
    # Cost = buyout + signing bonus + first month salary
    signing_bonus = contract.base_salary * 0.5  # 50% of annual salary
    first_month = contract.base_salary / 12
    total_cost = buyout_amount + signing_bonus + first_month
    
    if player_team.budget.current_cash < total_cost:
        errors.append(f"Insufficient funds (need ${total_cost:,}, have ${player_team.budget.current_cash:,})")
    
    # Check if budget would fall below safety threshold
    remaining = player_team.budget.current_cash - total_cost
    safety_threshold = player_team.budget.minimum_operating_cash * 2
    
    if remaining < safety_threshold:
        errors.append(f"Would leave budget below safety threshold (${remaining:,} < ${safety_threshold:,})")
    
    # Display errors if any
    if errors:
        messagebox.showerror(
            "Cannot Complete Buyout",
            "\n\n".join(["Transaction blocked:"] + errors)
        )
        return
    
    # Step 2: Confirmation dialog
    confirm_msg = f"""Trigger buyout clause for {driver.name}?

Current Team: {original_team.name}
Overall Rating: {driver.overall_rating:.0f}
Morale: {getattr(driver, 'morale', 50):.0f}

COSTS:
Buyout to {original_team.name}: ${buyout_amount:,}
Signing Bonus: ${signing_bonus:,}
First Month Salary: ${first_month:,}
TOTAL: ${total_cost:,}

Remaining Budget: ${remaining:,}

Proceed with buyout?"""
    
    if not messagebox.askyesno("Confirm Driver Poaching", confirm_msg):
        return
    
    # Step 3: Execute buyout transaction
    try:
        # Pay buyout to original team
        self.sim_state.apply_contract_buyout(original_team, contract, driver.name)
        
        # Deduct from player budget
        player_team.budget.current_cash -= (signing_bonus + first_month)
        
        # Log transactions
        player_team.budget.transactions.append({
            'day': current_day,
            'amount': -buyout_amount,
            'description': f"Contract buyout for {driver.name} (paid to {original_team.name})",
            'category': 'buyout'
        })
        
        player_team.budget.transactions.append({
            'day': current_day,
            'amount': -(signing_bonus + first_month),
            'description': f"Signing bonus + first month for {driver.name}",
            'category': 'salary'
        })
        
        # Step 4: Remove from original team
        if driver in original_team.drivers:
            idx = original_team.drivers.index(driver)
            original_team.drivers[idx] = None
        
        # Step 5: Create new contract for player team
        new_contract = Contract(
            role="Driver",
            team_name=player_team.name,
            base_salary=int(contract.base_salary * 1.2),  # 20% raise for poached drivers
            start_day=current_day,
            duration_days=365,  # 1 year default
            poaching_protection_until=current_day + 30,  # 30-day lock
            loyalty_factor=0.8  # Slightly more likely to leave again
        )
        
        driver.contract = new_contract
        
        # Step 6: Add to player team
        # Find first empty roster slot
        for i, existing_driver in enumerate(player_team.drivers):
            if existing_driver is None:
                player_team.drivers[i] = driver
                break
        else:
            # No empty slot found, add to list (shouldn't happen due to validation)
            player_team.drivers.append(driver)
        
        # Step 7: Generate events
        self.sim_state.event_history.append(SimEvent(
            event_type="transaction",
            category="driver_poached",
            ts=self.sim_state.tick,
            priority=85.0,
            severity="info",
            data={
                'driver': driver.name,
                'from_team': original_team.name,
                'to_team': player_team.name,
                'buyout_amount': buyout_amount,
                'new_salary': new_contract.base_salary,
                'total_cost': total_cost,
                'player_action': True
            }
        ))
        
        # Step 8: Morale impacts
        # Driver gets morale boost (new opportunity)
        if hasattr(driver, 'morale'):
            driver.morale = min(100.0, driver.morale + 15.0)
        
        # Original team morale hit
        for entity in (original_team.drivers + original_team.engineers + original_team.mechanics):
            if entity and hasattr(entity, 'morale'):
                entity.morale = max(0.0, entity.morale - 5.0)
        
        # Success message
        messagebox.showinfo(
            "Buyout Successful",
            f"{driver.name} has been signed!\n\nPaid ${total_cost:,} total.\nDriver morale boosted by new opportunity."
        )
        
        # Refresh UI
        self._refresh_roster()
        self._refresh_job_board()
        self._refresh_financial_overview()
        
    except Exception as e:
        messagebox.showerror("Transaction Failed", f"Error during buyout: {str(e)}")
        print(f"[FTB] Poaching error: {e}")
```

#### Step 5: AI Poaching Behavior

```python
# Location: Add to AI decision-making system, around line 11000-11500

def _ai_consider_driver_poaching(self, team: Team, league: League) -> Optional[Dict[str, Any]]:
    """AI teams occasionally attempt to poach high-performing drivers
    
    Factors:
    - Budget health (must have 3x buyout amount available)
    - Championship position (more likely if competitive)
    - Driver gap (current driver significantly worse than target)
    - Opportunity (target driver has low morale, available for poaching)
    """
    # Only consider poaching if budget is healthy
    if team.budget.current_cash < team.budget.minimum_operating_cash * 5:
        return None
    
    # Only mid-season or later (not in first 5 races)
    if self.races_completed_this_season < 5:
        return None
    
    # Find poachable drivers better than current drivers
    current_avg = sum(d.overall_rating for d in team.drivers if d) / max(len([d for d in team.drivers if d]), 1)
    
    targets = []
    current_day = self.sim_day_of_year
    
    for other_team in league.teams:
        if other_team.name == team.name:
            continue
        
        for driver in other_team.drivers:
            if not driver or not hasattr(driver, 'contract'):
                continue
            
            contract = driver.contract
            if not contract or not contract.is_poachable(current_day):
                continue
            
            if not contract.open_to_offers:
                continue
            
            # Must be significantly better
            if driver.overall_rating < current_avg + 10:
                continue
            
            buyout = contract.calculate_buyout_amount(other_team.tier, current_day)
            
            # Must be affordable (3x buffer)
            if buyout * 3 > team.budget.current_cash:
                continue
            
            targets.append({
                'driver': driver,
                'team': other_team,
                'contract': contract,
                'buyout': buyout,
                'rating_gap': driver.overall_rating - current_avg
            })
    
    if not targets:
        return None
    
    # Sort by rating gap (want biggest upgrade)
    targets.sort(key=lambda x: x['rating_gap'], reverse=True)
    
    # 20% base chance to attempt poaching
    # Increased if championship position is good
    team_position = getattr(team, 'championship_position', 10)
    if team_position <= 3:
        poach_chance = 0.35  # 35% for top teams
    elif team_position <= 5:
        poach_chance = 0.25
    else:
        poach_chance = 0.15
    
    if random.random() < poach_chance:
        return targets[0]  # Attempt to poach best target
    
    return None


def _ai_execute_driver_poaching(self, team: Team, poach_data: Dict[str, Any]) -> bool:
    """AI executes driver poaching transaction"""
    driver = poach_data['driver']
    original_team = poach_data['team']
    contract = poach_data['contract']
    buyout = poach_data['buyout']
    
    current_day = self.sim_day_of_year
    
    # Similar transaction logic as player poaching
    # ... (simplified version of player poaching logic) ...
    
    # Success depends on:
    # 1. Financial capacity (already checked)
    # 2. Driver willingness (based on morale, team reputation)
    
    driver_morale = getattr(driver, 'morale', 50.0)
    team_reputation = team.standing_metrics.get('reputation', 50.0)
    
    acceptance_chance = 0.5 + (team_reputation - 50.0) / 100.0
    
    if driver_morale < 30:
        acceptance_chance += 0.3  # Desperate to leave
    
    if random.random() < acceptance_chance:
        # Execute transaction (same as player logic)
        # ...
        
        # Log event
        self.event_history.append(SimEvent(
            event_type="transaction",
            category="ai_driver_poached",
            ts=self.tick,
            priority=75.0,
            severity="info",
            data={
                'driver': driver.name,
                'from_team': original_team.name,
                'to_team': team.name,
                'buyout_amount': buyout,
                'player_action': False
            }
        ))
        
        return True
    
    return False
```

**Testing Checklist:**
- [ ] Poachable drivers appear in Job Board with correct info
- [ ] Buyout amounts calculate correctly (fixed clause vs. dynamic)
- [ ] Transaction validation prevents overspending
- [ ] Driver successfully moves from original team to player team
- [ ] Original team receives buyout payment
- [ ] Morale impacts apply to all parties
- [ ] Recent signees (<30 days) are protected from poaching
- [ ] AI teams occasionally attempt poaching
- [ ] Contract expiry threshold prevents pointless buyouts (<14 days remaining)
- [ ] UI refreshes correctly after transaction

---

### 9. Narrator Tick Alignment & Priority Rebalancing

**Current State:**
- Narrator plugin exists: `/plugins/meta/ftb_narrator_plugin.py`
- ~80+ commentary types defined (line 99-170)
- Reads from `ftb_state_db.py` SQLite database

**Problem:** Narrator may surface stale events or low-priority content instead of most recent, relevant developments (especially race results).

**Verified Database Structure:**
```python
# From ftb_state_db.py, line ~100-200
# Tables exist:
# - game_state_snapshot (tick, phase, season, day_of_year)
# - race_results (race_id, season, player_positions, points)
# - events (tick_created, event_type, priority, severity, data)
```

#### Implementation:

**Step 1: Add Tick Tracking to Narrator**

```python
# Location: ftb_narrator_plugin.py, around line 200-300

class FTBNarratorPlugin(MetaPluginBase):
    def __init__(self):
        super().__init__()
        self.current_tick = 0  # NEW: Track current game tick
        self.last_processed_tick = 0  # NEW: Last tick we narrated
        self.race_result_priority_window = 5  # NEW: Ticks after race to prioritize race content
        self.last_race_tick = None  # NEW: When most recent race occurred
        # ... existing fields ...
    
    def initialize(self, runtime_context, cfg, mem):
        # ... existing init ...
        
        # Load current tick from DB
        self._sync_current_tick()
    
    def _sync_current_tick(self):
        """Read current tick from game state database"""
        if not self.db_path or not os.path.exists(self.db_path):
            return
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT tick, phase FROM game_state_snapshot WHERE id = 1")
            row = cursor.fetchone()
            
            if row:
                self.current_tick = row[0]
                self.current_phase = row[1]
            
            conn.close()
        except Exception as e:
            print(f"[FTB Narrator] Error syncing tick: {e}")
```

**Step 2: Implement Event Purging System**

```python
# Location: Add to ftb_narrator_plugin.py, around line 500

def _purge_stale_events(self):
    """Remove outdated events from candidate queue
    
    Rules:
    1. Remove events >10 ticks old (unless high priority)
    2. Remove superseded events (new race result replaces old one)
    3. Remove repeated commentary on same topic
    """
    if not hasattr(self, 'event_candidates'):
        self.event_candidates = []
    
    purged = []
    kept = []
    
    tick_threshold = self.current_tick - 10
    
    for candidate in self.event_candidates:
        tick_created = candidate.get('tick_created', 0)
        event_type = candidate.get('event_type', '')
        priority = candidate.get('priority', 50.0)
        
        # Rule 1: Age threshold
        if tick_created < tick_threshold and priority < 80.0:
            purged.append(('too_old', candidate))
            continue
        
        # Rule 2: Superseded race results
        if event_type == 'race_result':
            # Check if newer race result exists
            newer_race = any(
                c.get('event_type') == 'race_result' and 
                c.get('tick_created', 0) > tick_created
                for c in self.event_candidates
                if c != candidate
            )
            if newer_race:
                purged.append(('superseded', candidate))
                continue
        
        # Rule 3: Duplicate low-impact events
        if priority < 60.0:
            # Check for duplicates in recent narration history
            already_covered = self._was_recently_narrated(event_type, candidate.get('data', {}))
            if already_covered:
                purged.append(('duplicate', candidate))
                continue
        
        kept.append(candidate)
    
    self.event_candidates = kept
    
    # Debug logging
    if purged:
        print(f"[FTB Narrator] Purged {len(purged)} stale events:")
        for reason, event in purged[:5]:  # Show first 5
            print(f"  - {reason}: {event.get('event_type')} (tick {event.get('tick_created')})")


def _was_recently_narrated(self, event_type: str, event_data: Dict) -> bool:
    """Check if this topic was recently covered in narration"""
    if not hasattr(self, 'narration_history'):
        self.narration_history = []
    
    # Check last 10 narrations
    for past_narration in self.narration_history[-10:]:
        if past_narration.get('event_type') == event_type:
            # For some event types, check data similarity
            if event_type in ['morale_change', 'financial_update']:
                # Don't repeat unless significant change
                return True
    
    return False
```

**Step 3: Priority Reweighting with Recency Bias**

```python
# Location: Candidate scoring logic, around line 800-1000

def _calculate_candidate_priority(self, candidate: Dict) -> float:
    """Calculate final priority score with recency, impact, and relevance weights
    
    Formula:
    final_priority = base_priority × recency_multiplier × impact_weight × relevance_weight
    """
    base_priority = candidate.get('priority', 50.0)
    tick_created = candidate.get('tick_created', self.current_tick)
    event_type = candidate.get('event_type', '')
    data = candidate.get('data', {})
    
    # RECENCY MULTIPLIER (most important factor)
    tick_age = self.current_tick - tick_created
    
    if tick_age == 0:
        recency_multiplier = 2.0  # Just happened - double priority
    elif tick_age <= 2:
        recency_multiplier = 1.5  # Very recent
    elif tick_age <= 5:
        recency_multiplier = 1.2  # Recent
    elif tick_age <= 10:
        recency_multiplier = 1.0  # Normal
    else:
        recency_multiplier = 0.5  # Old news
    
    # IMPACT WEIGHT (event significance)
    impact_weight = 1.0
    
    if event_type == 'race_result':
        impact_weight = 3.0  # Race results are always headline news
    elif event_type == 'transaction':
        impact_weight = 2.0  # Signings/firings are big news
    elif event_type == 'financial_crisis':
        impact_weight = 2.5  # Financial crises matter
    elif event_type in ['morale_change', 'minor_update']:
        impact_weight = 0.7  # Routine updates are background noise
    
    # RELEVANCE WEIGHT (player team vs. world events)
    relevance_weight = 1.0
    
    is_player_team = (
        data.get('team') == self.player_team_name or
        data.get('team_name') == self.player_team_name or
        data.get('player_action', False)
    )
    
    if is_player_team:
        relevance_weight = 2.0  # Player events are twice as relevant
    else:
        # World events are relevant if affecting player's league/tier
        player_league = data.get('league', '')
        if player_league and player_league == self.player_league_name:
            relevance_weight = 1.3  # Same league is somewhat relevant
    
    # RACE RESULT DOMINANCE RULE
    if event_type == 'race_result' and is_player_team:
        # Recent race results for player team are ALWAYS top priority
        if tick_age <= 3:
            return 1000.0  # Override everything else
    
    # Calculate final score
    final_score = base_priority * recency_multiplier * impact_weight * relevance_weight
    
    return final_score
```

**Step 4: Race Result Dominance Rule**

```python
# Location: Narration candidate selection, around line 1200

def _select_next_narration_beat(self) -> Optional[Dict]:
    """Select next narration beat with race result dominance
    
    Race results get mandatory coverage before other content.
    """
    # Check if player's race just completed
    if self.last_race_tick and (self.current_tick - self.last_race_tick) <= 3:
        # We're in the "race result priority window"
        
        # Find all race result candidates
        race_candidates = [
            c for c in self.event_candidates
            if c.get('event_type') == 'race_result'
        ]
        
        # Filter to player team results
        player_race_candidates = [
            c for c in race_candidates
            if (c.get('data', {}).get('team') == self.player_team_name or
                c.get('data', {}).get('player_action', False))
        ]
        
        if player_race_candidates:
            # FORCE race coverage - this overrides everything else
            # Sort by most recent first
            player_race_candidates.sort(
                key=lambda c: c.get('tick_created', 0),
                reverse=True
            )
            
            selected = player_race_candidates[0]
            
            # Mark as covered
            self.event_candidates.remove(selected)
            
            print(f"[FTB Narrator] RACE DOMINANCE: Forcing race result coverage")
            return selected
    
    # Normal candidate selection (priority-based)
    if not self.event_candidates:
        return None
    
    # Score all candidates
    scored = [
        (self._calculate_candidate_priority(c), c)
        for c in self.event_candidates
    ]
    
    # Sort by score (descending)
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Select highest priority
    selected_score, selected_candidate = scored[0]
    
    # Remove from candidates
    self.event_candidates.remove(selected_candidate)
    
    print(f"[FTB Narrator] Selected: {selected_candidate.get('event_type')} (score: {selected_score:.1f})")
    
    return selected_candidate
```

**Step 5: Update Narrator on Race Completion**

```python
# Location: ftb_state_db.py write operations, around line 1400

def write_race_result(db_path: str, race_result_data: Dict) -> None:
    """Write race result to database AND trigger narrator priority update"""
    # ... existing write logic ...
    
    # NEW: Update narrator state
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get current tick
    cursor.execute("SELECT tick FROM game_state_snapshot WHERE id = 1")
    row = cursor.fetchone()
    current_tick = row[0] if row else 0
    
    # Insert high-priority event for narrator
    cursor.execute("""
        INSERT INTO narrator_priority_events (
            tick_created,
            event_type,
            priority,
            severity,
            data_json,
            covered
        ) VALUES (?, ?, ?, ?, ?, ?)
    """, (
        current_tick,
        'race_result',
        1000.0,  # Maximum priority
        'headline',
        json.dumps(race_result_data),
        False
    ))
    
    conn.commit()
    conn.close()
```

**Step 6: Add Database Table for Narrator Priority**

```python
# Location: ftb_state_db.py schema initialization, around line 100

def init_db(db_path: str):
    # ... existing tables ...
    
    # NEW: Narrator priority events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS narrator_priority_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tick_created INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            priority REAL NOT NULL,
            severity TEXT,
            data_json TEXT,
            covered INTEGER DEFAULT 0,  -- 0 = not covered, 1 = covered
            created_at REAL NOT NULL DEFAULT (julianday('now'))
        )
    """)
    
    # Index for efficient querying
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_narrator_uncovered 
        ON narrator_priority_events(covered, priority DESC, tick_created DESC)
    """)
```

**Testing & Validation:**

```python
# Add debug command to test narrator priority

def _debug_narrator_priority(self):
    """Show narrator's current candidate priority list"""
    print("\n" + "="*60)
    print("NARRATOR PRIORITY QUEUE")
    print("="*60)
    print(f"Current Tick: {self.current_tick}")
    print(f"Last Race Tick: {self.last_race_tick}")
    print(f"Candidates: {len(self.event_candidates)}")
    print()
    
    # Score and sort
    scored = [
        (self._calculate_candidate_priority(c), c)
        for c in self.event_candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    
    # Display top 10
    for i, (score, candidate) in enumerate(scored[:10], 1):
        event_type = candidate.get('event_type', 'unknown')
        tick_created = candidate.get('tick_created', 0)
        age = self.current_tick - tick_created
        team = candidate.get('data', {}).get('team', 'N/A')
        
        print(f"{i}. {event_type:20s} | Score: {score:6.1f} | Age: {age:2d} ticks | Team: {team}")
    
    print("="*60 + "\n")
```

**Testing Checklist:**
- [ ] Narrator tracks current tick correctly
- [ ] Race results appear with priority score >900
- [ ] Race results narrate before routine financial updates
- [ ] Events >10 ticks old are purged (unless high priority)
- [ ] Duplicate morale updates don't repeat
- [ ] Player team events score higher than world events
- [ ] Race result dominance window (3 ticks) forces race coverage
- [ ] Stale events don't accumulate indefinitely
- [ ] Narrator feels responsive to game state changes

---

## 📦 Implementation Tools & Utilities

### Global Refresh Method Factory

```python
# Location: Add to FTBWidget class as utility

def create_refresh_method(self, tab_name: str, data_loader_func, ui_builder_func):
    """Factory for creating standardized refresh methods
    
    Usage:
        self._refresh_sponsors = self.create_refresh_method(
            'sponsors',
            lambda: self.sim_state.player_team.sponsors,
            self._build_sponsors_display
        )
    """
    def refresh():
        if not self.sim_state:
            return
        
        try:
            # Load data
            data = data_loader_func()
            
            # Rebuild UI
            ui_builder_func(data)
            
            # Optional feedback
            self._flash_refresh_confirmation(tab_name)
            
        except Exception as e:
            print(f"[FTB] Refresh error ({tab_name}): {e}")
            messagebox.showerror(f"Refresh Failed", f"Could not refresh {tab_name}: {str(e)}")
    
    return refresh

def _flash_refresh_confirmation(self, tab_name: str):
    """Brief visual feedback on successful refresh"""
    # Could show brief toast notification or play audio click
    pass
```

### Testing Framework

```python
# Location: Create new file tests/test_ftb_upgrades.py

import unittest
from plugins.ftb_game import SimState, Driver, Team, Contract

class TestMoraleSystem(unittest.TestCase):
    def setUp(self):
        self.state = SimState()
        self.team = Team(name="Test Team", tier=1)
        self.driver = Driver(name="Test Driver", ...)
        self.driver.morale = 50.0
        self.driver.morale_baseline = 50.0
        self.driver.mettle = 60.0
        self.team.drivers = [self.driver]
    
    def test_mean_reversion_convergence(self):
        """Morale should converge to baseline over time"""
        self.driver.morale = 80.0  # Start high
        
        for _ in range(50):  # 50 ticks
            self.state._apply_morale_mean_reversion(self.team)
        
        # Should be close to baseline (50.0) after 50 ticks
        self.assertAlmostEqual(self.driver.morale, 50.0, delta=10.0)
    
    def test_diminishing_returns_high_morale(self):
        """High morale should resist further increases"""
        self.driver.morale = 85.0
        
        multiplier = calculate_morale_diminishing_returns(85.0, 10.0)
        
        # Should be significantly reduced
        self.assertLess(multiplier, 0.6)
    
    def test_no_runaway_drift(self):
        """Series of good results shouldn't push morale to 100"""
        # Simulate 10 great results
        for _ in range(10):
            self.driver.morale += 8.0 * calculate_morale_diminishing_returns(self.driver.morale, 8.0)
            self.state._apply_morale_mean_reversion(self.team)
        
        # Should plateau below 100
        self.assertLess(self.driver.morale, 95.0)


class TestContractExpiry(unittest.TestCase):
    def test_expiry_notifications_trigger(self):
        """Notifications should trigger at 30d, 14d, 7d"""
        state = SimState()
        team = Team(name="Test Team", tier=1)
        driver = Driver(name="Test Driver", ...)
        driver.contract = Contract(
            role="Driver",
            team_name=team.name,
            base_salary=100000,
            start_day=0,
            duration_days=30  # Will expire in 30 days
        )
        team.drivers = [driver]
        state.player_team = team
        state.sim_day_of_year = 0
        
        # Advance to 30 days remaining
        notifications_before = len(state.event_history)
        state._check_contract_expiry_notifications()
        notifications_after = len(state.event_history)
        
        self.assertEqual(notifications_after, notifications_before + 1)


class TestDriverPoaching(unittest.TestCase):
    def test_buyout_calculation(self):
        """Buyout should scale with contract value and tier"""
        contract = Contract(
            role="Driver",
            team_name="Test Team",
            base_salary=500000,
            start_day=0,
            duration_days=365
        )
        
        buyout_t1 = calculate_contract_buyout(contract, 1, 0)
        buyout_t5 = calculate_contract_buyout(contract, 5, 0)
        
        # Higher tier = higher buyout
        self.assertGreater(buyout_t5, buyout_t1)
    
    def test_poaching_protection(self):
        """Newly signed drivers should be protected"""
        contract = Contract(
            role="Driver",
            team_name="Test Team",
            base_salary=100000,
            start_day=0,
            duration_days=365,
            poaching_protection_until=30
        )
        
        # At day 15 - protected
        self.assertFalse(contract.is_poachable(15))
        
        # At day 35 - poachable
        self.assertTrue(contract.is_poachable(35))


if __name__ == '__main__':
    unittest.main()
```

---

## 📅 Implementation Timeline

### Week 1: Critical Fixes
- **Days 1-2:** Recent Race Results Bug Fix
- **Days 3-4:** Contract Expiry Dashboard Alerts
- **Day 5:** Testing & integration

### Week 2: Stability
- **Days 1-3:** Morale System Stabilization
  - Add baseline system
  - Implement mean reversion
  - Add diminishing returns
- **Days 4-5:** Testing & tuning

### Week 3: UX Improvements
- **Days 1-3:** UI Refresh Controls
  - Add buttons to 6 major tabs
  - Implement enhanced refresh methods
- **Days 4-5:** Sponsors tab refresh + polish

### Week 4-5: Advanced Features
- **Days 1-4:** Driver Poaching System
  - Contract status fields
  - Job Board enhancement
  - Transaction logic
- **Days 5-6:** AI poaching behavior
- **Day 7:** Testing

### Week 6: Narrator Enhancement
- **Days 1-3:** Narrator Tick Alignment
  - Add tick tracking
  - Implement purging
  - Priority reweighting
- **Days 4-5:** Race result dominance
- **Days 6-7:** Testing & tuning

---

## 🔍 Variables & Code Reference Quick Guide

### Core Classes & Locations

| Class/Function | File | Line Range | Purpose |
|----------------|------|------------|---------|
| `SimState` | ftb_game.py | 3350-4500 | Main simulation state |
| `Driver` | ftb_game.py | 1568-1700 | Driver entity |
| `Contract` | ftb_game.py | 2550-2650 | Contract dataclass |
| `JobBoard` | ftb_game.py | 3215-3310 | Job market system |
| `FTBWidget` | ftb_game.py | 17500-29841 | UI widget class |
| `FTBNarratorPlugin` | ftb_narrator_plugin.py | 1-3454 | Narrator system |
| `ftb_state_db` | ftb_state_db.py | 1-3921 | State database layer |

### Key Variable Names (Verified)

**SimState:**
- `self.tick` - Current game tick
- `self.sim_day_of_year` - Current day (1-365)
- `self.races_completed_this_season` - Race counter
- `self.event_history` - List of SimEvent objects
- `self.player_team` - Player's Team object

**Team:**
- `team.name` - Team name string
- `team.drivers` - List of Driver objects
- `team.budget.current_cash` - Current money
- `team.standing_metrics` - Dict with 'morale', 'reputation', etc.

**Driver:**
- `driver.morale` - Current morale (0-100)
- `driver.mettle` - Resilience stat (0-100)
- `driver.overall_rating` - Composite skill rating
- `driver.contract` - Contract object

**Contract:**
- `contract.base_salary` - Annual salary
- `contract.days_remaining(day)` - Method to check remaining days
- `contract.exit_clauses` - Dict with 'buyout_cost', etc.

**Events:**
- `SimEvent.event_type` or `SimEvent.category` - Event type string
- `SimEvent.data` - Dict with event-specific data
- `SimEvent.ts` or `SimEvent.tick` - When event occurred
- `SimEvent.priority` - Priority score (0-100)

---

## ⚠️ Risk Mitigation

### Data Integrity Risks

1. **Contract Poaching Edge Cases**
   - Risk: Driver ends up on multiple rosters
   - Mitigation: Atomic transaction pattern, validation before/after
   - Test: Concurrent poaching attempts

2. **Morale Overflow**
   - Risk: Morale goes <0 or >100
   - Mitigation: Clamp all morale changes with `max(0, min(100, value))`
   - Test: Extreme event sequences

3. **Event History Memory Leak**
   - Risk: event_history grows unbounded
   - Mitigation: Implement intelligent trimming (keep important events, trim old routine ones)
   - Test: Long gameplay sessions (1000+ ticks)

### Performance Risks

1. **Refresh Button Spam**
   - Risk: Rapid clicking causes UI lag
   - Mitigation: Add cooldown timer (1 second) or disable during refresh
   - Test: Rapid clicking stress test

2. **Narrator Database Queries**
   - Risk: Slow queries on large databases
   - Mitigation: Add indexes, limit query size
   - Test: Database with 10,000+ events

### User Experience Risks

1. **Morale Feels "Wrong"**
   - Risk: Players don't understand why morale changed
   - Mitigation: Detailed tooltips, event log entries explaining morale changes
   - Test: User feedback sessions

2. **Poaching Confusion**
   - Risk: Players don't understand buyout costs
   - Mitigation: Clear confirmation dialogs with cost breakdown
   - Test: New user onboarding

---

## 📊 Success Metrics

### Quantitative Goals

- **Bug Fix Success:**
  - Recent race results display 100% of completed races
  - Contract alerts appear 100% of the time when <30 days remaining
  
- **Morale Stability:**
  - No morale values below 5.0 or above 95.0 after 100+ ticks
  - Morale converges to baseline within 40 ticks with no events
  
- **Performance:**
  - All refresh operations complete in <500ms
  - Narrator candidate selection in <100ms
  - No UI freezes during poaching transactions

### Qualitative Goals

- Players feel informed about contract status
- Morale changes feel logical and predictable
- Race results feel like "headline news" in narration
- Poaching adds strategic depth without overwhelming complexity

---

## 📝 Notes & Assumptions

1. **Database Consistency:** Assumes `ftb_state_db.py` is the authoritative state source for narrator
2. **Event Structure:** Assumes `SimEvent` has either `.category` or `.event_type` attribute (verify both)
3. **UI Framework:** Assumes `customtkinter` is available and working
4. **Backward Compatibility:** All changes maintain backward compatibility with existing saves

---

## 🚀 Quick Start Checklist

**Before starting implementation:**
- [ ] Read this entire document
- [ ] Create feature branch: `git checkout -b ftb-upgrades-phase0`
- [ ] Back up current saves: copy `ftb_autosave.db` and `ftb_autosave.json`
- [ ] Run tests: ensure current codebase works
- [ ] Set up test environment with multiple completed races

**During implementation:**
- [ ] Make frequent commits with descriptive messages
- [ ] Test each feature independently before moving to next
- [ ] Document any deviations from plan
- [ ] Ask questions if variable names or structure don't match

**After each phase:**
- [ ] Run full test suite
- [ ] Play-test for 30+ minutes
- [ ] Check for memory leaks
- [ ] Update documentation if needed

---

**END OF IMPLEMENTATION PLAN**

*This document should be treated as a living spec. Update it as you discover implementation details or need to adjust approach.*
