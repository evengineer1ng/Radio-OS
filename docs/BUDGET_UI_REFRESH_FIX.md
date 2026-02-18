# Budget UI Refresh Fix

## Problem
Budget/cashflow appeared frozen in the UI - cash value stayed the same every tick despite having active income streams and staff salaries.

## Root Cause
The budget **was** being updated correctly every tick in `apply_financial_flows()`:
- Income was being added: `team.budget.cash += tick_income`  
- Operational costs were being subtracted: `team.budget.cash -= total_operational_cost`

However, the UI was never being told to refresh because the dirty flag was only being set **if events were returned**:

```python
# OLD CODE (BUGGY)
financial_events = FTBSimulation.apply_financial_flows(state)
if financial_events:  # ⚠️ Only marks dirty if events exist!
    state.mark_dirty('finance')
events.extend(financial_events)
```

Since `apply_financial_flows()` only returns events for economic crises (rare), the `finance` dirty flag was never being set during normal ticks. This meant:
- Backend: Budget was updating correctly ✅
- UI: Never refreshed to show new values ❌

## Fix
**Always mark finance dirty** when financial flows are applied, regardless of whether events are generated:

```python
# NEW CODE (FIXED)
financial_events = FTBSimulation.apply_financial_flows(state)
# Always mark finance as dirty when budget ticks (UI needs to refresh)
state.mark_dirty('finance')
events.extend(financial_events)
```

## Location
**File**: `plugins/ftb_game.py`  
**Lines**: 9075-9081 (in `tick_simulation()`)

## Expected Behavior After Fix
- Cash value updates every tick  
- Income flows in: +$669.64/tick (from Media Rights: $75,000/season ÷ 112 ticks)
- Payroll flows out: -$425.22/tick (5 staff members)
- Net change: **+$244.43 per tick**
- UI refreshes immediately to show new cash value

## Testing
1. Load a save game (e.g., `championshiprun.json`)
2. Advance 1 tick using "Next Tick" button
3. Verify cash increases by expected amount (~$244 in test save)
4. Advance multiple ticks to confirm continuous updates
5. Check that widgets displaying budget values update in real-time

## Related Systems
This fix affects any UI widget that displays budget/cash values:
- Main game controller UI (budget display)
- Financial overview widgets
- Team management panels
- Any custom widgets showing `team.budget.cash`

All of these will now update every tick as expected.

## Diagnostic Tool
Created `check_budget.py` to analyze budget state in save files:
```bash
python3 check_budget.py saves/championshiprun.json
```

This tool shows:
- Current cash and tick number
- Income streams and per-tick breakdown
- Staff salaries and total payroll
- Net cashflow calculation
- Expected cash after next tick
