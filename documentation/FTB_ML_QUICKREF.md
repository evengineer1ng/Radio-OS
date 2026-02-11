# FTB ML Quick Reference

## Generate Training Data
```bash
python tools/ftb_ml_datagen.py --seasons 10 --teams 100 --output_dir data/ml_training
```
**Output**: `data/ml_training/run_<timestamp>_*.json`  
**Check**: Survival rate 60-80%, 40k-60k decisions

## Train IL Policy
```bash
python -m plugins.ftb_ml_policy data/ml_training/run_XXX_decisions.json data/ml_training/run_XXX_outcomes.json models/baseline_policy_v1.pth
```
**Check**: Val loss < 0.20, completes in 5-10 mins

## Enable ML in Game
```python
# Add to station entrypoint
from plugins.ftb_ml_policy import TeamPrincipalPolicy
state.ml_policy_enabled = True
state._ml_policy_model = TeamPrincipalPolicy.load('models/baseline_policy_v1.pth')
```

## Train RL Policy (Optional)
```bash
pip install gym stable-baselines3
python tools/ftb_rl_trainer.py --baseline models/baseline_policy_v1.pth --output models/rl_policy_v1.pth --timesteps 500000
```
**Time**: 8-12 hours

## Query Training Data
```python
from plugins.ftb_state_db import query_ai_decisions, query_team_outcomes

decisions = query_ai_decisions(db_path, limit=5000)
successful = query_team_outcomes(db_path, min_budget_health=50.0, survived_only=True)
```

## Success Metrics
- Bankruptcy rate: < 10%
- Survival (5 seasons): > 70%
- Budget health: > 40 avg
- Behavioral diversity: stdev > 15 points

## Files
- `plugins/ftb_game.py`: Economic realism + ML integration
- `plugins/ftb_state_db.py`: Logging tables + queries
- `plugins/ftb_ml_policy.py`: PyTorch IL model
- `tools/ftb_ml_datagen.py`: Data generator
- `tools/ftb_rl_trainer.py`: RL fine-tuning
- `documentation/FTB_ML_SYSTEM.md`: Full guide

## Debug
```python
# Check if policy loaded
print(f"ML enabled: {state.ml_policy_enabled}")
print(f"Model: {state._ml_policy_model}")

# Manual scoring test
from plugins.ftb_ml_policy import TeamPrincipalPolicy
policy = TeamPrincipalPolicy.load('models/baseline_policy_v1.pth')
scores = policy.score_actions(team_state_dict, actions_list, principal_stats_dict)
print(f"Scores: {scores}")
```
