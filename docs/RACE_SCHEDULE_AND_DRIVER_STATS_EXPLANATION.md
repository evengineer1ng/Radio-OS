# Race Schedule Change & Driver Stats Explanation

## 1. Race Schedule Shift (Year 1, Day 2 Start)

### Change Made
The race schedule has been shifted to start on **Year 1, Day 2** instead of Year 1, Day 1.

**File Modified:** `plugins/ftb_game.py` (line ~6368)
- Changed `start_week = 1` to `start_week = 2`

### How It Works
- The game uses a tick system where **1 tick = 1 day** (see `days_per_tick = 1`)
- The schedule is calculated as: `start_week + idx*spacing`
  - For the first race (idx=0): `2 + 0*spacing = 2` (Day 2)
  - For the second race: `2 + 1*spacing = 2 + spacing` (e.g., Day 16 for Tier 1)
  
### Race Spacing by Tier
After the delay, races follow these intervals:
- **Tier 1 (Grassroots/Karting)**: Every 14 days (bi-weekly local events)
- **Tier 2 (Formula V/F4)**: Every 10 days (frequent regional racing)
- **Tier 3 (Formula X/F3)**: Every 10 days (packed F3 schedule)
- **Tier 4 (Formula Y/F2)**: Every 7 days (weekly F2 racing)
- **Tier 5 (Formula Z/F1)**: Every 7 days (weekly F1 grand prix)

### Example Schedule (Tier 1, 12 races)
- Race 1: Day 2
- Race 2: Day 16 (2 + 14)
- Race 3: Day 30 (2 + 28)
- Race 4: Day 44 (2 + 42)
- ... and so on

---

## 2. Driver Stats: Learning Rate & Consistency

### Learning Rate (`learning_rate`)
**Purpose:** Controls how quickly a driver improves their skills over time.

**Range:** 0-100 (typically 20-80)
- **Low learning_rate (20-40)**: Slow improvement, takes longer to master new tracks/skills
- **Medium learning_rate (40-60)**: Balanced progression
- **High learning_rate (60-80+)**: Rapid improvement, adapts quickly to changes

**Where It's Used:**
1. **Track Learning** (`track_learning_speed` stat works alongside this)
2. **Regulation Adaptation** (when rules change between seasons)
3. **Staff Conversion** (when retired drivers become engineers):
   - Contributes to `innovation_bias` (50% weight)
   - Contributes to `iteration_speed` (30% weight)
   - Contributes to `systems_thinking` (30% weight)
   - Contributes to `long_term_orientation` (30% weight)

**Example:**
```python
# From ftb_game.py:
"innovation_bias": lambda d: (d.adaptability * 0.5 + d.learning_rate * 0.5),
"iteration_speed": lambda d: 50.0 + (d.learning_rate - 50.0) * 0.3,
```

A driver with `learning_rate = 80` will become a more innovative engineer if they retire into a technical role.

---

### Consistency (`consistency`)
**Purpose:** Controls how reliably a driver performs at their expected level (reduces variance in lap times).

**Range:** 0-100 (typically 20-80)
- **Low consistency (20-40)**: Erratic performance, big swings lap-to-lap
- **Medium consistency (40-60)**: Balanced variance
- **High consistency (60-80+)**: Very stable, predictable lap times

**Where It's Used:**

#### 1. **Qualifying Performance Variance** (`plugins/ftb_race_day.py`, line 140)
```python
variance = 5.0 * (1.0 - getattr(driver, 'consistency', 50.0) / 100.0)
final_score = combined_score + rng.uniform(-variance, variance)
```
- **Consistency = 100**: `variance = 0` (no random swing)
- **Consistency = 50**: `variance = 2.5` (±2.5 point swing)
- **Consistency = 0**: `variance = 5.0` (±5.0 point swing)

**Example:** Two drivers with identical base pace (score = 100):
- Driver A (consistency=80): Final quali score = 100 ± 1.0 = 99-101
- Driver B (consistency=20): Final quali score = 100 ± 4.0 = 96-104

Driver B might sometimes out-qualify Driver A on a good day, but Driver A is more reliable.

#### 2. **Qualifying Variance Range** (`plugins/ftb_game.py`, line 9327)
```python
consistency = getattr(driver, 'consistency', 50.0)
variance_range = (100.0 - consistency) / 200.0
variance_roll = rng.uniform(-variance_range * 10, variance_range * 10)
```
- **Consistency = 100**: `variance_range = 0` → no variance
- **Consistency = 50**: `variance_range = 0.25` → ±2.5 variance
- **Consistency = 0**: `variance_range = 0.5` → ±5.0 variance

#### 3. **Race Lap Time Variance** (`plugins/ftb_game.py`, line 10052)
```python
# Base lap time
lap_time = driver_data['base_lap_time']

# Add consistency variance
variance = (100.0 - driver_data['consistency']) / 100.0
lap_time += rng.uniform(-variance, variance)
```
- **Consistency = 100**: `variance = 0` (perfect lap times every lap)
- **Consistency = 50**: `variance = 0.5` (±0.5 seconds per lap)
- **Consistency = 0**: `variance = 1.0` (±1.0 seconds per lap)

**Example Race Scenario (50 laps):**
- **Driver A** (consistency=80, base lap time=90.0s):
  - Lap times range: 89.8s - 90.2s (±0.2s variance)
  - Total time: ~4500 seconds ± 10 seconds
  
- **Driver B** (consistency=30, base lap time=90.0s):
  - Lap times range: 89.3s - 90.7s (±0.7s variance)
  - Total time: ~4500 seconds ± 35 seconds

Driver B might have some amazing laps and some terrible laps, while Driver A is more predictable.

---

## 3. How These Stats Interact in Races

### Qualifying
1. **Base Score** calculated from driver stats + car performance
2. **Consistency Variance** applied: inconsistent drivers have unpredictable quali results
3. **Grid Position** determined by final score

### Race
1. **Base Lap Time** calculated from all performance stats
2. **Each Lap:**
   - Apply consistency variance (±random amount per lap)
   - Apply tire degradation
   - Check for mechanical failures (reliability stat)
   - Check for mistakes/crashes (mistake_rate stat)
3. **Final Position** determined by accumulated time

### Strategy Implications
- **High consistency + low pace**: Reliable but slow (good for consistency points)
- **Low consistency + high pace**: Fast but unpredictable (can win or crash)
- **High consistency + high pace**: The ideal combination (expensive drivers!)
- **Learning rate**: Matters more long-term (young drivers with high learning_rate are investments)

---

## 4. Additional Related Stats

### Track Learning Speed
- Works with `learning_rate` to determine how quickly drivers master new circuits
- High track_learning_speed = better performance on tracks they haven't raced at before

### Adaptability
- Similar to learning_rate but focused on adapting to new situations mid-race
- Used in staff conversions alongside learning_rate

### Mistake Rate
- Separate from consistency
- Controls frequency of driving errors (crashes, spins)
- Can cause DNFs even with high consistency

### Recovery From Error
- How quickly a driver bounces back after making a mistake
- Works independently of consistency

---

## Summary

**Race Schedule:** First race now happens on Day 2 instead of Day 1, giving players an extra day to prepare.

**Learning Rate:** Long-term stat affecting skill progression and adaptation. High learning_rate = faster improvement.

**Consistency:** Short-term stat affecting performance variance. High consistency = reliable lap times and predictable results.

Both stats are rated 0-100, with 50 being average. They operate independently but complement each other in creating diverse driver profiles.
