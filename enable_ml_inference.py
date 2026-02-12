"""
Enable ML inference in your FTB save game.

This script loads the trained model and sets flags so AI teams 
use ML-guided decisions instead of pure rule-based scoring.

WARNING: Model was trained on only 234 decisions with fake success scores.
For production use, collect 1000-5000 real gameplay decisions first.
"""

import sqlite3
import sys
from pathlib import Path

# Import ML policy
try:
    from plugins.ftb_ml_policy import TeamPrincipalPolicy
except ImportError:
    print("❌ Cannot import ftb_ml_policy - torch not installed?")
    sys.exit(1)

def enable_ml_for_save(save_path: str, model_path: str = "models/ftb_baseline_v1.pth"):
    """Enable ML inference for a save game"""
    
    # Verify files exist
    save_file = Path(save_path)
    model_file = Path(model_path)
    
    if not save_file.exists():
        print(f"❌ Save file not found: {save_path}")
        return False
    
    if not model_file.exists():
        print(f"❌ Model file not found: {model_path}")
        return False
    
    # Load model to verify it works
    try:
        model = TeamPrincipalPolicy.load(model_path)
        print(f"✅ Loaded ML model: {model_path} ({model_file.stat().st_size:,} bytes)")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return False
    
    # Connect to save database
    try:
        conn = sqlite3.connect(save_path)
        cursor = conn.cursor()
        
        # Check if ml_config table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='ml_config'
        """)
        
        if not cursor.fetchone():
            # Create ml_config table
            cursor.execute("""
                CREATE TABLE ml_config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            print("✅ Created ml_config table")
        
        # Set ML-enabled flag and model path
        cursor.execute("""
            INSERT OR REPLACE INTO ml_config (key, value)
            VALUES ('ml_policy_enabled', 'true')
        """)
        
        cursor.execute("""
            INSERT OR REPLACE INTO ml_config (key, value)
            VALUES ('ml_model_path', ?)
        """, (model_path,))
        
        conn.commit()
        conn.close()
        
        print(f"""
✅ ML inference ENABLED for save: {save_path}

The game will now:
1. Load {model_path} at startup
2. Use ML policy for AI team decisions
3. Continue logging decisions for retraining

NOTE: The model was trained on limited data (234 decisions).
Watch for unusual AI behavior and collect more data for retraining.
        """)
        
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def disable_ml_for_save(save_path: str):
    """Disable ML inference for a save game"""
    try:
        conn = sqlite3.connect(save_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO ml_config (key, value)
            VALUES ('ml_policy_enabled', 'false')
        """)
        
        conn.commit()
        conn.close()
        
        print(f"✅ ML inference DISABLED for save: {save_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    # Example usage
    save_path = input("Enter path to your FTB save file: ").strip()
    
    if not save_path:
        print("Using default: stations/FromTheBackmarker/save.json")
        save_path = "stations/FromTheBackmarker/save.json"
    
    action = input("Enable or disable ML? (enable/disable): ").strip().lower()
    
    if action == "enable":
        enable_ml_for_save(save_path)
    elif action == "disable":
        disable_ml_for_save(save_path)
    else:
        print("❌ Invalid action. Use 'enable' or 'disable'")
