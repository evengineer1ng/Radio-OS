"""Check ML training data from latest generated database."""
from plugins.ftb_state_db import query_ai_decisions, query_team_outcomes
import os
import glob

# Find latest database
db_files = glob.glob("data/ml_training/*.db")
if not db_files:
    print("No databases found in data/ml_training/")
    exit(1)

latest_db = max(db_files, key=os.path.getmtime)
print(f"Latest database: {latest_db}")

try:
    decisions = query_ai_decisions(latest_db, limit=100000)
    outcomes = query_team_outcomes(latest_db, limit=10000)
    
    print(f'\n=== ML Training Data ===')
    print(f'Decisions logged: {len(decisions)}')
    print(f'Season outcomes logged: {len(outcomes)}')
    print(f'Ready to train: {"YES" if len(decisions) >= 1000 else "Need more data"}')
    
    if len(decisions) > 0:
        print(f'\nSample decision:')
        sample = decisions[0]
        print(f'  Team: {sample["team_name"]}')
        print(f'  Action: {sample["action_chosen"]["name"]}')
        print(f'  Season: {sample["season"]}')
        print(f'  Tick: {sample["tick"]}')
    
    if len(outcomes) > 0:
        print(f'\nSample outcome:')
        sample = outcomes[0]
        print(f'  Team: {sample["team_name"]}')
        print(f'  Position: {sample["championship_position"]}')
        print(f'  Success Score: {sample["success_score"]:.2f}')
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
