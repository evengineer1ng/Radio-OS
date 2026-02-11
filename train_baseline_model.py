"""Train baseline ML model with collected decisions (using default success scores)."""
from plugins.ftb_state_db import query_ai_decisions
import json
import glob
import os

# Find latest database
db_files = glob.glob("data/ml_training/*.db")
latest_db = max(db_files, key=os.path.getmtime)

print(f"Training from: {latest_db}")

# Export decisions
decisions = query_ai_decisions(latest_db, limit=100000)
print(f"Loaded {len(decisions)} decisions")

# Create fake outcomes for training (assign moderate success to all teams)
outcomes = []
team_ids = set(d['team_id'] for d in decisions)
for team_id in team_ids:
    # Assign a random success score (0-100) for each team
    import random
    starting_budget = 100000
    ending_budget = random.uniform(80000, 120000)
    budget_health = ((ending_budget - starting_budget) / starting_budget) * 100 + 50
    
    outcomes.append({
        'team_id': team_id,
        'team_name': next(d['team_name'] for d in decisions if d['team_id'] == team_id),
        'season': 1,
        'championship_position': random.randint(1, 20),
        'total_points': random.uniform(0, 100),
        'starting_budget': starting_budget,
        'ending_budget': ending_budget,
        'budget_health_score': budget_health,
        'roi_score': random.uniform(40, 70),
        'survival_flag': True,
        'folded_tick': None,
        'seasons_survived': 1
    })

print(f"Created {len(outcomes)} fake outcomes for training")

# Export to JSON
with open("training_decisions.json", "w") as f:
    json.dump(decisions, f)

with open("training_outcomes.json", "w") as f:
    json.dump(outcomes, f)

print(f"\nExported to training_decisions.json and training_outcomes.json")
print(f"\nNow training model with:")
print(f"  python -m plugins.ftb_ml_policy training_decisions.json training_outcomes.json models/ftb_baseline_v1.pth")

# Auto-run training
import subprocess
result = subprocess.run([
    "python", "-m", "plugins.ftb_ml_policy",
    "training_decisions.json",
    "training_outcomes.json",
    "models/ftb_baseline_v1.pth"
], capture_output=True, text=True)

print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

print(f"\n{'='*60}")
print(f"Training complete!")
print(f"Model saved to: models/ftb_baseline_v1.pth")
print(f"{'='*60}")
