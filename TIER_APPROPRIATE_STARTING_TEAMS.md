# Tier-Appropriate Starting Teams — Implementation Fix

## Issue
Previously, when starting a new game in any tier (Grassroots, Formula V, Formula X, Formula Y, or Formula Z), the player would always take over the first team in `grassroots_1` league, regardless of the `tier` parameter passed to `start_new_game()`.

This meant:
- Starting in Formula Z would give you a grassroots-level team with:
  - Budget: ~$40k-$130k (instead of $80M-$250M)
  - 2 Drivers with stats ~32 (instead of ~80)
  - 1 Mechanic (instead of 6)
  - 0 Engineers (instead of 5)
  - Stats mean of 32 (instead of 80)

## Fix
Modified `/plugins/ftb_game.py` in the `create_new_save()` method (around line 13127) to:

1. **Map tier parameter to league ID**:
   ```python
   tier_map = {
       'grassroots': 'grassroots',
       'formula_v': 'formula_v',
       'formula_x': 'formula_x',
       'formula_y': 'formula_y',
       'formula_z': 'formula_z',
   }
   tier_name_str = tier_map.get(tier.lower(), 'grassroots')
   target_league_id = f'{tier_name_str}_1'
   ```

2. **Log the tier selection**:
   ```python
   print(f"[FTB] Player starting in tier: {tier} → league: {target_league_id}")
   ```

3. **Fixed null check** for sponsor initialization (line ~13239):
   ```python
   if state.player_team and state.player_team.name not in state.sponsorships:
   ```

## Results

### Starting in Grassroots (Tier 1)
- Budget: $40k-$130k
- 2 Drivers (stats ~32)
- 1 Mechanic (stats ~32)
- 0 Engineers
- 1 Strategist (stats ~32)
- Principal (stats ~37)
- Salary multiplier: 0.4x

### Starting in Formula V (Tier 2)
- Budget: $400k-$800k
- 2 Drivers (stats ~44)
- 2 Mechanics (stats ~44)
- 1 Engineer (stats ~44)
- 1 Strategist (stats ~44)
- Principal (stats ~49)
- Salary multiplier: 1.5x

### Starting in Formula X (Tier 3)
- Budget: $2M-$5M
- 2 Drivers (stats ~56)
- 3 Mechanics (stats ~56)
- 2 Engineers (stats ~56)
- 1 Strategist (stats ~56)
- Principal (stats ~61)
- Salary multiplier: 4.0x

### Starting in Formula Y (Tier 4)
- Budget: $10M-$25M
- 2 Drivers (stats ~68)
- 4 Mechanics (stats ~68)
- 3 Engineers (stats ~68)
- 1 Strategist (stats ~68)
- Principal (stats ~73)
- Salary multiplier: 12.0x

### Starting in Formula Z (Tier 5)
- Budget: $80M-$250M
- 2 Drivers (stats ~80)
- 6 Mechanics (stats ~80)
- 5 Engineers (stats ~80)
- 1 Strategist (stats ~80)
- Principal (stats ~85)
- Salary multiplier: 60.0x

## Configuration

The tier configurations are defined in `WorldBuilder.TIER_CONFIG` and `WorldBuilder.TIER_ENVELOPES`:

### Budget Ranges by Tier
```python
TIER_CONFIG = {
    'grassroots': {'budget_range': (40000.0, 130000.0)},      # $40k-$130k
    'formula_v': {'budget_range': (400000.0, 800000.0)},      # $400k-$800k
    'formula_x': {'budget_range': (2000000.0, 5000000.0)},    # $2M-$5M
    'formula_y': {'budget_range': (10000000.0, 25000000.0)},  # $10M-$25M
    'formula_z': {'budget_range': (80000000.0, 250000000.0)}, # $80M-$250M
}
```

### Staff Counts by Tier
```python
TIER_ENVELOPES = {
    'grassroots': {'mechanics_count': 1, 'engineers_count': 0},
    'formula_v': {'mechanics_count': 2, 'engineers_count': 1},
    'formula_x': {'mechanics_count': 3, 'engineers_count': 2},
    'formula_y': {'mechanics_count': 4, 'engineers_count': 3},
    'formula_z': {'mechanics_count': 6, 'engineers_count': 5},
}
```

### Stat Means by Tier
```python
TIER_ENVELOPES = {
    'grassroots': {'stat_mean': 32},  # Low-skill young drivers
    'formula_v': {'stat_mean': 44},   # Developing talent
    'formula_x': {'stat_mean': 56},   # Experienced racers
    'formula_y': {'stat_mean': 68},   # Elite prospects
    'formula_z': {'stat_mean': 80},   # World-class professionals
}
```

## Testing

To test the fix:

1. **Start a new game in Formula Z**:
   - From setup wizard, select "Formula Z" tier
   - Check player team budget shows $80M-$250M
   - Verify you have 6 mechanics, 5 engineers
   - Check driver stats are in the 73-87 range (mean 80 ± stddev 7)

2. **Start a new game in Grassroots**:
   - Select "Grassroots" tier
   - Check budget is $40k-$130k
   - Verify you have 1 mechanic, 0 engineers
   - Check driver stats are in the 24-40 range (mean 32 ± stddev 8)

3. **Console output**:
   - Look for log line: `[FTB] Player starting in tier: formula_z → league: formula_z_1`
   - Verify league assignment matches tier selected

## Related Systems

### Origin Story Modifiers
Origin stories still apply their modifiers **after** tier-based team assignment, so:
- **Game Show Winner**: +$50k cash bonus
- **Grassroots Hustler**: No cash bonus, increased media standing
- **Former Driver**: Budget penalties, reputation bonus
- **Corporate Spinout**: Massive budget boost
- **Engineering Savant**: Tech focus advantages

These modifiers scale with tier, so a Formula Z "Corporate Spinout" might get a +$50M bonus while a Grassroots "Corporate Spinout" gets +$200k.

### Feature Gates
Tier features still apply based on `team.tier`:
- **Grassroots**: Max 2 drivers, 1 engineer, no strategist unlocked initially
- **Formula V+**: Full roster unlocked
- **Formula X+**: Advanced development options
- **Formula Y+**: Elite facilities
- **Formula Z**: All features unlocked

### Promotion/Relegation
Starting in a higher tier means:
- You can be relegated if you finish poorly
- You can apply for promotion to higher tiers (if in Tier 2-4)
- Championship prizes are tier-appropriate (Formula Z P1 = $15M vs Grassroots P1 = $150k)

## Code Changes Summary

**File**: `/Users/even/Documents/Radio-OS-1.03/plugins/ftb_game.py`

**Lines Modified**:
- Line ~13127: Changed hardcoded `'grassroots_1'` to dynamic `target_league_id`
- Line ~13120-13132: Added tier mapping logic
- Line ~13239: Added null check for `state.player_team`

**Impact**: 
- ✅ Players now start with tier-appropriate teams
- ✅ No gameplay balance changes (teams were always generated correctly, just not assigned correctly)
- ✅ No breaking changes to existing saves
- ✅ No UI changes required

**Testing Status**: 
- ✅ No syntax errors
- ⏳ Requires runtime testing with different tier selections

---

**Related Documentation**:
- See `FTB_DATA_EXPLORER.md` for new data exploration features
- See `PROMOTION_RELEGATION_SYSTEM.md` for tier movement mechanics
- See `SEASON_ROLLOVER_AND_PAYOUTS.md` for championship rewards by tier

**Date**: February 13, 2026
