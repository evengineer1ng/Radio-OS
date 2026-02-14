#!/usr/bin/env python3
"""
Diagnostic script to check if budget/cashflow is working correctly
"""

import sys
import json

def check_budget_flow(save_path: str):
    """Check budget state in save file"""
    with open(save_path, 'r') as f:
        data = json.load(f)
    
    tick = data.get('tick', 0)
    player_team = data.get('player_team')
    
    if not player_team:
        print("❌ No player team found")
        return
    
    budget = player_team.get('budget', {})
    cash = budget.get('cash', 0)
    income_streams = budget.get('income_streams', [])
    staff_salaries = budget.get('staff_salaries', {})
    
    print(f"\n{'='*60}")
    print(f"BUDGET DIAGNOSTIC - {save_path}")
    print(f"{'='*60}")
    print(f"\nCurrent Tick: {tick}")
    print(f"Team: {player_team.get('name', 'Unknown')}")
    print(f"\n💰 Current Cash: ${cash:,.2f}")
    
    print(f"\n📈 Income Streams:")
    total_season_income = 0
    for stream in income_streams:
        name, amount, freq = stream
        total_season_income += amount
        print(f"  - {name}: ${amount:,.2f} per {freq}")
    
    print(f"\n  Total Season Income: ${total_season_income:,.2f}")
    print(f"  Income per tick (÷112): ${total_season_income / 112:,.2f}")
    
    print(f"\n💸 Staff Salaries (per tick):")
    total_payroll = sum(staff_salaries.values())
    for name, salary in staff_salaries.items():
        print(f"  - {name}: ${salary:,.2f}")
    print(f"\n  Total Payroll per tick: ${total_payroll:,.2f}")
    
    print(f"\n📊 Net Cashflow per tick:")
    income_per_tick = total_season_income / 112
    net = income_per_tick - total_payroll
    print(f"  Income: +${income_per_tick:,.2f}")
    print(f"  Payroll: -${total_payroll:,.2f}")
    print(f"  Net: {'+'if net >= 0 else ''}{net:,.2f} per tick")
    
    print(f"\n🔮 Expected Cash after 1 tick:")
    print(f"  Current: ${cash:,.2f}")
    print(f"  After 1 tick: ${cash + net:,.2f}")
    print(f"  Change: {'+'if net >= 0 else ''}{net:,.2f}")
    
    print(f"\n{'='*60}")
    
    # Check if values seem frozen
    if cash > 0 and abs(cash - round(cash, 2)) < 0.01:
        print(f"\n⚠️  Cash value appears to be a clean round number")
        print(f"   This might indicate it's not updating between ticks")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python check_budget.py <save_path>")
        print("\nExample:")
        print("  python check_budget.py saves/championshiprun.json")
        sys.exit(1)
    
    check_budget_flow(sys.argv[1])
