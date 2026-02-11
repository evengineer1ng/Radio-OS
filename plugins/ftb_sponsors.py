"""
From the Backmarker - Procedural Sponsor Generation System

Generates infinite sponsor companies with distinct personalities, financial profiles,
and contract behaviors. No hand-authored lists - fully algorithmic generation using
pattern templates and seed-based determinism.

Each sponsor is a system with money, pressure, personality, and narrative hooks.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum
import hashlib
import random
import json


# ============================================================
# ENUMS AND CONSTANTS
# ============================================================

class Industry(Enum):
    """Primary industry categories"""
    AUTOMOTIVE = "automotive"
    ENERGY = "energy"
    TECHNOLOGY = "technology"
    FINANCE = "finance"
    CONSUMER = "consumer"
    INDUSTRIAL = "industrial"
    MEDIA = "media"
    LOCAL = "local"


class SubIndustry(Enum):
    """Detailed sub-industry classifications"""
    # Automotive
    OEM = "oem"
    AFTERMARKET = "aftermarket"
    PERFORMANCE_PARTS = "performance_parts"
    EV_TECH = "ev_tech"
    
    # Energy
    FUEL = "fuel"
    RENEWABLE = "renewable"
    SYNTHETIC_FUELS = "synthetic_fuels"
    
    # Technology
    SOFTWARE = "software"
    AI = "ai"
    SEMICONDUCTORS = "semiconductors"
    CONSUMER_ELECTRONICS = "consumer_electronics"
    
    # Finance
    RETAIL_BANK = "retail_bank"
    HEDGE_FUND = "hedge_fund"
    CRYPTO_EXCHANGE = "crypto_exchange"
    PAYMENTS = "payments"
    
    # Consumer
    APPAREL = "apparel"
    FOOTWEAR = "footwear"
    BEVERAGE = "beverage"
    NUTRITION = "nutrition"
    
    # Industrial
    MANUFACTURING = "manufacturing"
    LOGISTICS = "logistics"
    ROBOTICS = "robotics"
    
    # Media
    STREAMING = "streaming"
    SPORTS_BROADCAST = "sports_broadcast"
    GAMING = "gaming"
    
    # Local
    CONSTRUCTION = "construction"
    AUTO_DEALERSHIP = "auto_dealership"
    REGIONAL_BRAND = "regional_brand"


class FinancialTier(Enum):
    """Budget tier classifications"""
    MICRO = "micro"
    REGIONAL = "regional"
    NATIONAL = "national"
    GLOBAL = "global"


class BrandTone(Enum):
    """Brand personality tone"""
    GRITTY = "gritty"
    CORPORATE = "corporate"
    VISIONARY = "visionary"
    REBELLIOUS = "rebellious"
    HERITAGE = "heritage"
    INNOVATIVE = "innovative"


class InvolvementLevel(Enum):
    """Motorsport involvement history"""
    CURIOUS = "curious"
    ACTIVE = "active"
    LEGACY = "legacy"


class BrandingVisibility(Enum):
    """How aggressively sponsor brands the team"""
    SUBTLE = "subtle"
    AGGRESSIVE = "aggressive"
    DOMINANT = "dominant"


class ContractType(Enum):
    """Contract structure"""
    FIXED_SHORT = "fixed_short"  # 3-10 races
    SEASON_PARTNERSHIP = "season_partnership"  # Full season


class OriginStoryTag(Enum):
    """Heritage classification"""
    FAMILY_BUSINESS = "family_business"
    STARTUP_UNICORN = "startup_unicorn"
    CONGLOMERATE_SPINOFF = "conglomerate_spinoff"
    MERGER_ENTITY = "merger_entity"
    FOUNDER_VISION = "founder_vision"


# Industry → Sub-industries mapping
INDUSTRY_SUBINDUSTRIES: Dict[Industry, List[SubIndustry]] = {
    Industry.AUTOMOTIVE: [SubIndustry.OEM, SubIndustry.AFTERMARKET, SubIndustry.PERFORMANCE_PARTS, SubIndustry.EV_TECH],
    Industry.ENERGY: [SubIndustry.FUEL, SubIndustry.RENEWABLE, SubIndustry.SYNTHETIC_FUELS],
    Industry.TECHNOLOGY: [SubIndustry.SOFTWARE, SubIndustry.AI, SubIndustry.SEMICONDUCTORS, SubIndustry.CONSUMER_ELECTRONICS],
    Industry.FINANCE: [SubIndustry.RETAIL_BANK, SubIndustry.HEDGE_FUND, SubIndustry.CRYPTO_EXCHANGE, SubIndustry.PAYMENTS],
    Industry.CONSUMER: [SubIndustry.APPAREL, SubIndustry.FOOTWEAR, SubIndustry.BEVERAGE, SubIndustry.NUTRITION],
    Industry.INDUSTRIAL: [SubIndustry.MANUFACTURING, SubIndustry.LOGISTICS, SubIndustry.ROBOTICS],
    Industry.MEDIA: [SubIndustry.STREAMING, SubIndustry.SPORTS_BROADCAST, SubIndustry.GAMING],
    Industry.LOCAL: [SubIndustry.CONSTRUCTION, SubIndustry.AUTO_DEALERSHIP, SubIndustry.REGIONAL_BRAND],
}

# Tier-based budget ranges (per season, in dollars)
TIER_BUDGET_RANGES = {
    FinancialTier.MICRO: (5000, 15000),
    FinancialTier.REGIONAL: (20000, 80000),
    FinancialTier.NATIONAL: (100000, 300000),
    FinancialTier.GLOBAL: (400000, 1500000),
}

# Tier volatility (likelihood of sudden withdrawal)
TIER_VOLATILITY = {
    FinancialTier.MICRO: 0.15,
    FinancialTier.REGIONAL: 0.10,
    FinancialTier.NATIONAL: 0.08,
    FinancialTier.GLOBAL: 0.25,
}

# Tier loyalty base (likelihood to renew)
TIER_LOYALTY_BASE = {
    FinancialTier.MICRO: 0.75,
    FinancialTier.REGIONAL: 0.60,
    FinancialTier.NATIONAL: 0.45,
    FinancialTier.GLOBAL: 0.30,
}

# Name generation components (pattern templates)
PHONETIC_CONSONANTS = ['b', 'd', 'f', 'g', 'h', 'j', 'k', 'l', 'm', 'n', 'p', 'r', 's', 't', 'v', 'w', 'z']
PHONETIC_VOWELS = ['a', 'e', 'i', 'o', 'u', 'ei', 'ai', 'ou']

ABSTRACT_CONCEPTS = [
    'Velocity', 'Unity', 'Edge', 'Apex', 'Forge', 'Pulse', 'Vector', 'Nexus',
    'Summit', 'Horizon', 'Eclipse', 'Titan', 'Vortex', 'Nova', 'Zenith', 'Thunder',
    'Lightning', 'Quantum', 'Fusion', 'Catalyst', 'Momentum', 'Kinetic', 'Dynamic',
    'Precision', 'Pioneer', 'Frontier', 'Sovereign', 'Prime', 'Pinnacle', 'Crest'
]

INDUSTRIAL_SUFFIXES = [
    'Motors', 'Dynamics', 'Systems', 'Group', 'Works', 'Industries', 'Engineering',
    'Technologies', 'Solutions', 'International', 'Corporation', 'Enterprises'
]

TECH_SUFFIXES = [
    'Labs', 'AI', 'Digital', 'Technologies', 'Computing', 'Software', 'Systems',
    'Analytics', 'Data', 'Cloud', 'Networks', 'Tech'
]

MOTORSPORT_CUES = [
    'Racing', 'Performance', 'GP', 'Sport', 'Motorsport', 'Speed', 'Track',
    'Circuit', 'Podium', 'Championship'
]

GEOGRAPHIC_PREFIXES = [
    'North', 'South', 'East', 'West', 'Central', 'Pacific', 'Atlantic', 'Global',
    'International', 'United', 'Continental', 'Regional', 'National', 'Metro'
]

INDUSTRY_KEYWORDS = {
    Industry.AUTOMOTIVE: ['Auto', 'Vehicle', 'Drive', 'Wheel', 'Engine', 'Transmission'],
    Industry.ENERGY: ['Energy', 'Power', 'Fuel', 'Charge', 'Volt', 'Electric'],
    Industry.TECHNOLOGY: ['Tech', 'Digital', 'Cyber', 'Smart', 'Connect', 'Data'],
    Industry.FINANCE: ['Capital', 'Investments', 'Financial', 'Equity', 'Ventures', 'Holdings'],
    Industry.CONSUMER: ['Brand', 'Lifestyle', 'Premium', 'Select', 'Elite', 'Choice'],
    Industry.INDUSTRIAL: ['Industrial', 'Manufacturing', 'Production', 'Build', 'Construct', 'Fabrication'],
    Industry.MEDIA: ['Media', 'Broadcast', 'Stream', 'Content', 'Entertainment', 'Productions'],
    Industry.LOCAL: ['Local', 'Community', 'Regional', 'City', 'Town', 'District'],
}


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Heritage:
    """Company heritage and origin"""
    founding_year: int
    origin_story_tag: OriginStoryTag


@dataclass
class BrandProfile:
    """Brand personality and positioning"""
    tone: BrandTone
    prestige: float  # 0.0-1.0
    risk_appetite: float  # 0.0-1.0
    ethics: float  # 0.0-1.0


@dataclass
class FinancialProfile:
    """Financial capacity and stability"""
    tier: FinancialTier
    budget_min: int
    budget_max: int
    volatility: float


@dataclass
class MotorsportAlignment:
    """Motorsport involvement preferences"""
    involvement_level: InvolvementLevel
    preferred_series: List[str]
    values: List[str]


@dataclass
class ContractBehavior:
    """Contract lifecycle personality"""
    loyalty: float  # 0.0-1.0
    pressure_threshold: float  # 0.0-1.0
    performance_dependency: float  # 0.0-1.0
    reputation_dependency: float  # 0.0-1.0


@dataclass
class ActivationStyle:
    """Branding and activation preferences"""
    branding_visibility: BrandingVisibility
    requires_podiums: bool
    requires_media_mentions: bool
    requires_driver_profile: bool


@dataclass
class NarrativeHooks:
    """Flags for narrative system"""
    scandal_risk: float  # 0.0-1.0
    bailout_savior: bool
    hostile_exit: bool
    legacy_sponsor: bool


@dataclass
class SponsorProfile:
    """Complete sponsor company profile"""
    sponsor_id: str
    name: str
    short_name: str
    industry: Industry
    sub_industry: SubIndustry
    headquarters_country: str
    headquarters_region: str
    heritage: Heritage
    brand_profile: BrandProfile
    financial_profile: FinancialProfile
    motorsport_alignment: MotorsportAlignment
    contract_behavior: ContractBehavior
    activation_style: ActivationStyle
    narrative_hooks: NarrativeHooks
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        def enum_to_str(obj):
            if isinstance(obj, Enum):
                return obj.value
            elif isinstance(obj, dict):
                return {k: enum_to_str(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [enum_to_str(item) for item in obj]
            elif hasattr(obj, '__dataclass_fields__'):
                # Handle nested dataclasses
                return {k: enum_to_str(v) for k, v in asdict(obj).items()}
            elif hasattr(obj, '__dict__'):
                return {k: enum_to_str(v) for k, v in obj.__dict__.items()}
            return obj
        
        return enum_to_str(asdict(self))


# ============================================================
# PROCEDURAL GENERATION ENGINE
# ============================================================

def _deterministic_hash(seed: int, component: str, index: int) -> int:
    """Generate deterministic hash for stable procedural generation"""
    combined = f"{seed}_{component}_{index}"
    hash_val = int(hashlib.sha256(combined.encode()).hexdigest(), 16)
    return hash_val


def _hash_to_float(seed: int, component: str, index: int) -> float:
    """Generate deterministic float 0.0-1.0"""
    hash_val = _deterministic_hash(seed, component, index)
    return (hash_val % 10000) / 10000.0


def _hash_to_choice(seed: int, component: str, index: int, choices: List) -> any:
    """Deterministic choice from list"""
    hash_val = _deterministic_hash(seed, component, index)
    return choices[hash_val % len(choices)]


def generate_phonetic_surname(seed: int, sponsor_idx: int, syllables: int = 2) -> str:
    """Generate phonetic surname (e.g., 'Kardos', 'Veltran', 'Nexara')"""
    name_parts = []
    for i in range(syllables):
        cons = _hash_to_choice(seed, f"surname_cons_{i}", sponsor_idx, PHONETIC_CONSONANTS)
        vowel = _hash_to_choice(seed, f"surname_vowel_{i}", sponsor_idx, PHONETIC_VOWELS)
        name_parts.append(cons.upper() if i == 0 else cons)
        name_parts.append(vowel)
    
    # Add final consonant sometimes
    if _hash_to_float(seed, "surname_final_cons", sponsor_idx) > 0.6:
        name_parts.append(_hash_to_choice(seed, "surname_final", sponsor_idx, ['s', 'n', 'x', 'r', 'd', 't']))
    
    return ''.join(name_parts).capitalize()


def generate_company_name(seed: int, tier: int, industry: Industry, sponsor_idx: int) -> Tuple[str, str]:
    """
    Generate procedural company name using pattern templates.
    Returns (full_name, short_name)
    
    Patterns:
    - [FounderSurname] + [IndustrialSuffix]
    - [AbstractConcept] + [TechSuffix]
    - [Geographic] + [IndustryKeyword]
    - [Initialism] + [MotorsportCue]
    """
    pattern_choice = _hash_to_float(seed, "name_pattern", sponsor_idx)
    
    if pattern_choice < 0.30:
        # Pattern: FounderSurname + IndustrialSuffix
        surname = generate_phonetic_surname(seed, sponsor_idx)
        suffix = _hash_to_choice(seed, "industrial_suffix", sponsor_idx, INDUSTRIAL_SUFFIXES)
        full_name = f"{surname} {suffix}"
        short_name = surname
    
    elif pattern_choice < 0.55:
        # Pattern: AbstractConcept + TechSuffix (or IndustrialSuffix)
        concept = _hash_to_choice(seed, "abstract_concept", sponsor_idx, ABSTRACT_CONCEPTS)
        if industry in [Industry.TECHNOLOGY, Industry.MEDIA]:
            suffix = _hash_to_choice(seed, "tech_suffix", sponsor_idx, TECH_SUFFIXES)
        else:
            suffix = _hash_to_choice(seed, "industrial_suffix", sponsor_idx, INDUSTRIAL_SUFFIXES)
        full_name = f"{concept} {suffix}"
        short_name = concept
    
    elif pattern_choice < 0.75:
        # Pattern: Geographic + IndustryKeyword + Suffix
        geo = _hash_to_choice(seed, "geographic", sponsor_idx, GEOGRAPHIC_PREFIXES)
        keyword = _hash_to_choice(seed, "industry_keyword", sponsor_idx, INDUSTRY_KEYWORDS.get(industry, ['Group']))
        full_name = f"{geo} {keyword}"
        short_name = f"{geo}{keyword[0]}"
    
    else:
        # Pattern: Initialism/Concept + MotorsportCue
        concept = _hash_to_choice(seed, "abstract_concept2", sponsor_idx, ABSTRACT_CONCEPTS)
        motorsport = _hash_to_choice(seed, "motorsport_cue", sponsor_idx, MOTORSPORT_CUES)
        full_name = f"{concept} {motorsport}"
        short_name = concept
    
    return full_name, short_name


def determine_financial_tier(team_tier: int, rng: random.Random, allow_tier_breakthrough: bool = False) -> FinancialTier:
    """
    Determine sponsor financial tier based on team tier.
    Distribution ensures tier-appropriate sponsor pools.
    
    Team Tier 1 (Grassroots): 80% micro, 20% regional
    Team Tier 2-3: 40% micro, 40% regional, 20% national
    Team Tier 4: 20% regional, 50% national, 30% global
    Team Tier 5 (Formula Z): 10% national, 50% global, 40% global
    
    If allow_tier_breakthrough=True, sponsors can be one tier above normal (underdog sponsors).
    """
    roll = rng.random()
    
    # Tier breakthrough: 10% chance to get sponsor from tier above
    if allow_tier_breakthrough and roll < 0.10:
        if team_tier == 1:
            return FinancialTier.NATIONAL  # Jump from micro/regional to national
        elif team_tier in [2, 3]:
            return FinancialTier.GLOBAL if roll < 0.05 else FinancialTier.GLOBAL  # Rare jump to global, or national->global
        elif team_tier == 4:
            return FinancialTier.GLOBAL  # Already near top, just ensure global
        # Tier 5 already has access to globals, no breakthrough needed
    
    # Normal tier-appropriate distribution
    if team_tier == 1:
        return FinancialTier.MICRO if roll < 0.80 else FinancialTier.REGIONAL
    
    elif team_tier in [2, 3]:
        if roll < 0.40:
            return FinancialTier.MICRO
        elif roll < 0.80:
            return FinancialTier.REGIONAL
        else:
            return FinancialTier.NATIONAL
    
    elif team_tier == 4:
        if roll < 0.20:
            return FinancialTier.REGIONAL
        elif roll < 0.70:
            return FinancialTier.NATIONAL
        else:
            return FinancialTier.GLOBAL
    
    else:  # team_tier >= 5
        if roll < 0.10:
            return FinancialTier.NATIONAL
        elif roll < 0.60:
            return FinancialTier.GLOBAL
        else:
            return FinancialTier.GLOBAL


def calculate_loyalty(heritage: Heritage, ethics: float, involvement_level: InvolvementLevel, 
                      tier: FinancialTier) -> float:
    """Calculate sponsor loyalty based on personality factors"""
    base_loyalty = TIER_LOYALTY_BASE[tier]
    
    # Legacy sponsors are more loyal
    if involvement_level == InvolvementLevel.LEGACY:
        base_loyalty += 0.20
    elif involvement_level == InvolvementLevel.ACTIVE:
        base_loyalty += 0.10
    
    # High ethics = more loyal
    base_loyalty += (ethics - 0.5) * 0.20
    
    # Older companies = more stable
    company_age = 2026 - heritage.founding_year
    if company_age > 50:
        base_loyalty += 0.15
    elif company_age > 20:
        base_loyalty += 0.08
    
    return min(1.0, max(0.0, base_loyalty))


def calculate_pressure_threshold(prestige: float, tier: FinancialTier) -> float:
    """Calculate performance pressure threshold"""
    # High prestige brands demand more
    base_threshold = 0.60
    base_threshold -= prestige * 0.30
    
    # Larger sponsors demand more
    if tier == FinancialTier.GLOBAL:
        base_threshold -= 0.15
    elif tier == FinancialTier.NATIONAL:
        base_threshold -= 0.08
    
    return max(0.20, min(0.80, base_threshold))


def calculate_performance_dependency(industry: Industry, involvement_level: InvolvementLevel) -> float:
    """How much does this sponsor care about on-track results?"""
    base = 0.50
    
    # Industries with direct automotive credibility care more
    if industry in [Industry.AUTOMOTIVE, Industry.ENERGY]:
        base += 0.20
    elif industry in [Industry.MEDIA, Industry.CONSUMER]:
        base -= 0.10  # Care more about exposure than results
    
    # Involvement level
    if involvement_level == InvolvementLevel.LEGACY:
        base += 0.15  # Heritage brands care about winning
    elif involvement_level == InvolvementLevel.CURIOUS:
        base -= 0.15  # Newbies just want exposure
    
    return max(0.20, min(0.90, base))


def calculate_reputation_dependency(industry: Industry, ethics: float) -> float:
    """How much does this sponsor care about team reputation/image?"""
    base = 0.40
    
    # Consumer-facing brands care about image
    if industry in [Industry.CONSUMER, Industry.MEDIA]:
        base += 0.25
    
    # High ethics = care about reputation
    base += ethics * 0.20
    
    return max(0.20, min(0.80, base))


def generate_sponsor_profile(seed: int, team_tier: int, sponsor_idx: int, allow_tier_breakthrough: bool = False) -> SponsorProfile:
    """
    Generate complete sponsor profile with all personality traits.
    Fully deterministic based on seed and index.
    
    allow_tier_breakthrough: If True, allows sponsors one tier above normal for underdog breakthrough stories.
    """
    # Initialize RNG for this sponsor
    rng = random.Random(_deterministic_hash(seed, "sponsor_base", sponsor_idx))
    
    # Generate unique ID
    sponsor_id = f"SPO_{seed}_{sponsor_idx}"
    
    # Determine financial tier (with optional breakthrough)
    financial_tier = determine_financial_tier(team_tier, rng, allow_tier_breakthrough=allow_tier_breakthrough)
    
    # Tag high-risk-appetite breakthrough sponsors
    is_underdog_gamble = False
    if allow_tier_breakthrough and financial_tier.value in ["national", "global"] and team_tier <= 3:
        is_underdog_gamble = True
    
    # Select industry and sub-industry
    industry = _hash_to_choice(seed, "industry", sponsor_idx, list(Industry))
    sub_industry = _hash_to_choice(seed, "subindustry", sponsor_idx, INDUSTRY_SUBINDUSTRIES[industry])
    
    # Generate name
    full_name, short_name = generate_company_name(seed, team_tier, industry, sponsor_idx)
    
    # Heritage
    current_year = 2026
    founding_year = current_year - int(_hash_to_float(seed, "company_age", sponsor_idx) * 80 + 5)  # 5-85 years old
    origin_story = _hash_to_choice(seed, "origin_story", sponsor_idx, list(OriginStoryTag))
    heritage = Heritage(founding_year=founding_year, origin_story_tag=origin_story)
    
    # Brand profile
    tone = _hash_to_choice(seed, "brand_tone", sponsor_idx, list(BrandTone))
    prestige = _hash_to_float(seed, "prestige", sponsor_idx)
    risk_appetite = _hash_to_float(seed, "risk_appetite", sponsor_idx)
    
    # Underdog gamble sponsors have high risk appetite
    if is_underdog_gamble:
        risk_appetite = max(0.75, risk_appetite)
    
    ethics = _hash_to_float(seed, "ethics", sponsor_idx)
    brand_profile = BrandProfile(tone=tone, prestige=prestige, risk_appetite=risk_appetite, ethics=ethics)
    
    # Financial profile
    budget_min, budget_max = TIER_BUDGET_RANGES[financial_tier]
    
    # Underdog gamble sponsors pay less (50-80% of tier-above normal)
    if is_underdog_gamble:
        reduction_factor = 0.5 + (variance * 0.3)  # 50-80% payment
        budget_min = int(budget_min * reduction_factor)
        budget_max = int(budget_max * reduction_factor)
    
    # Add variance within tier
    variance = _hash_to_float(seed, "budget_variance", sponsor_idx)
    range_size = budget_max - budget_min
    actual_min = int(budget_min + range_size * variance * 0.3)
    actual_max = int(budget_max - range_size * (1.0 - variance) * 0.3)
    volatility = TIER_VOLATILITY[financial_tier]
    # Crypto/finance are more volatile
    if industry == Industry.FINANCE and sub_industry == SubIndustry.CRYPTO_EXCHANGE:
        volatility *= 1.8
    financial_profile = FinancialProfile(
        tier=financial_tier,
        budget_min=actual_min,
        budget_max=actual_max,
        volatility=volatility
    )
    
    # Motorsport alignment
    involvement = _hash_to_choice(seed, "involvement", sponsor_idx, list(InvolvementLevel))
    # Preferred series based on tier
    if team_tier <= 2:
        preferred_series = ['grassroots', 'regional_series']
    elif team_tier <= 3:
        preferred_series = ['formula_x', 'endurance', 'regional_formula']
    else:
        preferred_series = ['formula_z', 'formula_y', 'prestigious_series']
    
    # Values based on industry
    if industry == Industry.TECHNOLOGY:
        values = ['innovation', 'future', 'disruption']
    elif industry == Industry.AUTOMOTIVE:
        values = ['performance', 'engineering', 'heritage']
    elif industry == Industry.FINANCE:
        values = ['prestige', 'success', 'elite']
    elif industry == Industry.CONSUMER:
        values = ['lifestyle', 'youth', 'energy']
    else:
        values = ['grit', 'determination', 'craft']
    
    motorsport_alignment = MotorsportAlignment(
        involvement_level=involvement,
        preferred_series=preferred_series,
        values=values
    )
    
    # Contract behavior
    loyalty = calculate_loyalty(heritage, ethics, involvement, financial_tier)
    pressure_threshold = calculate_pressure_threshold(prestige, financial_tier)
    performance_dependency = calculate_performance_dependency(industry, involvement)
    reputation_dependency = calculate_reputation_dependency(industry, ethics)
    contract_behavior = ContractBehavior(
        loyalty=loyalty,
        pressure_threshold=pressure_threshold,
        performance_dependency=performance_dependency,
        reputation_dependency=reputation_dependency
    )
    
    # Activation style
    # Higher tier = more aggressive branding
    if financial_tier == FinancialTier.GLOBAL:
        visibility = BrandingVisibility.DOMINANT if rng.random() > 0.3 else BrandingVisibility.AGGRESSIVE
    elif financial_tier == FinancialTier.NATIONAL:
        visibility = BrandingVisibility.AGGRESSIVE if rng.random() > 0.4 else BrandingVisibility.SUBTLE
    else:
        visibility = BrandingVisibility.SUBTLE if rng.random() > 0.3 else BrandingVisibility.AGGRESSIVE
    
    # Demands based on tier and prestige
    requires_podiums = (financial_tier in [FinancialTier.GLOBAL, FinancialTier.NATIONAL] and prestige > 0.6)
    requires_media = (industry in [Industry.MEDIA, Industry.CONSUMER] or prestige > 0.5)
    requires_driver_profile = (industry == Industry.CONSUMER and financial_tier in [FinancialTier.NATIONAL, FinancialTier.GLOBAL])
    
    activation_style = ActivationStyle(
        branding_visibility=visibility,
        requires_podiums=requires_podiums,
        requires_media_mentions=requires_media,
        requires_driver_profile=requires_driver_profile
    )
    
    # Narrative hooks
    scandal_risk = _hash_to_float(seed, "scandal_risk", sponsor_idx)
    # Low ethics = higher scandal risk
    scandal_risk = scandal_risk * (1.5 - ethics)
    scandal_risk = min(1.0, scandal_risk)
    
    bailout_savior = (loyalty > 0.70 and financial_tier in [FinancialTier.REGIONAL, FinancialTier.NATIONAL] and rng.random() > 0.85)
    hostile_exit = (loyalty < 0.40 and prestige > 0.60)
    legacy_sponsor = (involvement == InvolvementLevel.LEGACY and heritage.founding_year < 1980)
    
    narrative_hooks = NarrativeHooks(
        scandal_risk=scandal_risk,
        bailout_savior=bailout_savior,
        hostile_exit=hostile_exit,
        legacy_sponsor=legacy_sponsor
    )
    
    # Headquarters (simplified for now)
    countries = ['USA', 'UK', 'Germany', 'Japan', 'Italy', 'France', 'Spain', 'Netherlands', 'Switzerland']
    headquarters_country = _hash_to_choice(seed, "hq_country", sponsor_idx, countries)
    headquarters_region = "Regional HQ"  # Placeholder
    
    return SponsorProfile(
        sponsor_id=sponsor_id,
        name=full_name,
        short_name=short_name,
        industry=industry,
        sub_industry=sub_industry,
        headquarters_country=headquarters_country,
        headquarters_region=headquarters_region,
        heritage=heritage,
        brand_profile=brand_profile,
        financial_profile=financial_profile,
        motorsport_alignment=motorsport_alignment,
        contract_behavior=contract_behavior,
        activation_style=activation_style,
        narrative_hooks=narrative_hooks
    )


def generate_exclusivity_clauses(profile: SponsorProfile, rng: random.Random) -> List[str]:
    """
    Generate exclusivity clauses based on sponsor industry and tier.
    These constrain team decisions (parts, other sponsors).
    """
    clauses = []
    
    # Larger sponsors demand more exclusivity
    if profile.financial_profile.tier in [FinancialTier.GLOBAL, FinancialTier.NATIONAL]:
        if profile.industry == Industry.AUTOMOTIVE:
            if rng.random() > 0.7:
                clauses.append(f"no_competitor_{profile.sub_industry.value}_parts")
            if profile.financial_profile.tier == FinancialTier.GLOBAL and rng.random() > 0.6:
                clauses.append("exclusive_automotive_category")
        
        elif profile.industry == Industry.ENERGY:
            if rng.random() > 0.65:
                clauses.append("exclusive_energy_sponsor")
        
        elif profile.industry == Industry.TECHNOLOGY:
            if rng.random() > 0.75:
                clauses.append(f"exclusive_{profile.sub_industry.value}_partner")
        
        # Dominant branding can demand naming rights
        if profile.activation_style.branding_visibility == BrandingVisibility.DOMINANT:
            if rng.random() > 0.80:
                clauses.append("team_naming_rights")
    
    return clauses


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def profile_to_json(profile: SponsorProfile) -> str:
    """Serialize profile to JSON string"""
    class EnumEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, Enum):
                return obj.value
            return super().default(obj)
    return json.dumps(profile.to_dict(), cls=EnumEncoder)


def profile_from_json(json_str: str) -> SponsorProfile:
    """Deserialize profile from JSON string"""
    data = json.loads(json_str)
    
    # Reconstruct enums
    heritage = Heritage(
        founding_year=data['heritage']['founding_year'],
        origin_story_tag=OriginStoryTag(data['heritage']['origin_story_tag'])
    )
    
    brand_profile = BrandProfile(
        tone=BrandTone(data['brand_profile']['tone']),
        prestige=data['brand_profile']['prestige'],
        risk_appetite=data['brand_profile']['risk_appetite'],
        ethics=data['brand_profile']['ethics']
    )
    
    financial_profile = FinancialProfile(
        tier=FinancialTier(data['financial_profile']['tier']),
        budget_min=data['financial_profile']['budget_min'],
        budget_max=data['financial_profile']['budget_max'],
        volatility=data['financial_profile']['volatility']
    )
    
    motorsport_alignment = MotorsportAlignment(
        involvement_level=InvolvementLevel(data['motorsport_alignment']['involvement_level']),
        preferred_series=data['motorsport_alignment']['preferred_series'],
        values=data['motorsport_alignment']['values']
    )
    
    contract_behavior = ContractBehavior(
        loyalty=data['contract_behavior']['loyalty'],
        pressure_threshold=data['contract_behavior']['pressure_threshold'],
        performance_dependency=data['contract_behavior']['performance_dependency'],
        reputation_dependency=data['contract_behavior']['reputation_dependency']
    )
    
    activation_style = ActivationStyle(
        branding_visibility=BrandingVisibility(data['activation_style']['branding_visibility']),
        requires_podiums=data['activation_style']['requires_podiums'],
        requires_media_mentions=data['activation_style']['requires_media_mentions'],
        requires_driver_profile=data['activation_style']['requires_driver_profile']
    )
    
    narrative_hooks = NarrativeHooks(
        scandal_risk=data['narrative_hooks']['scandal_risk'],
        bailout_savior=data['narrative_hooks']['bailout_savior'],
        hostile_exit=data['narrative_hooks']['hostile_exit'],
        legacy_sponsor=data['narrative_hooks']['legacy_sponsor']
    )
    
    return SponsorProfile(
        sponsor_id=data['sponsor_id'],
        name=data['name'],
        short_name=data['short_name'],
        industry=Industry(data['industry']),
        sub_industry=SubIndustry(data['sub_industry']),
        headquarters_country=data['headquarters_country'],
        headquarters_region=data['headquarters_region'],
        heritage=heritage,
        brand_profile=brand_profile,
        financial_profile=financial_profile,
        motorsport_alignment=motorsport_alignment,
        contract_behavior=contract_behavior,
        activation_style=activation_style,
        narrative_hooks=narrative_hooks
    )


if __name__ == "__main__":
    # Test generation
    print("=== Procedural Sponsor Generation Test ===\n")
    
    for tier in range(1, 6):
        print(f"\n--- Team Tier {tier} Sponsors ---")
        for i in range(3):
            profile = generate_sponsor_profile(seed=12345, team_tier=tier, sponsor_idx=tier*100+i)
            print(f"\n{profile.name} ({profile.short_name})")
            print(f"  Industry: {profile.industry.value} / {profile.sub_industry.value}")
            print(f"  Financial Tier: {profile.financial_profile.tier.value}")
            print(f"  Budget Range: ${profile.financial_profile.budget_min:,} - ${profile.financial_profile.budget_max:,}")
            print(f"  Loyalty: {profile.contract_behavior.loyalty:.2f} | Prestige: {profile.brand_profile.prestige:.2f}")
            print(f"  Performance Dependency: {profile.contract_behavior.performance_dependency:.2f}")
            print(f"  Demands: Podiums={profile.activation_style.requires_podiums}, Media={profile.activation_style.requires_media_mentions}")
            print(f"  Narrative: Legacy={profile.narrative_hooks.legacy_sponsor}, Hostile Exit={profile.narrative_hooks.hostile_exit}")
