# Phase 3: Testing & Polish Checklist

## Testing Date
February 13, 2026

## Overview
Comprehensive testing of all Phase 0, Phase 1, and Phase 2 features implemented in the FTB upgrades project.

---

## Phase 0: Critical Bug Fixes

### ✅ 0.1: Recent Race Results Display
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Load game after completing a race
- [ ] Verify race results appear in Dashboard > Recent Results section
- [ ] Check that race_id grouping works correctly
- [ ] Verify multiple races display properly
- [ ] Confirm no duplicate entries

**Expected Behavior:**
- Race results show: position, driver name, team, points, race name
- Grouped by race_id
- Shows last 5 races
- No filtering errors in logs

**Test Command:**
```bash
# Check for race result events in database
sqlite3 stations/*/ftb_state.db "SELECT * FROM events_buffer WHERE category='race_result' ORDER BY tick DESC LIMIT 5;"
```

---

### ✅ 0.2: Contract Expiry Dashboard Alerts
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Load game with contracts expiring in <7 days
- [ ] Verify red "Critical" alerts appear in Dashboard
- [ ] Load game with contracts expiring in 7-14 days
- [ ] Verify yellow "Upcoming" alerts appear
- [ ] Load game with contracts expiring in 14-30 days
- [ ] Verify blue "Notice" alerts appear
- [ ] Confirm alerts update as days pass

**Expected Behavior:**
- Widget shows categorized contract alerts:
  - **Critical (Red):** <7 days remaining
  - **Upcoming (Yellow):** 7-14 days remaining
  - **Notice (Blue):** 14-30 days remaining
- Each alert shows: entity name, role, days remaining, salary
- Sorted by urgency (critical first)

**Test Command:**
```bash
# Check contract expiry dates in save file
python3 -c "import json; data=json.load(open('ftb_autosave.json')); print('Contracts:', [(c['entity_name'], c['role'], c['end_day']) for t in data.get('teams', []) for c in t.get('active_contracts', [])])"
```

---

## Phase 1: Morale System Stabilization

### ✅ 1.1: Morale Baseline System
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Create new game, verify all entities have morale_baseline field
- [ ] Check that baselines are personality-driven (50-80 range)
- [ ] Advance 50 ticks, verify morale trends toward baseline
- [ ] Manually set entity morale to 90, verify it drifts down toward baseline
- [ ] Manually set entity morale to 20, verify it drifts up toward baseline

**Expected Behavior:**
- All entities have `morale_baseline` field (50-80)
- Morale drifts 8% toward baseline daily (if difference >20)
- No runaway morale (should stabilize around baseline ±10)
- `morale_last_updated` field tracks last update day

**Test Command:**
```bash
# Check entity morale baselines
python3 -c "import json; data=json.load(open('ftb_autosave.json')); entities=[e for t in data.get('teams', []) for e in t.get('roster', [])]; print('Morale baselines:', [(e['name'], e.get('morale', 50), e.get('morale_baseline', 'MISSING')) for e in entities[:5]])"
```

**Code Location:**
- `plugins/ftb_game.py` lines 1431-1470: Entity class baseline field
- `plugins/ftb_game.py` line 4292: `apply_morale_mean_reversion()` method
- `plugins/ftb_game.py` line 8013: Daily tick integration

---

### ✅ 1.2: Morale Diminishing Returns
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Complete race with very high morale (90+)
- [ ] Verify morale gain is reduced (diminishing returns)
- [ ] Complete race with very low morale (20-)
- [ ] Verify morale loss is reduced (floor protection)
- [ ] Complete race with mid-range morale (40-60)
- [ ] Verify morale changes are normal

**Expected Behavior:**
- High morale (>80): gains reduced by up to 70%
- Low morale (<30): losses reduced by up to 60%
- Mid morale (40-60): normal changes (no reduction)
- Formula: `reduction = 0.7 × ((morale - 40) / 50)²` for gains
- Formula: `reduction = 0.6 × ((40 - morale) / 30)²` for losses

**Test Command:**
```bash
# Run simulation and watch morale changes
grep -E "morale.*diminishing|Applying diminishing" stations/*/runtime.log | tail -20
```

**Code Location:**
- `plugins/ftb_game.py` line 8452: `calculate_morale_diminishing_returns()` method
- `plugins/ftb_game.py` lines 8540-8625: Applied to race performance morale

---

### ✅ 1.3: UI Refresh Controls
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Open Roster tab, click "↻ Refresh" button
- [ ] Verify roster list updates without full UI rebuild
- [ ] Open Car tab, click "↻ Refresh" button
- [ ] Verify car overview and parts list update
- [ ] Open Development tab, click "↻ Refresh Projects" button
- [ ] Verify project list updates
- [ ] Open Infrastructure tab, click "↻ Refresh" button
- [ ] Verify infrastructure items update
- [ ] Open Sponsors tab, click "↻ Refresh" button
- [ ] Verify sponsor list updates
- [ ] Verify refresh buttons have ↻ icon and proper tooltip

**Expected Behavior:**
- Refresh buttons appear in all 5 tabs
- Clicking refresh updates that tab's content only
- No full UI rebuild (faster than switching tabs)
- Tooltip shows "Refresh [tab name]"

**Code Locations:**
- Line 18747: Roster tab refresh
- Line 20842: Car tab refresh
- Line 21761: Development tab refresh
- Line 21789: Infrastructure tab refresh
- Line 24477: Sponsors tab refresh

---

## Phase 2: Driver Poaching System

### ✅ 2.1: Contract Enhancements
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Create new contract, verify has `open_to_offers=False`
- [ ] Verify has `poaching_protection_until` field (30 days)
- [ ] Verify has `buyout_clause_fixed=None` field
- [ ] Verify has `loyalty_factor=1.0` field
- [ ] Check `is_poachable()` method returns False during protection period
- [ ] Check `calculate_buyout_amount()` returns tier-based amount

**Expected Behavior:**
- All new contracts have 4 new fields
- Protection period prevents poaching for 30 days
- Buyout calculation: `remaining_value × tier_multiplier`
- Tier multipliers: T1=10%, T2=20%, T3=30%, T4=45%, T5=60%

**Test Command:**
```bash
# Check contract structure
python3 -c "import json; data=json.load(open('ftb_autosave.json')); contracts=[c for t in data.get('teams', []) for c in t.get('active_contracts', [])]; print('Contract fields:', contracts[0].keys() if contracts else 'No contracts')"
```

**Code Location:**
- `plugins/ftb_game.py` lines 2078-2167: Contract class

---

### ✅ 2.2: Daily Contract Openness Tracking
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Set driver morale to 30, advance 1 day
- [ ] Verify contract opens to offers (morale factor 0.9)
- [ ] Set team to bottom 25% performance, advance 1 day
- [ ] Verify contract opens (performance factor 0.5)
- [ ] Set team budget to 1.5× bankruptcy threshold
- [ ] Verify contract opens (financial factor 0.7)
- [ ] Put 80-rated driver on T1 team (underutilized)
- [ ] Verify contract opens (underutilization factor 0.6)

**Expected Behavior:**
- Daily evaluation of all contracts
- 4 factors checked: morale, performance, financial, underutilization
- Opens to offers when average factor >0.4
- Logs: "Contract openness: [name] -> open_to_offers=[bool]"

**Test Command:**
```bash
# Check for contract openness evaluation
grep "Contract openness:" stations/*/runtime.log | tail -10
```

**Code Location:**
- `plugins/ftb_game.py` lines 4410-4507: `update_contract_openness_flags()` method
- `plugins/ftb_game.py` line 8016: Daily tick integration

---

### ✅ 2.3: Poachable Drivers UI
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Open Job Market tab
- [ ] Click "Poachable Drivers" sub-tab
- [ ] Verify list shows drivers with `open_to_offers=True`
- [ ] Verify shows: name, rating, age, nationality, current team
- [ ] Verify shows: stats (speed, racecraft, consistency, wet)
- [ ] Verify shows: contract (days remaining, salary)
- [ ] Verify shows: morale with emoji and color
- [ ] Verify shows: buyout amount
- [ ] Verify "Attempt Poach" button appears if affordable
- [ ] Verify button disabled if can't afford

**Expected Behavior:**
- Rich driver cards with all relevant info
- Morale emoji: 😠 (<35), 😟 (35-50), 😐 (50-65), 🙂 (65+)
- Buyout calculation shown
- Button state reflects affordability
- Empty state message if no poachable drivers

**Test Command:**
```bash
# Create test scenario with low morale driver
python3 -c "
import json
data = json.load(open('ftb_autosave.json'))
for team in data.get('teams', []):
    if team['name'] != data.get('player_team'):
        for entity in team.get('roster', [])[:1]:
            entity['morale'] = 30  # Force low morale
            print(f'Set {entity[\"name\"]} morale to 30')
json.dump(data, open('ftb_autosave.json', 'w'))
"
```

**Code Locations:**
- Line 18931: Poachable Drivers tab
- Lines 19308-19396: `_refresh_poachable_drivers()` method
- Lines 20520-20658: `_display_poachable_driver_card()` method

---

### ✅ 2.4: Player Poaching Transaction
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Click "Attempt Poach" on affordable driver
- [ ] Verify validation checks roster space
- [ ] Verify validation checks financial capacity
- [ ] Verify confirmation dialog shows full breakdown:
  - Buyout amount to original team
  - Signing bonus to driver
  - Adjusted salary (25% raise)
  - Total cost
- [ ] Click "Confirm Poach"
- [ ] Verify driver removed from original team
- [ ] Verify driver added to player roster
- [ ] Verify budget deducted correctly
- [ ] Verify original team receives buyout payment
- [ ] Verify new contract created (2 seasons, 30-day protection)
- [ ] Verify morale reset to 60
- [ ] Verify high-priority event generated (85.0)

**Expected Behavior:**
- Multi-step validation before confirmation
- Clear cost breakdown in dialog
- Atomic transaction (all-or-nothing)
- Auto-refresh Job Market and Roster tabs
- Success dialog confirms transaction

**Test Command:**
```bash
# Watch for poaching events
grep "ftb_poach_driver" stations/*/runtime.log | tail -5
```

**Code Locations:**
- Lines 20173-20497: `_attempt_driver_poach()` UI flow
- Lines 29989-30084: "ftb_poach_driver" backend handler

---

### ✅ 2.5: AI Team Poaching
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Advance simulation 30 days (monthly cycle)
- [ ] Check logs for AI poaching attempts
- [ ] Verify tier-based aggression rates:
  - T1 teams: ~5% monthly
  - T2 teams: ~10% monthly
  - T3 teams: ~15% monthly
  - T4 teams: ~25% monthly
  - T5 teams: ~35% monthly
- [ ] Verify AI teams target drivers with `open_to_offers=True`
- [ ] Verify AI teams can't poach from player team
- [ ] Verify AI teams need 50% budget buffer
- [ ] Verify successful poach creates new contract (25% raise, 2 seasons)
- [ ] Verify poached driver gets 30-day protection

**Expected Behavior:**
- Monthly execution (every 30 days)
- Aggressive tier targeting (low tiers more desperate)
- 2× chance if understaffed (drivers 10+ rating below average)
- Decision formula: `(rating/100) × (1.0 - cost_ratio)`
- Upgrade targets get 1.5× boost
- Logs show: "AI Poaching: [team] poached [driver] from [original_team]"

**Test Command:**
```bash
# Check for AI poaching activity
grep "AI Poaching:" stations/*/runtime.log | tail -10
grep "process_ai_poaching_attempts" stations/*/runtime.log | tail -5
```

**Code Location:**
- `plugins/ftb_game.py` lines 4509-4699: `process_ai_poaching_attempts()` method
- `plugins/ftb_game.py` line 8017: Monthly tick integration

---

### ✅ 2.6: Narrator Tick Alignment
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Start narrator, verify tick syncs with game state
- [ ] Check logs for "Tick sync:" messages
- [ ] Advance simulation 15 ticks without narrator
- [ ] Start narrator, verify events >10 ticks purged
- [ ] Complete a race, verify narrator coverage within 3 ticks
- [ ] Check for "RACE RESULT DOMINANCE" log message
- [ ] Verify race-focused commentary types used:
  - POST_RACE_COOLDOWN
  - RACE_ATMOSPHERE
  - DRIVER_SPOTLIGHT
  - DRIVER_TRAJECTORY
  - RECAP
  - MOMENTUM_CHECK
- [ ] Check event freshness markers (🔥⚡) in logs
- [ ] Verify recent events appear first in commentary

**Expected Behavior:**
- Narrator tick = game simulation tick
- Events >10 ticks old automatically purged
- Recency multipliers: 2.0x (this tick), 1.5x (≤2), 1.2x (≤5), 1.0x (≤10)
- Race results ≤3 ticks force race-focused segments
- Freshness markers visible in logs

**Test Command:**
```bash
# Check narrator tick alignment
grep -E "Tick sync:|RACE RESULT DOMINANCE:|Purged.*events" stations/*/runtime.log | tail -20

# Check for freshness markers
grep -E "🔥|⚡" stations/*/runtime.log | tail -10
```

**Code Locations:**
- `plugins/meta/ftb_narrator_plugin.py` line ~1383: `_sync_current_tick()` method
- `plugins/meta/ftb_narrator_plugin.py` line ~1435: `_purge_old_events()` method
- `plugins/meta/ftb_narrator_plugin.py` line ~1524: Race result dominance
- `plugins/meta/ftb_narrator_plugin.py` line ~2810: Recency multipliers

---

## Performance Testing

### 🔍 Tick Processing Time
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Measure baseline tick time (before upgrades)
- [ ] Measure current tick time (after upgrades)
- [ ] Verify morale reversion adds <5ms per tick
- [ ] Verify contract openness adds <10ms per tick
- [ ] Verify AI poaching adds <50ms per monthly cycle

**Expected Performance:**
- Morale reversion: O(n) where n = entities (~50-200)
- Contract openness: O(n) where n = active contracts (~50-200)
- AI poaching: O(n²) worst case, but monthly (acceptable)
- Total overhead: <20ms per daily tick

**Test Command:**
```bash
# Profile tick execution
grep -E "Daily tick|Tick.*ms" stations/*/runtime.log | tail -20
```

---

### 🔍 Database Query Performance
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Check database file size
- [ ] Verify events_buffer doesn't grow unbounded
- [ ] Check query times for narrator event polling
- [ ] Verify purging keeps table size reasonable

**Expected Performance:**
- events_buffer: <10,000 rows (purging keeps it clean)
- Query time: <10ms per query
- Database size: <50MB for long-running games

**Test Command:**
```bash
# Check database stats
ls -lh stations/*/ftb_state.db
sqlite3 stations/*/ftb_state.db "SELECT COUNT(*) FROM events_buffer;"
sqlite3 stations/*/ftb_state.db "SELECT COUNT(*) FROM events_buffer WHERE emitted_to_narrator=0;"
```

---

## Integration Testing

### 🔗 Cross-Feature Interactions
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Low morale triggers contract openness → AI poaching → narrator coverage
- [ ] Race result generates event → morale change → diminishing returns → narrator priority
- [ ] Poaching transaction → morale reset → baseline drift → UI refresh
- [ ] Contract expiry alert → player action → refresh button → updated state

**Expected Behavior:**
- All systems work together harmoniously
- No race conditions or conflicting updates
- Event flow: game → database → narrator → audio
- UI updates reflect backend state changes

---

## Edge Cases & Error Handling

### ⚠️ Boundary Conditions
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Empty roster (no drivers)
- [ ] No contracts (free agents only)
- [ ] Zero budget (bankruptcy)
- [ ] Morale at 0 or 100 (extremes)
- [ ] Contract with 0 days remaining
- [ ] Poaching with insufficient funds
- [ ] Batch advance >100 days
- [ ] Narrator with no events

**Expected Behavior:**
- No crashes or exceptions
- Graceful degradation
- Helpful error messages
- State remains consistent

---

## Backward Compatibility

### 🔄 Save Game Migration
**Status:** 🟡 Needs Testing

**Test Cases:**
- [ ] Load old save (pre-upgrade)
- [ ] Verify morale_baseline added to all entities
- [ ] Verify contract fields added to all contracts
- [ ] Verify no data loss
- [ ] Verify game continues normally
- [ ] Save and reload, verify persistence

**Expected Behavior:**
- Line 5573: Backward compatibility migration
- All old saves work without errors
- New fields populated with sensible defaults
- No breaking changes

**Code Location:**
- `plugins/ftb_game.py` line 5573: Migration logic

---

## Documentation & Polish

### 📚 Documentation
**Status:** 🟡 Needs Review

**Deliverables:**
- [ ] FTB_UPGRADES_IMPLEMENTATION_PLAN.md (complete)
- [ ] PHASE1_EXECUTION_SUMMARY.md (complete)
- [ ] PHASE2_EXECUTION_SUMMARY.md (complete)
- [ ] NARRATOR_TICK_ALIGNMENT_IMPLEMENTATION.md (complete)
- [ ] PHASE3_TESTING_CHECKLIST.md (this file)
- [ ] Update README.md with new features
- [ ] Add user guide section for poaching system

---

### 🎨 UI Polish
**Status:** 🟡 Needs Review

**Items:**
- [ ] Verify all refresh buttons have tooltips
- [ ] Check button alignment and spacing
- [ ] Verify morale emoji rendering correctly
- [ ] Check dialog sizing (confirmation dialogs)
- [ ] Verify empty states have helpful messages
- [ ] Check color coding consistency (alerts, morale)

---

## Test Execution Plan

### Day 1: Core Systems
1. Create fresh test save
2. Test morale baseline and reversion (50 ticks)
3. Test diminishing returns (10 races)
4. Test UI refresh buttons (all 6 tabs)
5. Document results

### Day 2: Driver Poaching
1. Force low morale on test drivers
2. Verify contract openness triggers
3. Test player poaching flow (3 drivers)
4. Advance 90 days, observe AI poaching
5. Document results

### Day 3: Narrator & Integration
1. Complete races, verify narrator coverage
2. Test tick alignment and event purging
3. Test recency multipliers
4. Run 200-tick integration test
5. Document results

### Day 4: Performance & Edge Cases
1. Profile tick execution times
2. Test edge cases and boundaries
3. Load old saves, verify migration
4. Stress test (1000+ ticks)
5. Document results

### Day 5: Polish & Documentation
1. Review all documentation
2. Update user guides
3. Create release notes
4. Final validation pass
5. Prepare for release

---

## Success Criteria

### Must Pass
- ✅ No crashes or exceptions during normal gameplay
- ✅ All features work as specified in implementation plan
- ✅ Backward compatibility maintained
- ✅ Performance overhead <10% per tick
- ✅ UI responsive and intuitive

### Should Pass
- 🎯 Narrator coverage feels natural and timely
- 🎯 Morale system prevents runaway drift
- 🎯 Driver poaching creates interesting dynamics
- 🎯 UI refresh buttons improve UX noticeably
- 🎯 Contract alerts help player planning

### Nice to Have
- ⭐ Zero bugs found during testing
- ⭐ Performance improvement vs baseline
- ⭐ Positive player feedback on new features
- ⭐ Documentation comprehensive and clear

---

## Testing Status Summary

**Total Test Cases:** 50+  
**Completed:** 0  
**In Progress:** 0  
**Blocked:** 0  
**Failed:** 0  

**Overall Status:** 🟡 Ready to Begin Testing

---

## Notes
- Use fresh save file for clean testing
- Keep runtime logs for analysis
- Document unexpected behaviors
- Test on macOS (user's platform)
- Verify with Python 3.10+

---

**Next Steps:**
1. Run automated syntax/import checks
2. Execute Day 1 test plan
3. Document findings
4. Address any issues discovered
5. Proceed to Day 2 testing
