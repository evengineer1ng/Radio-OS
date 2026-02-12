"""
FromTheBackmarker RL Fine-Tuning Pipeline

Uses Proximal Policy Optimization (PPO) to fine-tune the imitation learning baseline.
Wraps the FTB simulation as an OpenAI Gym environment for RL training.

Requirements:
    pip install gym stable-baselines3

Usage:
    python tools/ftb_rl_trainer.py --checkpoint models/baseline_policy_v1.pth --output models/rl_policy_v1.pth
"""

import sys
import os
import argparse
import numpy as np
from pathlib import Path
from typing import Dict, Any, Tuple

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import gym
    from gym import spaces
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv
    from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
except ImportError:
    print("[FTB RL] ERROR: stable-baselines3 not installed. Run: pip install gym stable-baselines3")
    sys.exit(1)

import torch
import torch.nn as nn

# Import FTB simulation and ML policy
from plugins.ftb_game import FTBSimulation, SimState, Team, League, AIPrincipal
from plugins.ftb_ml_policy import TeamPrincipalPolicy


class FTBTeamEnv(gym.Env):
    """
    OpenAI Gym environment wrapper for FTB team principal simulation.
    
    State: Team state vector (budget, roster, standings, etc.)
    Action: Discrete action index (maps to hire/fire/develop/etc.)
    Reward: Change in team success score (budget health + performance + survival)
    """
    
    metadata = {'render.modes': ['human']}
    
    def __init__(self, initial_state: SimState, team_index: int = 0):
        super().__init__()
        
        self.state = initial_state
        self.team_index = team_index
        self.team = initial_state.ai_teams[team_index]
        
        self.initial_budget = self.team.budget.cash
        self.initial_position = self.team.standing_metrics.get('championship_position', 99)
        
        # Define action/observation spaces
        self.action_space = spaces.Discrete(20)  # Up to 20 possible action types
        
        # Observation: normalized team state (15 features)
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(15,), dtype=np.float32
        )
        
        self.episode_ticks = 0
        self.max_episode_ticks = 50  # ~1 season
    
    def reset(self) -> np.ndarray:
        """Reset environment to initial state."""
        # Restore initial team state
        self.team.budget.cash = self.initial_budget
        self.episode_ticks = 0
        
        return self._get_observation()
    
    def _get_observation(self) -> np.ndarray:
        """Convert team state to normalized observation vector."""
        obs = np.array([
            self.team.budget.cash / 100000.0,  # Budget normalized to $100k
            (self.team.budget.cash - self.initial_budget) / max(self.initial_budget, 1.0),  # Budget change
            len(self.team.drivers) / 2.0,  # Roster counts normalized
            len(self.team.engineers) / 3.0,
            len(self.team.mechanics) / 4.0,
            1.0 if self.team.strategist else 0.0,
            self.team.tier / 5.0,  # Tier normalized
            (99 - self.team.standing_metrics.get('championship_position', 99)) / 99.0,  # Position (higher = better)
            self.team.standing_metrics.get('morale', 50.0) / 100.0,
            self.team.standing_metrics.get('reputation', 50.0) / 100.0,
            self.episode_ticks / self.max_episode_ticks,  # Time in season
            0.0, 0.0, 0.0, 0.0  # Padding
        ], dtype=np.float32)
        
        return obs[:15]  # Ensure exactly 15 features
    
    def step(self, action_idx: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute one timestep.
        
        Args:
            action_idx: Discrete action index
        
        Returns:
            observation, reward, done, info
        """
        # Map action index to FTB action
        actions = FTBSimulation.get_available_actions(self.team, self.state)
        
        if action_idx < len(actions):
            chosen_action = actions[action_idx]
        else:
            # Invalid action, no-op
            chosen_action = None
        
        # Record pre-action state
        pre_budget = self.team.budget.cash
        pre_position = self.team.standing_metrics.get('championship_position', 99)
        
        # Execute action
        if chosen_action:
            try:
                events = FTBSimulation.apply_action(chosen_action, self.team, self.state)
            except Exception as e:
                print(f"[FTB RL Env] Action failed: {e}")
        
        # Advance simulation
        try:
            FTBSimulation.tick_simulation(self.state)
        except Exception as e:
            print(f"[FTB RL Env] Tick failed: {e}")
        
        self.episode_ticks += 1
        
        # Calculate reward
        reward = self._calculate_reward(pre_budget, pre_position)
        
        # Check if episode done
        done = self.episode_ticks >= self.max_episode_ticks or self.team.budget.cash < -50000
        
        # Info dict
        info = {
            'episode_ticks': self.episode_ticks,
            'budget': self.team.budget.cash,
            'position': self.team.standing_metrics.get('championship_position', 99)
        }
        
        return self._get_observation(), reward, done, info
    
    def _calculate_reward(self, pre_budget: float, pre_position: int) -> float:
        """
        Calculate reward signal for RL training.
        
        Reward = 0.3*Δbudget_health + 0.25*Δchampionship + 0.25*Δroi + 0.2*survival - 10*bankruptcy
        """
        post_budget = self.team.budget.cash
        post_position = self.team.standing_metrics.get('championship_position', 99)
        
        # Budget health change (normalized)
        budget_delta = (post_budget - pre_budget) / max(self.initial_budget, 1.0)
        budget_reward = budget_delta * 0.3
        
        # Championship position improvement (lower position = better)
        position_delta = (pre_position - post_position) / 99.0  # Normalize
        position_reward = position_delta * 0.25
        
        # ROI proxy: performance relative to spending
        # (Simplified: would need full season tracking)
        roi_reward = 0.0
        
        # Survival bonus
        survival_reward = 0.2 if post_budget > 0 else 0.0
        
        # Bankruptcy penalty
        bankruptcy_penalty = -10.0 if post_budget < -50000 else 0.0
        
        total_reward = budget_reward + position_reward + roi_reward + survival_reward + bankruptcy_penalty
        
        return float(total_reward)
    
    def render(self, mode='human'):
        """Render environment state (optional)."""
        print(f"Tick {self.episode_ticks}: Budget=${self.team.budget.cash:,.0f}, "
              f"Position={self.team.standing_metrics.get('championship_position', 99)}")


def make_ftb_env(num_teams: int = 10, tier: int = 3) -> DummyVecEnv:
    """
    Create vectorized FTB environment for RL training.
    
    Args:
        num_teams: Number of teams in league
        tier: Tier level (1-5)
    
    Returns:
        Vectorized gym environment
    """
    def _init():
        # Create minimal simulation state
        from plugins.ftb_state_db import init_db
        import tempfile
        
        state = SimState()
        state.state_db_path = tempfile.mktemp(suffix=".db")
        init_db(state.state_db_path)
        
        state.tick = 0
        state.season_number = 1
        state.sim_year = 2025
        state.sim_day_of_year = 1
        state.phase = "development"
        state.seed = f"rl_training_{np.random.randint(10000)}"
        
        # Create league with teams
        state.leagues = {}
        state.ai_teams = []
        
        league = League(league_id=f"tier_{tier}_rl", name=f"Tier {tier} RL Training", tier=tier)
        league.teams = []
        league.championship_table = {}
        league.schedule = []
        
        for i in range(num_teams):
            team = Team(name=f"RL_Team_{i}")
            team.team_id = f"rl_team_{i}"
            team.tier = tier
            team.budget.cash = 500000.0
            team.principal = AIPrincipal.FromArchetype("The Pragmatist", team.name)
            team.standing_metrics = {'championship_position': i + 1, 'morale': 50.0, 'reputation': 50.0}
            team.seasons_active = 1
            
            league.teams.append(team)
            state.ai_teams.append(team)
        
        state.leagues[league.league_id] = league
        
        # Initialize other components
        state.tracks = {}
        state.free_agent_pool = []
        state.parts_catalog = {}
        state.sponsorships = {t.name: [] for t in state.ai_teams}
        state.contracts = {}
        state._rngs = {}
        
        return FTBTeamEnv(state, team_index=0)
    
    return DummyVecEnv([_init])


def train_rl_policy(
    baseline_checkpoint: str,
    output_checkpoint: str,
    total_timesteps: int = 500000,
    eval_freq: int = 10000
):
    """
    Train RL policy via PPO, starting from IL baseline.
    
    Args:
        baseline_checkpoint: Path to imitation learning checkpoint
        output_checkpoint: Where to save RL-trained model
        total_timesteps: Total training timesteps
        eval_freq: Evaluation frequency
    """
    print(f"[FTB RL] Starting reinforcement learning training...")
    print(f"  Baseline: {baseline_checkpoint}")
    print(f"  Output: {output_checkpoint}")
    print(f"  Timesteps: {total_timesteps}")
    
    # Create environment
    env = make_ftb_env(num_teams=10, tier=3)
    
    # Create PPO agent
    model = PPO(
        "MlpPolicy",
        env,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        verbose=1,
        tensorboard_log="./logs/ftb_rl/"
    )
    
    # TODO: Initialize PPO policy with IL baseline weights (requires architecture matching)
    # For now, train from scratch
    
    # Setup callbacks
    eval_env = make_ftb_env(num_teams=10, tier=3)
    eval_callback = EvalCallback(
        eval_env,
        best_model_save_path=str(Path(output_checkpoint).parent),
        log_path="./logs/ftb_rl_eval/",
        eval_freq=eval_freq,
        deterministic=True,
        render=False
    )
    
    checkpoint_callback = CheckpointCallback(
        save_freq=50000,
        save_path=str(Path(output_checkpoint).parent / "rl_checkpoints"),
        name_prefix="ftb_rl"
    )
    
    # Train
    print("[FTB RL] Training PPO agent...")
    model.learn(
        total_timesteps=total_timesteps,
        callback=[eval_callback, checkpoint_callback]
    )
    
    # Save final model
    model.save(output_checkpoint)
    print(f"[FTB RL] Training complete! Model saved to: {output_checkpoint}")


def main():
    parser = argparse.ArgumentParser(description='RL fine-tuning for FTB team principals')
    parser.add_argument('--baseline', type=str, required=True,
                       help='Path to imitation learning baseline checkpoint')
    parser.add_argument('--output', type=str, default='models/rl_policy_v1.pth',
                       help='Output path for RL-trained model')
    parser.add_argument('--timesteps', type=int, default=500000,
                       help='Total training timesteps')
    parser.add_argument('--eval_freq', type=int, default=10000,
                       help='Evaluation frequency')
    
    args = parser.parse_args()
    
    train_rl_policy(
        baseline_checkpoint=args.baseline,
        output_checkpoint=args.output,
        total_timesteps=args.timesteps,
        eval_freq=args.eval_freq
    )


if __name__ == "__main__":
    main()
