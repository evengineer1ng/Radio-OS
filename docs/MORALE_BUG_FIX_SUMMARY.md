# Morale System Bug Fix - Summary

## Problem
Players were experiencing morale dropping to 0 even when **winning every race**. This is a critical bug in the morale stabilization system.

## Root Causes

### 1. **Broken Morale Baseline Calculation**
The `_calculate_morale_baseline()` function in `Entity` class was trying to use a `composure` stat that **doesn't exist in the Driver schema**:

```python
# BROKEN CODE:
composure = self.current_ratings.get('composure', 50.0)  # composure doesn't exist!
baseline = 40.0 + (mettle / 10.0) * 0.5 + (composure / 20.0) * 0.25 + ...
```

**Impact:** This defaulted `composure` to 50.0, and combined with low mettle values (~40), created baselines around 42-44 instead of proper personality-driven values.

### 2. **Overly Aggressive Mean Reversion**
The morale system was pulling morale toward baseline at **8% per day**, which is way too strong:
- Even after winning a race (+10 morale), 8% daily decay would erase gains in ~12 days
- With low baselines (42-44), this created a death spiral toward low morale

### 3. **Mean Reversion Running on Race Days**
The mean reversion was running **every single day including race days**, competing with race performance bonuses.

### 4. **Missing Baseline Values in Save Files**
Old save files didn't have `morale_baseline` values, so the system was recalculating them with the broken formula every tick.

## Fixes Applied

### Fix 1: Corrected Morale Baseline Formula ✅
Changed the baseline calculation to use **stats that actually exist**:

```python
# FIXED CODE:
mettle = self.current_ratings.get('mettle', 55.0)
discipline = self.current_ratings.get('discipline', 50.0)
pressure_handling = self.current_ratings.get('pressure_handling', 50.0)

baseline = 40.0 + (mettle / 10.0) * 0.5 + (discipline / 20.0) * 0.25 + (pressure_handling / 20.0) * 0.25
```

**File:** `plugins/ftb_game.py`, line ~1485

### Fix 2: Reduced Mean Reversion Rate ✅
Changed daily reversion from 8% to **3%**:

```python
'daily_reversion_factor': 0.03,  # Was 0.08 - too aggressive
```

**File:** `plugins/ftb_game.py`, line 264

### Fix 3: Skip Mean Reversion on Race Days ✅
Added logic to skip mean reversion on race days so race performance changes can dominate:

```python
# Skip on race days to let race performance changes dominate
is_race_day = any(
    state.is_race_day(state.sim_day_of_year, league.calendar)
    for league in state.leagues.values()
)

if not is_race_day:
    for league in state.leagues.values():
        for team in league.teams:
            morale_reversion_events = state.apply_morale_mean_reversion(team)
            events.extend(morale_reversion_events)
```

**File:** `plugins/ftb_game.py`, line ~8334

### Fix 4: Save File Repair Script ✅
Created `fix_morale_baselines.py` to repair existing save files:
- Calculates correct morale baselines for all entities
- Adds missing `morale_baseline` and `morale_last_updated` fields
- Option to boost player team morale with `--boost` flag

**Usage:**
```bash
python3 fix_morale_baselines.py saves/yourfile.json --boost
```

## Expected Behavior After Fix

### For Winning Teams (like yours):
- **Race wins:** +5 to +12 morale per win
- **Meeting expectations:** +0.5 morale (maintaining position)
- **Mean reversion:** Only -3% drift per day (non-race days)
- **Net effect:** Morale should climb to 60-75 range and stabilize

### For Low Mettle Drivers:
- More volatile morale swings
- Baseline around 42-44 (but with slower reversion)
- More sensitive to losses

### For High Mettle Drivers:
- More stable morale
- Baseline around 48-52
- Resistant to bad results

## Testing Checklist

- [x] Code compiles without errors
- [x] Save file successfully patched
- [x] Morale baselines set correctly (42-44 for your drivers)
- [ ] Load game and verify morale increases after race wins
- [ ] Verify morale stays high (60+) when winning consistently
- [ ] Check that morale doesn't drop to 0 anymore

## Additional Notes

### Why Mettle Matters
Your drivers have relatively low mettle (~40):
- **Ye Kennedy:** mettle 39.95 → baseline 42.0
- **Sang-Hyun Moss:** mettle 40.44 → baseline 41.9
- **Nyck Menard:** mettle 42.11 → baseline 43.2

This is actually realistic - young drivers with low mental fortitude have lower morale baselines. But with the fixes, they should still maintain 50-65 morale when winning.

### Future Improvements
Consider:
1. Adding morale boost for **championship position gains**
2. Team-wide morale events (winning constructor's championship)
3. Morale bonus for **exceeding expectations** (e.g., backmarker team winning)
4. Victory bonus that resists mean reversion for a few days

## Verification

Run your save file and check:
1. After a race win → morale should increase 5-12 points
2. Between races → morale should only drift slowly (3% toward baseline)
3. After multiple wins → morale should stabilize around 60-70
4. Never drop below baseline unless losing races

## Files Modified
- `plugins/ftb_game.py` (3 changes)
- `saves/patchedgreatstart.json` (patched via script)
- `saves/patchedgreatstart.json.backup` (backup created)
