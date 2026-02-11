"""
From the Backmarker - Racing Management Simulation Game Plugin

ONE comprehensive plugin containing:
- Entity system with full stat models (Driver ~26, Engineer ~24, etc.)
- Event system
- Economic system  
- Simulation engine (pure computation, NO LLM)
- Job board
- UI widget
- Feed worker (converts sim events to audio candidates)

Design principles:
- Simulation is pure math (no LLM calls)
- Money is the only constraint
- Time × Results × Role governs standing metrics
- No player stats, no archetypes
- ZenGM-style depth through multi-dimensional ratings
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from abc import ABC, abstractmethod
import random
import time
import json
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from enum import Enum


# ============================================================
# SECTION 1: Entity System
# ============================================================

STATS_SCHEMAS = {
    "Driver": {
        "pace": 50.0, "qualifying_pace": 50.0, "race_pace": 50.0,
        "low_fuel_performance": 50.0, "high_fuel_performance": 50.0,
        "tire_conservation": 50.0, "tire_warmup": 50.0, "wet_weather_skill": 50.0,
        "consistency": 50.0, "mistake_rate": 50.0, "recovery_from_error": 50.0,
        "stint_stability": 50.0, "fatigue_sensitivity": 50.0,
        "racecraft": 50.0, "overtaking_skill": 50.0, "defensive_skill": 50.0,
        "starts": 50.0, "spatial_awareness": 50.0,
        "adaptability": 50.0, "learning_rate": 50.0, "track_learning_speed": 50.0,
        "regulation_adaptation": 50.0,
        "feedback_quality": 50.0, "technical_language_alignment": 50.0,
        "setup_sensitivity": 50.0,
        "pressure_handling": 50.0, "confidence_volatility": 50.0,
        "aggression": 50.0, "discipline": 50.0, "ego": 50.0, "political_awareness": 50.0
    },
    "Engineer": {
        "technical_depth": 50.0, "systems_thinking": 50.0, "aero_understanding": 50.0,
        "mechanical_understanding": 50.0, "powertrain_understanding": 50.0,
        "innovation_bias": 50.0, "concept_generation_rate": 50.0, "upgrade_effectiveness": 50.0,
        "upgrade_scalability": 50.0, "regulation_interpretation": 50.0,
        "correlation_accuracy": 50.0, "simulation_fidelity": 50.0, "trackside_translation": 50.0,
        "data_noise_tolerance": 50.0,
        "iteration_speed": 50.0, "delivery_discipline": 50.0, "project_management": 50.0,
        "failure_recovery_speed": 50.0, "reliability_focus": 50.0,
        "communication": 50.0, "driver_alignment": 50.0, "cross_department_alignment": 50.0,
        "knowledge_transfer": 50.0
    },
    "Mechanic": {
        "build_quality": 50.0, "assembly_precision": 50.0, "component_handling": 50.0,
        "torque_discipline": 50.0, "pre_race_preparation": 50.0,
        "pit_execution": 50.0, "coordination": 50.0, "reaction_time": 50.0,
        "tool_familiarity": 50.0, "procedure_adherence": 50.0,
        "error_rate": 50.0, "error_detection_speed": 50.0, "error_recovery_quality": 50.0,
        "rework_efficiency": 50.0,
        "fatigue_resistance": 50.0, "stress_handling": 50.0, "burnout_rate": 50.0,
        "focus_retention": 50.0, "weekend_consistency": 50.0, "morale": 50.0
    },
    "Strategist": {
        "race_reading": 50.0, "situational_awareness": 50.0, "traffic_modeling": 50.0,
        "gap_estimation": 50.0, "opponent_intent_reading": 50.0,
        "tire_modeling": 50.0, "degradation_prediction": 50.0, "weather_forecasting": 50.0,
        "safety_car_prediction": 50.0, "virtual_safety_car_modeling": 50.0,
        "risk_calibration": 50.0, "reward_estimation": 50.0, "commitment_threshold": 50.0,
        "plan_flexibility": 50.0, "contingency_depth": 50.0,
        "timing_sense": 50.0, "pit_window_precision": 50.0, "call_latency": 50.0,
        "multi_car_coordination": 50.0, "morale": 50.0
    },
    "AIPrincipal": {
        "aggression": 50.0, "risk_tolerance": 50.0, "patience": 50.0,
        "long_term_orientation": 50.0, "short_term_pressure_response": 50.0,
        "financial_discipline": 50.0, "budget_forecasting_accuracy": 50.0,
        "capital_allocation_balance": 50.0, "cost_cap_management": 50.0, "liquidity_conservatism": 50.0,
        "talent_evaluation_accuracy": 50.0, "talent_strategy": 50.0, "succession_planning": 50.0,
        "staff_loyalty_bias": 50.0, "ruthlessness": 50.0,
        "organizational_cohesion": 50.0, "culture_resilience": 50.0, "burnout_mitigation": 50.0,
        "crisis_management": 50.0,
        "political_instinct": 50.0, "media_management": 50.0, "regulatory_navigation": 50.0,
        "supplier_relationship_management": 50.0
    },
    "Car": {
        "aero_efficiency": 50.0, "downforce_peak": 50.0, "downforce_consistency": 50.0,
        "drag": 50.0, "power_output": 50.0, "power_delivery_smoothness": 50.0,
        "mechanical_grip": 50.0, "platform_stability": 50.0,
        "driveability": 50.0, "setup_window": 50.0, "ride_height_sensitivity": 50.0,
        "balance_sensitivity": 50.0,
        "reliability": 50.0, "thermal_tolerance": 50.0, "component_wear_rate": 50.0,
        "failure_mode_severity": 50.0,
        "upgrade_sensitivity": 50.0, "upgrade_synergy": 50.0, "concept_coherence": 50.0,
        "development_ceiling": 50.0, "regulation_resilience": 50.0
    }
}

@dataclass
class Entity:
    """
    Base entity with universal meta-properties.
    Growth/decay mechanics applied uniformly by simulation.
    """
    name: str = ""
    age: int = 20
    
    # Universal meta-properties (with defaults)
    potential_ceiling: float = field(default=100.0)  # Max achievable ability
    decay_rate: float = field(default=0.5)  # How quickly ability degrades post-peak
    variance_band: float = field(default=5.0)  # Performance noise
    form_momentum: float = field(default=0.0)  # Short-term streak effect
    
    # Current ratings (canonical source of truth)
    current_ratings: Dict[str, float] = field(default_factory=dict)
    
    # Performance history for time-series analysis
    performance_history: List[Tuple[int, Dict[str, float]]] = field(default_factory=list)
    
    def __post_init__(self):
        # Initialize current_ratings from schema if empty
        if not self.current_ratings:
            cls_name = self.__class__.__name__
            if cls_name in STATS_SCHEMAS:
                # Copy defaults
                self.current_ratings = STATS_SCHEMAS[cls_name].copy()

    def __getattr__(self, name: str) -> Any:
        # Proxy access to current_ratings keys
        if "current_ratings" in self.__dict__ and name in self.current_ratings:
            return self.current_ratings[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
    def __setattr__(self, name: str, value: Any) -> None:
        # Intercept writes to stats to update current_ratings
        cls_name = self.__class__.__name__
        if cls_name in STATS_SCHEMAS and name in STATS_SCHEMAS[cls_name]:
            if "current_ratings" in self.__dict__:
                self.current_ratings[name] = value
                return
        super().__setattr__(name, value)
    
    def update_growth(self, context: Dict[str, Any]) -> None:
        """Apply potential progression based on context."""
        # Peak age curves vary by entity type
        # Default implementation - override in subclasses for specific curves
        peak_age = context.get('peak_age', 30)
        age_factor = 1.0 - abs(self.age - peak_age) / 20.0
        age_factor = max(0.1, min(1.0, age_factor))
        
        # Apply momentum from recent results
        momentum = self.form_momentum
        stability = context.get('team_stability', 0.5)
        
        # Growth rate
        base_growth = 0.1 * age_factor * stability
        momentum_boost = momentum * 0.05
        
        # Update ratings toward potential ceiling
        for stat_name, current_value in self.current_ratings.items():
            if current_value < self.potential_ceiling:
                potential_remaining = (self.potential_ceiling - current_value) / 100.0
                growth = base_growth * potential_remaining + momentum_boost
                new_value = current_value + growth
                self.current_ratings[stat_name] = max(1.0, min(99.0, new_value))
    
    def apply_decay(self) -> None:
        """Apply decline pressure based on age and decay_rate."""
        # Simple post-peak decline
        peak_age = 30  # Override in subclasses
        if self.age > peak_age:
            years_past_peak = self.age - peak_age
            decay_amount = self.decay_rate * (years_past_peak / 10.0)
            
            for stat_name in self.current_ratings:
                self.current_ratings[stat_name] -= decay_amount
                self.current_ratings[stat_name] = max(1.0, self.current_ratings[stat_name])
    
    def get_expected_performance(self, context: Dict[str, Any], rng: random.Random) -> float:
        """Calculate expected performance from ratings."""
        # Weight relevant stats by context
        # Base implementation: average all ratings
        if not self.current_ratings:
            return 50.0
        
        total = sum(self.current_ratings.values())
        avg = total / len(self.current_ratings)
        
        # Add variance
        variance = rng.uniform(-self.variance_band, self.variance_band)
        
        # Add form momentum
        momentum_effect = self.form_momentum * 5.0
        
        result = avg + variance + momentum_effect
        return max(0.0, min(100.0, result))
    
    # ============================================
    # Derived Metric Aggregation Layer
    # ============================================
    
    @property
    def overall_rating(self) -> float:
        """Average of all current ratings - universal quality metric"""
        if not self.current_ratings:
            return 50.0
        return sum(self.current_ratings.values()) / len(self.current_ratings)
    
    @property
    def potential_rating(self) -> float:
        """Projected rating at peak potential"""
        return min(self.overall_rating + (self.potential_ceiling - self.overall_rating), 100.0)
    
    @property
    def peak_age_range(self) -> Tuple[int, int]:
        """Expected peak age range for this entity type (override in subclasses)"""
        return (27, 32)  # Default for drivers


@dataclass
class Driver(Entity):
    """~26 stats - high-impact human entity"""
    
    # Required base fields (must come first)
    name: str = ""
    age: int = 20
    
    # Stats are defined in STATS_SCHEMAS["Driver"]
    # No local fields needed - Entity canonicalizes them
    
    # Driver-specific derived metrics
    @property
    def raw_pace(self) -> float:
        """Pure speed ability (qualifying + race + overall pace)"""
        return (
            self.current_ratings.get('pace', 50.0) +
            self.current_ratings.get('qualifying_pace', 50.0) +
            self.current_ratings.get('race_pace', 50.0)
        ) / 3.0
    
    @property
    def risk_profile(self) -> float:
        """Tendency toward mistakes and aggression (higher = riskier)"""
        return (
            self.current_ratings.get('aggression', 50.0) +
            self.current_ratings.get('mistake_rate', 50.0) -
            self.current_ratings.get('discipline', 50.0)
        ) / 3.0 + 50.0
    
    @property
    def execution_quality(self) -> float:
        """Consistency and error recovery ability"""
        return (
            self.current_ratings.get('consistency', 50.0) +
            self.current_ratings.get('recovery_from_error', 50.0) +
            self.current_ratings.get('spatial_awareness', 50.0)
        ) / 3.0


@dataclass  
class Engineer(Entity):
    """~24 stats - long-horizon human entity"""
    
    # Required base fields
    name: str = ""
    age: int = 25
    
    # Stats definitions removed - canonicalized in Entity.current_ratings
    
    # Engineer-specific derived metrics
    @property
    def technical_depth_score(self) -> float:
        """Overall technical understanding across domains"""
        return (
            self.current_ratings.get('technical_depth', 50.0) +
            self.current_ratings.get('aero_understanding', 50.0) +
            self.current_ratings.get('mechanical_understanding', 50.0) +
            self.current_ratings.get('systems_thinking', 50.0)
        ) / 4.0
    
    @property
    def development_velocity(self) -> float:
        """Speed and effectiveness of development work"""
        return (
            self.current_ratings.get('iteration_speed', 50.0) +
            self.current_ratings.get('upgrade_effectiveness', 50.0) +
            self.current_ratings.get('delivery_discipline', 50.0)
        ) / 3.0
    
    @property
    def correlation_reliability(self) -> float:
        """Accuracy of simulations to reality"""
        return (
            self.current_ratings.get('correlation_accuracy', 50.0) +
            self.current_ratings.get('simulation_fidelity', 50.0) +
            self.current_ratings.get('trackside_translation', 50.0)
        ) / 3.0


@dataclass
class Mechanic(Entity):
    """~22 stats - execution-focused entity"""
    
    # Required base fields
    name: str = ""
    age: int = 22
    
    # Stats definitions removed - canonicalized in Entity.current_ratings
    
    # Mechanic-specific derived metrics
    @property
    def build_quality_score(self) -> float:
        """Preparation and assembly quality"""
        return (
            self.current_ratings.get('build_quality', 50.0) +
            self.current_ratings.get('assembly_precision', 50.0) +
            self.current_ratings.get('pre_race_preparation', 50.0)
        ) / 3.0
    
    @property
    def pit_execution_score(self) -> float:
        """Live pit stop performance"""
        return (
            self.current_ratings.get('pit_execution', 50.0) +
            self.current_ratings.get('coordination', 50.0) +
            self.current_ratings.get('reaction_time', 50.0)
        ) / 3.0


@dataclass
class Strategist(Entity):
    """~23 stats - shapes outcomes without touching car"""
    
    # Required base fields
    name: str = ""
    age: int = 30
    
    # Stats definitions removed - canonicalized in Entity.current_ratings
    
    # Strategist-specific derived metrics
    @property
    def situational_iq(self) -> float:
        """Awareness and race reading ability"""
        return (
            self.current_ratings.get('race_reading', 50.0) +
            self.current_ratings.get('situational_awareness', 50.0) +
            self.current_ratings.get('traffic_modeling', 50.0)
        ) / 3.0
    
    @property
    def decision_speed(self) -> float:
        """Timing and reaction quality"""
        return (
            self.current_ratings.get('timing_sense', 50.0) +
            self.current_ratings.get('call_latency', 50.0) +
            self.current_ratings.get('pit_window_precision', 50.0)
        ) / 3.0


@dataclass
class AIPrincipal(Entity):
    """~25 stats - organizational state & tendency vector (NOT intelligence)"""
    
    # Required base fields
    name: str = ""
    age: int = 45
    
    # Stats definitions removed - canonicalized in Entity.current_ratings


@dataclass
class Car(Entity):
    """~24 stats - stateful, season-bound artifact"""
    
    # Required base fields (cars don't age like humans)
    name: str = ""
    age: int = 0
    
    # Versioning
    version: int = 1
    
    # Stats definitions removed - canonicalized in Entity.current_ratings
    
    # Car-specific derived metrics
    @property
    def performance_envelope(self) -> float:
        """Raw speed potential"""
        return (
            self.current_ratings.get('aero_efficiency', 50.0) +
            self.current_ratings.get('downforce_peak', 50.0) +
            self.current_ratings.get('power_output', 50.0) +
            self.current_ratings.get('mechanical_grip', 50.0)
        ) / 4.0
    
    @property
    def usability(self) -> float:
        """Driver friendliness and setup window"""
        return (
            self.current_ratings.get('driveability', 50.0) +
            self.current_ratings.get('setup_window', 50.0) +
            self.current_ratings.get('platform_stability', 50.0)
        ) / 3.0
    
    @property
    def reliability_score(self) -> float:
        """Likelihood of finishing races"""
        return self.current_ratings.get('reliability', 50.0)


# ============================================================
# SECTION 2: Event System
# ============================================================

@dataclass
class SimEvent:
    """Atomic unit of simulation change"""
    event_type: str  # "time", "structural", "outcome", "opportunity", "pressure", "consequence"
    category: str  # "race_result", "contract_expiry", "financial_stress", etc.
    ts: int  # Simulation timestamp
    priority: float  # For audio narration importance
    severity: str = "info"  # Severity level for event routing
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: int = 0  # Auto-incrementing unique identifier
    caused_by: Optional[int] = None  # Parent event ID for causality tracking


@dataclass
class DecisionOption:
    """Single option within a decision"""
    id: str
    label: str
    cost: float = 0.0
    description: str = ""
    consequence_preview: str = ""


@dataclass
class DecisionEvent:
    """
    Multi-option decision requiring player response.
    Blocks certain actions until resolved.
    """
    decision_id: str
    category: str  # "ownership_ultimatum", "fire_sale", "staff_poaching", etc.
    prompt: str  # Main decision question
    options: List[DecisionOption]
    deadline_tick: int  # Auto-resolve if unresolved by this tick
    auto_resolve_option_id: str  # Which option to pick on timeout
    created_tick: int
    resolved: bool = False
    chosen_option_id: Optional[str] = None


class SimEventBus:
    """Priority queue for simulation events"""
    
    def __init__(self):
        self._queue: List[SimEvent] = []
        self._history: List[SimEvent] = []
    
    def enqueue(self, event: SimEvent) -> None:
        """Add event to queue, sorted by priority"""
        self._queue.append(event)
        self._queue.sort(key=lambda e: e.priority, reverse=True)
        self._history.append(event)
    
    def dequeue(self) -> Optional[SimEvent]:
        """Pop highest priority event"""
        return self._queue.pop(0) if self._queue else None
    
    def peek_next(self) -> Optional[SimEvent]:
        """Look at next event without removing"""
        return self._queue[0] if self._queue else None
    
    def clear(self) -> None:
        """Clear all queued events"""
        self._queue.clear()


# Event taxonomy constants
TIME_EVENTS = ["advance_day", "advance_week", "enter_race_weekend", "exit_race_weekend", 
               "enter_offseason", "regulation_cycle"]

STRUCTURAL_EVENTS = ["new_car", "regulation_change", "team_entry", "team_exit", 
                     "engine_supplier_change"]

OUTCOME_EVENTS = ["race_result", "championship_result", "dev_success", "dev_failure",
                  "financial_gain", "financial_loss", "contract_signed", "contract_break"]

OPPORTUNITY_EVENTS = ["contract_expiry", "job_listing", "sponsor_offer", 
                     "staff_available", "regulation_loophole"]


# ============================================================
# SECTION 3: Economic System
# ============================================================

# Infrastructure upkeep cost tiers (per tick)
INFRASTRUCTURE_UPKEEP_COST = {
    'factory_quality': lambda quality: quality * 10.0,  # $500/tick for 50 quality
    'wind_tunnel': lambda quality: quality * 8.0,       # $400/tick for 50 quality
    'simulator': lambda quality: quality * 6.0,         # $300/tick for 50 quality
}

# Suggested salary ranges per entity type (annual, divided by ~50 ticks/year)
SALARY_BASE = {
    'Driver': 200.0,       # $200/tick base (~10k/year)
    'Engineer': 100.0,     # $100/tick base (~5k/year)
    'Mechanic': 80.0,      # $80/tick base (~4k/year)
    'Strategist': 120.0,   # $120/tick base (~6k/year)
    'AIPrincipal': 150.0,  # $150/tick base (~7.5k/year)
}

@dataclass
class IncomeSource:
    """Represents an income stream"""
    name: str
    amount: float
    frequency: str  # "per_race", "per_season", "monthly"


class Budget:
    """Money-based constraint system"""
    
    def __init__(self, cash: float = 100000.0):
        self.cash = cash
        self.burn_rate = 0.0  # Per sim-tick (generic expenses)
        self.committed_spend: List[Tuple[int, float]] = []  # (tick_due, amount)
        self.income_streams: List[IncomeSource] = []
        
        # Staff salary tracking (entity: salary_per_tick)
        self.staff_salaries: Dict[str, float] = {}
    
    def can_afford(self, cost: float) -> bool:
        """Check if action is financially legal"""
        return self.cash >= cost
    
    def commit(self, amount: float, duration: int) -> None:
        """Commit to future obligation"""
        self.committed_spend.append((duration, amount))
    
    def advance_tick(self, current_tick: int) -> None:
        """Apply burn rate and resolve commitments"""
        self.cash -= self.burn_rate
        
        # Resolve due commitments
        due = [amt for tick, amt in self.committed_spend if tick <= current_tick]
        for amt in due:
            self.cash -= amt
        self.committed_spend = [(t, amt) for t, amt in self.committed_spend 
                               if t > current_tick]
    
    def calculate_staff_payroll(self) -> float:
        """Calculate total staff payroll per tick"""
        return sum(self.staff_salaries.values())
    
    def add_staff_salary(self, entity_name: str, salary: float) -> None:
        """Add or update staff salary"""
        self.staff_salaries[entity_name] = salary
    
    def remove_staff_salary(self, entity_name: str) -> None:
        """Remove staff salary when entity leaves"""
        if entity_name in self.staff_salaries:
            del self.staff_salaries[entity_name]


class Action:
    """Base class for all managerial actions"""
    
    def __init__(self, name: str, cost: float, opportunity_cost: Optional[str] = None, target: Any = None):
        self.name = name
        self.cost = cost
        self.opportunity_cost = opportunity_cost
        self.target = target  # Entity ID, role name, or other action parameter
    
    def is_legal(self, budget: Budget, team_state: Any) -> bool:
        """Check if action is legal given current constraints"""
        return budget.can_afford(self.cost)


# ============================================================
# SECTION 4: State Container
# ============================================================

class Team:
    """Team state container"""
    
    def __init__(self, name: str):
        self.name = name
        self.budget = Budget()
        self.drivers: List[Driver] = []
        self.engineers: List[Engineer] = []
        self.mechanics: List[Mechanic] = []
        self.strategist: Optional[Strategist] = None
        self.principal: Optional[AIPrincipal] = None  # None if player-controlled
        self.car: Car = Car(name=f"{name} Car")
        self.infrastructure: Dict[str, float] = {
            'factory_quality': 50.0,
            'wind_tunnel': 50.0,
            'simulator': 50.0,
        }
        # Standing metrics (Time × Results × Role)
        self.standing_metrics: Dict[str, float] = {
            'legitimacy': 50.0,
            'reputation': 50.0,
            'media_standing': 50.0,
            'ownership_confidence': 50.0,
            'political_capital': 50.0,
            'morale': 50.0,
        }
    
    def add_entity_with_salary(self, entity: Entity) -> None:
        """Add entity to team and calculate salary based on overall rating"""
        entity_type = type(entity).__name__
        
        # Calculate salary: base + bonus for rating above 50
        base_salary = SALARY_BASE.get(entity_type, 100.0)
        rating_multiplier = entity.overall_rating / 50.0  # 50 rating = 1x, 75 rating = 1.5x
        salary_per_tick = base_salary * rating_multiplier
        
        # Add to appropriate roster
        if isinstance(entity, Driver):
            self.drivers.append(entity)
        elif isinstance(entity, Engineer):
            self.engineers.append(entity)
        elif isinstance(entity, Mechanic):
            self.mechanics.append(entity)
        elif isinstance(entity, Strategist):
            self.strategist = entity
        elif isinstance(entity, AIPrincipal):
            self.principal = entity
        
        # Register salary
        self.budget.add_staff_salary(entity.name, salary_per_tick)
    
    def remove_entity(self, entity: Entity) -> None:
        """Remove entity from team and cancel salary"""
        # Remove from roster
        if isinstance(entity, Driver) and entity in self.drivers:
            self.drivers.remove(entity)
        elif isinstance(entity, Engineer) and entity in self.engineers:
            self.engineers.remove(entity)
        elif isinstance(entity, Mechanic) and entity in self.mechanics:
            self.mechanics.remove(entity)
        elif isinstance(entity, Strategist) and entity == self.strategist:
            self.strategist = None
        elif isinstance(entity, AIPrincipal) and entity == self.principal:
            self.principal = None
        
        # Cancel salary
        self.budget.remove_staff_salary(entity.name)


class League:
    """League structure"""
    
    def __init__(self, name: str, tier: int, tier_name: str = "grassroots"):
        self.name = name
        self.tier = tier  # 1-5 (1=Grassroots, 5=Formula Z)
        self.tier_name = tier_name
        self.teams: List[Team] = []
        self.schedule: List[int] = [] # List of tick numbers when races occur
        self.standings: Dict[str, float] = {} # TeamID -> Points (legacy, use championship_table)
        self.championship_table: Dict[str, float] = {}  # Team name -> season points
        self.races_this_season: int = 0  # Counter for season end detection


class JobListing:
    """Job board entry"""
    
    def __init__(self, team: Team, role: str, expectation_band: str, 
                 patience_profile: float, risk_profile: float):
        self.team = team
        self.role = role
        self.expectation_band = expectation_band
        self.patience_profile = patience_profile
        self.risk_profile = risk_profile


class JobBoard:
    """Labor market primitive"""
    
    def __init__(self):
        self.vacancies: List[JobListing] = []
    
    def add_vacancy(self, listing: JobListing) -> None:
        self.vacancies.append(listing)
    
    def remove_vacancy(self, listing: JobListing) -> None:
        if listing in self.vacancies:
            self.vacancies.remove(listing)
    
    def filter_visible_to_player(self, player_metrics: Dict[str, float]) -> List[JobListing]:
        """Filter vacancies based on player standing"""
        # Visibility depends on legitimacy, reputation, last exit severity
        legitimacy = player_metrics.get('legitimacy', 50.0)
        reputation = player_metrics.get('reputation', 50.0)
        
        visible = []
        for listing in self.vacancies:
            # Simple threshold model (can be expanded)
            required_legitimacy = 30.0 if listing.expectation_band == "low" else 60.0
            if legitimacy >= required_legitimacy:
                visible.append(listing)
        
        return visible
    
    def apply_for_job(self, state: 'SimState', player_metrics: Dict[str, float], listing: JobListing) -> bool:
        """Apply for job - probabilistic acceptance with competing candidates"""
        legitimacy = player_metrics.get('legitimacy', 50.0)
        reputation = player_metrics.get('reputation', 50.0)
        
        # Simple acceptance model
        base_chance = 0.5
        legitimacy_modifier = (legitimacy - 50.0) / 100.0
        reputation_modifier = (reputation - 50.0) / 100.0
        
        acceptance_chance = base_chance + legitimacy_modifier + reputation_modifier
        acceptance_chance = max(0.1, min(0.9, acceptance_chance))
        
        return state.rng.random() < acceptance_chance


class SimState:
    """Unified simulation state"""
    
    def __init__(self):
        self.tick: int = 0
        self.phase: str = "offseason"  # offseason, race_weekend, development
        
        # Calendar tracking
        self.sim_year: int = 1
        self.sim_day_of_year: int = 1
        self.days_per_tick: int = 1  # Daily ticks (ZenGM style)
        self.days_per_year: int = 365
        
        # Season tracking
        self.races_completed_this_season: int = 0
        self.season_number: int = 1
        self.in_offseason: bool = False
        self.offseason_ticks_remaining: int = 0
        
        self.player_team: Optional[Team] = None
        self.player_identity: List[str] = []  # 5 typed answers from "who are you?"
        self.player_focus: Optional[str] = None  # "what to focus on?"
        self.time_mode: str = "paused" # "paused", "auto", "manual"
        self.control_mode: str = "human"  # "human" or "delegated"
        self.save_mode: str = "replayable"  # "replayable" or "permanent"
        self.seed: int = 42  # RNG seed for deterministic replay
        
        # RNG Streams for determinism
        self.rngs: Dict[str, random.Random] = {
            "master": random.Random(42),
            "race": random.Random(42),
            "dev": random.Random(42),
            "contracts": random.Random(42),
            "world": random.Random(42)
        }
        
        self.ai_teams: List[Team] = []
        self.leagues: Dict[str, League] = {}
        self.job_board = JobBoard()
        self.event_history: List[SimEvent] = []
        self.world_state: Dict[str, Any] = {}
        self.pending_developments: List[Dict[str, Any]] = []  # List of {team_name, resolve_tick, cost, engineer_bonus}
        self.pending_decisions: List[DecisionEvent] = []  # Active decisions awaiting player response
        self._next_event_id: int = 1  # Auto-incrementing event ID counter

    def get_rng(self, stream: str, context: Any = None) -> random.Random:
        """Get a deterministic RNG seeded by (master_seed + tick + stream + context)."""
        import hashlib
        input_str = f"{self.seed}:{self.tick}:{stream}:{str(context)}"
        # Stable seed generation
        seed_int = int(hashlib.md5(input_str.encode()).hexdigest(), 16)
        return random.Random(seed_int)
    
    def current_date_str(self) -> str:
        """Return formatted calendar date"""
        return f"Year {self.sim_year}, Day {self.sim_day_of_year}"
    
    def advance_calendar(self) -> List[SimEvent]:
        """Advance calendar and return birthday events when entities age"""
        events = []
        
        # Increment calendar
        self.sim_day_of_year += self.days_per_tick
        
        # Check for year rollover
        if self.sim_day_of_year > self.days_per_year:
            self.sim_day_of_year = 1
            self.sim_year += 1
            
            # Age all human entities (not cars) when year rolls over
            all_teams = [self.player_team] + self.ai_teams if self.player_team else self.ai_teams
            
            for team in all_teams:
                if team is None:
                    continue
                
                # Process human entities only (drivers, engineers, mechanics, strategists, principals)
                entities_to_age = (
                    team.drivers + 
                    team.engineers + 
                    team.mechanics + 
                    ([team.strategist] if team.strategist else []) +
                    ([team.principal] if team.principal else [])
                )
                
                for entity in entities_to_age:
                    if entity is None or isinstance(entity, Car):
                        continue
                    
                    # Increment age
                    entity.age += 1
                    
                    # Generate birthday event
                    events.append(SimEvent(
                        event_type="time",
                        category="entity_birthday",
                        ts=self.tick,
                        priority=10.0,
                        severity="info",
                        data={
                            'entity_name': entity.name,
                            'entity_type': type(entity).__name__,
                            'new_age': entity.age,
                            'team': team.name if team else 'Unknown'
                        }
                    ))
        
        return events
    
    def _serialize_entity(self, entity: Optional[Entity]) -> Optional[Dict[str, Any]]:
        """Helper to serialize any entity"""
        if entity is None:
            return None
        return {
            'name': entity.name,
            'age': entity.age,
            'potential_ceiling': entity.potential_ceiling,
            'decay_rate': entity.decay_rate,
            'variance_band': entity.variance_band,
            'form_momentum': entity.form_momentum,
            'current_ratings': entity.current_ratings,
            'performance_history': entity.performance_history,
        }
    
    def _deserialize_entity(self, data: Dict[str, Any], entity_class) -> Entity:
        """Helper to deserialize any entity"""
        entity = entity_class(name=data.get('name', 'Unknown'), age=data.get('age', 20))
        entity.potential_ceiling = data.get('potential_ceiling', 100.0)
        entity.decay_rate = data.get('decay_rate', 0.5)
        entity.variance_band = data.get('variance_band', 5.0)
        entity.form_momentum = data.get('form_momentum', 0.0)
        entity.current_ratings = data.get('current_ratings', {})
        entity.performance_history = data.get('performance_history', [])
        return entity
    
    def save_to_json(self, path: str) -> None:
        """Serialize state to JSON with full entity persistence"""
        def serialize_team(team: Team) -> Dict[str, Any]:
            return {
                'name': team.name,
                'budget': {
                    'cash': team.budget.cash,
                    'burn_rate': team.budget.burn_rate,
                    'committed_spend': team.budget.committed_spend,
                    'income_streams': [(inc.name, inc.amount, inc.frequency) for inc in team.budget.income_streams],
                    'staff_salaries': team.budget.staff_salaries,
                },
                'drivers': [self._serialize_entity(d) for d in team.drivers],
                'engineers': [self._serialize_entity(e) for e in team.engineers],
                'mechanics': [self._serialize_entity(m) for m in team.mechanics],
                'strategist': self._serialize_entity(team.strategist),
                'principal': self._serialize_entity(team.principal),
                'car': self._serialize_entity(team.car),
                'infrastructure': team.infrastructure,
                'standing_metrics': team.standing_metrics,
            }
        
        data = {
            'save_version': 2,  # BUMPED TO v2 for comprehensive refactor
            'tick': self.tick,
            'phase': self.phase,
            'sim_year': self.sim_year,
            'sim_day_of_year': self.sim_day_of_year,
            'days_per_tick': self.days_per_tick,
            'days_per_year': self.days_per_year,
            'races_completed_this_season': self.races_completed_this_season,
            'season_number': self.season_number,
            'in_offseason': self.in_offseason,
            'offseason_ticks_remaining': self.offseason_ticks_remaining,
            'time_mode': self.time_mode,
            'control_mode': self.control_mode,
            'save_mode': self.save_mode,
            'seed': self.seed,
            'player_identity': self.player_identity,
            'player_focus': self.player_focus,
            'player_team': serialize_team(self.player_team) if self.player_team else None,
            'ai_teams': [serialize_team(t) for t in self.ai_teams],
            'leagues': {
                name: {
                    'name': lg.name,
                    'tier': lg.tier,
                    'tier_name': lg.tier_name,
                    'team_names': [t.name for t in lg.teams],
                    'schedule': lg.schedule,
                    'championship_table': lg.championship_table,
                    'races_this_season': lg.races_this_season
                } 
                for name, lg in self.leagues.items()
            },
            'world_state': self.world_state,
            'pending_developments': self.pending_developments,
            'pending_decisions': [
                {
                    'decision_id': d.decision_id,
                    'category': d.category,
                    'prompt': d.prompt,
                    'options': [{'id': opt.id, 'label': opt.label, 'cost': opt.cost, 
                                'description': opt.description, 'consequence_preview': opt.consequence_preview}
                               for opt in d.options],
                    'deadline_tick': d.deadline_tick,
                    'auto_resolve_option_id': d.auto_resolve_option_id,
                    'created_tick': d.created_tick,
                    'resolved': d.resolved,
                    'chosen_option_id': d.chosen_option_id
                }
                for d in self.pending_decisions
            ],
            'event_history': [
                {
                    'event_type': e.event_type,
                    'category': e.category,
                    'ts': e.ts,
                    'priority': e.priority,
                    'severity': e.severity,
                    'data': e.data,
                    'event_id': e.event_id,
                    'caused_by': e.caused_by
                }
                for e in self.event_history[-100:]  # Save last 100 events
            ],
            '_next_event_id': self._next_event_id,
            'rng_state': random.getstate() if hasattr(self, 'rng') else None,
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @staticmethod
    def load_from_json(path: str) -> 'SimState':
        """Deserialize state from JSON with full entity restoration"""
        state = SimState()
        if not os.path.exists(path):
            return state
        
        with open(path, 'r') as f:
            data = json.load(f)
            
        # Version check - ENFORCE V2 ONLY
        version = data.get('save_version', 0)
        if version != 2:
            raise ValueError(f"Save file version {version} is incompatible with v2 simulation. "
                           "This is an alpha refactor - please start a new game.")
        
        state.tick = data.get('tick', 0)
        state.phase = data.get('phase', 'offseason')
        state.sim_year = data.get('sim_year', 1)
        state.sim_day_of_year = data.get('sim_day_of_year', 1)
        state.days_per_tick = data.get('days_per_tick', 1)
        state.days_per_year = data.get('days_per_year', 365)
        state.races_completed_this_season = data.get('races_completed_this_season', 0)
        state.season_number = data.get('season_number', 1)
        state.in_offseason = data.get('in_offseason', False)
        state.offseason_ticks_remaining = data.get('offseason_ticks_remaining', 0)
        state.time_mode = data.get('time_mode', 'paused')
        state.control_mode = data.get('control_mode', 'human')
        state.save_mode = data.get('save_mode', 'replayable')
        state.seed = data.get('seed', 42)
        state.player_identity = data.get('player_identity', [])
        state.player_focus = data.get('player_focus')
        state.world_state = data.get('world_state', {})
        state.pending_developments = data.get('pending_developments', [])
        state._next_event_id = data.get('_next_event_id', 1)
        
        # Restore event history
        event_history_data = data.get('event_history', [])
        state.event_history = [
            SimEvent(
                event_type=e['event_type'],
                category=e['category'],
                ts=e['ts'],
                priority=e['priority'],
                severity=e.get('severity', 'info'),
                data=e.get('data', {}),
                event_id=e.get('event_id', 0),
                caused_by=e.get('caused_by')
            )
            for e in event_history_data
        ]
        
        # Restore pending decisions
        decision_data = data.get('pending_decisions', [])
        state.pending_decisions = [
            DecisionEvent(
                decision_id=d['decision_id'],
                category=d['category'],
                prompt=d['prompt'],
                options=[
                    DecisionOption(
                        id=opt['id'],
                        label=opt['label'],
                        cost=opt.get('cost', 0.0),
                        description=opt.get('description', ''),
                        consequence_preview=opt.get('consequence_preview', '')
                    )
                    for opt in d.get('options', [])
                ],
                deadline_tick=d['deadline_tick'],
                auto_resolve_option_id=d['auto_resolve_option_id'],
                created_tick=d['created_tick'],
                resolved=d.get('resolved', False),
                chosen_option_id=d.get('chosen_option_id')
            )
            for d in decision_data
        ]
        
        # Restore RNG for deterministic replay
        rng_state = data.get('rng_state')
        if state.save_mode == "replayable" and rng_state:
            random.setstate(rng_state)
        elif state.save_mode == "replayable":
            # Fallback if no RNG state saved
            state.rngs['master'] = random.Random(state.seed)
        else:
            state.rngs['master'] = random.Random()
        
        # Deserialize teams
        def deserialize_team(team_data: Dict[str, Any]) -> Team:
            team = Team(name=team_data['name'])
            
            # Budget
            budget_data = team_data.get('budget', {})
            team.budget.cash = budget_data.get('cash', 100000.0)
            team.budget.burn_rate = budget_data.get('burn_rate', 0.0)
            team.budget.committed_spend = budget_data.get('committed_spend', [])
            team.budget.income_streams = [
                IncomeSource(name=name, amount=amt, frequency=freq) 
                for name, amt, freq in budget_data.get('income_streams', [])
            ]
            team.budget.staff_salaries = budget_data.get('staff_salaries', {})
            
            # Entities
            team.drivers = [state._deserialize_entity(d, Driver) for d in team_data.get('drivers', [])]
            team.engineers = [state._deserialize_entity(e, Engineer) for e in team_data.get('engineers', [])]
            team.mechanics = [state._deserialize_entity(m, Mechanic) for m in team_data.get('mechanics', [])]
            
            strategist_data = team_data.get('strategist')
            team.strategist = state._deserialize_entity(strategist_data, Strategist) if strategist_data else None
            
            principal_data = team_data.get('principal')
            team.principal = state._deserialize_entity(principal_data, AIPrincipal) if principal_data else None
            
            car_data = team_data.get('car')
            team.car = state._deserialize_entity(car_data, Car) if car_data else Car(name=f"{team.name} Car")
            
            team.infrastructure = team_data.get('infrastructure', {})
            team.standing_metrics = team_data.get('standing_metrics', {})
            
            return team
        
        player_team_data = data.get('player_team')
        state.player_team = deserialize_team(player_team_data) if player_team_data else None
        
        state.ai_teams = [deserialize_team(t) for t in data.get('ai_teams', [])]
        
        # Deserialize leagues and restore team references
        leagues_data = data.get('leagues', {})
        all_teams = ([state.player_team] if state.player_team else []) + state.ai_teams
        
        for name, lg_data in leagues_data.items():
            league = League(
                name=lg_data['name'],
                tier=lg_data['tier'],
                tier_name=lg_data.get('tier_name', 'grassroots')
            )
            league.schedule = lg_data.get('schedule', [])
            league.championship_table = lg_data.get('championship_table', {})
            league.races_this_season = lg_data.get('races_this_season', 0)
            
            # Restore team references by matching names
            team_names = lg_data.get('team_names', [])
            for team_name in team_names:
                team_obj = next((t for t in all_teams if t.name == team_name), None)
                if team_obj and team_obj not in league.teams:
                    league.teams.append(team_obj)
            
            state.leagues[name] = league
        
        return state


class WorldBuilder:
    """Deterministic world generation pipeline"""
    
    TIER_CONFIG = {
        'grassroots': {'count': 10, 'tier': 1, 'teams': 16, 'budget_range': (200000.0, 500000.0)},
        'formula_v': {'count': 6, 'tier': 2, 'teams': 16, 'budget_range': (800000.0, 1500000.0)},
        'formula_x': {'count': 4, 'tier': 3, 'teams': 10, 'budget_range': (3000000.0, 8000000.0)},
        'formula_y': {'count': 2, 'tier': 4, 'teams': 11, 'budget_range': (15000000.0, 40000000.0)},
        'formula_z': {'count': 1, 'tier': 5, 'teams': 10, 'budget_range': (140000000.0, 400000000.0)},
    }
    
    @staticmethod
    def generate_world(state: SimState) -> None:
        """Populate empty state with full world"""
        rng = state.get_rng("world", "init")
        state.ai_teams = [] # Clear existing
        state.leagues = {}
        
        # 1. Create Leagues
        for tier_name, config in WorldBuilder.TIER_CONFIG.items():
            for i in range(config['count']):
                league_id = f"{tier_name}_{i+1}"
                league_name = f"{tier_name.replace('_', ' ').title()} League {i+1}"
                if config['count'] == 1:
                     league_name = tier_name.replace('_', ' ').title()
                
                league = League(league_name, config['tier'], tier_name)
                state.leagues[league_id] = league
                
                # 2. Generate Schedule
                weeks = 24 if tier_name == 'formula_z' else 14 if tier_name == 'formula_y' else 10
                start_week = 5
                league.schedule = [start_week + idx*2 for idx in range(weeks)]
                
                # 3. Generate Teams
                WorldBuilder._generate_teams(state, league, config, rng)
                
    @staticmethod
    def _generate_teams(state: SimState, league: League, config: Dict[str, Any], rng: random.Random) -> None:
        num_teams = config['teams']
        tier_base = 20 + league.tier * 12
        
        for i in range(num_teams):
            team_name = f"{league.name.split(' ')[0]} Team {i+1}"
            team = Team(team_name)
            team.budget.cash = rng.uniform(*config['budget_range'])
            
            # Principal
            p = AIPrincipal(f"Principal {i}")
            for k in STATS_SCHEMAS['AIPrincipal']:
                p.current_ratings[k] = float(max(1, min(99, rng.gauss(tier_base + 5, 10))))
            team.principal = p
            
            # Drivers
            for d_idx in range(2):
                d = Driver(f"Driver {league.tier}-{i}-{d_idx}")
                d.age = rng.randint(18, 35)
                for k in STATS_SCHEMAS['Driver']:
                    d.current_ratings[k] = float(max(1, min(99, rng.gauss(tier_base, 10))))
                team.drivers.append(d)
                
            # Mechanics (1 for now)
            m = Mechanic(f"Mechanic {i}")
            for k in STATS_SCHEMAS['Mechanic']:
                m.current_ratings[k] = float(max(1, min(99, rng.gauss(tier_base, 10))))
            team.mechanics.append(m)

            # Strategist
            s = Strategist(f"Strategist {i}")
            for k in STATS_SCHEMAS['Strategist']:
                s.current_ratings[k] = float(max(1, min(99, rng.gauss(tier_base, 10))))
            team.strategist = s

            # Car
            c = Car(f"{team_name} Chassis")
            car_base = tier_base
            for k in STATS_SCHEMAS['Car']:
                c.current_ratings[k] = float(max(1, min(99, rng.gauss(car_base, 5))))
            team.car = c
            
            league.teams.append(team)
            state.ai_teams.append(team)


# ============================================================
# SECTION 5: Simulation Engine (Pure Computation, NO LLM)
# ============================================================

# Stat weighting tables for different series/regulations
# Format: {'stat_name': weight} where weights sum to ~1.0 for clarity

QUALIFYING_WEIGHTS = {
    'default': {
        'driver': {
            'qualifying_pace': 0.6,
            'pace': 0.4,
        },
        'car': {
            'aero_efficiency': 0.3,
            'downforce_peak': 0.2,
            'power_output': 0.2,
            'mechanical_grip': 0.3,
        },
        'mechanic': {
            'pre_race_preparation': 1.0,
        },
        'phase_weights': {  # How much each entity type contributes
            'driver': 0.5,
            'car': 0.4,
            'mechanic': 0.1,
        },
    },
}

RACE_WEIGHTS = {
    'default': {
        'driver': {
            'race_pace': 0.4,
            'pace': 0.2,
            'tire_conservation': 0.2,
            'consistency': 0.2,
        },
        'car': {
            'aero_efficiency': 0.3,
            'reliability': 0.3,
            'mechanical_grip': 0.2,
            'power_delivery_smoothness': 0.2,
        },
        'phase_weights': {
            'driver': 0.6,
            'car': 0.4,
        },
    },
}

STRATEGY_WEIGHTS = {
    'default': {
        'strategist': {
            'race_reading': 0.6,
            'tire_modeling': 0.4,
        },
        'impact_multiplier': 0.15,  # How much strategy can swing performance
    },
}

PIT_WEIGHTS = {
    'default': {
        'mechanic': {
            'pit_execution': 0.7,
            'coordination': 0.3,
        },
        'impact_multiplier': 0.1,  # Pit quality effect on race outcome
    },
}

class FTBSimulation:
    """
    All game computation lives here.
    NO LLM CALLS - only numerical computation.
    """
    
    @staticmethod
    def score_entity(entity: Entity, weights: Dict[str, float]) -> float:
        """Score an entity based on weighted stats"""
        if not entity: return 0.0
        score = 0.0
        total_weight = 0.0
        
        for stat, weight in weights.items():
            val = getattr(entity, stat, 50.0)
            score += val * weight
            total_weight += weight
            
        return score / total_weight if total_weight > 0 else 50.0

    @staticmethod
    def compose_phase_score(parts: Dict[str, float], weights: Dict[str, float]) -> float:
        """Compose weighted score from components (driver, car, etc.)"""
        score = 0.0
        total_weight = 0.0
        
        for part_name, val in parts.items():
            w = weights.get(part_name, 0.0)
            score += val * w
            total_weight += w
            
        return score / total_weight if total_weight > 0 else 0.0

    
    @staticmethod
    def tick_simulation(state: SimState) -> List[SimEvent]:
        """
        Main tick loop - advance simulation and return events for narration.
        """
        events = []
        
        # Advance time
        state.tick += 1
        
        # Advance calendar and age entities
        birthday_events = state.advance_calendar()
        events.extend(birthday_events)
        
        # Handle offseason ticks
        if state.in_offseason and state.offseason_ticks_remaining > 0:
            state.offseason_ticks_remaining -= 1
            if state.offseason_ticks_remaining == 0:
                state.in_offseason = False
                events.append(SimEvent(
                    event_type="time",
                    category="offseason_end",
                    ts=state.tick,
                    priority=75.0,
                    data={'new_season': state.season_number, 'message': 'New season begins!'}
                ))
        
        # Resolve pending developments
        dev_events = FTBSimulation._resolve_pending_developments(state)
        events.extend(dev_events)
        
        # Phase progression and race simulation (only if not in offseason)
        if not state.in_offseason:
            if state.phase == "offseason" and state.tick % 7 == 0:
                state.phase = "race_weekend"
                events.append(SimEvent(
                    event_type="time",
                    category="enter_race_weekend",
                    ts=state.tick,
                    priority=70.0,
                    data={'calendar_date': state.current_date_str()}
                ))
            elif state.phase == "race_weekend":
                # Simulate race
                race_events = FTBSimulation.simulate_race_weekend(state)
                events.extend(race_events)
                state.phase = "development"
                
                # Check for season end (16 races completed)
                if state.races_completed_this_season >= 16:
                    season_end_events = FTBSimulation.process_season_end(state)
                    events.extend(season_end_events)
            elif state.phase == "development":
                state.phase = "offseason"
        
        # Update entity growth/decay
        FTBSimulation.update_entity_growth_decay(state)
        
        # Apply financial flows
        financial_events = FTBSimulation.apply_financial_flows(state)
        events.extend(financial_events)
        
        # Update standing metrics
        if state.player_team:
            expectations = FTBSimulation.infer_role_and_expectations(state, state.player_team)
            standing_events = FTBSimulation.update_standing_metrics(state, state.player_team, {}, expectations.get('role', 'survivor'))
            events.extend(standing_events)
        
        # Generate opportunities
        opp_events = FTBSimulation.generate_opportunities(state)
        events.extend(opp_events)
        
        # Formula Z news generation (if meta plugin is available)
        # This is called periodically from meta plugin, but we trigger it here
        # The meta plugin will check if enough time has passed
        
        # AI team action execution (probabilistic 10% per team per tick)
        ai_action_events = FTBSimulation._execute_ai_team_actions(state)
        events.extend(ai_action_events)
        
        # Check pending decisions and auto-resolve expired ones
        decision_events = FTBSimulation.check_pending_decisions(state)
        events.extend(decision_events)
        
        # Assign event IDs to all events
        for event in events:
            if event.event_id == 0:
                event.event_id = FTBSimulation._generate_event_id(state)
        
        # Persist events to history (for standing metrics and replay analysis)
        state.event_history.extend(events)
        
        # Trim event history to last 100 events to prevent unbounded growth
        if len(state.event_history) > 100:
            state.event_history = state.event_history[-100:]
        
        return events
    
    @staticmethod
    def simulate_race_weekend(state: SimState) -> List[SimEvent]:
        """Pure numerical race simulation using entity stats"""
        events = []
        rng = state.get_rng("race", context=f"weekend_{state.tick}")
        
        if not state.player_team or not state.player_team.drivers:
            return events
        
        # Get all teams with drivers
        # TODO: update to use state.leagues in Phase 2, but keep legacy list support for now
        all_teams = [state.player_team] + state.ai_teams if state.player_team else state.ai_teams
        teams_with_drivers = [t for t in all_teams if t and t.drivers]
        
        if not teams_with_drivers:
            return events
            
        # ============================================
        # QUALIFYING
        # ============================================
        qual_weights = QUALIFYING_WEIGHTS['default']
        qualifying_scores = []
        
        for team in teams_with_drivers:
            driver = team.drivers[0] # Primary driver only for MVP
            car = team.car
            mechanic = team.mechanics[0] if team.mechanics else None
            
            # Score components
            # Note: We pass the weights directly, missing keys in entity will default to 50.0 via getattr logic
            d_score = FTBSimulation.score_entity(driver, qual_weights['driver'])
            c_score = FTBSimulation.score_entity(car, qual_weights['car']) 
            m_score = FTBSimulation.score_entity(mechanic, qual_weights.get('mechanic', {}))
            
            # Compose
            parts = {'driver': d_score, 'car': c_score, 'mechanic': m_score}
            base_score = FTBSimulation.compose_phase_score(parts, qual_weights['phase_weights'])
            
            # Consistency variance (derived from driver consistency stat)
            consistency = getattr(driver, 'consistency', 50.0)
            variance_range = (100.0 - consistency) / 200.0
            variance_roll = rng.uniform(-variance_range * 10, variance_range * 10)
            
            final_score = base_score + variance_roll
            qualifying_scores.append((team, driver, final_score))
            
        qualifying_scores.sort(key=lambda x: x[2], reverse=True)
        
        # Emit Qualifying Results
        for position, (team, driver, score) in enumerate(qualifying_scores, 1):
             gap_to_pole = (qualifying_scores[0][2] - score) / 10.0
             events.append(SimEvent(
                event_type="outcome",
                category="qualifying_result",
                ts=state.tick,
                priority=70.0,
                data={
                    'position': position,
                    'team': team.name,
                    'driver': driver.name,
                    'gap_to_pole': round(gap_to_pole, 3),
                    'score': round(score, 2)
                }
            ))
            
        # ============================================
        # RACE
        # ============================================
        race_weights = RACE_WEIGHTS['default']
        strat_weights = STRATEGY_WEIGHTS['default']
        pit_weights = PIT_WEIGHTS['default']
        
        race_scores = []
        
        for grid_pos, (team, driver, qual_score) in enumerate(qualifying_scores, 1):
            car = team.car
            strategist = team.strategist
            mechanic = team.mechanics[0] if team.mechanics else None
            
            # 1. Base Pace
            d_score = FTBSimulation.score_entity(driver, race_weights['driver'])
            c_score = FTBSimulation.score_entity(car, race_weights['car'])
            base_pace = FTBSimulation.compose_phase_score({'driver': d_score, 'car': c_score}, race_weights['phase_weights'])
            
            # 2. Racecraft / Grid Context
            racecraft_bonus = 0.0
            if grid_pos > 1:
                rc = getattr(driver, 'racecraft', 50.0)
                ov = getattr(driver, 'overtaking_skill', 50.0)
                racecraft_bonus = ((rc + ov)/2.0 - 50.0) * 0.1
                
            # 3. Strategy
            strategy_delta = 0.0
            if strategist:
                s_score = FTBSimulation.score_entity(strategist, strat_weights['strategist'])
                strategy_delta = (s_score - 50.0) * strat_weights.get('impact_multiplier', 0.15)
                
            # 4. Pit Stops
            pit_delta = 0.0
            if mechanic:
                m_score = FTBSimulation.score_entity(mechanic, pit_weights['mechanic'])
                pit_delta = (m_score - 50.0) * pit_weights.get('impact_multiplier', 0.1)

            # 5. Reliability / DNF
            reliability = getattr(car, 'reliability', 50.0)
            dnf_chance = (100.0 - reliability) / 200.0 
            dnf_chance = max(0.005, min(0.5, dnf_chance))
            
            dnf_roll = rng.random()
            if dnf_roll < dnf_chance:
                events.append(SimEvent(
                    event_type="outcome",
                    category="dnf",
                    ts=state.tick,
                    priority=75.0,
                    data={
                        'driver': driver.name, 'team': team.name, 
                        'reason': 'mechanical', 'reliability_stat': reliability
                    }
                ))
                continue
                
            # 6. Incidents
            mistake_rate = getattr(driver, 'mistake_rate', 50.0)
            incident_chance = mistake_rate / 200.0
            if rng.random() < incident_chance:
                penalty = rng.uniform(5.0, 20.0)
                base_pace -= penalty # Direct penalty
                events.append(SimEvent(
                    event_type="outcome",
                    category="incident",
                    ts=state.tick,
                    priority=70.0,
                    data={'driver': driver.name, 'team': team.name, 'penalty': round(penalty, 1)}
                ))
                
            final_score = base_pace + racecraft_bonus + strategy_delta + pit_delta
            race_scores.append((team, driver, grid_pos, final_score))
            
        if not race_scores:
            return events

        race_scores.sort(key=lambda x: (x[3], -x[2]), reverse=True)
        
        points_table = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1]
        
        # Find which league(s) participated in this race
        participating_leagues = set()
        for team, _, _, _ in race_scores:
            for league in state.leagues.values():
                if team in league.teams:
                    participating_leagues.add(league)
                    break
        
        for position, (team, driver, grid_pos, score) in enumerate(race_scores, 1):
            points = points_table[position-1] if position <= len(points_table) else 0
            
            # Award points to championship table
            for league in participating_leagues:
                if team in league.teams:
                    if team.name not in league.championship_table:
                        league.championship_table[team.name] = 0.0
                    league.championship_table[team.name] += points
                    break
            
            events.append(SimEvent(
                event_type="outcome",
                category="race_result",
                ts=state.tick,
                priority=80.0,
                data={
                    'position': position,
                    'grid_position': grid_pos,
                    'points': points,
                    'team': team.name,
                    'driver': driver.name,
                    'score': round(score, 2)
                }
            ))
        
        # Increment race counter for participating leagues (once per league)
        for league in participating_leagues:
            league.races_this_season += 1
        
        # Increment global season race counter
        state.races_completed_this_season += 1
            
        return events
    
    @staticmethod
    def process_season_end(state: SimState) -> List[SimEvent]:
        """
        End-of-season resolution: championship final standings, promotion/relegation, 
        team exits, and standing metric shocks.
        """
        events = []
        
        # Process each league
        for league_id, league in state.leagues.items():
            # Check if this league completed a full season (16 races)
            if league.races_this_season < 16:
                continue
            
            # Sort teams by championship points
            teams_sorted = sorted(
                league.championship_table.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            # Emit championship standings event
            events.append(SimEvent(
                event_type="outcome",
                category="season_end",
                ts=state.tick,
                priority=95.0,
                severity="major",
                data={
                    'league': league.name,
                    'tier': league.tier,
                    'champion': teams_sorted[0][0] if teams_sorted else None,
                    'champion_points': teams_sorted[0][1] if teams_sorted else 0,
                    'standings': teams_sorted[:10]  # Top 10
                }
            ))
            
            # Promotion logic (top 2 teams in tiers 1-4)
            if league.tier < 5 and len(teams_sorted) >= 2:
                # Get promoted teams
                promoted_teams = []
                for i in range(min(2, len(teams_sorted))):
                    team_name = teams_sorted[i][0]
                    # Find team object
                    team_obj = next((t for t in league.teams if t.name == team_name), None)
                    if team_obj:
                        promoted_teams.append((team_name, team_obj))
                        events.append(SimEvent(
                            event_type="outcome",
                            category="team_promotion",
                            ts=state.tick,
                            priority=90.0,
                            severity="major",
                            data={
                                'team': team_name,
                                'from_tier': league.tier,
                                'to_tier': league.tier + 1,
                                'final_points': teams_sorted[i][1]
                            }
                        ))
                
                # Actually move teams to higher tier (simplified - find first league in next tier)
                target_tier = league.tier + 1
                target_leagues = [l for l in state.leagues.values() if l.tier == target_tier]
                if target_leagues:
                    target_league = target_leagues[0]  # Pick first available
                    for team_name, team_obj in promoted_teams:
                        league.teams.remove(team_obj)
                        target_league.teams.append(team_obj)
            
            # Relegation logic (bottom 2 teams in tiers 2-5)
            if league.tier > 1 and len(teams_sorted) >= 2:
                # Get relegated teams
                relegated_teams = []
                for i in range(min(2, len(teams_sorted))):
                    idx = -(i+1)  # Start from end
                    team_name = teams_sorted[idx][0]
                    team_obj = next((t for t in league.teams if t.name == team_name), None)
                    if team_obj:
                        relegated_teams.append((team_name, team_obj))
                        events.append(SimEvent(
                            event_type="outcome",
                            category="team_relegation",
                            ts=state.tick,
                            priority=90.0,
                            severity="major",
                            data={
                                'team': team_name,
                                'from_tier': league.tier,
                                'to_tier': league.tier - 1,
                                'final_points': teams_sorted[idx][1]
                            }
                        ))
                
                # Move teams to lower tier
                target_tier = league.tier - 1
                target_leagues = [l for l in state.leagues.values() if l.tier == target_tier]
                if target_leagues:
                    target_league = target_leagues[0]
                    for team_name, team_obj in relegated_teams:
                        league.teams.remove(team_obj)
                        target_league.teams.append(team_obj)
            
            # Team liquidation (last place in tier 1)
            if league.tier == 1 and len(teams_sorted) >= 1:
                last_team_name = teams_sorted[-1][0]
                last_team_obj = next((t for t in league.teams if t.name == last_team_name), None)
                if last_team_obj and teams_sorted[-1][1] < 5:  # Fewer than 5 points = liquidation
                    events.append(SimEvent(
                        event_type="outcome",
                        category="team_liquidation",
                        ts=state.tick,
                        priority=95.0,
                        severity="critical",
                        data={
                            'team': last_team_name,
                            'tier': league.tier,
                            'final_points': teams_sorted[-1][1],
                            'reason': 'chronic_failure'
                        }
                    ))
                    # Remove from league and AI teams
                    league.teams.remove(last_team_obj)
                    if last_team_obj in state.ai_teams:
                        state.ai_teams.remove(last_team_obj)
            
            # ============================================================
            # SEASON-END STANDING METRIC SHOCKS (Phase 2.2)
            # ============================================================
            # Evaluate each team's performance vs expectations
            for team_name, final_points in teams_sorted:
                team_obj = next((t for t in league.teams if t.name == team_name), None)
                if not team_obj:
                    continue
                
                # Get expectations for this team
                expectations = FTBSimulation.infer_role_and_expectations(state, team_obj)
                expected_range = expectations.get('expected_range', (8, 12))
                points_target = expectations.get('points_target', 10)
                
                # Determine finish position in championship
                finish_position = next((i+1 for i, (name, _) in enumerate(teams_sorted) if name == team_name), len(teams_sorted))
                
                # Evaluate performance
                overachieved = finish_position < expected_range[0] - 2  # 3+ positions better
                met_expectations = expected_range[0] <= finish_position <= expected_range[1]
                underperformed = finish_position > expected_range[1] and finish_position <= expected_range[1] + 2
                failed_badly = finish_position > expected_range[1] + 2  # 3+ positions worse
                
                # Apply standing metric shocks
                if overachieved:
                    team_obj.standing_metrics['ownership_confidence'] = min(100, team_obj.standing_metrics['ownership_confidence'] + 15)
                    team_obj.standing_metrics['legitimacy'] = min(100, team_obj.standing_metrics['legitimacy'] + 10)
                    team_obj.standing_metrics['reputation'] = min(100, team_obj.standing_metrics['reputation'] + 8)
                    
                    if team_obj == state.player_team:
                        events.append(SimEvent(
                            event_type="outcome",
                            category="season_overachievement",
                            ts=state.tick,
                            priority=90.0,
                            severity="major",
                            data={
                                'team': team_name,
                                'finish_position': finish_position,
                                'expected_range': expected_range,
                                'points': final_points,
                                'message': 'Exceptional season results exceed all expectations'
                            }
                        ))
                elif met_expectations:
                    team_obj.standing_metrics['ownership_confidence'] = min(100, team_obj.standing_metrics['ownership_confidence'] + 5)
                    team_obj.standing_metrics['legitimacy'] = min(100, team_obj.standing_metrics['legitimacy'] + 5)
                    team_obj.standing_metrics['reputation'] = min(100, team_obj.standing_metrics['reputation'] + 5)
                elif underperformed:
                    team_obj.standing_metrics['ownership_confidence'] = max(0, team_obj.standing_metrics['ownership_confidence'] - 8)
                    team_obj.standing_metrics['legitimacy'] = max(0, team_obj.standing_metrics['legitimacy'] - 5)
                    
                    if team_obj == state.player_team:
                        events.append(SimEvent(
                            event_type="pressure",
                            category="season_underperformance",
                            ts=state.tick,
                            priority=85.0,
                            severity="major",
                            data={
                                'team': team_name,
                                'finish_position': finish_position,
                                'expected_range': expected_range,
                                'points': final_points,
                                'message': 'Season results disappoint ownership - pressure mounting'
                            }
                        ))
                elif failed_badly:
                    team_obj.standing_metrics['ownership_confidence'] = max(0, team_obj.standing_metrics['ownership_confidence'] - 20)
                    team_obj.standing_metrics['legitimacy'] = max(0, team_obj.standing_metrics['legitimacy'] - 15)
                    team_obj.standing_metrics['reputation'] = max(0, team_obj.standing_metrics['reputation'] - 10)
                    
                    if team_obj == state.player_team:
                        events.append(SimEvent(
                            event_type="pressure",
                            category="ownership_ultimatum",
                            ts=state.tick,
                            priority=95.0,
                            severity="critical",
                            data={
                                'team': team_name,
                                'finish_position': finish_position,
                                'expected_range': expected_range,
                                'points': final_points,
                                'message': 'Catastrophic season failure triggers ownership emergency meeting',
                                'ultimatum': 'Immediate improvement required or face termination'
                            }
                        ))
            
            # ============================================================
            # PRIZE MONEY & INCOME DISTRIBUTION (Phase 3.2)
            # ============================================================
            # Award prize money based on championship position
            # Tier-scaled prize pools:
            tier_prize_scales = {
                1: 500000,    # Tier 1 (Grassroots)
                2: 1000000,   # Tier 2 (Formula V)
                3: 2500000,   # Tier 3 (Formula X)
                4: 5000000,   # Tier 4 (Formula Y)
                5: 10000000   # Tier 5 (Formula Z)
            }
            
            base_prize = tier_prize_scales.get(league.tier, 500000)
            
            for position, (team_name, points) in enumerate(teams_sorted, 1):
                team_obj = next((t for t in league.teams if t.name == team_name), None)
                if not team_obj:
                    continue
                
                # Exponential decay: P1 gets base, P2 gets 60%, P3 gets 40%, etc.
                position_multiplier = max(0.1, 1.0 / (position ** 0.7))
                prize_money = base_prize * position_multiplier
                
                # Award the prize money
                team_obj.budget.cash += prize_money
                
                # Update income streams for next season (sponsorships based on media standing)
                media_standing = team_obj.standing_metrics.get('media_standing', 50.0)
                base_sponsorship = 100000
                media_bonus = max(0, (media_standing - 50) / 10) * 50000  # +50k per 10 points over 50
                season_sponsorship = base_sponsorship + media_bonus
                
                # Clear old income streams and add new ones
                team_obj.budget.income_streams = []
                team_obj.budget.income_streams.append(
                    IncomeSource(name="Sponsorship", amount=season_sponsorship, frequency="season")
                )
                
                if team_obj == state.player_team:
                    events.append(SimEvent(
                        event_type="outcome",
                        category="prize_money",
                        ts=state.tick,
                        priority=80.0,
                        severity="info",
                        data={
                            'team': team_name,
                            'position': position,
                            'prize': prize_money,
                            'sponsorship': season_sponsorship,
                            'message': f'Season prizes awarded: ${prize_money:,.0f} + ${season_sponsorship:,.0f} sponsorship'
                        }
                    ))
            
            # Reset championship table for new season
            league.championship_table = {}
            league.races_this_season = 0
        
        # Reset global season counter
        state.races_completed_this_season = 0
        state.season_number += 1
        state.in_offseason = True
        state.offseason_ticks_remaining = 56  # 8 weeks
        
        return events
    
    @staticmethod
    def simulate_development_cycle(state: SimState, team: Team) -> Dict[str, Any]:
        """Car development resolution: correlation risk, regression, etc."""
        # Engineer stats determine success probability
        # Simplified for MVP
        return {'success': state.rng.random() > 0.5}
    
    @staticmethod
    def update_entity_growth_decay(state: SimState) -> None:
        """Apply potential progression and decline pressure"""
        # All entities age and evolve
        # Drivers peak earlier, engineers peak later
        context = {'week': state.tick, 'team_stability': 0.5}
        
        # Collect all entities from all teams
        all_teams = [state.player_team] + state.ai_teams if state.player_team else state.ai_teams
        
        for team in all_teams:
            if team is None:
                continue
            
            # Process all entity types
            entities_to_process = (
                team.drivers + 
                team.engineers + 
                team.mechanics + 
                ([team.strategist] if team.strategist else []) +
                ([team.principal] if team.principal else [])
            )
            
            for entity in entities_to_process:
                if entity is None:
                    continue
                # Apply growth and decay
                entity.update_growth(context)
                entity.apply_decay()
                # Note: current_ratings are already updated in place by these methods
    
    @staticmethod
    def apply_financial_flows(state: SimState) -> List[SimEvent]:
        """Budget ticks, income, expenses, salaries, and infrastructure upkeep"""
        events = []
        all_teams = [state.player_team] + state.ai_teams if state.player_team else state.ai_teams
        
        for team in all_teams:
            if team is None:
                continue
            
            # Calculate income (per-tick from season total)
            # Income is distributed evenly across ~112 ticks per season (16 races × 7 ticks)
            tick_income = 0.0
            for income_stream in team.budget.income_streams:
                tick_income += income_stream.amount / 112.0  # Distribute across season
            
            # Calculate costs for this tick
            payroll_cost = team.budget.calculate_staff_payroll()
            
            # Infrastructure upkeep costs
            infrastructure_cost = 0.0
            for facility, quality in team.infrastructure.items():
                if facility in INFRASTRUCTURE_UPKEEP_COST:
                    infrastructure_cost += INFRASTRUCTURE_UPKEEP_COST[facility](quality)
            
            # Total operational cost
            total_operational_cost = payroll_cost + infrastructure_cost
            
            # Apply income and costs
            team.budget.cash += tick_income
            team.budget.cash -= total_operational_cost
            
            # Apply standard budget tick (burn rate + commitments)
            team.budget.advance_tick(state.tick)
            
            # Check for economic crisis (only for player team)
            if team == state.player_team:
                crisis_events = FTBSimulation.check_economic_crisis(state, team)
                events.extend(crisis_events)
        
        return events
    
    @staticmethod
    def check_economic_crisis(state: SimState, team: Team) -> List[SimEvent]:
        """
        Multi-stage bankruptcy pipeline with escalating severity.
        Returns events triggered by cash runway thresholds.
        """
        events = []
        cash_runway = FTBSimulation.calculate_cash_runway(team)
        
        # Threshold 1: < 20 weeks (140 ticks) - Warning
        if 135 < cash_runway < 140:  # Narrow window to avoid spam
            events.append(SimEvent(
                event_type="pressure",
                category="economic_warning",
                ts=state.tick,
                priority=70.0,
                severity="warning",
                data={
                    'team': team.name,
                    'cash_runway_weeks': cash_runway / 7,
                    'cash': team.budget.cash,
                    'message': 'Cash reserves declining - monitor burn rate carefully'
                }
            ))
        
        # Threshold 2: < 10 weeks (70 ticks) - Hiring Freeze
        if cash_runway < 70 and not hasattr(team, '_hiring_freeze_active'):
            team._hiring_freeze_active = True
            events.append(SimEvent(
                event_type="consequence",
                category="hiring_freeze",
                ts=state.tick,
                priority=85.0,
                severity="major",
                data={
                    'team': team.name,
                    'cash_runway_weeks': cash_runway / 7,
                    'cash': team.budget.cash,
                    'message': 'Hiring freeze imposed - all recruitment actions blocked'
                }
            ))
        elif cash_runway >= 70 and hasattr(team, '_hiring_freeze_active'):
            # Lift hiring freeze if runway improves
            delattr(team, '_hiring_freeze_active')
        
        # Threshold 3: < 5 weeks (35 ticks) - Forced Development Cancellation
        if cash_runway < 35 and not hasattr(team, '_dev_cancelled'):
            team._dev_cancelled = True
            # Cancel all pending developments for this team
            cancelled_count = 0
            for dev in state.pending_developments[:]:
                if dev.get('team_name') == team.name:
                    state.pending_developments.remove(dev)
                    cancelled_count += 1
            
            if cancelled_count > 0:
                events.append(SimEvent(
                    event_type="consequence",
                    category="development_cancellation",
                    ts=state.tick,
                    priority=90.0,
                    severity="critical",
                    data={
                        'team': team.name,
                        'cash_runway_weeks': cash_runway / 7,
                        'developments_cancelled': cancelled_count,
                        'message': f'Cash crisis forces cancellation of {cancelled_count} development projects'
                    }
                ))
        elif cash_runway >= 35 and hasattr(team, '_dev_cancelled'):
            delattr(team, '_dev_cancelled')
        
        # Threshold 4: < 2 weeks (14 ticks) - Fire Sale Decision Required
        if cash_runway < 14 and not hasattr(team, '_fire_sale_triggered'):
            team._fire_sale_triggered = True
            
            # Create fire sale decision
            options = []
            if team.drivers:
                options.append(DecisionOption(
                    id="fire_driver_0",
                    label=f"Fire {team.drivers[0].name}",
                    cost=0,
                    description=f"Remove driver from payroll",
                    consequence_preview="Reputation -5, immediate cost savings"
                ))
            if team.engineers:
                options.append(DecisionOption(
                    id="fire_engineer_0",
                    label=f"Fire {team.engineers[0].name}",
                    cost=0,
                    description=f"Remove engineer from payroll",
                    consequence_preview="Reputation -3, reduced development capability"
                ))
            options.append(DecisionOption(
                id="sell_asset",
                label="Sell wind tunnel capacity",
                cost=0,
                description="Degrade wind tunnel quality by 10 points",
                consequence_preview="+$150k cash, permanent infrastructure loss"
            ))
            
            if options:
                decision = FTBSimulation.create_decision(
                    state,
                    category="fire_sale",
                    prompt="Team on brink of insolvency - immediate action required to raise cash",
                    options=options,
                    deadline_ticks=7,  # 1 week to decide
                    auto_resolve_id=options[0].id
                )
                
                events.append(SimEvent(
                    event_type="pressure",
                    category="decision_required",
                    ts=state.tick,
                    priority=95.0,
                    severity="critical",
                    data={
                        'decision_id': decision.decision_id,
                        'cash_runway_weeks': cash_runway / 7,
                        'message': 'CRITICAL: Fire sale decision required'
                    }
                ))
        elif cash_runway >= 14 and hasattr(team, '_fire_sale_triggered'):
            delattr(team, '_fire_sale_triggered')
        
        # Threshold 5: < 0 cash for 3+ consecutive ticks - Administration
        if team.budget.cash < 0:
            if not hasattr(team, '_negative_cash_ticks'):
                team._negative_cash_ticks = 0
            team._negative_cash_ticks += 1
            
            if team._negative_cash_ticks >= 3:
                events.append(SimEvent(
                    event_type="outcome",
                    category="administration",
                    ts=state.tick,
                    priority=100.0,
                    severity="critical",
                    data={
                        'team': team.name,
                        'cash': team.budget.cash,
                        'message': 'Team enters administration - ownership changes hands',
                        'consequence': 'Player removed from position'
                    }
                ))
                # TODO: In full implementation, trigger game over or forced job transfer
        else:
            if hasattr(team, '_negative_cash_ticks'):
                team._negative_cash_ticks = 0
        
        return events
    
    @staticmethod
    def infer_role_and_expectations(state: SimState, team: Team) -> Dict[str, Any]:
        """Numerical inference from budget, resources, history"""
        # Find team's league
        team_league = None
        for league in state.leagues.values():
            if team in league.teams:
                team_league = league
                break
        
        if not team_league:
            # Default for unassigned teams
            return {
                "role": "survivor",
                "expected_range": (8, 12),
                "points_target": 10,
                "patience_weeks": 20,
                "ownership_sensitivity": 1.0
            }
        
        # Calculate budget percentile within league
        league_budgets = [t.budget.cash for t in team_league.teams]
        league_budgets.sort()
        team_budget_rank = league_budgets.index(team.budget.cash) if team.budget.cash in league_budgets else len(league_budgets) // 2
        budget_percentile = team_budget_rank / max(1, len(league_budgets) - 1)
        
        # Calculate recent race average (last 5 races)
        recent_positions = []
        for event in reversed(state.event_history[-50:]):
            if event.category == 'race_result' and event.data.get('team') == team.name:
                pos = event.data.get('position', 0)
                if pos > 0:
                    recent_positions.append(pos)
                if len(recent_positions) >= 5:
                    break
        
        avg_finish = sum(recent_positions) / len(recent_positions) if recent_positions else len(team_league.teams) / 2
        
        # Calculate infrastructure quality score (0-100)
        infra_score = 0.0
        if team.infrastructure:
            wt_quality = team.infrastructure.get('wind_tunnel_quality', 0)
            sim_quality = team.infrastructure.get('simulator_quality', 0)
            factory_quality = team.infrastructure.get('factory_quality', 0)
            infra_score = (wt_quality * 0.4 + sim_quality * 0.3 + factory_quality * 0.3)
        
        # Calculate championship position percentile
        champ_percentile = 0.5  # Default mid-pack
        if team.name in team_league.championship_table:
            teams_sorted = sorted(team_league.championship_table.items(), key=lambda x: x[1], reverse=True)
            team_champ_rank = next((i for i, (name, _) in enumerate(teams_sorted) if name == team.name), len(teams_sorted) // 2)
            champ_percentile = team_champ_rank / max(1, len(teams_sorted) - 1)
        
        # Composite role score (0-100): higher = better expected performance
        role_score = (
            budget_percentile * 40 +  # Budget is primary driver
            (1.0 - (avg_finish / len(team_league.teams))) * 30 +  # Results matter
            (infra_score / 100.0) * 20 +  # Infrastructure supports development
            (1.0 - champ_percentile) * 10  # Championship position
        )
        
        # Map role_score to role bands
        num_teams = len(team_league.teams)
        if role_score >= 80:
            role = "favorite"
            expected_range = (1, 3)
            points_target = num_teams * 18  # Expect consistent podiums
            patience_weeks = 12
            ownership_sensitivity = 1.5
        elif role_score >= 60:
            role = "aspirant"
            expected_range = (3, 6)
            points_target = num_teams * 10
            patience_weeks = 16
            ownership_sensitivity = 1.3
        elif role_score >= 40:
            role = "contender"
            expected_range = (5, 10)
            points_target = num_teams * 5
            patience_weeks = 20
            ownership_sensitivity = 1.1
        elif role_score >= 25:
            role = "survivor"
            expected_range = (8, 12)
            points_target = num_teams * 2
            patience_weeks = 24
            ownership_sensitivity = 0.9
        else:
            role = "backmarker"
            expected_range = (10, num_teams)
            points_target = max(5, num_teams)
            patience_weeks = 30
            ownership_sensitivity = 0.7
        
        # Formula Z pressure amplification
        if team_league.tier == 5:
            patience_weeks = int(patience_weeks * 0.5)
            ownership_sensitivity *= 1.5
            # Tighten ranges
            mid = (expected_range[0] + expected_range[1]) // 2
            spread = max(1, (expected_range[1] - expected_range[0]) // 2)
            expected_range = (mid - spread, mid + spread)
        
        return {
            "role": role,
            "expected_range": expected_range,
            "points_target": points_target,
            "patience_weeks": patience_weeks,
            "ownership_sensitivity": ownership_sensitivity
        }
    
    @staticmethod
    def update_standing_metrics(state: SimState, team: Team, results: Dict, role: str) -> List[SimEvent]:
        """
        Time × Results × Role continuous update with hard gates and threshold triggers.
        Returns events triggered by metric thresholds.
        """
        events = []
        
        # Passive decay
        for metric in team.standing_metrics:
            team.standing_metrics[metric] *= 0.999  # Slow continuous decay
            team.standing_metrics[metric] = max(0, min(100, team.standing_metrics[metric]))
        
        # Results impact (simplified)
        if 'race_position' in results:
            position = results['race_position']
            if position <= 3:
                team.standing_metrics['reputation'] += 0.5
            elif position <= 10:
                team.standing_metrics['reputation'] += 0.1
        
        # Wire race results to standing metrics
        # Parse recent race_result events from event history
        recent_positions = []
        for event in state.event_history[-10:]:  # Check last 10 events
            if event.category == 'race_result':
                event_team = event.data.get('team', '')
                position = event.data.get('position', 0)
                
                # Only update if this event is for the current team
                if event_team == team.name and position > 0:
                    recent_positions.append(position)
                    
                    # Update media_standing based on finish position
                    if position <= 3:
                        team.standing_metrics['media_standing'] += 1.5
                    elif position <= 7:
                        team.standing_metrics['media_standing'] += 0.5
                    elif position <= 10:
                        team.standing_metrics['media_standing'] -= 0.2
                    else:
                        team.standing_metrics['media_standing'] -= 0.8
                    
                    # Update ownership_confidence
                    if position <= 3:
                        team.standing_metrics['ownership_confidence'] += 0.05
                    elif position >= 11:
                        team.standing_metrics['ownership_confidence'] -= 0.02
        
        # Calculate legitimacy dynamically
        # Find budget percentile
        budget_percentile = 50.0  # Default
        league_for_team = None
        for league in state.leagues.values():
            if team in league.teams:
                league_for_team = league
                budgets = sorted([t.budget.cash for t in league.teams])
                if team.budget.cash in budgets:
                    rank = budgets.index(team.budget.cash)
                    budget_percentile = (rank / max(1, len(budgets) - 1)) * 100
                break
        
        # Average finish position for last 5 races
        avg_finish = sum(recent_positions[-5:]) / len(recent_positions[-5:]) if recent_positions else 10
        num_teams = len(league_for_team.teams) if league_for_team else 16
        finish_score = max(0, 100 * (1 - avg_finish / num_teams))
        
        # Years in tier (approximation from season number)
        years_in_tier = min(3, state.season_number)
        
        # Championship position score
        champ_score = 50.0
        if league_for_team and team.name in league_for_team.championship_table:
            teams_sorted = sorted(league_for_team.championship_table.items(), key=lambda x: x[1], reverse=True)
            team_rank = next((i for i, (name, _) in enumerate(teams_sorted) if name == team.name), len(teams_sorted) // 2)
            champ_score = max(0, 100 * (1 - team_rank / max(1, len(teams_sorted))))
        
        # Composite legitimacy calculation
        new_legitimacy = (
            budget_percentile * 0.3 +
            finish_score * 0.4 +
            (years_in_tier * 10) * 0.2 +
            champ_score * 0.1
        )
        team.standing_metrics['legitimacy'] = new_legitimacy
        
        # Morale decay when cash runway < 10 weeks
        cash_runway = FTBSimulation.calculate_cash_runway(team)
        if cash_runway < 70:  # 10 weeks = 70 ticks
            team.standing_metrics['morale'] -= 0.5
        
        # Clamp all values
        for metric in team.standing_metrics:
            team.standing_metrics[metric] = max(0, min(100, team.standing_metrics[metric]))
        
        # ============================================================
        # THRESHOLD-TRIGGERED EVENTS (Hard Gates)
        # ============================================================
        
        # Only generate these events for player team to avoid spam
        if team != state.player_team:
            return events
        
        ownership_conf = team.standing_metrics['ownership_confidence']
        legitimacy = team.standing_metrics['legitimacy']
        reputation = team.standing_metrics['reputation']
        media_standing = team.standing_metrics['media_standing']
        morale = team.standing_metrics['morale']
        political_capital = team.standing_metrics.get('political_capital', 50.0)
        
        # Ownership Confidence Thresholds
        if ownership_conf < 20 and ownership_conf > 18:  # Small window to avoid spam
            events.append(SimEvent(
                event_type="pressure",
                category="ownership_ultimatum",
                ts=state.tick,
                priority=95.0,
                severity="critical",
                data={
                    'team': team.name,
                    'ownership_confidence': ownership_conf,
                    'message': 'Ownership demands immediate improvement or face termination',
                    'expected_results': 'P8+ in next 3 races'
                }
            ))
        elif ownership_conf < 10:
            events.append(SimEvent(
                event_type="consequence",
                category="forced_asset_sale",
                ts=state.tick,
                priority=90.0,
                severity="major",
                data={
                    'team': team.name,
                    'ownership_confidence': ownership_conf,
                    'asset': 'wind_tunnel_quality',
                    'degradation': -5,
                    'cash_injection': 200000,
                    'message': 'Ownership forces sale of infrastructure to raise cash'
                }
            ))
            # Apply the forced sale
            if 'wind_tunnel_quality' in team.infrastructure:
                team.infrastructure['wind_tunnel_quality'] = max(0, team.infrastructure['wind_tunnel_quality'] - 5)
                team.budget.cash += 200000
        
        # Morale Thresholds
        if morale < 30 and morale > 28:
            events.append(SimEvent(
                event_type="pressure",
                category="staff_morale_crisis",
                ts=state.tick,
                priority=80.0,
                severity="major",
                data={
                    'team': team.name,
                    'morale': morale,
                    'message': 'Staff morale at critical levels - performance penalties active',
                    'penalty': -5
                }
            ))
        
        if morale < 15:
            # Risk of staff resignation
            rng = state.get_rng("morale", state.tick)
            all_staff = team.drivers + team.engineers + team.mechanics
            for staff in all_staff:
                if rng.random() < 0.05:  # 5% chance per staff member
                    events.append(SimEvent(
                        event_type="consequence",
                        category="staff_resignation",
                        ts=state.tick,
                        priority=85.0,
                        severity="critical",
                        data={
                            'team': team.name,
                            'entity_name': staff.name,
                            'entity_type': type(staff).__name__,
                            'morale': morale,
                            'message': f'{staff.name} resigned due to poor working conditions'
                        }
                    ))
        
        # Media Standing Rewards/Penalties
        if media_standing > 70 and media_standing < 72:  # One-time windfall check
            events.append(SimEvent(
                event_type="outcome",
                category="sponsorship_windfall",
                ts=state.tick,
                priority=75.0,
                severity="info",
                data={
                    'team': team.name,
                    'media_standing': media_standing,
                    'bonus': 50000,
                    'message': 'Strong media presence attracts surprise sponsor bonus'
                }
            ))
            team.budget.cash += 50000
        
        if media_standing < 30:
            events.append(SimEvent(
                event_type="consequence",
                category="media_blackout",
                ts=state.tick,
                priority=60.0,
                severity="info",
                data={
                    'team': team.name,
                    'media_standing': media_standing,
                    'message': 'Media interest wanes - reduced coverage and sponsor visibility'
                }
            ))
        
        # Reputation Effects on Hiring Costs
        # (Implementation note: this will be checked in Action.hire_driver/hire_engineer legality)
        
        return events
    
    @staticmethod
    def generate_opportunities(state: SimState) -> List[SimEvent]:
        """Contract expiries, job board updates"""
        events = []
        rng = state.get_rng("opportunities", state.tick)
        
        # Job vacancy creation (15% chance per tick)
        if rng.random() < 0.15:
            # Find underperforming AI teams (legitimacy < 40 or low standing metrics)
            struggling_teams = [
                t for t in state.ai_teams 
                if t.standing_metrics.get('legitimacy', 50) < 40 
                or t.standing_metrics.get('reputation', 50) < 35
            ]
            
            if struggling_teams:
                team = rng.choice(struggling_teams)
                
                # Determine role (weighted toward driver/engineer)
                role_weights = [
                    ('driver', 0.4),
                    ('engineer', 0.3),
                    ('team_principal', 0.2),
                    ('strategist', 0.1)
                ]
                role = rng.choices(
                    [r for r, w in role_weights],
                    weights=[w for r, w in role_weights]
                )[0]
                
                # Find team's league tier
                tier = state.player_team.name if state.player_team else "grassroots"
                for league_id, league in state.leagues.items():
                    if team in league.teams:
                        tier = league_id
                        break
                
                # Create job listing
                job = JobListing(
                    team_name=team.name,
                    role=role,
                    tier=tier,
                    expectation_band=(40, 70),  # Mid-range expectations
                    patience_profile=30  # ticks to auto-fill
                )
                
                state.job_board.vacancies.append(job)
                
                events.append(SimEvent(
                    event_type="opportunity",
                    category="job_listing",
                    ts=state.tick,
                    priority=50.0,
                    severity="info",
                    data={
                        'role': role,
                        'team': team.name,
                        'tier': tier
                    }
                ))
        
        # Job vacancy removal (5% chance per tick per vacancy)
        vacancies_to_remove = []
        for job in state.job_board.vacancies:
            if rng.random() < 0.05:
                vacancies_to_remove.append(job)
                
                events.append(SimEvent(
                    event_type="opportunity",
                    category="job_removed",
                    ts=state.tick,
                    priority=20.0,
                    severity="info",
                    data={
                        'role': job.role,
                        'team': job.team_name,
                        'reason': 'position filled'
                    }
                ))
        
        for job in vacancies_to_remove:
            state.job_board.vacancies.remove(job)
        
        return events
    
    @staticmethod
    def create_decision(state: SimState, category: str, prompt: str, options: List[DecisionOption], 
                       deadline_ticks: int = 20, auto_resolve_id: str = None) -> DecisionEvent:
        """Create a new decision event and add to pending decisions"""
        decision_id = f"decision_{state.tick}_{category}"
        auto_id = auto_resolve_id or options[0].id  # Default to first option
        
        decision = DecisionEvent(
            decision_id=decision_id,
            category=category,
            prompt=prompt,
            options=options,
            deadline_tick=state.tick + deadline_ticks,
            auto_resolve_option_id=auto_id,
            created_tick=state.tick,
            resolved=False
        )
        
        state.pending_decisions.append(decision)
        return decision
    
    @staticmethod
    def resolve_decision(state: SimState, decision_id: str, chosen_option_id: str) -> List[SimEvent]:
        """Resolve a decision and apply its consequences"""
        events = []
        
        # Find the decision
        decision = next((d for d in state.pending_decisions if d.decision_id == decision_id), None)
        if not decision or decision.resolved:
            return events
        
        # Mark as resolved
        decision.resolved = True
        decision.chosen_option_id = chosen_option_id
        
        # Find the chosen option
        chosen_option = next((opt for opt in decision.options if opt.id == chosen_option_id), None)
        if not chosen_option:
            return events
        
        # Apply costs
        if state.player_team and chosen_option.cost > 0:
            state.player_team.budget.cash -= chosen_option.cost
        
        # Emit resolution event
        events.append(SimEvent(
            event_type="outcome",
            category=f"decision_resolved_{decision.category}",
            ts=state.tick,
            priority=85.0,
            severity="major",
            data={
                'decision_id': decision_id,
                'category': decision.category,
                'chosen_option': chosen_option.label,
                'cost': chosen_option.cost,
                'message': f'Decision made: {chosen_option.label}'
            }
        ))
        
        # Apply specific consequence logic based on category
        consequence_events = FTBSimulation._apply_decision_consequences(state, decision.category, chosen_option_id)
        events.extend(consequence_events)
        
        return events
    
    @staticmethod
    def _apply_decision_consequences(state: SimState, category: str, option_id: str) -> List[SimEvent]:
        """Apply specific consequences for different decision types"""
        events = []
        team = state.player_team
        if not team:
            return events
        
        # Ownership Ultimatum
        if category == "ownership_ultimatum":
            if option_id == "accept_terms":
                team.standing_metrics['reputation'] = max(0, team.standing_metrics['reputation'] - 10)
                team.standing_metrics['ownership_confidence'] = 60.0  # Reset to stable level
            elif option_id == "seek_investor":
                team.budget.cash += 100000
                team.standing_metrics['ownership_confidence'] = 55.0
                # TODO: Add debt tracking
            elif option_id == "resign":
                # TODO: Trigger job search or game over
                pass
        
        # Fire Sale
        elif category == "fire_sale":
            if option_id.startswith("fire_driver"):
                # Remove first driver
                if team.drivers:
                    fired = team.drivers[0]
                    team.drivers.remove(fired)
                    team.budget.remove_staff_salary(fired.name)
                    team.standing_metrics['reputation'] -= 5
            elif option_id.startswith("fire_engineer"):
                if team.engineers:
                    fired = team.engineers[0]
                    team.engineers.remove(fired)
                    team.budget.remove_staff_salary(fired.name)
                    team.standing_metrics['reputation'] -= 3
            elif option_id == "sell_asset":
                if 'wind_tunnel' in team.infrastructure:
                    team.infrastructure['wind_tunnel'] = max(0, team.infrastructure['wind_tunnel'] - 10)
                    team.budget.cash += 150000
        
        # Development Risk Choice
        elif category == "development_risk":
            # Store chosen risk profile for use in resolve_development
            # This would be referenced when the development completes
            pass
        
        return events
    
    @staticmethod
    def check_pending_decisions(state: SimState) -> List[SimEvent]:
        """Check for expired decisions and auto-resolve them"""
        events = []
        
        for decision in state.pending_decisions[:]:
            if not decision.resolved and state.tick >= decision.deadline_tick:
                # Auto-resolve with default option
                auto_events = FTBSimulation.resolve_decision(
                    state, 
                    decision.decision_id, 
                    decision.auto_resolve_option_id
                )
                events.extend(auto_events)
                
                events.append(SimEvent(
                    event_type="consequence",
                    category="decision_auto_resolved",
                    ts=state.tick,
                    priority=75.0,
                    severity="warning",
                    data={
                        'decision_id': decision.decision_id,
                        'message': 'Decision deadline passed - automatically resolved'
                    }
                ))
        
        # Remove resolved decisions
        state.pending_decisions = [d for d in state.pending_decisions if not d.resolved]
        
        return events
    
    @staticmethod
    def evaluate_action(action: Action, team: Team, state: SimState) -> float:
        """Pure numerical action scoring for AI teams"""
        # Simplified evaluation - full implementation would analyze impact
        base_score = 50.0
        
        # Financial viability
        if not action.is_legal(team.budget, team):
            return 0.0
        
        return base_score
    
    @staticmethod
    def apply_tendency_weights(score: float, tendencies: AIPrincipal) -> float:
        """Bias action score by AI principal tendencies"""
        # Tendencies modify evaluation, not simulation outcomes
        aggression_modifier = (tendencies.current_ratings['aggression'] - 50.0) / 100.0
        return score * (1.0 + aggression_modifier)
    
    @staticmethod
    def ai_team_decide(team: Team, state: SimState) -> Optional[Action]:
        """AI team decision: evaluate + weight + select (NO LLM)"""
        actions = FTBSimulation.get_available_actions(team, state)
        
        if not actions:
            return None
        
        # Evaluate all actions
        scored_actions = []
        for action in actions:
            score = FTBSimulation.evaluate_action(action, team, state)
            if team.principal:
                score = FTBSimulation.apply_tendency_weights(score, team.principal)
            scored_actions.append((action, score))
        
        # Select best
        scored_actions.sort(key=lambda x: x[1], reverse=True)
        return scored_actions[0][0] if scored_actions else None
    
    @staticmethod
    @staticmethod
    def get_available_actions(team: Team, state: SimState) -> List[Action]:
        """Enumerate legal actions based on budget, phase, contracts"""
        actions = []
        
        # Hiring actions
        actions.append(Action("hire_driver", cost=50000, target=None))
        actions.append(Action("hire_engineer", cost=30000, target=None))
        
        # Firing actions (one per current employee)
        for driver in team.drivers:
            # Small cost for severance
            actions.append(Action("fire_driver", cost=5000, target=driver.name))
        
        for engineer in team.engineers:
            actions.append(Action("fire_engineer", cost=3000, target=engineer.name))
        
        # Development
        actions.append(Action("develop_car", cost=100000, target=None))
        
        # Job applications (for player team only)
        if team == state.player_team:
            visible_jobs = state.job_board.filter_visible_to_player(team.standing_metrics)
            for job in visible_jobs:
                # Application fee (small)
                actions.append(Action("apply_for_job", cost=1000, target=job))
        
        # Filter to legal only (budget check)
        return [a for a in actions if a.is_legal(team.budget, team)]
    
    @staticmethod
    def apply_origin_modifiers(state: SimState, origin: str) -> None:
        """Apply disclosed origin effects (starting cash, perception)"""
        if not state.player_team:
            return
        
        origin_effects = {
            'game_show_winner': {'cash': 150000, 'media_standing': 60, 'legitimacy': 40},
            'grassroots_hustler': {'cash': 50000, 'media_standing': 40, 'legitimacy': 60},
            'former_driver': {'cash': 80000, 'media_standing': 55, 'legitimacy': 55},
            'corporate_spinout': {'cash': 500000, 'media_standing': 50, 'legitimacy': 45},
            'engineering_savant': {'cash': 120000, 'media_standing': 45, 'legitimacy': 50},
        }
        
        effects = origin_effects.get(origin, {})
        state.player_team.budget.cash = effects.get('cash', 100000)
        state.player_team.standing_metrics['media_standing'] = effects.get('media_standing', 50)
        state.player_team.standing_metrics['legitimacy'] = effects.get('legitimacy', 50)
    
    @staticmethod
    def create_new_save(origin_story: str, player_identity: List[str], save_mode: str, 
                       tier: str = "grassroots", seed: Optional[int] = None) -> SimState:
        """Initialize a new game save"""
        state = SimState()
        state.save_mode = save_mode
        state.player_identity = player_identity
        
        # Set seed for deterministic mode
        if seed is None:
            seed = int(time.time())
            
        state.seed = seed
        
        # 1. Generate Full World
        WorldBuilder.generate_world(state)
        
        # 2. Assign Player (Simple MVP: Take over first Grassroots team)
        # TODO: Implement proper Founder/Manager selection logic based on origin_story
        target_league_id = 'grassroots_1'
        if target_league_id in state.leagues:
            league = state.leagues[target_league_id]
            if league.teams:
                p_team = league.teams[0]
                p_team.name = "Player Racing"
                state.player_team = p_team
                if p_team in state.ai_teams:
                    state.ai_teams.remove(p_team)
                # Ensure principal is removed or converted
                p_team.principal = None 
        else:
             # Fallback
             state.player_team = Team("Player Racing")
        
        # Apply origin effects (budget adjustments etc)
        FTBSimulation.apply_origin_modifiers(state, origin_story)
        
        return state
    
    @staticmethod
    def _generate_event_id(state: SimState) -> int:
        """Generate unique event ID and increment counter"""
        event_id = state._next_event_id
        state._next_event_id += 1
        return event_id
    
    @staticmethod
    def apply_action(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """
        Apply an action to the simulation state and return consequence events.
        This creates stateful multi-system side effects.
        """
        events = []
        
        # Validate action is legal
        if not action.is_legal(team.budget, team):
            return events  # Silently fail if illegal
        
        # Deduct cost immediately
        team.budget.cash -= action.cost
        
        # Route to specific action handlers
        if action.name == "hire_driver":
            events.extend(FTBSimulation._apply_hire_driver(action, team, state))
        elif action.name == "fire_driver":
            events.extend(FTBSimulation._apply_fire_driver(action, team, state))
        elif action.name == "hire_engineer":
            events.extend(FTBSimulation._apply_hire_engineer(action, team, state))
        elif action.name == "fire_engineer":
            events.extend(FTBSimulation._apply_fire_engineer(action, team, state))
        elif action.name == "develop_car":
            events.extend(FTBSimulation._apply_develop_car(action, team, state))
        elif action.name == "apply_for_job":
            events.extend(FTBSimulation._apply_job_application(action, team, state))
        
        # Assign event IDs
        for event in events:
            if event.event_id == 0:
                event.event_id = FTBSimulation._generate_event_id(state)
        
        return events
    
    @staticmethod
    def _apply_hire_driver(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """Hire a driver from the job market or generate new one"""
        events = []
        
        # If target is a driver entity, use it; otherwise generate new driver
        if action.target and isinstance(action.target, Driver):
            driver = action.target
        else:
            # Generate new driver with tier-appropriate stats
            rng = state.get_rng("hiring", f"driver_{state.tick}")
            tier_base = 30 + rng.randint(0, 20)
            driver = Driver(name=f"Driver_{state.tick}", age=18 + rng.randint(0, 15))
            
            # Initialize ratings around tier base
            for stat in driver.current_ratings:
                driver.current_ratings[stat] = tier_base + rng.uniform(-10, 10)
        
        # Add to roster
        team.drivers.append(driver)
        
        # Calculate salary (base * overall rating / 50)
        salary = SALARY_BASE['Driver'] * (driver.overall_rating / 50.0)
        team.budget.add_staff_salary(driver.name, salary)
        
        # Create events
        hire_event = SimEvent(
            event_type="structural",
            category="driver_hired",
            ts=state.tick,
            priority=60.0,
            severity="info",
            data={
                'team': team.name,
                'driver': driver.name,
                'age': driver.age,
                'overall_rating': driver.overall_rating,
                'salary': salary,
                'cost': action.cost
            }
        )
        events.append(hire_event)
        
        # Morale boost from new hire (slight)
        team.standing_metrics['morale'] = min(100, team.standing_metrics['morale'] + 2.0)
        
        morale_event = SimEvent(
            event_type="outcome",
            category="morale_change",
            ts=state.tick,
            priority=30.0,
            severity="info",
            data={
                'team': team.name,
                'change': +2.0,
                'reason': f"New driver {driver.name} joins team",
                'new_morale': team.standing_metrics['morale']
            },
            caused_by=hire_event.event_id  # Will be set in apply_action
        )
        events.append(morale_event)
        
        # Reputation shift based on hire quality
        rep_change = (driver.overall_rating - 50.0) * 0.1
        team.standing_metrics['reputation'] = max(0, min(100, team.standing_metrics['reputation'] + rep_change))
        
        return events
    
    @staticmethod
    def _apply_fire_driver(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """Fire a driver from the roster"""
        events = []
        
        # Find driver by name (action.target should be driver name)
        driver_name = action.target
        driver = next((d for d in team.drivers if d.name == driver_name), None)
        
        if not driver:
            return events  # No-op if driver not found
        
        # Calculate seniority penalty (years with team approximated by performance_history length)
        seniority = len(driver.performance_history)
        rep_penalty = min(5.0, seniority * 0.5)
        
        # Remove from roster and payroll
        team.drivers.remove(driver)
        team.budget.remove_staff_salary(driver_name)
        
        # Create events
        fire_event = SimEvent(
            event_type="structural",
            category="driver_fired",
            ts=state.tick,
            priority=70.0,
            severity="warning",
            data={
                'team': team.name,
                'driver': driver_name,
                'seniority': seniority,
                'overall_rating': driver.overall_rating
            }
        )
        events.append(fire_event)
        
        # Morale hit
        team.standing_metrics['morale'] = max(0, team.standing_metrics['morale'] - 5.0)
        
        morale_event = SimEvent(
            event_type="outcome",
            category="morale_change",
            ts=state.tick,
            priority=50.0,
            severity="warning",
            data={
                'team': team.name,
                'change': -5.0,
                'reason': f"Driver {driver_name} fired",
                'new_morale': team.standing_metrics['morale']
            },
            caused_by=fire_event.event_id
        )
        events.append(morale_event)
        
        # Reputation penalty
        team.standing_metrics['reputation'] = max(0, team.standing_metrics['reputation'] - rep_penalty)
        
        rep_event = SimEvent(
            event_type="outcome",
            category="reputation_change",
            ts=state.tick,
            priority=50.0,
            severity="warning",
            data={
                'team': team.name,
                'change': -rep_penalty,
                'reason': f"Firing {driver_name} with {seniority} years tenure",
                'new_reputation': team.standing_metrics['reputation']
            },
            caused_by=fire_event.event_id
        )
        events.append(rep_event)
        
        return events
    
    @staticmethod
    def _apply_hire_engineer(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """Hire an engineer"""
        events = []
        
        # Generate new engineer
        rng = state.get_rng("hiring", f"engineer_{state.tick}")
        tier_base = 30 + rng.randint(0, 20)
        engineer = Engineer(name=f"Engineer_{state.tick}", age=22 + rng.randint(0, 15))
        
        for stat in engineer.current_ratings:
            engineer.current_ratings[stat] = tier_base + rng.uniform(-10, 10)
        
        team.engineers.append(engineer)
        
        salary = SALARY_BASE['Engineer'] * (engineer.overall_rating / 50.0)
        team.budget.add_staff_salary(engineer.name, salary)
        
        events.append(SimEvent(
            event_type="structural",
            category="engineer_hired",
            ts=state.tick,
            priority=50.0,
            severity="info",
            data={
                'team': team.name,
                'engineer': engineer.name,
                'overall_rating': engineer.overall_rating,
                'salary': salary
            }
        ))
        
        team.standing_metrics['morale'] = min(100, team.standing_metrics['morale'] + 1.0)
        
        return events
    
    @staticmethod
    def _apply_fire_engineer(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """Fire an engineer"""
        events = []
        
        engineer_name = action.target
        engineer = next((e for e in team.engineers if e.name == engineer_name), None)
        
        if not engineer:
            return events
        
        team.engineers.remove(engineer)
        team.budget.remove_staff_salary(engineer_name)
        
        events.append(SimEvent(
            event_type="structural",
            category="engineer_fired",
            ts=state.tick,
            priority=50.0,
            severity="info",
            data={'team': team.name, 'engineer': engineer_name}
        ))
        
        team.standing_metrics['morale'] = max(0, team.standing_metrics['morale'] - 3.0)
        
        return events
    
    @staticmethod
    def _apply_develop_car(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """
        Initiate car development with delayed resolution.
        Creates a pending development that resolves after N ticks.
        """
        events = []
        
        # Calculate engineer bonus (average technical depth of all engineers)
        engineer_bonus = 0.0
        if team.engineers:
            engineer_bonus = sum(e.technical_depth_score for e in team.engineers) / len(team.engineers)
        
        # Development resolves in 14 ticks (2 weeks) by default
        resolve_tick = state.tick + 14
        
        # Record pending development
        state.pending_developments.append({
            'team_name': team.name,
            'resolve_tick': resolve_tick,
            'cost': action.cost,
            'engineer_bonus': engineer_bonus,
            'initiated_tick': state.tick
        })
        
        # Immediate event
        events.append(SimEvent(
            event_type="structural",
            category="development_initiated",
            ts=state.tick,
            priority=60.0,
            severity="info",
            data={
                'team': team.name,
                'cost': action.cost,
                'resolve_tick': resolve_tick,
                'engineer_bonus': engineer_bonus
            }
        ))
        
        return events
    
    @staticmethod
    def _apply_job_application(action: Action, team: Team, state: SimState) -> List[SimEvent]:
        """
        Apply for a job opening. If accepted, transfer player team.
        """
        events = []
        
        # action.target should be a JobListing
        job = action.target
        
        if not job or not isinstance(job, JobListing):
            return events
        
        # Check acceptance probability based on standing metrics
        acceptance_prob = state.job_board.apply_for_job(team, job)
        
        rng = state.get_rng("jobs", f"application_{state.tick}")
        accepted = rng.random() < acceptance_prob
        
        if accepted:
            # Find the AI team and transfer player to it
            target_team = next((t for t in state.ai_teams if t.name == job.team_name), None)
            
            if target_team:
                # Transfer player identity to new team
                old_team_name = state.player_team.name
                state.player_team = target_team
                state.ai_teams.remove(target_team)
                
                events.append(SimEvent(
                    event_type="structural",
                    category="job_accepted",
                    ts=state.tick,
                    priority=90.0,
                    severity="info",
                    data={
                        'old_team': old_team_name,
                        'new_team': target_team.name,
                        'role': job.role,
                        'tier': job.tier
                    }
                ))
                
                # Remove job from board
                if job in state.job_board.vacancies:
                    state.job_board.vacancies.remove(job)
        else:
            events.append(SimEvent(
                event_type="opportunity",
                category="job_rejected",
                ts=state.tick,
                priority=60.0,
                severity="warning",
                data={
                    'team': team.name,
                    'target_team': job.team_name,
                    'role': job.role,
                    'acceptance_prob': acceptance_prob
                }
            ))
        
        return events
    
    @staticmethod
    def _resolve_pending_developments(state: SimState) -> List[SimEvent]:
        """
        Check for pending developments that should resolve this tick.
        Roll outcomes based on engineer bonus and update car stats.
        """
        events = []
        resolved = []
        
        for dev in state.pending_developments:
            if dev['resolve_tick'] <= state.tick:
                # Find team
                team = state.player_team if state.player_team and state.player_team.name == dev['team_name'] else None
                if not team:
                    team = next((t for t in state.ai_teams if t.name == dev['team_name']), None)
                
                if not team or not team.car:
                    resolved.append(dev)
                    continue
                
                # Roll outcome: success / minor gain / regression
                # Engineer bonus (0-100) biases toward success
                rng = state.get_rng("dev", f"resolve_{dev['initiated_tick']}")
                roll = rng.random() * 100.0
                
                # Base probabilities: 30% regression, 40% minor, 30% breakthrough
                # Engineer bonus shifts these: +1% success per engineer point above 50
                engineer_bonus = dev['engineer_bonus']
                success_threshold = 70.0 - (engineer_bonus - 50.0)  # Lower threshold = easier success
                minor_threshold = 30.0
                
                if roll < minor_threshold:
                    outcome = "regression"
                    rating_change = -rng.uniform(1.0, 3.0)
                elif roll < success_threshold:
                    outcome = "minor_gain"
                    rating_change = rng.uniform(0.5, 2.0)
                else:
                    outcome = "breakthrough"
                    rating_change = rng.uniform(2.0, 5.0)
                
                # Apply to car (update a random stat)
                stat_names = list(team.car.current_ratings.keys())
                if stat_names:
                    target_stat = rng.choice(stat_names)
                    old_value = team.car.current_ratings[target_stat]
                    team.car.current_ratings[target_stat] = max(0, min(100, old_value + rating_change))
                    new_value = team.car.current_ratings[target_stat]
                    
                    events.append(SimEvent(
                        event_type="outcome",
                        category="development_result",
                        ts=state.tick,
                        priority=70.0,
                        severity="info" if outcome != "regression" else "warning",
                        data={
                            'team': team.name,
                            'outcome': outcome,
                            'stat': target_stat,
                            'old_value': old_value,
                            'new_value': new_value,
                            'change': rating_change,
                            'cost': dev['cost'],
                            'engineer_bonus': engineer_bonus
                        }
                    ))
                
                resolved.append(dev)
        
        # Remove resolved developments
        for dev in resolved:
            state.pending_developments.remove(dev)
        
        return events
    
    @staticmethod
    def _execute_ai_team_actions(state: SimState) -> List[SimEvent]:
        """
        AI teams probabilistically execute actions (10% chance per team per tick).
        """
        events = []
        rng = state.get_rng("ai_actions", state.tick)
        
        for team in state.ai_teams:
            if rng.random() < 0.10:  # 10% chance per tick
                # Get available actions for this team
                actions = FTBSimulation.get_available_actions(team, state)
                
                if actions:
                    # Use existing AI decision logic
                    action = FTBSimulation.ai_team_decide(team, state)
                    
                    if action and action in actions:
                        # Apply the action
                        action_events = FTBSimulation.apply_action(action, team, state)
                        events.extend(action_events)
                        
                        # Log AI action summary
                        events.append(SimEvent(
                            event_type="structural",
                            category="ai_action",
                            ts=state.tick,
                            priority=20.0,
                            severity="info",
                            data={
                                'team': team.name,
                                'action': action.name,
                                'cost': action.cost
                            }
                        ))
        
        return events
    
    @staticmethod
    def calculate_cash_runway(team: Team) -> float:
        """
        Calculate weeks of cash remaining at current burn rate.
        Returns number of ticks (weeks) until cash runs out.
        """
        payroll_per_tick = team.budget.calculate_staff_payroll()
        
        # Calculate infrastructure upkeep
        upkeep_per_tick = 0.0
        for key, calc_func in INFRASTRUCTURE_UPKEEP_COST.items():
            quality = team.infrastructure.get(key, 0.0)
            upkeep_per_tick += calc_func(quality)
        
        total_burn = payroll_per_tick + upkeep_per_tick + team.budget.burn_rate
        
        if total_burn <= 0:
            return float('inf')  # No burn, infinite runway
        
        return team.budget.cash / total_burn
    
    @staticmethod
    def calculate_reputation_trend(state: SimState, team: Team, lookback_ticks: int = 10) -> str:
        """
        Calculate reputation trend over last N ticks.
        Returns '↑' (increasing), '↓' (decreasing), or '→' (stable).
        """
        # Get reputation changes from recent event history
        recent_events = [e for e in state.event_history if e.ts > (state.tick - lookback_ticks)]
        reputation_changes = [
            e.data.get('change', 0.0) for e in recent_events 
            if e.category == 'reputation_change'
        ]
        
        # Also check current vs historical
        if not reputation_changes:
            # No explicit reputation events, check passive decay assumption
            # If no race results, should be declining slowly
            return '→'
        
        total_change = sum(reputation_changes)
        
        if total_change > 2.0:
            return '↑'
        elif total_change < -2.0:
            return '↓'
        else:
            return '→'
    
    @staticmethod
    def calculate_morale_state(team: Team) -> str:
        """
        Bin morale into Low/Stable/High categories.
        """
        morale = team.standing_metrics.get('morale', 50.0)
        
        if morale < 40.0:
            return "Low"
        elif morale > 60.0:
            return "High"
        else:
            return "Stable"


# ============================================================
# SECTION 6: UI Widget
# ============================================================

try:
    import tkinter as tk
    from tkinter import ttk, simpledialog
    
    class FTBWidget(tk.Frame):
        """Main game interface handling Setup Wizard and Game Loop"""
        
        def __init__(self, parent, runtime_stub):
            super().__init__(parent)
            self.runtime = runtime_stub
            self.state = None
            self.current_view = None  # "wizard" or "game"
            
            # Queue is created in register_widgets - just log that we're using it
            cmd_q = self.runtime.get("ftb_cmd_q")
            print(f"[FTB WIDGET] Using queue id={id(cmd_q)}, runtime dict id={id(self.runtime)}, queue exists={cmd_q is not None}")
            
            # Wizard Variables
            self.wiz_seed = tk.StringVar(value=str(int(time.time())))
            self.wiz_save_mode = tk.StringVar(value="permanent")
            self.wiz_origin = tk.StringVar(value="grassroots_hustler")
            self.wiz_identity = tk.StringVar(value="The Stranger")
            self.wiz_tier = tk.StringVar(value="grassroots")
            
            # Build container
            self.container = ttk.Frame(self)
            self.container.pack(fill=tk.BOTH, expand=True)
            
            self.show_wizard()
        
        def clear_ui(self):
            for widget in self.container.winfo_children():
                widget.destroy()
        
        def show_wizard(self):
            if self.current_view == "wizard": return
            self.clear_ui()
            self.current_view = "wizard"
            
            # Header
            ttk.Label(self.container, text="New Game Setup", font=("Arial", 14, "bold")).pack(pady=10)
            
            # Form Frame
            form = ttk.Frame(self.container)
            form.pack(fill=tk.X, padx=20)
            
            # 1. Save Mode
            lf_mode = ttk.LabelFrame(form, text="1. Save Mode")
            lf_mode.pack(fill=tk.X, pady=5)
            ttk.Label(lf_mode, text="Deterministic: Same seed = same outcomes (replayable)").pack(anchor=tk.W, padx=5)
            ttk.Label(lf_mode, text="Permanent: Entropy injected (unique playthrough)").pack(anchor=tk.W, padx=5)
            ttk.Radiobutton(lf_mode, text="Replayable (Deterministic)", variable=self.wiz_save_mode, value="replayable").pack(anchor=tk.W, padx=5)
            ttk.Radiobutton(lf_mode, text="Permanent (Entropy)", variable=self.wiz_save_mode, value="permanent").pack(anchor=tk.W, padx=5)
            
            # 2. Seed
            lf_seed = ttk.LabelFrame(form, text="2. World Seed")
            lf_seed.pack(fill=tk.X, pady=5)
            ttk.Label(lf_seed, text="Locks world generation & RNG (editable only here)").pack(anchor=tk.W, padx=5)
            seed_row = ttk.Frame(lf_seed)
            seed_row.pack(fill=tk.X, padx=5, pady=5)
            ttk.Entry(seed_row, textvariable=self.wiz_seed, width=20).pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(seed_row, text="Randomize", command=lambda: self.wiz_seed.set(str(int(time.time())))).pack(side=tk.LEFT, padx=5)
            
            # 3. Identity
            lf_ident = ttk.LabelFrame(form, text="3. Identity & Origin")
            lf_ident.pack(fill=tk.X, pady=5)
            ttk.Label(lf_ident, text="Origin Story (affects starting conditions):").pack(anchor=tk.W, padx=5)
            origins = ['game_show_winner', 'grassroots_hustler', 'former_driver', 'corporate_spinout', 'engineering_savant']
            ttk.Combobox(lf_ident, textvariable=self.wiz_origin, values=origins, state="readonly").pack(fill=tk.X, padx=5, pady=2)
            
            ttk.Label(lf_ident, text="Player Identity (comma-separated descriptors):").pack(anchor=tk.W, padx=5, pady=(10, 0))
            self.wiz_identity_text = tk.Text(lf_ident, height=3, width=40, wrap=tk.WORD)
            self.wiz_identity_text.pack(fill=tk.X, padx=5, pady=5)
            self.wiz_identity_text.insert('1.0', "The Stranger")
            
            # 4. Confirmation & Start
            confirm_frame = ttk.Frame(self.container)
            confirm_frame.pack(pady=10, padx=20)
            ttk.Label(confirm_frame, text="These settings are locked once game starts", font=("Arial", 9, "italic")).pack()
            ttk.Button(self.container, text="START NEW GAME", command=self.confirm_and_submit_wizard).pack(pady=10, fill=tk.X, padx=20)
        
        def confirm_and_submit_wizard(self):
            """Show confirmation dialog before starting game"""
            from tkinter import messagebox
            print("[FTB] confirm_and_submit_wizard called")  # Debug log
            
            try:
                seed = int(self.wiz_seed.get())
            except:
                seed = int(time.time())
            
            save_mode = self.wiz_save_mode.get()
            origin = self.wiz_origin.get()
            identity_text = self.wiz_identity_text.get('1.0', tk.END).strip()
            identity_list = [s.strip() for s in identity_text.split(',') if s.strip()]
            
            print(f"[FTB] Showing confirmation: seed={seed}, mode={save_mode}, origin={origin}")  # Debug log
            
            # Build confirmation message
            msg = f"""Game Setup Confirmation:

Seed: {seed}
Save Mode: {save_mode.title()}
Origin: {origin.replace('_', ' ').title()}
Identity: {', '.join(identity_list)}

These settings cannot be changed after starting.
Only way to modify is by editing the save file directly.

Start game with these settings?"""
            
            confirmed = messagebox.askyesno("Confirm New Game", msg)
            print(f"[FTB] User confirmed: {confirmed}")  # Debug log
            
            if confirmed:
                q = self.runtime["ftb_cmd_q"]
                print(f"[FTB BUTTON] Putting command in queue id={id(q)}, runtime dict id={id(self.runtime)}")
                q.put({
                    "cmd": "ftb_new_save",
                    "origin": origin,
                    "identity": identity_list,
                    "save_mode": save_mode,
                    "tier": self.wiz_tier.get(),
                    "seed": seed
                })
                print(f"[FTB BUTTON] Command queued successfully! Queue size now: {q.qsize()}")
        
        def submit_wizard(self):
            """Send setup command to controller"""
            try:
                seed = int(self.wiz_seed.get())
            except:
                seed = int(time.time())
                
            self.runtime["ftb_cmd_q"].put({
                "cmd": "ftb_new_save",
                "origin": self.wiz_origin.get(),
                "identity": [self.wiz_identity.get()], # List format
                "save_mode": self.wiz_save_mode.get(),
                "tier": self.wiz_tier.get(),
                "seed": seed
            })
            
        def show_game_interface(self):
            if self.current_view == "game": return
            self.clear_ui()
            self.current_view = "game"
            
            # --- Menu Bar ---
            menubar = tk.Menu(self)
            filemenu = tk.Menu(menubar, tearoff=0)
            filemenu.add_command(label="New Game", command=self.new_game)
            filemenu.add_command(label="Save Game", command=self.save_game)
            filemenu.add_command(label="Load Game", command=self.load_game)
            filemenu.add_separator()
            filemenu.add_command(label="Exit to Menu", command=self.exit_to_menu)
            menubar.add_cascade(label="File", menu=filemenu)
            
            # Try to set menu (may not work on all platforms)
            try:
                self.master.config(menu=menubar)
            except:
                pass
            
            # --- Time Control Toolbar ---
            toolbar = ttk.Frame(self.container)
            toolbar.pack(fill=tk.X, padx=5, pady=5)
            
            self.cal_label = ttk.Label(toolbar, text="--/--", font=("Arial", 10, "bold"), width=15)
            self.cal_label.pack(side=tk.LEFT)
            
            ttk.Button(toolbar, text="+1 Day", command=lambda: self.send_tick(1)).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="+1 Week", command=lambda: self.send_tick_batch(7)).pack(side=tk.LEFT, padx=2)
            ttk.Button(toolbar, text="+1 Month", command=lambda: self.send_tick_batch(30)).pack(side=tk.LEFT, padx=2)
            
            # --- Main Layout: Left side (metrics + team) and Right side (event log) ---
            main_container = ttk.Frame(self.container)
            main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Left side
            left_frame = ttk.Frame(main_container)
            left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # --- Pressure Indicators Dashboard ---
            metrics_frame = ttk.LabelFrame(left_frame, text="Pressure Indicators")
            metrics_frame.pack(fill=tk.X, padx=5, pady=5)
            
            self.runway_label = ttk.Label(metrics_frame, text="Cash Runway: --")
            self.runway_label.pack(anchor=tk.W)
            
            self.rep_trend_label = ttk.Label(metrics_frame, text="Reputation Trend: --")
            self.rep_trend_label.pack(anchor=tk.W)
            
            self.morale_label = ttk.Label(metrics_frame, text="Morale: --")
            self.morale_label.pack(anchor=tk.W)
            
            # --- Team Overview ---
            team_frame = ttk.LabelFrame(left_frame, text="Team Overview")
            team_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            self.team_label = ttk.Label(team_frame, text="Team: Loading...")
            self.team_label.pack(anchor=tk.W)
            
            self.budget_label = ttk.Label(team_frame, text="Budget: $0")
            self.budget_label.pack(anchor=tk.W)
            
            self.mode_label = ttk.Label(team_frame, text="Status: Paused")
            self.mode_label.pack(anchor=tk.W)
            
            # Right side - Event Log
            log_frame = ttk.LabelFrame(main_container, text="Event Log")
            log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Scrollable text widget
            log_scroll = ttk.Scrollbar(log_frame)
            log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            
            self.event_log_text = tk.Text(log_frame, wrap=tk.WORD, height=20, width=50, 
                                          yscrollcommand=log_scroll.set)
            self.event_log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            log_scroll.config(command=self.event_log_text.yview)
            
            # Configure tags for severity colors
            self.event_log_text.tag_config("info", foreground="black")
            self.event_log_text.tag_config("warning", foreground="orange")
            self.event_log_text.tag_config("causality", foreground="gray")
        
        def new_game(self):
            """Return to wizard for new game"""
            self.runtime["ftb_cmd_q"].put({"cmd": "ftb_reset"})
            self.show_wizard()
        
        def save_game(self):
            """Prompt for save name and save"""
            name = simpledialog.askstring("Save Game", "Enter save name:")
            if name:
                # Construct path in saves directory
                import os
                saves_dir = "saves"
                if not os.path.exists(saves_dir):
                    os.makedirs(saves_dir)
                
                # Sanitize filename
                safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
                if not safe_name:
                    safe_name = "save"
                
                path = os.path.join(saves_dir, f"{safe_name}.json")
                self.runtime["ftb_cmd_q"].put({"cmd": "ftb_save", "path": path})
        
        def load_game(self):
            """Open save browser dialog"""
            # TODO: Implement full save browser with metadata
            # For now, simple file dialog
            import os
            from tkinter import filedialog
            filename = filedialog.askopenfilename(
                initialdir="saves",
                title="Select save file",
                filetypes=(("JSON files", "*.json"), ("All files", "*.*"))
            )
            if filename:
                self.runtime["ftb_cmd_q"].put({"cmd": "ftb_load_save", "path": filename})
        
        def exit_to_menu(self):
            """Exit to menu without destroying save"""
            self.runtime["ftb_cmd_q"].put({"cmd": "ftb_reset"})
            self.show_wizard()
        
        def send_tick(self, n):
            self.runtime["ftb_cmd_q"].put({"cmd": "ftb_tick_step", "n": n})
        
        def send_tick_batch(self, n):
            """Send batch tick command which generates summary"""
            self.runtime["ftb_cmd_q"].put({"cmd": "ftb_tick_batch", "n": n})
        
        def update_from_state(self, state: SimState):
            """Called by poll when state exists"""
            if state is None:
                self.show_wizard()
                return
                
            self.show_game_interface()
            self.state = state
            
            # Use safe access as state might be snapshot or object
            date_str = getattr(state, "current_date_str", lambda: "Unknown")()
            if isinstance(date_str, str): 
                self.cal_label.config(text=date_str)
            
            # Access attributes safely
            p_team = state.player_team
            if p_team:
                self.team_label.config(text=f"Team: {p_team.name}")
                self.budget_label.config(text=f"Bank: ${p_team.budget.cash:,.0f}")
                
                # Update pressure indicators
                runway = FTBSimulation.calculate_cash_runway(p_team)
                if runway == float('inf'):
                    runway_text = "∞ (No burn)"
                    runway_color = "green"
                elif runway < 10:
                    runway_text = f"{runway:.1f} weeks"
                    runway_color = "red"
                elif runway < 30:
                    runway_text = f"{runway:.1f} weeks"
                    runway_color = "orange"
                else:
                    runway_text = f"{runway:.1f} weeks"
                    runway_color = "green"
                
                self.runway_label.config(text=f"Cash Runway: {runway_text}", foreground=runway_color)
                
                rep_trend = FTBSimulation.calculate_reputation_trend(state, p_team)
                self.rep_trend_label.config(text=f"Reputation Trend: {rep_trend}")
                
                morale_state = FTBSimulation.calculate_morale_state(p_team)
                morale_color = "red" if morale_state == "Low" else "green" if morale_state == "High" else "black"
                self.morale_label.config(text=f"Morale: {morale_state}", foreground=morale_color)
                
            tm = getattr(state, "time_mode", "paused")
            self.mode_label.config(text=f"Time: {tm.title()}")
            
            # Update event log
            self.update_event_log(state)
        
        def update_event_log(self, state: SimState):
            """Update event log with recent events, showing causality"""
            if not hasattr(self, 'event_log_text'):
                return
            
            # Clear log
            self.event_log_text.delete('1.0', tk.END)
            
            # Show last 20 events
            recent_events = state.event_history[-20:] if state.event_history else []
            
            # Build causality map
            event_map = {e.event_id: e for e in recent_events}
            
            for event in recent_events:
                # Check if this is a child event
                indent = ""
                tag = "info"
                
                if event.caused_by and event.caused_by in event_map:
                    indent = "  → "
                    tag = "causality"
                
                if event.severity == "warning":
                    tag = "warning"
                
                # Format event text
                timestamp = f"T{event.ts}"
                category = event.category.replace('_', ' ').title()
                text = f"{timestamp} [{category}]"
                
                # Add key data
                if 'team' in event.data:
                    text += f" {event.data['team']}"
                if 'driver' in event.data:
                    text += f" - {event.data['driver']}"
                if 'change' in event.data:
                    text += f" ({event.data['change']:+.1f})"
                
                # Insert with indentation and tags
                self.event_log_text.insert(tk.END, indent + text + "\n", tag)
            
            # Auto-scroll to bottom
            self.event_log_text.see(tk.END)

        def start_poll(self):
            """Begin UI refresh loop"""
            self.after(500, self._poll)
        
        def _poll(self):
            """Poll controller for state updates"""
            controller = self.runtime.get("ftb_controller")
            if not controller:
                self.after(500, self._poll)
                return

            # If no state, we are in wizard mode
            if not controller.state:
                if self.current_view != "wizard":
                    self.show_wizard()
            else:
                # Switch to game view if necessary
                if self.current_view != "game":
                    self.show_game_interface()
                
                try:
                    # Get snapshot
                    with controller.state_lock:
                         # We can't deepcopy easily, so we just use the reference carefully
                         # or checks simple values. Ideally we'd clone but for UI refresh 
                         # accessing properties is usually fine if we don't iterate lists.
                         pass
                    # Just call update with live state for now
                    self.update_from_state(controller.state)
                except Exception:
                    pass
            
            self.after(500, self._poll)

except ImportError:
    # Fallback if tkinter not available
    class FTBWidget:
        def __init__(self, parent, runtime_stub):
            pass


# ============================================================
# SECTION 6.4: Narration Helper Methods (for narrative_engine)
# ============================================================

class FTBNarrationHelpers:
    """Helper methods to extract narrative facts from simulation state"""
    
    @staticmethod
    def get_player_team_name(state: SimState) -> str:
        """Get player team identifier"""
        if state.player_team:
            return state.player_team.name
        return ""
    
    @staticmethod
    def get_team_league(state: SimState, team_name: str) -> Tuple[str, int]:
        """
        Find which league/tier a team belongs to.
        
        Returns:
            (league_name, tier_number)
        """
        for league_name, league in state.leagues.items():
            for team in league.teams:
                if team.name == team_name:
                    return (league.name, league.tier)
        return ("Unknown", 0)
    
    @staticmethod
    def get_narration_facts(state: SimState, events: List[SimEvent]) -> Dict[str, Any]:
        """
        Build minimal context bundle for narrator LLM.
        This avoids dumping full state into prompts.
        
        Returns:
            Compact dict with only narrative-relevant facts
        """
        facts = {
            "day": state.tick,
            "phase": state.phase,
            "date_str": state.current_date_str()
        }
        
        # Player team facts
        if state.player_team:
            team = state.player_team
            league_name, tier = FTBNarrationHelpers.get_team_league(state, team.name)
            
            facts["team"] = {
                "name": team.name,
                "cash": team.budget.cash,
                "burn_rate": team.budget.burn_rate,
                "league": league_name,
                "tier": tier
            }
            
            # Driver info (assume single driver for now)
            if team.drivers:
                driver = team.drivers[0]
                facts["team"]["driver"] = driver.name
        
        # Season context
        facts["season"] = {
            "number": state.season_number,
            "races_completed": state.races_completed_this_season,
            "in_offseason": state.in_offseason
        }
        
        # Recent trend (derive from event history)
        recent_trend = FTBNarrationHelpers._calculate_recent_trend(state)
        facts["recent_trend"] = recent_trend
        
        # Formula Z standings (tier 1)
        formula_z_data = FTBNarrationHelpers._get_formula_z_standings(state)
        if formula_z_data:
            facts["formula_z_top3"] = formula_z_data["top3"]
            facts["formula_z_leader_gap"] = formula_z_data["leader_gap"]
        
        return facts
    
    @staticmethod
    def _calculate_recent_trend(state: SimState) -> str:
        """Derive trajectory from recent race results"""
        # Look at last 3 race results for player team
        race_results = [
            e for e in state.event_history[-20:]
            if e.category == "race_result" and 
               e.data.get("team") == (state.player_team.name if state.player_team else "")
        ][-3:]
        
        if len(race_results) < 2:
            return "unknown"
        
        # Check if positions are improving
        positions = [e.data.get("position", 20) for e in race_results]
        
        # Simple trend detection
        if positions[-1] < positions[0] - 2:
            return "improving"
        elif positions[-1] > positions[0] + 2:
            return "declining"
        else:
            return "flat"
    
    @staticmethod
    def _get_formula_z_standings(state: SimState) -> Optional[Dict[str, Any]]:
        """Get Formula Z (tier 1) championship standings"""
        # Find tier 1 league
        formula_z_league = None
        for league in state.leagues.values():
            if league.tier == 1:
                formula_z_league = league
                break
        
        if not formula_z_league:
            return None
        
        # Get top 3
        standings = sorted(
            formula_z_league.championship_table.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        if not standings:
            return None
        
        leader_points = standings[0][1]
        second_points = standings[1][1] if len(standings) > 1 else 0
        
        return {
            "top3": [team for team, _ in standings],
            "leader_gap": leader_points - second_points
        }


# ============================================================
# SECTION 6.5: FTB Controller (Runtime Boundary)
# ============================================================

class FTBController:
    """
    Boundary object between FTB simulation engine and Radio OS runtime.
    
    Responsibilities:
    - Run tick loop thread
    - Process UI commands (delegate, save, load, tick control)
    - Convert SimEvent → StationEvent
    - Periodic widget refresh
    - Save/load with expanded serialization
    """
    
    def __init__(self, runtime: Dict[str, Any], mem: Dict[str, Any]):
        self.runtime = runtime
        self.mem = mem
        self.state: Optional[SimState] = None
        self.tick_rate = 2.0  # seconds per tick
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.state_lock = threading.Lock()
        self.autosave_interval = 10  # ticks
        
        # Get logger
        self.log = runtime.get('log', print)
    
    def start_new_game(self, origin: Optional[str] = None, 
                      identity: Optional[List[str]] = None,
                      save_mode: Optional[str] = None,
                      tier: str = "grassroots",
                      seed: Optional[int] = None) -> None:
        """Create new save and initialize simulation"""
        self.log("ftb", f"Starting new game: origin={origin}, identity={identity}, save_mode={save_mode}, tier={tier}, seed={seed}")
        cfg = self.runtime.get("config", {}).get("ftb", {})
        
        origin = origin or cfg.get("origin_story", "game_show_winner")
        identity = identity or cfg.get("player_identity", [])
        save_mode = save_mode or cfg.get("save_mode", "permanent")
        starting_tier = cfg.get("starting_tier", tier)
        
        if seed is None:
            seed = int(time.time()) if save_mode == "permanent" else 42
        
        self.log("ftb", f"Creating new save with resolved params...")
        with self.state_lock:
            self.state = FTBSimulation.create_new_save(
                origin_story=origin,
                player_identity=identity,
                save_mode=save_mode,
                tier=starting_tier,
                seed=seed
            )
        
        self.log("ftb", f"New game created successfully! Team: {self.state.player_team.name if self.state and self.state.player_team else 'None'}")
        
        self.log("ftb", f"New game: {origin} | {starting_tier} | {save_mode} | Seed: {seed}")
    
    def load_save(self, path: str) -> None:
        """Load save from JSON"""
        try:
            with self.state_lock:
                self.state = SimState.load_from_json(path)
            self.log("ftb", f"Loaded save: {path}")
        except Exception as e:
            self.log("ftb", f"Failed to load save: {e}")
    
    def save_game(self, path: Optional[str] = None) -> None:
        """Save current state to JSON"""
        if not self.state:
            return
        
        if path is None:
            station_dir = self.runtime.get("STATION_DIR", ".")
            path = os.path.join(station_dir, "ftb_autosave.json")
        
        try:
            with self.state_lock:
                self.state.save_to_json(path)
            self.log("ftb", f"Saved to {path}")
        except Exception as e:
            self.log("ftb", f"Failed to save: {e}")
    
    def start(self) -> None:
        """Start tick loop thread"""
        if self.thread and self.thread.is_alive():
            return
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log("ftb", "Controller started")
    
    def stop(self) -> None:
        """Stop tick loop thread"""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2.0)
        self.log("ftb", "Controller stopped")
    
    def _run(self) -> None:
        """Main tick loop"""
        self.log("ftb", "Controller thread started, entering main loop...")
        tick_count = 0
        
        while not self.stop_event.is_set():
            try:
                tick_count += 1
                if tick_count % 10 == 0:  # Log heartbeat every 20 seconds
                    cmd_q = self.runtime.get("ftb_cmd_q")
                    q_size = cmd_q.qsize() if cmd_q else -1
                    self.log("ftb", f"Thread heartbeat: tick={tick_count}, q_size={q_size}, state={'exists' if self.state else 'None'}")
                
                # Handle UI commands
                self._handle_ui_cmds()
                
                # Advance simulation (only if auto mode)
                if self.state and self.state.time_mode == 'auto':
                    with self.state_lock:
                        events = FTBSimulation.tick_simulation(self.state)
                    
                    # Convert and emit events
                    self._emit_events(events)
                    
                    # Auto-save
                    if self.state.tick % self.autosave_interval == 0:
                        self.save_game()
                
                # Refresh widget (always, if state exists)
                if self.state:
                    self._refresh_widget()
                
            except Exception as e:
                import traceback
                self.log("ftb", f"Tick error: {e}")
                self.log("ftb", traceback.format_exc())
            
            time.sleep(self.tick_rate)
    
    def _handle_ui_cmds(self) -> None:
        """Process commands from ftb_cmd_q"""
        ftb_cmd_q = self.runtime.get("ftb_cmd_q")
        if not ftb_cmd_q:
            print(f"[FTB CONTROLLER] _handle_ui_cmds: no ftb_cmd_q found in runtime dict id={id(self.runtime)}")
            return
        
        if ftb_cmd_q.empty():
            return  # Nothing to process
        
        print(f"[FTB CONTROLLER] _handle_ui_cmds: queue id={id(ftb_cmd_q)} has items, size={ftb_cmd_q.qsize()}, runtime dict id={id(self.runtime)}")
        
        try:
            while not ftb_cmd_q.empty():
                msg = ftb_cmd_q.get_nowait()
                cmd = msg.get("cmd", "")
                print(f"[FTB] Processing command: {cmd}, full_msg={msg}")
                self.log("ftb", f"Processing command: {cmd}")
                
                if cmd == "ftb_new_save":
                    print("[FTB] Handling ftb_new_save command")
                    origin = msg.get("origin")
                    identity = msg.get("identity")
                    save_mode = msg.get("save_mode")
                    tier = msg.get("tier", "grassroots")
                    seed = msg.get("seed")
                    print(f"[FTB] Calling start_new_game with: origin={origin}, identity={identity}, save_mode={save_mode}, tier={tier}, seed={seed}")
                    self.start_new_game(origin, identity, save_mode, tier, seed)
                    print("[FTB] start_new_game returned")
                
                elif cmd == "ftb_load_save":
                    path = msg.get("path")
                    if path:
                        self.load_save(path)
                
                elif cmd == "ftb_save":
                    path = msg.get("path")
                    self.save_game(path)
                
                elif cmd == "ftb_tick_step":
                    n = int(msg.get("n", 1))
                    if self.state:
                        for _ in range(n):
                            with self.state_lock:
                                events = FTBSimulation.tick_simulation(self.state)
                            self._emit_events(events)
                
                elif cmd == "ftb_tick_batch":
                    n = int(msg.get("n", 7))
                    if self.state:
                        # Execute batch and collect summary
                        start_tick = self.state.tick
                        start_cash = self.state.player_team.budget.cash if self.state.player_team else 0
                        all_events = []
                        
                        for _ in range(n):
                            with self.state_lock:
                                events = FTBSimulation.tick_simulation(self.state)
                                all_events.extend(events)
                            self._emit_events(events)
                        
                        # Generate summary event
                        with self.state_lock:
                            end_cash = self.state.player_team.budget.cash if self.state.player_team else 0
                            races = sum(1 for e in all_events if e.category == "race_result")
                            major_events = sum(1 for e in all_events if e.priority > 70)
                            
                            summary = SimEvent(
                                event_type="time",
                                category="time_batch_summary",
                                ts=self.state.tick,
                                priority=80.0,
                                severity="info",
                                event_id=FTBSimulation._generate_event_id(self.state),
                                data={
                                    'start_tick': start_tick,
                                    'end_tick': self.state.tick,
                                    'ticks': n,
                                    'net_cash_delta': end_cash - start_cash,
                                    'races_completed': races,
                                    'major_events_count': major_events,
                                    'start_cash': start_cash,
                                    'end_cash': end_cash
                                }
                            )
                            self.state.event_history.append(summary)
                            self._emit_events([summary])
                            
                            # Show popup via ui_q
                            ui_q = self.runtime.get("ui_q")
                            if ui_q:
                                ui_q.put({
                                    "type": "batch_summary",
                                    "data": summary.data
                                })
                
                elif cmd == "ftb_reset":
                    # Reset to wizard (clear state)
                    with self.state_lock:
                        self.state = None
                    self.log("ftb", "Reset to menu")
                
                elif cmd == "ftb_set_time_mode":
                    mode = msg.get("mode", "paused")
                    if self.state and mode in ["paused", "auto", "manual"]:
                        with self.state_lock:
                            self.state.time_mode = mode
                        self.log("ftb", f"Time mode set to {mode}")

                elif cmd == "ftb_set_tick_rate":
                    sec = float(msg.get("sec", 2.0))
                    self.tick_rate = max(0.1, min(10.0, sec))
                    self.log("ftb", f"Tick rate set to {self.tick_rate}s")
                
                elif cmd == "ftb_delegate":
                    focus = msg.get("focus", "balanced")
                    if self.state:
                        with self.state_lock:
                            self.state.control_mode = "delegated"
                            self.state.player_focus = focus
                        self.log("ftb", f"Delegation enabled: {focus}")
                
                elif cmd == "ftb_regain_control":
                    if self.state:
                        with self.state_lock:
                            self.state.control_mode = "human"
                        self.log("ftb", "Human control restored")
                
                elif cmd == "ftb_action":
                    action_id = msg.get("action_id")
                    params = msg.get("params", {})
                    # TODO: Apply action to state
                    self.log("ftb", f"Action: {action_id} {params}")
        
        except Exception as e:
            import traceback
            self.log("ftb", f"UI cmd error: {e}")
            self.log("ftb", traceback.format_exc())
    
    def _emit_events(self, sim_events: List[SimEvent]) -> None:
        """
        Emit From the Backmarker simulation events.

        Architectural guarantees:
        - SimEvents are NEVER spoken directly.
        - StationEvents are UI / observability ONLY.
        - ALL narration is produced exclusively by the FTB meta plugin
        via beat → segment emission.
        """

        # ------------------------------------------------------------------
        # 1. Emit UI-only StationEvents (NO radio path, NO narration)
        # ------------------------------------------------------------------
        ui_event_q = self.runtime.get("ui_event_q")
        StationEvent = self.runtime.get("StationEvent")

        if ui_event_q and StationEvent:
            for sim_event in sim_events:
                try:
                    ui_event_q.put(StationEvent(
                        source="ftb_game",
                        type=sim_event.category,
                        ts=sim_event.ts,
                        severity=sim_event.severity,
                        priority=0,  # irrelevant for UI-only
                        payload={
                            **sim_event.data,
                            "_ftb": True,
                            "_ui_only": True,
                            "_event_id": sim_event.event_id,
                        },
                    ))
                except Exception as e:
                    self.log("ftb", f"UI StationEvent emit error: {e}")

        # ------------------------------------------------------------------
        # 2. Emit narrative beats via FTB meta plugin (ONLY narration path)
        # ------------------------------------------------------------------
        try:
            ACTIVE_META_PLUGIN = self.runtime.get("ACTIVE_META_PLUGIN")
            if not ACTIVE_META_PLUGIN:
                return

            if not hasattr(ACTIVE_META_PLUGIN, "ftb_emit_segments"):
                return

            import bookmark
            conn = bookmark.db_connect()

            # Snapshot sim state safely
            with self.state_lock:
                state_snapshot = self.state

            # Meta plugin converts SimEvents → beats → DB segments
            ACTIVE_META_PLUGIN.ftb_emit_segments(
                sim_events,
                state_snapshot,
                conn
            )

            conn.close()

        except Exception as e:
            self.log("ftb", f"Narrative beat emission error: {e}")
            import traceback
            self.log("ftb", traceback.format_exc())

    def _refresh_widget(self) -> None:
        """Send widget update to UI"""
        ui_q = self.runtime.get("ui_q")
        if not ui_q or not self.state:
            return
        
        try:
            with self.state_lock:
                update_data = {
                    "tick": self.state.tick,
                    "date_str": self.state.current_date_str(),
                    "phase": self.state.phase,
                    "time_mode": self.state.time_mode,
                    "control_mode": self.state.control_mode,
                    "player_focus": self.state.player_focus,
                }
                
                if self.state.player_team:
                    update_data["team_name"] = self.state.player_team.name
                    update_data["league_name"] = "Unknown League"
                    # Find league of player team
                    for lg in self.state.leagues.values():
                        if self.state.player_team in lg.teams:
                            update_data["league_name"] = lg.name
                            break
                            
                    update_data["budget"] = self.state.player_team.budget.cash
            
            ui_q.put(("widget_update", {
                "widget_key": "ftb_game",
                "data": update_data
            }))
        
        except Exception as e:
            self.log("ftb", f"Widget refresh error: {e}")


# ============================================================
# SECTION 7: Widget Registration
# ============================================================

def register_widgets(registry, runtime_stub):
    """Register FTB widget and start controller"""
    # Create command queue for UI -> controller communication
    runtime_stub["ftb_cmd_q"] = queue.Queue()
    print(f"[FTB REGISTER] Created queue id={id(runtime_stub['ftb_cmd_q'])}, runtime dict id={id(runtime_stub)}")
    
    # Create and start controller
    mem = runtime_stub.get("mem") or {}
    controller = FTBController(runtime_stub, mem)
    runtime_stub["ftb_controller"] = controller
    controller.start()
    
    # Auto-create a default game if none exists
    # if not controller.state:
    #     controller.start_new_game()
    
    # Register widget factory - IMPORTANT: Use runtime_stub from closure, not rt parameter
    # The rt parameter may be a different dict instance each time the widget is created
    def factory(parent, rt):
        print(f"[FTB FACTORY] Creating widget with runtime_stub from closure id={id(runtime_stub)}, rt param id={id(rt)}")
        widget = FTBWidget(parent, runtime_stub)  # Use captured runtime_stub, not rt param
        widget.start_poll()  # Begin UI refresh loop
        return widget
    
    registry.register(
        "ftb_game",
        factory,
        title="From the Backmarker",
        default_panel="right"
    )


# ============================================================
# SECTION 8: Plugin Metadata
# ============================================================

PLUGIN_NAME = "From the Backmarker"
PLUGIN_DESC = "Formula Z Racing Manager - Simulation Mode"
IS_FEED = False  # No feed_worker - uses controller + meta plugin instead


