"""
FTB ML Policy - Team Principal Imitation Learning

PyTorch-based neural network for team principal decision-making.
Learns from successful team decisions via supervised imitation learning.

Architecture:
- StateEncoder: Encodes team state (budget, roster, standings) → 128-dim embedding
- ActionScorer: Scores actions given state embedding → action scores
- Training: MSE loss on action scores weighted by team success

Usage:
    from plugins.ftb_ml_policy import TeamPrincipalPolicy, train_policy
    
    # Train
    train_policy(training_data_path='data/ml_training/run_xxx_decisions.json',
                 outcomes_path='data/ml_training/run_xxx_outcomes.json',
                 checkpoint_path='stations/FromTheBackmarker/models/baseline_policy_v1.pth')
    
    # Inference
    policy = TeamPrincipalPolicy.load('stations/FromTheBackmarker/models/baseline_policy_v1.pth')
    scores = policy.score_actions(team_state, actions, principal_stats)
"""

import json
import numpy as np
from typing import Dict, List, Tuple, Any, Optional
from pathlib import Path

# Import PyTorch only when actually using the module
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import Dataset, DataLoader
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("[FTB ML Policy] Warning: PyTorch not installed - ML training/inference disabled")


# Plugin metadata
PLUGIN_NAME = "FTB ML Policy"
PLUGIN_DESC = "Machine-learned team principal decision policy"
IS_FEED = False


if TORCH_AVAILABLE:
    class TeamStateEncoder(nn.Module):
        """Encodes team state into fixed-size embedding."""
        
        def __init__(self, state_dim: int = 15, embedding_dim: int = 128):
            super().__init__()
            
            self.encoder = nn.Sequential(
                nn.Linear(state_dim, 64),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(64, 128),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(128, embedding_dim),
                nn.ReLU()
            )
    
    def forward(self, state_features: torch.Tensor) -> torch.Tensor:
        """
        Args:
            state_features: (batch, state_dim) tensor
        Returns:
            embeddings: (batch, embedding_dim) tensor
        """
        return self.encoder(state_features)


class ActionScorer(nn.Module):
    """Scores actions given state embedding and action features."""
    
    def __init__(self, state_embedding_dim: int = 128, action_dim: int = 5):
        super().__init__()
        
        combined_dim = state_embedding_dim + action_dim
        
        self.scorer = nn.Sequential(
            nn.Linear(combined_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1)
        )
    
    def forward(self, state_embedding: torch.Tensor, action_features: torch.Tensor) -> torch.Tensor:
        """
        Args:
            state_embedding: (batch, state_embedding_dim)
            action_features: (batch, action_dim)
        Returns:
            scores: (batch, 1) action quality scores
        """
        combined = torch.cat([state_embedding, action_features], dim=-1)
        return self.scorer(combined)


class TeamPrincipalPolicy(nn.Module):
    """Complete policy: state encoder + action scorer."""
    
    def __init__(self, state_dim: int = 15, action_dim: int = 5, embedding_dim: int = 128):
        super().__init__()
        
        self.state_encoder = TeamStateEncoder(state_dim, embedding_dim)
        self.action_scorer = ActionScorer(embedding_dim, action_dim)
        
        self.state_dim = state_dim
        self.action_dim = action_dim
    
    def forward(self, state_features: torch.Tensor, action_features: torch.Tensor) -> torch.Tensor:
        """
        Args:
            state_features: (batch, state_dim)
            action_features: (batch, action_dim)
        Returns:
            scores: (batch, 1)
        """
        state_embedding = self.state_encoder(state_features)
        scores = self.action_scorer(state_embedding, action_features)
        return scores
    
    def score_actions(
        self,
        team_state: Dict[str, float],
        actions: List[Dict[str, Any]],
        principal_stats: Optional[Dict[str, float]] = None
    ) -> List[float]:
        """
        Score a list of actions given current team state.
        
        Args:
            team_state: Dict with keys like 'budget', 'tier', 'championship_position', etc.
            actions: List of action dicts with 'name', 'cost', 'target'
            principal_stats: Optional principal personality stats (not used in base policy)
        
        Returns:
            List of scores (floats) for each action
        """
        self.eval()
        
        with torch.no_grad():
            # Encode team state
            state_tensor = self._encode_state(team_state)
            state_tensor = state_tensor.unsqueeze(0)  # (1, state_dim)
            
            # Encode and score each action
            scores = []
            for action in actions:
                action_tensor = self._encode_action(action)
                action_tensor = action_tensor.unsqueeze(0)  # (1, action_dim)
                
                score = self.forward(state_tensor, action_tensor)
                scores.append(float(score.item()))
        
        return scores
    
    def _encode_state(self, team_state: Dict[str, float]) -> torch.Tensor:
        """Convert team state dict to tensor."""
        features = [
            team_state.get('budget', 0.0) / 100000.0,  # Normalize to $100k
            team_state.get('budget_ratio', 0.0),
            float(team_state.get('num_drivers', 0)),
            float(team_state.get('num_engineers', 0)),
            float(team_state.get('num_mechanics', 0)),
            float(team_state.get('has_strategist', 0)),
            float(team_state.get('tier', 1)) / 5.0,  # Normalize to 0-1
            team_state.get('championship_position', 99) / 20.0,  # Normalize
            team_state.get('morale', 50.0) / 100.0,
            team_state.get('reputation', 50.0) / 100.0,
            # Pad to state_dim=15
            0.0, 0.0, 0.0, 0.0, 0.0
        ]
        return torch.tensor(features[:self.state_dim], dtype=torch.float32)
    
    def _encode_action(self, action: Dict[str, Any]) -> torch.Tensor:
        """Convert action dict to tensor."""
        # Action type encoding (one-hot-ish)
        action_name = action.get('name', 'unknown')
        action_type = 0.0
        if 'hire' in action_name:
            action_type = 1.0
        elif 'fire' in action_name:
            action_type = 2.0
        elif 'develop' in action_name:
            action_type = 3.0
        elif 'purchase' in action_name or 'buy' in action_name:
            action_type = 4.0
        elif 'upgrade' in action_name:
            action_type = 5.0
        
        features = [
            action_type / 5.0,  # Normalize
            action.get('cost', 0.0) / 100000.0,  # Normalize to $100k
            1.0 if action.get('target') else 0.0,
            # Pad to action_dim=5
            0.0, 0.0
        ]
        return torch.tensor(features[:self.action_dim], dtype=torch.float32)
    
    def save(self, path: str):
        """Save model checkpoint."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        torch.save({
            'state_dict': self.state_dict(),
            'state_dim': self.state_dim,
            'action_dim': self.action_dim
        }, path)
    
    @classmethod
    def load(cls, path: str) -> 'TeamPrincipalPolicy':
        """Load model from checkpoint."""
        checkpoint = torch.load(path, map_location='cpu')
        model = cls(
            state_dim=checkpoint.get('state_dim', 15),
            action_dim=checkpoint.get('action_dim', 5)
        )
        model.load_state_dict(checkpoint['state_dict'])
        return model


class DecisionDataset(Dataset):
    """Dataset of (state, action, score) tuples for training."""
    
    def __init__(self, decisions: List[Dict], outcomes: Dict[str, float]):
        """
        Args:
            decisions: List of decision dicts from ai_decisions table
            outcomes: Dict mapping team_id -> success_score
        """
        self.samples = []
        
        for decision in decisions:
            team_id = decision['team_id']
            success_score = outcomes.get(team_id, 0.0)
            
            # Skip if team was unsuccessful
            if success_score < 30.0:  # Threshold for "successful"
                continue
            
            state_vector = decision['state_vector']
            action_chosen = decision['action_chosen']
            
            # Get the score for the chosen action
            action_scores = decision.get('action_scores', {})
            base_score = action_scores.get(action_chosen['name'], 50.0)
            
            # Weight by team success
            weighted_score = base_score * (success_score / 50.0)
            
            self.samples.append({
                'state': state_vector,
                'action': action_chosen,
                'target_score': weighted_score
            })
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        
        # Encode state
        state_features = [
            sample['state'].get('budget', 0.0) / 100000.0,
            sample['state'].get('budget_ratio', 0.0),
            float(sample['state'].get('num_drivers', 0)),
            float(sample['state'].get('num_engineers', 0)),
            float(sample['state'].get('num_mechanics', 0)),
            float(sample['state'].get('has_strategist', 0)),
            float(sample['state'].get('tier', 1)) / 5.0,
            sample['state'].get('championship_position', 99) / 20.0,
            sample['state'].get('morale', 50.0) / 100.0,
            sample['state'].get('reputation', 50.0) / 100.0,
            0.0, 0.0, 0.0, 0.0, 0.0
        ]
        
        # Encode action
        action_name = sample['action'].get('name', 'unknown')
        action_type = 0.0
        if 'hire' in action_name:
            action_type = 1.0
        elif 'fire' in action_name:
            action_type = 2.0
        elif 'develop' in action_name:
            action_type = 3.0
        elif 'purchase' in action_name or 'buy' in action_name:
            action_type = 4.0
        elif 'upgrade' in action_name:
            action_type = 5.0
        
        action_features = [
            action_type / 5.0,
            sample['action'].get('cost', 0.0) / 100000.0,
            1.0 if sample['action'].get('target') else 0.0,
            0.0, 0.0
        ]
        
        return {
            'state': torch.tensor(state_features[:15], dtype=torch.float32),
            'action': torch.tensor(action_features[:5], dtype=torch.float32),
            'target_score': torch.tensor([sample['target_score']], dtype=torch.float32)
        }


def calculate_team_success_scores(outcomes: List[Dict]) -> Dict[str, float]:
    """
    Calculate success score for each team based on outcomes.
    
    Success = 0.3*solvency + 0.25*standing_stability + 0.25*roi + 0.2*survival
    """
    team_scores = {}
    
    for outcome in outcomes:
        team_id = outcome['team_id']
        
        # Solvency score (0-100)
        solvency = outcome['budget_health_score']
        
        # Standing stability (inverse of position, scaled)
        standing = 100.0 - (outcome['championship_position'] * 5.0)
        standing = max(0.0, min(100.0, standing))
        
        # ROI score (already 0-100)
        roi = outcome['roi_score']
        
        # Survival (binary -> 0 or 100)
        survival = 100.0 if outcome['survival_flag'] else 0.0
        
        # Weighted sum
        success_score = (
            0.3 * solvency +
            0.25 * standing +
            0.25 * roi +
            0.2 * survival
        )
        
        # Use max if team appears multiple times (multi-season)
        if team_id in team_scores:
            team_scores[team_id] = max(team_scores[team_id], success_score)
        else:
            team_scores[team_id] = success_score
    
    return team_scores


def train_policy(
    training_data_path: str,
    outcomes_path: str,
    checkpoint_path: str,
    epochs: int = 50,
    batch_size: int = 64,
    learning_rate: float = 0.001,
    validation_split: float = 0.2
):
    """
    Train team principal policy via imitation learning.
    
    Args:
        training_data_path: Path to decisions JSON
        outcomes_path: Path to outcomes JSON
        checkpoint_path: Where to save trained model
        epochs: Number of training epochs
        batch_size: Batch size for training
        learning_rate: Learning rate
        validation_split: Fraction of data for validation
    """
    print(f"[FTB ML] Training imitation learning policy...")
    print(f"  Data: {training_data_path}")
    print(f"  Outcomes: {outcomes_path}")
    
    # Load data
    with open(training_data_path, 'r') as f:
        decisions = json.load(f)
    with open(outcomes_path, 'r') as f:
        outcomes = json.load(f)
    
    print(f"  Loaded {len(decisions)} decisions, {len(outcomes)} outcomes")
    
    # Calculate success scores
    team_scores = calculate_team_success_scores(outcomes)
    print(f"  Calculated success scores for {len(team_scores)} teams")
    
    # Create dataset
    dataset = DecisionDataset(decisions, team_scores)
    print(f"  Created dataset with {len(dataset)} training samples")
    
    if len(dataset) == 0:
        print("[FTB ML] ERROR: No training samples! Check success criteria.")
        return
    
    # Split train/val
    val_size = int(len(dataset) * validation_split)
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = torch.utils.data.random_split(
        dataset, [train_size, val_size]
    )
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    # Create model
    model = TeamPrincipalPolicy()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.MSELoss()
    
    print(f"[FTB ML] Training for {epochs} epochs...")
    
    best_val_loss = float('inf')
    
    for epoch in range(epochs):
        # Training
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            optimizer.zero_grad()
            
            state = batch['state']
            action = batch['action']
            target = batch['target_score']
            
            pred = model(state, action)
            loss = criterion(pred, target)
            
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
        
        train_loss /= len(train_loader)
        
        # Validation
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for batch in val_loader:
                state = batch['state']
                action = batch['action']
                target = batch['target_score']
                
                pred = model(state, action)
                loss = criterion(pred, target)
                
                val_loss += loss.item()
        
        val_loss /= len(val_loader)
        
        # Print progress
        if (epoch + 1) % 5 == 0:
            print(f"  Epoch {epoch+1}/{epochs} - Train Loss: {train_loss:.4f} - Val Loss: {val_loss:.4f}")
        
        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            model.save(checkpoint_path)
            print(f"    Saved new best model (val_loss={val_loss:.4f})")
    
    print(f"[FTB ML] Training complete!")
    print(f"  Best validation loss: {best_val_loss:.4f}")
    print(f"  Model saved to: {checkpoint_path}")


# ============================================================================

# ============================================================================
# PLUGIN REGISTRATION (called by shell.py and runtime.py)
# ============================================================================

else:
    # Dummy implementations when PyTorch not available
    class TeamPrincipalPolicy:
        """Dummy policy class when PyTorch not available."""
        @staticmethod
        def load(path):
            raise ImportError("PyTorch not installed - cannot load ML policy")
        
        def score_actions(self, *args, **kwargs):
            raise ImportError("PyTorch not installed - cannot score actions")
    
    def train_policy(*args, **kwargs):
        """Dummy training function when PyTorch not available."""
        raise ImportError("PyTorch not installed - cannot train ML policy. Install with: pip install torch")


def register_widgets(registry, runtime_stub):
    """Register ML policy UI widgets (not currently used)."""
    pass


if __name__ == "__main__":
    # Example training run
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python ftb_ml_policy.py <decisions_json> <outcomes_json> [checkpoint_path]")
        sys.exit(1)
    
    decisions_path = sys.argv[1]
    outcomes_path = sys.argv[2]
    checkpoint_path = sys.argv[3] if len(sys.argv) > 3 else "models/baseline_policy_v1.pth"
    
    train_policy(decisions_path, outcomes_path, checkpoint_path)
