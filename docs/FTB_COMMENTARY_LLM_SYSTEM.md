# FTB LLM-Based Commentary System

## Overview

The new `ftb_broadcast_commentary_llm.py` plugin transforms race commentary from hardcoded templates into **contextually-rich LLM prompts** that generate dynamic, season-aware racing commentary.

## Key Improvements

### 1. **LLM Prompt-Based Generation**
Instead of template strings, the system generates detailed prompts that guide the LLM to produce:
- Contextually appropriate commentary for the league tier
- Championship-aware analysis
- Season narrative threading
- Dynamic personality-matched delivery

### 2. **Rich Season Context**
The `SeasonContext` dataclass tracks:
```python
- Championship standings (position, points, gaps)
- Recent form (last 3 results, momentum)
- Season progress (race number, races remaining)
- Team narrative (morale, budget tier, rivals)
- Championship implications (title fight, relegation danger)
- Historical context (best/worst finishes)
- Track-specific records
```

### 3. **Tier-Specific Broadcast Teams**

Each league tier has distinct commentary voices and personalities:

| Tier | Style | Play-by-Play Voice | Color Commentator |
|------|-------|-------------------|-------------------|
| 1: Grassroots | Local community radio feel | `am_puck` | `bf_lily` |
| 2: Enthusiast | Passionate fan coverage | `am_eric` | `af_river` |
| 3: Professional | Major sports network | `am_adam` | `af_bella` |
| 4: Premium | Elite sports channel | `bm_lewis` | `bf_emma` |
| 5: World Class | F1-style legendary broadcast | `bm_george` | `bf_alice` |

### 4. **Personality-Driven Prompts**

Each tier has a comprehensive style guide that shapes the LLM prompts:

#### Tier 1 (Grassroots)
- **PBP Style**: "enthusiastic local announcer who knows all the drivers personally"
- **Color Style**: "supportive local racing expert who explains things clearly"
- **Language**: Casual, accessible, local references
- **Energy**: High enthusiasm, genuine excitement

#### Tier 5 (World Class)
- **PBP Style**: "legendary voice of motorsport with decades of history"
- **Color Style**: "world champion analyst providing masterclass commentary"
- **Language**: Broadcast excellence, quotable moments, legacy awareness
- **Energy**: Controlled intensity, moment recognition, history-making awareness

## Usage Example

```python
from plugins.ftb_broadcast_commentary_llm import (
    LLMCommentaryGenerator, 
    SeasonContext
)

# Build rich season context
season_ctx = SeasonContext(
    player_position=3,
    player_points=142,
    championship_leader="Sarah Chen",
    championship_leader_points=178,
    points_gap_to_leader=36,
    race_number=8,
    total_races=12,
    races_remaining=4,
    last_three_results=[5, 2, 3],  # P5, P2, P3
    team_momentum='rising',
    budget_tier='midfield',
    can_win_championship=True,
    track_name="Riverside Circuit"
)

# Initialize generator for Tier 3 (Professional)
generator = LLMCommentaryGenerator(
    league_tier=3,
    player_team_name="Apex Racing",
    season_context=season_ctx
)

# Generate pre-race commentary prompt
prompts = generator.generate_pre_race_prompt(grid, "Riverside Circuit")

# Each prompt contains:
# - speaker: 'pbp' or 'color'
# - prompt: Full LLM prompt with context and instructions
# - event_type: 'pre_race', 'overtake', 'incident', etc.
# - max_tokens: Token budget for response
# - priority: Commentary priority (for queuing)

# Send prompts to your LLM system
for prompt in prompts:
    commentary_text = your_llm_call(prompt.prompt, max_tokens=prompt.max_tokens)
    voice = 'play_by_play' if prompt.speaker == 'pbp' else 'color_commentator'
    enqueue_audio(commentary_text, voice=voice, priority=prompt.priority)
```

## Prompt Structure

Every prompt includes:

### Base Context (All Prompts)
```
You are the [play-by-play/color] commentator: [personality description]

Style: [tier-specific style guide]
Broadcast quality: [quality standard]
Language: [language level]
Energy: [energy description]

[Season context in natural language]

CRITICAL RULES:
- 1-2 sentences maximum (40-60 words)
- Present tense, immediate action
- NO player references ("our team", "we", "you")
- Use driver/team names objectively
- Match the tier style exactly
```

### Event-Specific Task
```
TASK: [Specific instruction for this moment]
[Relevant facts and context]
Generate [type of commentary]:
```

## Commentary Events Supported

### 1. Pre-Race
- Opening call with grid context
- Championship implications analysis
- Historical context at this track

### 2. Lights Out
- Iconic race start call
- Tier-appropriate energy level

### 3. Overtakes
- Position change call
- Significance assessment (lead change, podium, player team)
- Strategic analysis follow-up (conditional)

### 4. Incidents
- Urgent incident call (crash, spin, mechanical)
- Damage assessment
- Championship impact analysis

### 5. Lap Updates
- Periodic race status (every 5 laps, key moments)
- Leader info and gaps
- Race phase narrative

### 6. Final Lap
- Maximum drama for final tour
- Championship implications

### 7. Checkered Flag
- Victory call
- Race summary with championship context

## Voice Configuration

### In Manifest (stations/FromTheBackmarker/manifest.yaml)

```yaml
audio:
  voices_provider: kokoro
  voices:
    host: am_adam
    narrator: bm_lewis
    formula_z_news_anchor: bf_emma
    formula_z_news: bf_emma  # Explicit for news broadcasts
    # Commentary voices are tier-dependent (auto-selected by tier)
```

### Accessing Tier Voices

```python
from plugins.ftb_broadcast_commentary_llm import get_commentary_voices_for_tier

# Get voice config for current tier
tier = 3
voices = get_commentary_voices_for_tier(tier)
# Returns: {'pbp': 'am_adam', 'color': 'af_bella'}
```

## Integration with Existing System

The LLM commentary generator produces `CommentaryPrompt` objects that need to be:

1. **Sent to LLM**: Extract the `prompt.prompt` text and send to your LLM endpoint
2. **Process Response**: Get generated commentary text from LLM
3. **Enqueue Audio**: Send to TTS with appropriate voice and priority

Example integration:
```python
def process_commentary_prompts(prompts: List[CommentaryPrompt], llm_client):
    for prompt in prompts:
        # Call LLM
        response = llm_client.generate(
            prompt=prompt.prompt,
            max_tokens=prompt.max_tokens,
            temperature=0.7  # Some creativity for natural variation
        )
        
        # Get voice for speaker
        voice_key = 'play_by_play' if prompt.speaker == 'pbp' else 'color_commentator'
        
        # Enqueue to audio system
        enqueue_audio_segment(
            text=response,
            voice=voice_key,
            priority=prompt.priority,
            category='commentary'
        )
```

## Formula Z News Anchor Fix

The Formula Z news anchor voice issue has been fixed with a robust fallback chain:

```python
# In ftb_narrator_plugin.py initialization
self.news_anchor_voice_path = (
    cfg.get("audio", {}).get("voices", {}).get("formula_z_news_anchor")  # Primary
    or cfg.get("audio", {}).get("voices", {}).get("formula_z_news")      # Alternate
    or cfg.get("audio", {}).get("voices", {}).get("news_anchor")         # Generic
    or cfg.get("voices", {}).get("formula_z_news_anchor")                # Legacy
    or self.voice_path  # Final fallback to narrator
)
```

Now Formula Z news will correctly use `bf_emma` instead of defaulting to the host voice.

## Benefits Over Template System

### Old System (ftb_broadcast_commentary.py)
- ❌ Hardcoded template strings
- ❌ Limited context awareness
- ❌ Repetitive phrasing
- ❌ No championship narrative
- ❌ Static personality per tier

### New System (ftb_broadcast_commentary_llm.py)
- ✅ Dynamic LLM-generated commentary
- ✅ Rich season and championship context
- ✅ Infinite variety in phrasing
- ✅ Narrative threads across season
- ✅ Personality-driven prompts per tier
- ✅ Contextual significance awareness
- ✅ Championship implications in every call

## Future Enhancements

1. **Historical Callbacks**: Reference previous races in the season
2. **Rivalry Tracking**: Maintain commentary about ongoing driver rivalries
3. **Weather Integration**: Commentary adjusts for changing conditions
4. **Strategy Analysis**: Deeper pit stop and tire strategy commentary
5. **Post-Race Interviews**: Generate interview prompts for drivers
6. **Multi-Language**: Leverage Kokoro's multilingual voices with translated prompts

## Testing

Test the system with:
```python
from plugins.ftb_broadcast_commentary_llm import LLMCommentaryGenerator, SeasonContext

# Create test context
ctx = SeasonContext(
    player_position=1,
    player_points=200,
    race_number=10,
    total_races=12,
    races_remaining=2,
    team_momentum='rising'
)

# Test Tier 1 (Grassroots)
gen_tier1 = LLMCommentaryGenerator(1, "Test Team", ctx)
prompts = gen_tier1.generate_lights_out_prompt()
print(f"Tier 1 Prompt:\n{prompts.prompt}\n")

# Test Tier 5 (World Class)
gen_tier5 = LLMCommentaryGenerator(5, "Test Team", ctx)
prompts = gen_tier5.generate_lights_out_prompt()
print(f"Tier 5 Prompt:\n{prompts.prompt}\n")
```

Compare the prompt styles to see how dramatically different the instructions are per tier.

## Migration Path

To migrate from old commentary system:

1. **Phase 1**: Run both systems in parallel, A/B test outputs
2. **Phase 2**: Route critical moments (lights out, checkered flag) to LLM system
3. **Phase 3**: Full migration once LLM latency and quality validated
4. **Phase 4**: Remove old template system, keep as fallback only

The old `ftb_broadcast_commentary.py` can remain as a zero-latency fallback if LLM generation fails or is too slow.
