# Event Header Survey - Complete VGR Binary Protocol Catalog

## Overview

This comprehensive survey systematically identifies and classifies ALL event header types in Vainglory replay (.vgr) binary format.

## Execution Instructions

```bash
cd D:\Documents\GitHub\VG_REVERSE_ENGINEERING
python -m vg.analysis.event_header_survey
```

Or use the inline runner:
```bash
python run_header_survey_inline.py
```

## What This Survey Does

### 1. Header Discovery (find_all_headers)
- Scans entire frame 0 of first 3 tournament matches
- Identifies ALL `[XX 04 YY]` patterns (byte at offset+1 == 0x04)
- Records every unique header type and all occurrence offsets

### 2. For Each Header Type, Extracts:

#### A. Frequency Analysis
- Count of events per frame
- Consistency across 3 matches (present in all/some)
- Count range (min-max-average)

#### B. Entity ID Detection
- Checks offset +5 for Big Endian uint16 entity ID
- Valid ranges:
  - 0: system
  - 1-10: infrastructure
  - 1000-20000: structures (turrets)
  - 20000-50000: minions
  - 50000-60000: players

#### C. Player-Relatedness
- Compares extracted entity IDs against known player entity IDs (from player blocks)
- Flags header as "player-related" if ANY events contain player eids

#### D. Payload Size Estimation
- Measures distance between consecutive same-header events
- Uses mode (most common distance) as estimated payload size
- Handles variable-length payloads (reports as VARIABLE)

#### E. Payload Pattern Analysis
For headers with ≥8 byte payloads:
- **Float32 detection**: Scans every 4-byte boundary for valid IEEE 754 floats
- **Uint16 patterns**: Scans every 2-byte boundary for non-zero uint16 values
- **Byte histogram**: Identifies most common byte values (detects padding, flags)

#### F. Sample Payloads
- Hex dump of first 3 events (up to 64 bytes each)
- Provides concrete data for manual inspection

### 3. Classification

Each header is classified into:

#### Known Headers (from existing research):
- `18 04 3E`: player_heartbeat (~60K/frame)
- `28 04 3F`: player_action (~33K/frame)
- `18 04 1E`: entity_state (~30K/frame)
- `18 04 1C`: kill_header (~2.7K total, not per-frame)
- `08 04 31`: death_header
- `10 04 1D`: credit_record (gold/assist/minion)
- `10 04 3D`: item_acquire
- `10 04 4B`: item_equip

#### Unknown Headers Classified By:
- `unknown_player_event`: Contains player entity IDs
- `unknown_structures_event`: Contains structure entity IDs
- `unknown_minions_event`: Contains minion entity IDs
- `unknown_system_event`: No recognizable entity IDs

### 4. Cross-Match Validation

Validates header consistency:
- Which headers appear in all 3 matches?
- Which are match-specific?
- Are frequencies stable across matches?

### 5. Output

#### Console Output:
```
================================================================================
COMPLETE EVENT HEADER CATALOG
================================================================================

[18 04 3E] - PLAYER_HEARTBEAT
  Frequency: ~60,123 events/frame
  Consistency: 3/3
  Payload Size: 37 bytes
  Player-Related: YES
  Entity Types: {'players': 20}
  Entity ID Sample: [51234, 52100, ...]
  Payload Sample (hex): 18 04 3E 00 00 C7 F2 FF FF ...
  Float32 detected: [(8, 123.456), (12, 987.654), ...]

[XX 04 YY] - UNKNOWN_PLAYER_EVENT
  ...
```

#### JSON Output: `vg/output/event_header_catalog.json`
```json
{
  "matches_analyzed": ["match1", "match2", "match3"],
  "headers": {
    "18 04 3E": {
      "purpose": "player_heartbeat",
      "frequency": 60123,
      "payload_size": 37,
      "player_related": true,
      "entity_types": {"players": 20},
      "consistency": {"present_in_matches": "3/3", ...},
      "sample_payloads": ["18 04 3E 00 00 ...", ...]
    }
  }
}
```

## Expected Discoveries

### High-Frequency Headers (Per-Frame Events)
These appear ~10K-60K times per frame and represent continuous state:

1. **Player state headers** (entity_types: players)
   - Position, rotation, movement vectors
   - Health, mana, energy
   - Animation state, facing direction
   - Camera position (spectator mode)

2. **Entity state headers** (entity_types: structures, minions)
   - Minion position/health
   - Turret state
   - Projectile tracking

3. **Action/input headers** (entity_types: players)
   - Movement commands (joystick input)
   - Ability activation
   - Target selection
   - Attack commands

### Low-Frequency Headers (Event-Driven)
These appear ~100-5000 times per match and represent discrete events:

1. **Combat events** (KNOWN)
   - `18 04 1C`: kills
   - `08 04 31`: deaths
   - `10 04 1D`: gold/credit records

2. **Item events** (KNOWN)
   - `10 04 3D`: item acquire
   - `10 04 4B`: item equip
   - Possibly: item activation (consumables)

3. **Objective events** (PARTIALLY KNOWN)
   - Kraken/Gold Mine capture
   - Turret destruction (via credit records)
   - Ace/game-end markers

4. **Ability events** (UNKNOWN - TO BE DISCOVERED)
   - Cooldown tracking
   - Ability level-up
   - Ultimate activation
   - Stun/root/debuff application

5. **Level/XP events** (UNKNOWN - TO BE DISCOVERED)
   - XP gain from minions/kills
   - Level-up events
   - Stat changes on level-up

### Rare Headers (Match Setup/Teardown)
These appear <100 times per match:

1. **Match initialization**
   - Hero selection confirmation
   - Team composition finalization
   - Spawn location assignment

2. **Match teardown**
   - Final statistics recording
   - Victory screen data
   - Post-game summary

## Discovery Priorities

After running the survey, focus on:

### Priority 1: Unknown Player-Related Headers
- High frequency + player entity IDs = critical game mechanics
- Likely: level-up, ability cooldowns, buff/debuff application

### Priority 2: Low-Frequency Non-Player Headers
- Event-driven objective mechanics
- Likely: Kraken/Mine events, turret capture, jungle boss kills

### Priority 3: Float32-Heavy Payloads
- Headers with many float values = position/stats/timers
- Compare float ranges to known game values (health: 0-5000, position: 0-15000)

## Validation Strategy

For each unknown header:

1. **Frequency correlation**: Does count match known game events?
   - Example: ~600 level-up events → 60 levels/match (10 players × 6 levels)

2. **Entity ID correlation**: Which entity types appear?
   - Player-only → player ability/stat
   - Mixed → interaction event (player attacks minion)

3. **Payload pattern matching**: What data types are present?
   - Many floats → continuous state (position, health)
   - Few floats + bytes → discrete event (level=5, ability_id=3)

4. **Truth comparison**: Cross-reference with external data
   - Level progression: compare to telemetry API
   - Ability usage: compare to match VODs

## Research Notes

### Known Header Payload Structures

```
[18 04 1C] Kill Header (37 bytes)
  [18 04 1C][00 00][killer_eid BE][FF FF FF FF][3F 80 00 00][29 00]
  - Timestamp: 7 bytes before header
  - killer_eid: offset +5 (2 bytes BE)
  - Constant: FF FF FF FF (4 bytes)
  - Constant: 3F 80 00 00 = float 1.0 (4 bytes)
  - Trailer: 29 00 (2 bytes)

[08 04 31] Death Header (20 bytes)
  [08 04 31][00 00][victim_eid BE][00 00][timestamp f32 BE][00 00 00]
  - victim_eid: offset +5 (2 bytes BE)
  - timestamp: offset +11 (4 bytes BE float)

[10 04 1D] Credit Record (12 bytes)
  [10 04 1D][00 00][eid BE][value f32 BE][action_byte]
  - eid: offset +5 (2 bytes BE)
  - value: offset +7 (4 bytes BE float)
  - action: offset +11 (1 byte)
    - 0x06: gold income
    - 0x08: passive gold
    - 0x0E: minion kill credit
    - 0x0F: minion kill gold
    - 0x0D: jungle credit

[10 04 3D] Item Acquire (20 bytes)
  [10 04 3D][00 00][eid BE][00 00][qty][item_id LE][00 00][counter BE][ts f32 BE]
  - eid: offset +5 (2 bytes BE)
  - quantity: offset +9 (1 byte, always 1)
  - item_id: offset +10 (2 bytes LE) <-- NOTE: Little Endian!
  - counter: offset +14 (2 bytes BE, sequential)
  - timestamp: offset +16 (4 bytes BE float)
```

### Discovery Method History

The project used **brute-force frequency matching** to discover headers:
- Deaths: Found in 19,306 combos, exactly 1 unique match
- Kills: Found with wider offsets (1-30) + 2/3/4-byte patterns
- Credit records: Found by scanning all action bytes within 500B of kill headers

**Lesson**: Always try frequency matching FIRST before hypothesis-driven approaches.

## Next Steps After Survey

1. Run the survey to generate complete catalog
2. Prioritize unknown headers by frequency + player-relatedness
3. For high-value unknowns:
   - Frequency-match against known game mechanics
   - Extract payload patterns (float32, uint16, bytes)
   - Cross-reference with telemetry API / match VODs
4. Document findings in project memory
5. Integrate discovered headers into unified_decoder.py

## Statistics to Track

- [STAT:total_unique_headers] Total number of unique [XX 04 YY] patterns
- [STAT:known_headers] Headers with identified purposes
- [STAT:unknown_headers] Headers requiring investigation
- [STAT:player_related_unknown] Unknown headers containing player entity IDs
- [STAT:high_frequency_unknown] Unknown headers with >10K events/frame

## Expected Runtime

- Frame parsing: ~5-10 seconds per match
- Header scanning: ~2-3 seconds per frame
- Pattern analysis: ~1-2 seconds per header type
- Total: ~2-3 minutes for 3 matches

## File Locations

- Script: `vg/analysis/event_header_survey.py`
- Output JSON: `vg/output/event_header_catalog.json`
- Input replays: From `vg/output/tournament_truth.json` → replay_file paths
- Truth data: `vg/output/tournament_truth.json`
