"""
FTB Heritage Templates - Procedural Manufacturer Identity System

Heritage templates define nationality-based manufacturing philosophies
that bias stat distributions for procedurally generated manufacturers.
Each template encodes design philosophy, typical strengths/weaknesses,
and naming grammar for authentic manufacturer diversity.

Design: Templates are NOT manufacturers themselves - they're blueprints
for generating unique manufacturer entities with coherent nationality identity.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class HeritageTemplate:
    """
    Nationality-based manufacturer template with philosophy biases.
    Used to generate unique Manufacturer entities with stat variance.
    """
    nationality: str  # "Japanese", "German", etc.
    naming_grammar: Dict[str, List[str]]  # Prefixes, suffixes, patterns
    philosophy_bias_stats: Dict[str, float]  # Stat modifiers (±10 points)
    typical_strengths: List[str]  # Descriptive text for narrative
    typical_weaknesses: List[str]  # Descriptive text for narrative
    tier_preference: Dict[int, float]  # Weighted probability per tier (1-5)


# ============================================================
# HERITAGE TEMPLATE DEFINITIONS
# ============================================================

HERITAGE_TEMPLATES: Dict[str, HeritageTemplate] = {
    "japanese": HeritageTemplate(
        nationality="Japanese",
        naming_grammar={
            "prefixes": ["Taka", "Yama", "Hiro", "Kawa", "Sato", "Naka", "Ishi"],
            "suffixes": ["Gawa", "Moto", "Dynamics", "Racing", "Tech", "Works"],
            "patterns": ["compound", "suffix"],  # TakaGawa, YamaDynamics
        },
        philosophy_bias_stats={
            "reliability_philosophy": +8.0,
            "quality_control_rigor": +10.0,
            "build_quality": +8.0,
            "consistency": +7.0,
            "innovation_rate": -3.0,  # More cautious, tested development
            "risk_appetite": -5.0,
        },
        typical_strengths=[
            "Exceptional reliability",
            "Consistent quality control",
            "Methodical development",
            "Long-term durability"
        ],
        typical_weaknesses=[
            "Conservative innovation pace",
            "Slower to breakthrough concepts",
            "Risk-averse development culture"
        ],
        tier_preference={1: 0.5, 2: 0.8, 3: 1.2, 4: 1.5, 5: 1.8}  # Stronger in upper tiers
    ),
    
    "german": HeritageTemplate(
        nationality="German",
        naming_grammar={
            "prefixes": ["Kraft", "Technik", "Präzision", "Hoch", "Schmidt", "Weber"],
            "suffixes": ["Motor", "Engineering", "Werke", "Systems", "Tech", "Dynamics"],
            "patterns": ["compound", "formal"],  # KraftMotor, TechnikWerke
        },
        philosophy_bias_stats={
            "quality_control_rigor": +12.0,
            "technical_heritage": +9.0,
            "cfd_capability": +8.0,
            "wind_tunnel_access": +7.0,
            "development_cycle_speed": -4.0,  # Thorough but slower
            "material_science_depth": +8.0,
        },
        typical_strengths=[
            "Engineering rigor",
            "Technical depth",
            "CFD/wind tunnel mastery",
            "Materials science leadership"
        ],
        typical_weaknesses=[
            "Slower development cycles",
            "Over-engineering tendencies",
            "Higher complexity/cost"
        ],
        tier_preference={1: 0.4, 2: 0.9, 3: 1.3, 4: 1.6, 5: 2.0}  # Dominant in Formula Z
    ),
    
    "italian": HeritageTemplate(
        nationality="Italian",
        naming_grammar={
            "prefixes": ["Rossi", "Bianchi", "Ferrari", "Veloce", "Corsa"],
            "suffixes": ["oni", "ini", "Motorsport", "Racing", "Corse", "Veloce"],
            "patterns": ["suffix", "passionate"],  # Rossioni, VeloceCorsa
        },
        philosophy_bias_stats={
            "aero_philosophy": +10.0,
            "innovation_rate": +7.0,
            "racing_pedigree": +9.0,
            "brand_prestige": +8.0,
            "financial_stability": -5.0,  # Passionate but volatile
            "consistency": -4.0,  # High peaks, lower valleys
        },
        typical_strengths=[
            "Aerodynamic artistry",
            "Racing heritage",
            "Passionate innovation",
            "Peak performance focus"
        ],
        typical_weaknesses=[
            "Financial volatility",
            "Inconsistent quality",
            "Emotional decision-making"
        ],
        tier_preference={1: 0.7, 2: 1.0, 3: 1.2, 4: 1.4, 5: 1.7}  # Strong across tiers
    ),
    
    "british": HeritageTemplate(
        nationality="British",
        naming_grammar={
            "prefixes": ["Hamilton", "Sterling", "Apex", "Sovereign", "Crown"],
            "suffixes": ["Engineering", "Motorsport", "Racing", "Technologies", "Systems"],
            "patterns": ["surname", "formal"],  # Hamilton Engineering, Apex Technologies
        },
        philosophy_bias_stats={
            "cost_cap_management": +8.0,
            "organizational_cohesion": +7.0,
            "supplier_relationship_management": +9.0,
            "customer_support": +8.0,
            "development_cycle_speed": +6.0,
            "material_science_depth": -3.0,
        },
        typical_strengths=[
            "Cost-efficient operations",
            "Organizational excellence",
            "Supplier partnerships",
            "Customer service focus"
        ],
        typical_weaknesses=[
            "Limited R&D budgets",
            "Materials science gaps",
            "Conservative tech philosophy"
        ],
        tier_preference={1: 1.8, 2: 1.5, 3: 1.0, 4: 0.7, 5: 0.4}  # Dominant in grassroots
    ),
    
    "american": HeritageTemplate(
        nationality="American",
        naming_grammar={
            "prefixes": ["Thunder", "Power", "Liberty", "Velocity", "Patriot"],
            "suffixes": ["Performance", "Racing", "Dynamics", "Motorsports", "Tech"],
            "patterns": ["bold", "compound"],  # ThunderPerformance, PowerDynamics
        },
        philosophy_bias_stats={
            "power_philosophy": +12.0,
            "risk_appetite": +8.0,
            "financial_stability": +7.0,
            "market_sensitivity": +6.0,
            "aero_philosophy": -6.0,  # Power-focused over aero
            "patience": -5.0,  # Aggressive, quick decisions
        },
        typical_strengths=[
            "Power unit dominance",
            "Risk-taking innovation",
            "Strong financial backing",
            "Market responsiveness"
        ],
        typical_weaknesses=[
            "Aerodynamic sophistication gaps",
            "Impatient development",
            "Over-reliance on power"
        ],
        tier_preference={1: 1.5, 2: 1.2, 3: 0.9, 4: 0.8, 5: 0.6}  # Stronger in lower tiers
    ),
    
    "scandinavian": HeritageTemplate(
        nationality="Scandinavian",
        naming_grammar={
            "prefixes": ["Nord", "Fjord", "Viking", "Arctic", "Svenson"],
            "suffixes": ["Motorsport", "Engineering", "Dynamics", "Racing", "Tech"],
            "patterns": ["nordic", "compound"],  # NordDynamics, VikingRacing
        },
        philosophy_bias_stats={
            "consistency": +11.0,
            "reliability_philosophy": +7.0,
            "innovation_rate": +5.0,
            "organizational_cohesion": +8.0,
            "brand_prestige": -4.0,  # Less heritage
            "racing_pedigree": -6.0,
        },
        typical_strengths=[
            "Exceptional consistency",
            "Reliable performance",
            "Innovative approaches",
            "Team cohesion"
        ],
        typical_weaknesses=[
            "Limited racing heritage",
            "Lower brand recognition",
            "Smaller talent pool"
        ],
        tier_preference={1: 1.0, 2: 1.1, 3: 1.0, 4: 0.8, 5: 0.5}  # Mid-tier focus
    ),
    
    "french": HeritageTemplate(
        nationality="French",
        naming_grammar={
            "prefixes": ["Renault", "Laurent", "Marseille", "Avant", "Nouveau"],
            "suffixes": ["Sport", "Technologie", "Racing", "Engineering", "Motorsport"],
            "patterns": ["elegant", "formal"],  # Laurent Technologie, AvantSport
        },
        philosophy_bias_stats={
            "innovation_rate": +10.0,
            "concept_generation": +8.0,
            "regulatory_adaptability": +9.0,
            "risk_appetite": +6.0,
            "build_quality": -5.0,  # Innovation over perfection
            "customer_support": -4.0,
        },
        typical_strengths=[
            "Innovation leadership",
            "Concept generation",
            "Regulation navigation",
            "Creative risk-taking"
        ],
        typical_weaknesses=[
            "Quality control issues",
            "Support infrastructure gaps",
            "Over-complexity"
        ],
        tier_preference={1: 0.6, 2: 0.9, 3: 1.1, 4: 1.4, 5: 1.3}  # Strong in upper tiers
    ),
    
    "korean": HeritageTemplate(
        nationality="Korean",
        naming_grammar={
            "prefixes": ["Seoul", "Hyundai", "Samsung", "Nexus", "Quantum"],
            "suffixes": ["Technologies", "Motorsport", "Engineering", "Dynamics", "Racing"],
            "patterns": ["modern", "tech"],  # QuantumTechnologies, SeoulDynamics
        },
        philosophy_bias_stats={
            "build_quality": +10.0,
            "manufacturing_complexity": +8.0,
            "development_cycle_speed": +7.0,
            "financial_stability": +6.0,
            "racing_pedigree": -8.0,  # New to motorsport
            "technical_heritage": -7.0,
        },
        typical_strengths=[
            "Manufacturing excellence",
            "Rapid development",
            "Financial strength",
            "Modern processes"
        ],
        typical_weaknesses=[
            "Limited racing heritage",
            "Newer technical knowledge",
            "Less motorsport experience"
        ],
        tier_preference={1: 1.2, 2: 1.0, 3: 0.8, 4: 0.6, 5: 0.3}  # Entry-level focus
    ),
}


def get_weighted_template(rng, tier: int) -> HeritageTemplate:
    """
    Select a heritage template with tier-weighted probability.
    
    Args:
        rng: Seeded random generator
        tier: League tier (1-5)
    
    Returns:
        Selected HeritageTemplate
    """
    weights = []
    templates = []
    
    for template_id, template in HERITAGE_TEMPLATES.items():
        weight = template.tier_preference.get(tier, 1.0)
        weights.append(weight)
        templates.append(template)
    
    # Weighted random choice
    total_weight = sum(weights)
    r = rng.random() * total_weight
    cumulative = 0.0
    
    for template, weight in zip(templates, weights):
        cumulative += weight
        if r <= cumulative:
            return template
    
    # Fallback to last template
    return templates[-1]
