"""Export ML training data from database to JSON files for training."""
from plugins.ftb_state_db import query_ai_decisions, query_team_outcomes
import json
import glob
import os

# Find latest database
db_files = glob.glob("data/ml_training/*.db")
latest_db = max(db_files, key=os.path.getmtime)

print(f"Exporting from: {latest_db}")

# Query data
decisions = query_ai_decisions(latest_db, limit=100000)
outcomes = query_team_outcomes(latest_db, limit=10000)

print(f"Decisions: {len(decisions)}")
print(f"Outcomes: {len(outcomes)}")

# Export to simple JSON files
with open("training_decisions.json", "w") as f:
    json.dump(decisions, f, indent=2)

with open("training_outcomes.json", "w") as f:
    json.dump(outcomes, f, indent=2)

print(f"\nExported to:")
print(f"  training_decisions.json ({os.path.getsize('training_decisions.json')} bytes)")
print(f"  training_outcomes.json ({os.path.getsize('training_outcomes.json')} bytes)")
print(f"\nReady to train with:")
print(f"  python -m plugins.ftb_ml_policy training_decisions.json training_outcomes.json models/test_policy_v1.pth")
