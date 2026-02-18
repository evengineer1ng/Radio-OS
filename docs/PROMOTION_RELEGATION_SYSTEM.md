# Promotion & Relegation System

## Overview
Realistic, choice-driven tier movement system where promotion and relegation are **NOT automatic**. Teams must apply or be invited for promotion, and relegation can be voluntary or forced based on multiple factors.

## ✅ Changes Implemented

### 1. Per-League Season Cycles
- **Each league runs independently** - no global season synchronization
- Formula Y finishes in ~18 weeks, Grassroots in ~24 weeks
- Leagues have their own `season_number` tracker
- Global `state.season_number` only advances when player's league completes
- No more waiting in "post-season limbo" for other tiers to finish

### 2. Promotion System (Application & Invitation)

#### Eligibility Calculation (0-100 score)
Promotion eligibility is calculated based on:
- **Championship Position** (40 pts): P1=40pts, P2=30pts, P3=20pts
- **Points Earned** (20 pts): Relative to expected winner points
- **Financial Health** (20 pts): Cash reserves vs. tier threshold
- **Reputation** (10 pts): Team reputation score
- **Infrastructure** (10 pts): Average facility quality

#### Invitation Path (Premium)
**Requirements:**
- Finish P1 or P2
- Eligibility score ≥ 75
- Cash reserves ≥ $200,000

**Benefits:**
- NO entry fee
- Guaranteed spot
- 6 weeks to respond

**Example Event:**
```
🎉 PROMOTION INVITATION
Congratulations! P1 finish has earned an invitation to Formula V!
Eligibility Score: 82/100
Entry Fee: $0 (Invited)
Decision Required: Accept or Decline
Expires: 6 weeks
```

#### Application Path (Self-Funded)
**Requirements:**
- Finish P1, P2, or P3
- Eligibility score ≥ 50

**Entry Fees by Tier:**
- Grassroots → Formula V: $100,000
- Formula V → Formula X: $250,000
- Formula X → Formula Y: $500,000
- Formula Y → Formula Z: $1,000,000

**Example Event:**
```
📋 PROMOTION APPLICATION AVAILABLE
P2 finish qualifies you to apply for promotion to Formula V
Eligibility Score: 58/100
Entry Fee: $100,000
Decision Required: Apply or Stay
Expires: 6 weeks
```

#### Ineligible Path (Not Ready)
Teams that finish in top 3 but don't meet criteria get feedback:
```
❌ PROMOTION INELIGIBLE
P3 finish - Not yet eligible for promotion
Score: 42/100 (Need 50+)
Focus on: Financial stability, Infrastructure quality
```

### 3. Relegation System (Forced or Voluntary)

#### Relegation Risk Evaluation (0-100 score)
Risk factors:
- **Championship Position** (40 pts): Last=40pts, 2nd-last=30pts, Bottom-3=20pts
- **Low Points** (20 pts): <10pts=20pts, <30pts=10pts
- **Financial Crisis** (30 pts): <$20k=30pts, <$50k=20pts, <$100k=10pts
- **Poor Reputation** (10 pts): <20 rep=10pts, <35 rep=5pts

#### Forced Relegation (Automatic)
**Triggers:**
- Risk score ≥ 80, OR
- Last place + financial crisis, OR
- <10 points + <$50k cash

**Example Event:**
```
⚠️ FORCED RELEGATION
Your team is being relegated to Grassroots
Position: P16/16 (Last place)
Points: 8
Risk Score: 85/100
Reasons:
  - Last place finish
  - Critically low points
  - Financial insolvency
  
This relegation is AUTOMATIC and will occur in 1 week.
```

#### Voluntary Relegation (Player Choice)
**Eligibility:**
- Risk score ≥ 40 (but not forced)
- Struggling performance but not catastrophic

**Benefits Offered:**
- Lower operating costs
- Easier competition
- Time to rebuild
- Reduced pressure

**Example Event:**
```
📉 VOLUNTARY RELEGATION OPTION
Struggling at P14 - Consider voluntary relegation to rebuild?
Risk Score: 55/100
Concerns:
  - Bottom 3 finish
  - Financial strain
  - Poor reputation
  
Benefits of Dropping to Grassroots:
  ✓ 40% lower operating costs
  ✓ Easier competition
  ✓ Time to rebuild infrastructure
  ✓ Reduced sponsor pressure
  
Decision Required: Relegate or Fight to Stay
Expires: 4 weeks
```

### 4. AI Team Behavior

**Promotion:**
- Invited teams: Always accept
- Application-eligible: 70% apply if they can afford it

**Relegation:**
- Forced: Always executed (no choice)
- Voluntary: 30% of struggling AI teams choose to drop down

### 5. Feature Unlocks/Losses

**Promotion Unlocks:**
- Strategist hiring (higher tiers)
- R&D projects (higher tiers)
- Manufacturer partnerships (top tiers)
- Additional upgrade packages
- More engineer/mechanic slots

**Relegation Losses:**
- May lose access to advanced features
- Reduced max staff counts
- Limited upgrade options

## UI Integration Needed

### Championship Standings View
The `RacingStats.svelte` component should be enhanced to show:

1. **Promotion Zone Indicators**
   ```
   P1  Team Alpha      285 pts  🎯 PROMOTION ELIGIBLE
   P2  Team Beta       240 pts  🎯 PROMOTION ELIGIBLE  
   P3  Team Gamma      195 pts  🎯 APPLICATION ZONE
   P4  Your Team       180 pts
   ...
   P14 Team Omega       45 pts  ⚠️ RELEGATION RISK
   P15 Team Last        32 pts  ⚠️ RELEGATION DANGER
   P16 Team Bottom      15 pts  🔴 FORCED RELEGATION
   ```

2. **Live Eligibility Tracker** (during season)
   ```
   📊 PROMOTION STATUS
   Current Position: P2
   Eligibility Score: 68/100
   
   Invite Threshold: 75 (Need 7 more points)
   Application Threshold: 50 (✓ Met)
   
   Score Breakdown:
   - Position: 30/40 ✓
   - Points: 15/20 ✓
   - Finances: 12/20 ⚠️
   - Reputation: 7/10 ✓
   - Infrastructure: 4/10 ⚠️
   
   To improve: Increase cash reserves, upgrade facilities
   ```

3. **Relegation Risk Indicator**
   ```
   ⚠️ RELEGATION RISK: MODERATE (42/100)
   
   Current Position: P12/16
   
   Risk Factors:
   - Below-average points (10 pts)
   - Financial strain (10 pts)
   - Lower-half finish (20 pts)
   - Poor reputation (2 pts)
   
   Safe Zone: Need to climb to P10 or better
   ```

4. **Interactive Decision Modals**
   - Accept/Decline promotion invitations
   - Apply for promotion (with fee confirmation)
   - Accept voluntary relegation or fight to stay
   - View detailed eligibility breakdown

## Technical Implementation

### Data Structures

**State.pending_promotions**
```python
[{
    'team_name': str,
    'team_obj': Team,
    'from_league': League,
    'to_tier': int,
    'is_invited': bool,
    'entry_fee': int,
    'process_tick': int  # When to execute
}]
```

**State.pending_relegations**
```python
[{
    'team_name': str,
    'team_obj': Team,
    'from_league': League,
    'to_tier': int,
    'forced': bool,
    'process_tick': int
}]
```

### Event Categories

**Promotion Events:**
- `promotion_invitation` - Player invited to promote
- `promotion_application` - Player can apply
- `promotion_ineligible` - Not ready yet
- `promotion_fee_paid` - Entry fee deducted
- `team_promoted` - Successfully moved up
- `tier_features_unlocked` - New features available

**Relegation Events:**
- `forced_relegation` - Automatic demotion
- `voluntary_relegation_offer` - Player can choose
- `team_relegated` - Successfully moved down
- `tier_features_lost` - Features removed

### Processing Flow

1. **Season End:** Calculate eligibility/risk scores
2. **Event Generation:** Send invitations/offers/warnings
3. **Decision Period:** Player has X weeks to respond
4. **Processing Tick:** AI teams auto-decide, pending moves execute
5. **Confirmation:** Generate completion events

## Testing Scenarios

1. **Win Championship with Strong Team**
   - Should receive invitation (no fee)
   - Accept → immediate promotion

2. **Finish P2 with Weak Finances**
   - Should receive application offer
   - Must pay $100k+ entry fee
   - Can decline if can't afford

3. **Finish P3 with Poor Infrastructure**
   - May not be eligible
   - Get feedback on what to improve

4. **Finish Last with No Money**
   - Forced relegation (no choice)
   - 1 week warning, then automatic

5. **Struggling Midfield**
   - Optional voluntary relegation
   - Can choose to rebuild in lower tier

## Balance Considerations

**Promotion Difficulty:**
- Top tier (Formula Z) entry: $1M + need P1-P2 finish
- Financial barriers prevent instant climbing
- Infrastructure requirements enforce gradual progression

**Relegation Protection:**
- Not automatic for mid-table finishes
- Financial crisis is main trigger
- Voluntary option gives player agency

**AI Churn:**
- 30% of struggling teams voluntarily drop
- Creates realistic tier movement
- Opens slots for promoted teams

## Future Enhancements

1. **Playoff System** for promotion (P3-P6 compete for final spots)
2. **License Requirements** (team must meet safety/quality standards)
3. **Promotion Bonuses** (prize money for promoted teams)
4. **Relegation Parachute Payments** (softens the blow)
5. **Multi-season Contracts** affecting promotion decisions
6. **Manufacturer Tie-ins** (promotion conditional on manufacturer support)
