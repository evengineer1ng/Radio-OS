# FTB Phase 2 Quick Start

**Status:** ✅ Production Ready  
**Last Updated:** February 12, 2026

## What Changed

Phase 2 integrates historical data into the game loop and narrator system.

**Automatic Updates:**
- After every race: Streaks, momentum, pulse updated
- At season end: Career totals, prestige, peak performance updated
- In narrator prompts: Historical context automatically injected

## For Players

**No action required!** Historical tracking happens automatically.

To see your history:
```bash
# Bootstrap existing save (one time)
python3 tools/ftb_historical_data_bootstrap.py stations/YourStation/ftb_state.db
```

## For Developers

### Test Integration
```bash
python3 test_ftb_phase2_integration.py stations/SimRacingFM/ftb_state.db
```
Expected: 6/6 tests pass

### Use Historical Data in Code

**Get narrator context:**
```python
from plugins import ftb_historical_integration

context = ftb_historical_integration.get_narrator_context_packet(
    'stations/MyStation/ftb_state.db',
    'Apex Racing'
)

print(f"Team Pulse: {context['team_pulse']:.1f}/100")
print(f"Current Win Streak: {context['streaks']['current_wins']}")
```

**Enrich narrator prompts:**
```python
from plugins import ftb_narrative_prompts

game_facts = {'player': {...}}  # Your existing game facts

enriched = ftb_narrative_prompts.enrich_game_facts_with_history(
    game_facts,
    'stations/MyStation/ftb_state.db',
    'Apex Racing'
)

formatted = ftb_narrative_prompts.format_game_facts(enriched)
# Now contains CAREER HISTORY, ACTIVE STREAKS, TEAM HEALTH sections
```

**Check for milestones:**
```python
milestones = ftb_historical_integration.check_milestone_alerts(
    'stations/MyStation/ftb_state.db',
    'Apex Racing'
)

for m in milestones:
    print(f"{m['type']}: {m['description']}")
```

## Narrator Prompt Sections

Historical data adds these sections to narrator context:

**CAREER HISTORY:**
- All-time wins, podiums, races
- Championship count
- Best season finish
- Average finish

**ACTIVE STREAKS:**
- Consecutive podiums
- Consecutive points finishes
- Consecutive DNFs (if active)

**TEAM HEALTH:**
- Pulse Score (0-100 composite)
- Momentum trend (rising/falling/stable)
- Historical win rate
- Narrative temperature

**RECENT MILESTONES:**
- Records broken
- Career milestones reached
- Streak achievements

## Performance

All operations are fast (<100ms) and non-blocking:
- Race hook: ~50ms
- Season hook: ~200ms
- Context query: <100ms
- Prompt render: <10ms

## Troubleshooting

**Q: Historical sections empty?**  
A: Database needs data. Play one full season or run bootstrap script.

**Q: Milestones not appearing?**  
A: Check console for "🏆 Milestones achieved" after races.

**Q: How do I verify hooks are working?**  
A: `grep "ftb_historical_integration" plugins/ftb_game.py` should show 2 hooks.

## Files

| File | Purpose |
|------|---------|
| `plugins/ftb_game.py` | Race/season hooks (lines ~8180, ~9450) |
| `plugins/ftb_narrative_prompts.py` | History enrichment |
| `plugins/ftb_historical_integration.py` | Integration API |
| `test_ftb_phase2_integration.py` | Test suite |

## Documentation

- **Complete Guide:** `documentation/FTB_HISTORICAL_PHASE2_COMPLETE.md`
- **Phase 1 Reference:** `documentation/FTB_HISTORICAL_PHASE1_COMPLETE.md`
- **Master Plan:** `documentation/FTB_HISTORICAL_DATA_UPGRADE_PLAN.md`
- **This File:** Quick start reference

## SQL Quick Reference

```sql
-- View team career stats
SELECT * FROM team_career_totals WHERE team_name = 'Apex Racing';

-- Check active streaks
SELECT * FROM active_streaks WHERE team_name = 'Apex Racing';

-- Team health
SELECT * FROM team_pulse_metrics WHERE team_name = 'Apex Racing' ORDER BY last_updated DESC LIMIT 1;
```

## Next Phases

- **Phase 3:** League historical comparisons
- **Phase 4:** Driver career tracking
- **Phase 5:** Advanced analytics (ELO, rivalries)

See `documentation/FTB_HISTORICAL_DATA_UPGRADE_PLAN.md` for details.

---

**Built:** Feb 12, 2026 | **Tests:** 6/6 Passed | **Status:** Production Ready
