#!/usr/bin/env python3
"""
FTB Upgrades - Code Validation Script
Validates that all implemented features have correct structure
"""

import sys
import re
from pathlib import Path

def validate_ftb_game():
    """Validate plugins/ftb_game.py has all required methods and fields"""
    print("=" * 70)
    print("VALIDATING: plugins/ftb_game.py")
    print("=" * 70)
    
    file_path = Path("plugins/ftb_game.py")
    if not file_path.exists():
        print("❌ ERROR: ftb_game.py not found!")
        return False
    
    content = file_path.read_text()
    
    checks = [
        # Morale System
        ("Morale baseline field", r"morale_baseline.*:.*float"),
        ("Morale last updated field", r"morale_last_updated.*:.*int"),
        ("Apply morale reversion method", r"def apply_morale_mean_reversion"),
        ("Calculate diminishing returns method", r"def calculate_morale_diminishing_returns"),
        ("MORALE_CONFIG constant", r"MORALE_CONFIG\s*=\s*{"),
        
        # Contract Enhancements
        ("Contract open_to_offers field", r"open_to_offers.*:.*bool"),
        ("Contract poaching_protection_until field", r"poaching_protection_until.*:.*Optional\[int\]"),
        ("Contract buyout_clause_fixed field", r"buyout_clause_fixed.*:.*Optional\[int\]"),
        ("Contract loyalty_factor field", r"loyalty_factor.*:.*float"),
        ("Contract is_poachable method", r"def is_poachable"),
        ("Contract calculate_buyout_amount method", r"def calculate_buyout_amount"),
        
        # Contract Openness Tracking
        ("Update contract openness method", r"def update_contract_openness_flags"),
        
        # AI Poaching
        ("Process AI poaching method", r"def process_ai_poaching_attempts"),
        
        # UI Refresh Controls
        ("Roster refresh button", r"Refresh.*roster"),
        ("Car refresh button", r"Refresh.*car"),
        ("Development refresh button", r"Refresh.*[Pp]rojects"),
        ("Infrastructure refresh button", r"Refresh.*infrastructure"),
        ("Sponsors refresh button", r"Refresh.*sponsors"),
        
        # Poachable Drivers UI
        ("Poachable Drivers tab", r"Poachable Drivers"),
        ("Refresh poachable drivers method", r"def _refresh_poachable_drivers"),
        ("Display poachable driver card method", r"def _display_poachable_driver_card"),
        ("Attempt driver poach method", r"def _attempt_driver_poach"),
        
        # Backend Handler
        ("ftb_poach_driver handler", r"ftb_poach_driver"),
        
        # Backward Compatibility
        ("Migration code", r"Backward compatibility.*morale_baseline"),
    ]
    
    passed = 0
    failed = 0
    
    for name, pattern in checks:
        if re.search(pattern, content, re.IGNORECASE):
            print(f"✅ {name}")
            passed += 1
        else:
            print(f"❌ {name} - NOT FOUND")
            failed += 1
    
    print()
    print(f"Result: {passed}/{len(checks)} checks passed")
    print()
    
    return failed == 0


def validate_narrator_plugin():
    """Validate plugins/meta/ftb_narrator_plugin.py has tick alignment features"""
    print("=" * 70)
    print("VALIDATING: plugins/meta/ftb_narrator_plugin.py")
    print("=" * 70)
    
    file_path = Path("plugins/meta/ftb_narrator_plugin.py")
    if not file_path.exists():
        print("❌ ERROR: ftb_narrator_plugin.py not found!")
        return False
    
    content = file_path.read_text()
    
    checks = [
        # Tick Alignment
        ("Sync current tick method", r"def _sync_current_tick"),
        ("Tick sync call in run_loop", r"self\._sync_current_tick\(\)"),
        
        # Event Purging
        ("Purge old events method", r"def _purge_old_events"),
        ("Tick-based purging", r"tick < current_tick - 10"),
        
        # Recency Multipliers
        ("Calculate recency multiplier method", r"def _calculate_event_recency_multiplier"),
        ("Apply recency boost method", r"def _apply_recency_boost_to_events"),
        ("Recency multiplier logic", r"tick_age == 0.*2\.0"),
        
        # Race Result Dominance
        ("Race result dominance check", r"has_fresh_race_result"),
        ("Race result dominance log", r"RACE RESULT DOMINANCE"),
        ("Race-focused segments", r"POST_RACE_COOLDOWN|RACE_ATMOSPHERE"),
        
        # Visual Debugging
        ("Freshness markers", r"🔥|⚡"),
    ]
    
    passed = 0
    failed = 0
    
    for name, pattern in checks:
        if re.search(pattern, content, re.IGNORECASE):
            print(f"✅ {name}")
            passed += 1
        else:
            print(f"❌ {name} - NOT FOUND")
            failed += 1
    
    print()
    print(f"Result: {passed}/{len(checks)} checks passed")
    print()
    
    return failed == 0


def validate_file_structure():
    """Validate key files exist"""
    print("=" * 70)
    print("VALIDATING: File Structure")
    print("=" * 70)
    
    required_files = [
        "plugins/ftb_game.py",
        "plugins/meta/ftb_narrator_plugin.py",
        "plugins/ftb_state_db.py",
        "FTB_UPGRADES_IMPLEMENTATION_PLAN.md",
        "PHASE1_EXECUTION_SUMMARY.md",
        "PHASE2_EXECUTION_SUMMARY.md",
        "NARRATOR_TICK_ALIGNMENT_IMPLEMENTATION.md",
        "PHASE3_TESTING_CHECKLIST.md",
    ]
    
    passed = 0
    failed = 0
    
    for file_path in required_files:
        path = Path(file_path)
        if path.exists():
            size = path.stat().st_size
            print(f"✅ {file_path} ({size:,} bytes)")
            passed += 1
        else:
            print(f"❌ {file_path} - NOT FOUND")
            failed += 1
    
    print()
    print(f"Result: {passed}/{len(required_files)} files found")
    print()
    
    return failed == 0


def main():
    """Run all validations"""
    print()
    print("╔" + "=" * 68 + "╗")
    print("║" + " FTB UPGRADES - CODE VALIDATION ".center(68) + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    results = []
    
    # File structure check
    results.append(("File Structure", validate_file_structure()))
    
    # Code validation
    results.append(("FTB Game Plugin", validate_ftb_game()))
    results.append(("Narrator Plugin", validate_narrator_plugin()))
    
    # Summary
    print("=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name:.<50} {status}")
    
    print()
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("🎉 ALL VALIDATIONS PASSED!")
        print()
        print("Next steps:")
        print("  1. Run the game: python shell.py")
        print("  2. Load or create a save file")
        print("  3. Follow PHASE3_TESTING_CHECKLIST.md")
        print()
        return 0
    else:
        print("⚠️  SOME VALIDATIONS FAILED")
        print()
        print("Please review the errors above and fix any issues.")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
