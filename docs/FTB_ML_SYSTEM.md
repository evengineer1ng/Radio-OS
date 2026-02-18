# FromTheBackmarker ML Team Principal Training System

Machine learning calibration system for AI team principals in FromTheBackmarker motorsports simulation. Trains team principals to make rational financial and strategic decisions that lead to solvency, competitive stability, and long-term survival.

## Overview

**Problem**: AI team principals make random, nonsensical moves based purely on attribute weights, causing all teams to crash and burn financially with no learning or adaptation.

**Solution**: Three-phase ML pipeline that learns a baseline rational behavior from successful simulated teams, then fine-tunes with reinforcement learning, with personality traits modulating decisions at key inflection points.

## Architecture

### Phase 1: Economic Realism (✅ Implemented)

Added constraints so ML learns within realistic boundaries:

- **Bankruptcy enforcement**: Teams fold after 3 consecutive ticks below -$50k debt
- **Cash flow forecasting**: `Budget.forecast_cash_flow()` projects 6 ticks ahead  
- **Bankruptcy prevention**: `evaluate_action()` rejects actions that forecast insolvency
- **Infrastructure maintenance**: 2% annual facility costs (processed monthly)
- **Salary growth caps**: Maximum 50% raise per transaction

**Files**: [`plugins/ftb_game.py`](plugins/ftb_game.py) lines 2610-2700, 10405-10550, 11336-11400

### Phase 2: Decision Logging (✅ Implemented)

Captures all AI decisions and outcomes for ML training:

**Database tables** (`plugins/ftb_state_db.py`):
- `ai_decisions`: state vector, action chosen, scores, principal stats, budget before/after
- `team_outcomes`: season results with budget_health_score, roi_score, survival_flag

**Logging integration** (`plugins/ftb_game.py`):
- `ai_team_decide()` logs every decision with full context
- `end_of_season_processing()` logs team season outcomes  
- `execute_team_fold()` logs bankruptcy events

**Query functions**:
```python
from plugins.ftb_state_db import query_ai_decisions, query_team_outcomes

decisions = query_ai_decisions(db_path, team_id="...", season=1, limit=1000)
successful = query_team_outcomes(db_path, min_budget_health=50.0, survived_only=True)
```

### Phase 3: Training Data Generation (✅ Implemented)

Headless simulation runner that generates 50k+ decisions from 100+ teams over 10 seasons.

**Usage**:
```bash
python tools/ftb_ml_datagen.py --seasons 10 --teams 100 --output_dir data/ml_training
```

**Output**:
- `run_<timestamp>_decisions.json`: All AI decisions
- `run_<timestamp>_outcomes.json`: All team season results
- `run_<timestamp>_successful.json`: Filtered successful teams only
- `run_<timestamp>_summary.json`: Statistics (survival rate, avg budget health, ROI)

**Success criteria**:
- `budget_health_score >= 50.0` (positive budget growth)
- `championship_position` mid-pack or better  
- `survival_flag = True` (team still exists)
- `seasons_survived >= 5`

### Phase 4: Imitation Learning Model (✅ Implemented)

PyTorch neural network trained via supervised learning on successful team decisions.

**Architecture** (`plugins/ftb_ml_policy.py`):
```
StateEncoder: team state (15 features) → 128-dim embedding
ActionScorer: [state embedding, action features] → score

Loss: MSE between predicted scores and outcome-weighted original scores
```

**Training**:
```bash
python -m plugins.ftb_ml_policy \
    data/ml_training/run_xxx_decisions.json \
    data/ml_training/run_xxx_outcomes.json \
    stations/FromTheBackmarker/models/baseline_policy_v1.pth
```

**Training parameters**:
- 50 epochs, batch_size=64, lr=0.001
- 80/20 train/validation split
- Early stopping on validation loss plateau

**Inference**:
```python
from plugins.ftb_ml_policy import TeamPrincipalPolicy

policy = TeamPrincipalPolicy.load('models/baseline_policy_v1.pth')
scores = policy.score_actions(team_state, actions, principal_stats)
```

### Phase 5: Game Loop Integration (✅ Implemented)

Modified `ai_team_decide()` to use ML policy when enabled.

**Enable ML policy**:
```python
# In station entrypoint or runtime
state.ml_policy_enabled = True
state._ml_policy_model = TeamPrincipalPolicy.load('models/baseline_policy_v1.pth')
```

**Hybrid mode**: Blend ML and rule-based scores for gradual rollout:
```python
final_score = 0.7 * ml_score + 0.3 * rule_based_score
```

**Fallback**: If ML policy fails, automatically fallsback to rule-based evaluation.

### Phase 6: Personality Inflection System (✅ Implemented)

Personality traits modulate the learned baseline at contextual inflection points.

**Function**: `apply_personality_inflection()` in [`ftb_game.py`](plugins/ftb_game.py)

**Inflection contexts**:

1. **Cash Crisis** (budget < 30% of baseline):
   - `financial_discipline`, `liquidity_conservatism` → amplify conservative actions up to 2x
   - `risk_tolerance`, `aggression` → still willing to spend (1.3x risky actions)

2. **Competitive Position** (P1-P3):
   - `risk_tolerance`, `aggression` → amplify bold moves (hiring, R&D) up to 1.5x

3. **Young Team** (< 3 seasons old):
   - `patience`, `long_term_orientation` → amplify infrastructure/development 1.5x

4. **Roster Quality Gap** (10+ points behind tier median):
   - `ruthlessness` → amplify firing decisions up to 1.6x
   - `staff_loyalty_bias` → resist firing even when behind (0.6x penalty)

**Activation**: Smooth sigmoid curves ensure gradual transitions:
```python
activation = 1 / (1 + exp(-sensitivity * (value - threshold)))
```

### Phase 7: RL Fine-Tuning (✅ Implemented)

Proximal Policy Optimization (PPO) to optimize beyond imitation learning baseline.

**Usage**:
```bash
python tools/ftb_rl_trainer.py \
    --baseline models/baseline_policy_v1.pth \
    --output models/rl_policy_v1.pth \
    --timesteps 500000
```

**Gym Environment**: [`tools/ftb_rl_trainer.py`](tools/ftb_rl_trainer.py)
- State: 15-feature team state vector
- Action: Discrete (20 action types)
- Reward: `0.3*Δbudget + 0.25*Δposition + 0.25*ROI + 0.2*survival - 10*bankruptcy`
- Episode: 50 ticks (~1 season)

**Training details**:
- Algorithm: PPO with clipping
- Policy: MLP (256-256 hidden layers)
- Learning rate: 3e-4
- Multi-opponent training: 10 teams per environment

**Note**: Currently trains from scratch; IL weight transfer requires architecture matching (future work).

## Quick Start

### 1. Generate Training Data

```bash
# Run 10-season simulation with 100 teams
python tools/ftb_ml_datagen.py --seasons 10 --teams 100 --output_dir data/ml_training
```

Expected: 50,000+ decisions, 70%+ survival rate, avg budget health > 40

### 2. Train Imitation Learning Baseline

```bash
# Train on successful teams only
python -m plugins.ftb_ml_policy \
    data/ml_training/run_<timestamp>_decisions.json \
    data/ml_training/run_<timestamp>_outcomes.json \
    stations/FromTheBackmarker/models/baseline_policy_v1.pth
```

Expected: Validation loss < 0.15, training completes in ~5 minutes

### 3. Enable ML Policy in Game

Edit station entrypoint (e.g., `stations/FromTheBackmarker/ftbfm.py`):

```python
# After creating SimState
from plugins.ftb_ml_policy import TeamPrincipalPolicy

state.ml_policy_enabled = True
state._ml_policy_model = TeamPrincipalPolicy.load('stations/FromTheBackmarker/models/baseline_policy_v1.pth')
```

### 4. (Optional) RL Fine-Tuning

```bash
# Requires: pip install gym stable-baselines3
python tools/ftb_rl_trainer.py \
    --baseline stations/FromTheBackmarker/models/baseline_policy_v1.pth \
    --output stations/FromTheBackmarker/models/rl_policy_v1.pth \
    --timesteps 500000
```

Expected: 15%+ improvement in outcome_score over IL baseline

## Validation

### Success Metrics

Run 100-season tournament and measure:

1. **Bankruptcy rate < 10%** (vs. ~100% without ML)
2. **Survival rate > 70%** after 5 seasons
3. **Budget health**: Avg ending budget > 80% of starting budget
4. **Competitive spread**: Championship position stdev > 15 points (not all clones)
5. **Personality diversity**: Conservative principals have higher survival, aggressive have higher podium rate

### Validation Script

```bash
# Run validation tournament
python tools/ftb_validate_ml.py \
    --policy models/baseline_policy_v1.pth \
    --seasons 100 \
    --output validation_results.json
```

### Identify Economic Weaknesses

Query the database for systematic failures:

```python
from plugins.ftb_state_db import query_ai_decisions

# Find actions that frequently lead to bankruptcy
risky_moves = conn.execute("""
    SELECT action_chosen_json, COUNT(*) as failures
    FROM ai_decisions d
    JOIN team_outcomes o ON d.team_id = o.team_id AND d.season = o.season
    WHERE o.survival_flag = 0
    GROUP BY action_chosen_json
    ORDER BY failures DESC
    LIMIT 10
""").fetchall()
```

## File Structure

```
plugins/
    ftb_game.py           # Core simulation + economic realism + inflection
    ftb_state_db.py       # Database schema + ML logging functions
    ftb_ml_policy.py      # PyTorch imitation learning model

tools/
    ftb_ml_datagen.py     # Training data generator
    ftb_rl_trainer.py     # RL fine-tuning pipeline
    ftb_validate_ml.py    # Validation script (TODO)

stations/FromTheBackmarker/
    models/
        baseline_policy_v1.pth  # Trained IL checkpoint
        rl_policy_v1.pth        # RL fine-tuned checkpoint
    
data/ml_training/
    run_<timestamp>_decisions.json
    run_<timestamp>_outcomes.json
    run_<timestamp>_successful.json
    run_<timestamp>_summary.json
```

## Configuration

### Manifest Settings

Add to `stations/FromTheBackmarker/manifest.yaml`:

```yaml
ml_policy: enabled  # Options: enabled, disabled, hybrid
ml_policy_checkpoint: models/baseline_policy_v1.pth
ml_policy_blend: 0.7  # For hybrid mode: 0.7*ML + 0.3*rules
```

### Personality Inflection Tuning

Adjust sensitivity in `apply_personality_inflection()`:

```python
# Make inflections more/less aggressive
crisis_activation = sigmoid_activation(0.3 - budget_ratio, 
                                      threshold=0.0, 
                                      sensitivity=20.0)  # Higher = sharper transitions
```

## Known Limitations

1. **IL baseline requires diverse successful teams**: If survival rate < 30% in training data, IL may not have enough positive examples
2. **RL training from scratch**: Weight transfer from IL → PPO not yet implemented (architecture mismatch)
3. **Static opponent pool**: RL trains against fixed-strategy opponents, not self-play
4. **No cash flow forecasting in RL**: Reward is post-hoc; could add forecasted bankruptcy to reward shaping

## Future Work

- **Self-play RL**: Train multiple policies against each other for emergent strategies
- **Curriculum learning**: Start RL in easy tiers (1-2), progress to harder (4-5)
- **Multi-season RL episodes**: Currently 1 season; extend to 5 seasons for long-term planning
- **Transformer architecture**: Replace MLP with attention for better state modeling
- **Online learning**: Continuously update policy from player's station data

## Troubleshooting

**"No training samples" error**: Training data had 0% survival rate. Adjust economic realism parameters (increase bankruptcy threshold, reduce costs) and regenerate data.

**ML policy crashes**: Check PyTorch version compatibility. Requires torch >= 1.9.0.

**Validation loss not decreasing**: Success score threshold too strict. Lower min_budget_health from 50.0 to 30.0.

**All teams make identical moves**: Personality inflection sensitivity too low. Increase multipliers from 0.5x to 1.0x+ in inflection contexts.

## License

Same as Radio OS project.

## Credits

Designed and implemented for FromTheBackmarker station to enable machine-learned, personality-driven team principal AI with economic realism and long-term strategic thinking.
