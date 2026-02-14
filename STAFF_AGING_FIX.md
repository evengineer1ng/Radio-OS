# Staff Aging System Fix - Realistic Peak Ages by Role

## Problem Identified
Non-driver staff entities (engineers, mechanics, strategists, principals) were decaying in their late 30s, using the same peak age (30) as drivers. This was unrealistic because:
- **Drivers** rely on physical reflexes and peak early (27-32)
- **Engineers/Technical Staff** rely on brain work and experience, peaking much later
- **Team Principals** rely on wisdom and leadership, peaking even later

## Solution Implemented
Modified the aging system to use **role-specific peak age ranges** that reflect realistic career trajectories.

---

## New Peak Age Ranges by Entity Type

### Driver (Physical Performance)
- **Peak Age Range:** 27-32 years old
- **Rationale:** Physical reflexes, reaction time, fitness peak in late 20s/early 30s
- **Decay Starts:** After age 32
- **Career Span:** Typically retire 35-42 depending on performance

### Engineer (Technical/Brain Work)
- **Peak Age Range:** 32-45 years old ⭐ **CHANGED**
- **Rationale:** Knowledge-based role that improves with experience
  - Technical depth builds over decades
  - Innovation and systems thinking mature with exposure
  - No physical decline pressure like drivers
- **Decay Starts:** After age 45
- **Career Span:** Can work effectively into 50s-60s

### Mechanic (Physical + Experience)
- **Peak Age Range:** 28-38 years old ⭐ **CHANGED**
- **Rationale:** Hybrid role requiring both physical capability and experience
  - Pit execution requires physical fitness (but less intense than driving)
  - Build quality and precision improve with experience
  - Moderate longevity between drivers and engineers
- **Decay Starts:** After age 38
- **Career Span:** Can work effectively into mid-40s

### Strategist (Mental/Experience)
- **Peak Age Range:** 30-50 years old ⭐ **CHANGED**
- **Rationale:** Pure mental work that benefits from extensive experience
  - Race reading improves with years of observation
  - Situational awareness builds pattern recognition over time
  - No physical component
- **Decay Starts:** After age 50
- **Career Span:** Can work effectively into 60s

### Team Principal (Leadership/Wisdom)
- **Peak Age Range:** 40-60 years old ⭐ **CHANGED**
- **Rationale:** Leadership role requiring extensive industry experience
  - Management skills mature over decades
  - Political awareness and negotiation improve with age
  - Wisdom-based decision making
- **Decay Starts:** After age 60
- **Career Span:** Can lead teams into 70s (see Frank Williams, Ron Dennis)

---

## Technical Implementation

### Files Modified
- `plugins/ftb_game.py`

### Changes Made

#### 1. Modified `Entity.apply_decay()` method (line ~1550)
**Before:**
```python
peak_age = 30  # Override in subclasses
if self.age > peak_age:
    years_past_peak = self.age - peak_age
```

**After:**
```python
# Use entity-specific peak age from peak_age_range property
peak_age_start, peak_age_end = self.peak_age_range
peak_age = (peak_age_start + peak_age_end) // 2  # Use midpoint of peak range
if self.age > peak_age_end:
    years_past_peak = self.age - peak_age_end
```

#### 2. Modified `Entity.update_growth()` method (line ~1513)
**Before:**
```python
peak_age = context.get('peak_age', 30)
age_factor = 1.0 - abs(self.age - peak_age) / 20.0
```

**After:**
```python
# Use entity-specific peak age range (midpoint for growth calculation)
peak_age_start, peak_age_end = self.peak_age_range
peak_age = (peak_age_start + peak_age_end) // 2
age_factor = 1.0 - abs(self.age - peak_age) / 20.0
```

#### 3. Added `peak_age_range` property overrides to each entity class

**Engineer class (line ~1693):**
```python
@property
def peak_age_range(self) -> Tuple[int, int]:
    """Engineers peak later than drivers - brain work, not physical"""
    return (32, 45)
```

**Mechanic class (line ~1728):**
```python
@property
def peak_age_range(self) -> Tuple[int, int]:
    """Mechanics peak slightly later than drivers - physical but experienced"""
    return (28, 38)
```

**Strategist class (line ~1763):**
```python
@property
def peak_age_range(self) -> Tuple[int, int]:
    """Strategists peak with experience - mental work"""
    return (30, 50)
```

**AIPrincipal class (line ~1773):**
```python
@property
def peak_age_range(self) -> Tuple[int, int]:
    """Principals peak with extensive experience - leadership role"""
    return (40, 60)
```

**Driver class (already existed, line ~1609):**
```python
@property
def peak_age_range(self) -> Tuple[int, int]:
    """Expected peak age range for this entity type"""
    return (27, 32)  # Default for drivers
```

---

## How Aging Works Now

### Growth Phase (Before Peak)
- Entities improve toward their `potential_ceiling`
- Growth rate is modified by:
  - **Age factor**: Peak growth at midpoint of peak_age_range, tapers before/after
  - **Infrastructure quality**: Better facilities = faster growth (±40%)
  - **Form momentum**: Recent good results boost growth
  - **Team stability**: Stable environment aids development

### Peak Phase (Within Peak Range)
- Minimal decay
- Can still improve if below potential ceiling
- Optimal performance window

### Decay Phase (After Peak End)
- Stats begin declining based on:
  - **Years past peak end**: More years = faster decay
  - **Decay rate**: Individual stat (some decline faster than others)
  - **Infrastructure quality**: Better facilities slow decay (up to -40%)

### Example Career Trajectories

#### 25-Year-Old Engineer
- **Current:** Still improving (7 years before peak)
- **Peak:** Ages 32-45 (13-year peak window!)
- **Decline:** Starts after 45
- **Viable Career:** Could work until 55-60 before serious decay

#### 25-Year-Old Driver
- **Current:** Rapid improvement (2-7 years before peak)
- **Peak:** Ages 27-32 (5-year peak window)
- **Decline:** Starts after 32
- **Retirement:** Typically 35-42 (faster decline than staff)

#### 40-Year-Old Principal
- **Current:** Entering peak (just reached ideal range)
- **Peak:** Ages 40-60 (20-year peak window!)
- **Decline:** Starts after 60
- **Viable Career:** Could lead until 65-70

---

## Gameplay Impact

### Before Fix (All Staff Decaying at 30+)
❌ 35-year-old engineer declining like a washed-up driver
❌ 38-year-old strategist losing sharpness unrealistically
❌ 42-year-old principal past peak when they should be in prime
❌ Staff careers ended prematurely, unrealistic turnover

### After Fix (Role-Specific Aging)
✅ 35-year-old engineer still improving, just entering prime
✅ 38-year-old strategist in peak performance range
✅ 42-year-old principal just starting peak years
✅ Realistic career spans, experience valued appropriately
✅ Younger drivers compete with experienced staff in hiring decisions

### Strategic Implications
1. **Long-term Staff Investments:** Engineers and strategists worth developing (longer careers)
2. **Driver Youth Premium:** Drivers have shorter windows, harder to develop veterans
3. **Principal Stability:** Team leaders can provide decades of consistent leadership
4. **Hiring Strategy:** Balance youth potential vs. veteran stability differently per role

---

## Testing Recommendations

### Manual Testing
1. **Create new game** with these changes
2. **Check staff ages** across all teams
3. **Advance 10-20 ticks** and observe stat changes
4. **Compare:**
   - 32-year-old driver (starting decline) vs. 32-year-old engineer (entering peak)
   - 38-year-old mechanic (end of peak) vs. 38-year-old strategist (mid-peak)
   - 45-year-old principal (mid-peak) vs. 45-year-old driver (retired or close)

### Expected Behaviors
- ✅ Drivers in late 30s should show stat decline
- ✅ Engineers in late 30s should maintain or improve stats
- ✅ Mechanics in early 40s should show slight decline
- ✅ Strategists in 40s should be stable/improving
- ✅ Principals in 50s should be at peak performance

---

## Real-World Parallels

### F1 Examples
- **Drivers:** Lewis Hamilton (39, rare exception), most retire by 35-40
- **Technical Directors:** Adrian Newey (65, still at peak), James Allison (56)
- **Team Principals:** Toto Wolff (52), Christian Horner (51), Fred Vasseur (56)
- **Engineers:** Many peak performers in 40s-50s with decades of experience

### Why This Matters
This fix ensures the game reflects motorsport reality where:
- Technical staff have longer, more stable careers than drivers
- Experience is valued in knowledge-based roles
- Team principals can lead for decades
- Driver talent windows are precious and short

---

## Summary

**Problem:** All staff aged like drivers (peak at 30, decline in late 30s)

**Solution:** Entity-specific peak age ranges reflecting real career trajectories

**Result:** 
- Drivers: Peak 27-32 (physical)
- Mechanics: Peak 28-38 (physical + experience)
- Strategists: Peak 30-50 (mental)
- Engineers: Peak 32-45 (technical/brain)
- Principals: Peak 40-60 (leadership/wisdom)

This creates realistic, varied career arcs that reward long-term staff investment while maintaining driver urgency.
