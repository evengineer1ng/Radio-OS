"""Quick script to check how much ML training data we have."""
from plugins.ftb_state_db import query_ai_decisions, query_team_outcomes

db_path = 'stations/FromTheBackmarker/ftb_state.db'

try:
    decisions = query_ai_decisions(db_path, limit=100000)
    outcomes = query_team_outcomes(db_path, limit=10000)
    
    print(f'\n=== ML Training Data Status ===')
    print(f'Decisions logged: {len(decisions)}')
    print(f'Season outcomes logged: {len(outcomes)}')
    print(f'Ready to train: {"YES - proceed with training" if len(decisions) >= 1000 else "Need more gameplay (recommend 5000+ decisions)"}')
    
    if len(decisions) > 0:
        # Show sample decision
        sample = decisions[0]
        print(f'\nSample decision:')
        print(f'  Team: {sample["team_name"]}')
        print(f'  Action: {sample["action_chosen"]["name"]}')
        print(f'  Season: {sample["season"]}')
    
    if len(outcomes) > 0:
        # Show sample outcome
        sample = outcomes[0]
        print(f'\nSample outcome:')
        print(f'  Team: {sample["team_name"]}')
        print(f'  Position: {sample["championship_position"]}')
        print(f'  Success Score: {sample["success_score"]:.2f}')
        
except Exception as e:
    print(f'Error checking data: {e}')
    print('Make sure you have run the simulation with ML logging enabled.')
