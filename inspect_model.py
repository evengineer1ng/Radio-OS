"""Inspect and test the trained ML model."""
import torch
from plugins.ftb_ml_policy import TeamPrincipalPolicy
import json
import os

# Check if model exists
model_path = "models/ftb_baseline_v1.pth"
if not os.path.exists(model_path):
    print(f"Model not found at: {model_path}")
    exit(1)

print(f"Loading model from: {model_path}")
print(f"File size: {os.path.getsize(model_path):,} bytes\n")

# Load the model
try:
    model = TeamPrincipalPolicy.load(model_path)
    print("✓ Model loaded successfully!\n")
except Exception as e:
    print(f"Error loading model: {e}")
    exit(1)

# Inspect model architecture
print("=" * 60)
print("MODEL ARCHITECTURE")
print("=" * 60)
print(model)
print()

# Count parameters
total_params = sum(p.numel() for p in model.parameters())
trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
print(f"Total parameters: {total_params:,}")
print(f"Trainable parameters: {trainable_params:,}\n")

# Test the model with sample data
print("=" * 60)
print("TESTING MODEL WITH SAMPLE DECISIONS")
print("=" * 60)

# Sample team state (mid-tier team, moderate budget)
sample_state = {
    'budget': 150000.0,
    'budget_ratio': 1.5,
    'num_drivers': 2,
    'num_engineers': 2,
    'num_mechanics': 3,
    'has_strategist': 0,
    'tier': 3,  # Formula X
    'championship_position': 8,
    'morale': 55.0,
    'reputation': 60.0
}

# Sample actions to evaluate
sample_actions = [
    {'name': 'hire_driver', 'cost': 50000, 'target': None},
    {'name': 'hire_engineer', 'cost': 30000, 'target': None},
    {'name': 'fire_driver', 'cost': 0, 'target': 0},
    {'name': 'develop_car', 'cost': 25000, 'target': None},
    {'name': 'purchase_part', 'cost': 15000, 'target': None},
]

# Sample principal stats (balanced manager)
principal_stats = {
    'financial_discipline': 55.0,
    'risk_tolerance': 50.0,
    'patience': 60.0
}

print("\nTeam State:")
print(f"  Budget: ${sample_state['budget']:,.0f}")
print(f"  Tier: {sample_state['tier']} (Formula X)")
print(f"  Position: {sample_state['championship_position']}")
print(f"  Staff: {sample_state['num_drivers']} drivers, {sample_state['num_engineers']} engineers, {sample_state['num_mechanics']} mechanics")

print("\nPrincipal Profile:")
print(f"  Financial Discipline: {principal_stats['financial_discipline']:.0f}")
print(f"  Risk Tolerance: {principal_stats['risk_tolerance']:.0f}")
print(f"  Patience: {principal_stats['patience']:.0f}")

print("\nAction Scores (higher = better):")
print("-" * 60)

# Score the actions
try:
    scores = model.score_actions(sample_state, sample_actions, principal_stats)
    
    # Sort by score
    scored_actions = list(zip(sample_actions, scores))
    scored_actions.sort(key=lambda x: x[1], reverse=True)
    
    for action, score in scored_actions:
        cost_str = f"${action['cost']:,}" if action['cost'] > 0 else "Free"
        print(f"  {action['name']:20s} {cost_str:>12s} → Score: {score:8.2f}")
    
    print(f"\n✓ Model recommends: {scored_actions[0][0]['name']} (score: {scored_actions[0][1]:.2f})")
    
except Exception as e:
    print(f"Error testing model: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("INSPECTION COMPLETE")
print("=" * 60)

# Show how to use in game
print("\nTo enable in your game:")
print("  1. Load model in game initialization:")
print("     from plugins.ftb_ml_policy import TeamPrincipalPolicy")
print("     state._ml_policy_model = TeamPrincipalPolicy.load('models/ftb_baseline_v1.pth')")
print("     state.ml_policy_enabled = True")
print("\n  2. AI teams will now use ML-based decision making!")
