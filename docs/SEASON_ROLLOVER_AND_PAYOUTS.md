# Season Rollover and Championship Payout Structure

## Summary
Implemented proper season rollover logic and a structured championship payout system with hype drift influence.

## Changes Made

### 1. Season Rollover Fix
**Problem**: Season 1 was rolling on forever - the `season_number` was never being incremented because the actual season end processing happened in `process_season_end_for_league()` but the increment was only in the legacy `process_season_end()` function.

**Solution**: 
- Added season rollover logic in `process_season_end_for_league()` that increments `season_number` only when ALL active leagues have completed their seasons
- Added helper method `_get_expected_races(league)` to centralize race count logic
- Uses `state.in_offseason` flag as a guard to prevent double-increments when multiple leagues finish in same tick
- Season now properly advances when all leagues finish their races
- Triggers offseason period (56 ticks / 8 weeks) between seasons
- Emits `season_rollover` event with priority 98.0 to announce new season

**Edge Case Handling**:
- If multiple leagues finish in the same tick, only the first one triggers the rollover
- `state.in_offseason` acts as a guard flag to prevent duplicate increments
- Skips the current league when checking if others are complete (since we're processing it)

### 2. Championship Payout Structure
**Problem**: Prize money used exponential decay formula with no clear defined payouts for specific positions.

**Solution**: Implemented tier-specific position-based payout structures:

#### Tier 1 (Grassroots) Championship Payouts:
- **P1**: $150,000
- **P2**: $110,000
- **P3**: $85,000
- **P4**: $70,000
- **P5**: $60,000
- **P6**: $55,000
- **P7**: $45,000
- **P8**: $35,000
- **P9**: $25,000
- **P10+**: $15,000

#### Other Tiers (scaled up):
- **Tier 2 (Formula V)**: 2.67x Grassroots
- **Tier 3 (Formula X)**: 8x Grassroots
- **Tier 4 (Formula Y)**: 20x Grassroots
- **Tier 5 (Formula Z)**: 53x Grassroots

### 3. Hype Drift Integration
**New Feature**: Championship prize money is now subject to "hype drift" ±15% based on league hype levels.

**How it works**:
- League hype typically ranges from 0.5 (low excitement) to 2.0 (high excitement)
- Hype modifier maps this to 0.85-1.15 (±15% variation)
- Formula: `hype_modifier = 0.85 + (clamp(league_hype, 0.5, 2.0) - 0.5) * 0.2`
- Final prize = `base_prize * hype_modifier`

**Example**: 
- P1 Grassroots base = $150k
- With 1.5x hype → modifier = 1.05 → payout = $157,500 (+7.5%)
- With 0.7x hype → modifier = 0.93 → payout = $139,500 (-7%)

### 4. Enhanced Event Messages
Prize money events now show:
- Championship position
- Hype bonus/penalty percentage for prize money
- Media rights payment (also affected by league hype)
- Example: `"Championship P1 Prize: $157,500 [+7.5% hype bonus] + $150,000 media rights [1.50x league hype!]"`

## Technical Details

### Key Functions Modified:
- `process_season_end_for_league()`: Added season rollover logic and new payout structure
- `tick_simulation()`: Refactored to use new `_get_expected_races()` helper
- Added `_get_expected_races()`: Static helper method for race count by tier

### Data Tracking:
- `state.season_number`: Now properly increments when all leagues complete
- `league.races_this_season`: Reset to 0 at season end
- `league.championship_table`: Reset to {} for new season
- `state.in_offseason`: Set to True with 56 tick countdown

### Race Counts by Tier:
- Tier 1 (Grassroots): 12 races
- Tier 2 (Formula V): 14 races
- Tier 3 (Formula X): 16 races
- Tier 4 (Formula Y): 18 races
- Tier 5 (Formula Z): 24 races

## Testing Recommendations

1. **Season Progression**: Play through a full season to verify season_number increments to 2
2. **Multi-League**: If multiple tiers exist, verify all must complete before season rolls over
3. **Payout Amounts**: Check that championship positions receive correct base amounts
4. **Hype Influence**: Monitor how league excitement affects prize payouts (look for [+X% hype bonus] messages)
5. **Offseason Period**: Verify 8-week break between seasons (56 ticks)

## Balance Notes

The grassroots payout structure creates interesting dynamics:
- **Top 3 protected**: P1-P3 get meaningful prize money ($85k-$150k)
- **Midfield struggle**: P4-P6 get modest payouts ($55k-$70k)
- **Bottom feeders**: P7-P9 barely break even ($25k-$45k)
- **Backmarkers**: P10+ get minimal survival money ($15k)

This creates natural financial pressure to climb the championship standings while keeping the door open for struggling teams to survive with clever management.

## Future Enhancements

Potential additions:
- Constructors championship separate from driver championship
- Bonus payouts for pole positions or race wins
- Season-long achievement bonuses (most improved, rookie of year, etc.)
- Tiered sponsorship bonuses based on championship finish
- Relegation/promotion financial penalties/bonuses
