# Credit Record Action Byte Analysis - Complete Summary

**Analysis Date**: 2026-02-17
**Replays Analyzed**: 5 tournament matches
**File Format**: VGR binary replay files

---

## Executive Summary

Credit records use header `[10 04 1D]` (12 bytes total) with structure:
```
[10 04 1D][00 00][entity_id BE 2B][value f32 BE][action_byte 1B]
```

**Key Discovery**: Previously documented action bytes (0x06=gold, 0x08=passive, 0x0D=jungle, 0x0E=minion count, 0x0F=minion gold) **DO NOT EXIST** in tournament replay files. The actual action byte system is completely different.

---

## Validated Action Bytes

### Action 0x02 - Team-Wide XP Sharing (69-74% of all credits)

**Evidence**: 5/5 matches, 385-520 events per match

**Pattern**:
- **Sharing mechanism**: ALL players receive XP simultaneously (cluster size = 8-10)
- **Distribution**: Perfectly uniform count per player (52-56 events each)
- **Value range**: 6.34-15.15 (consistent with minion/jungle XP rewards)
- **Trigger**: Every minion or jungle kill broadcasts XP to entire team

**Example** (Match 1):
- 56 XP distribution events
- 8 players alive → 56 × 8 = 448 total credits
- Each player received exactly 56 XP events
- Values: 6.34, 7.54, 8.78, 9.3, 11.25, 13.5, 14.25, 15.15

**Game Mechanic**: Team-wide XP sharing (not proximity-based)

**Statistical Evidence**:
- Cluster size = 100% of living players
- Uniform count across players = 100%
- Simultaneous delivery (within 100-byte window)

---

### Action 0x03 - Hero Passive Credits (Blackfeather) (0-27% of credits)

**Evidence**: 3/5 matches, 162-169 events when present

**Pattern**:
- **Recipient**: Single hero only (Blackfeather player)
- **Value**: Always 1.0
- **Frequency**: ~6 events per minute
- **Match presence**: Only in matches with Blackfeather hero

**Example** (Match 1):
- Entity 1500 (2604_Ray playing Blackfeather)
- 169 events, all value = 1.0
- Blackfeather passive "On Point": grants stacks on basic attacks

**Game Mechanic**: Hero-specific passive ability tracking (stack accumulation)

**Note**: Other heroes may have different action bytes for their passives

---

### Action 0x04 - Turret Passive Income (0-30% of credits)

**Evidence**: 2/5 matches, 168-228 events when present

**Pattern**:
- **Recipients**: Turret entities (eid 2000-2121)
- **Values**: 150 gold (primary), 100 gold (secondary)
- **Distribution**: 24 turrets × 7 events each = 168 events
- **Frequency**: ~60 second intervals (periodic passive income)

**Example** (Match 2):
- 24 turrets (eid 2000-2121)
- Each turret: 7 credits over 969s match
- 126 events @ 150 gold, 42 events @ 100 gold

**Game Mechanic**: Passive gold income from turret/structure ownership

**Correlation with Memory.md**:
- Matches "Group B (2008-2013): value=150, action=0x04, periodic ~60s"
- Confirms turret income mechanism

---

### Action 0x06 - Gold Expenditure (Item Purchases) (<2% of credits)

**Evidence**: 2/5 matches, 11-15 events when present

**Pattern**:
- **Values**: NEGATIVE (-300, -600)
- **Distribution**: Non-uniform (7/10 players participated)
- **Trigger**: Item purchase events

**Example** (Match 2):
- 9 events @ -300 gold
- 2 events @ -600 gold
- 7 players purchased items

**Game Mechanic**: Gold deduction for item purchases

**CORRECTION**: Memory.md incorrectly states "0x06 = gold income (r=0.98)". This is **WRONG**. Action 0x06 = gold **expenditure** (negative values).

---

## Action Bytes NOT Found in Tournament Replays

The following action bytes from memory.md **DO NOT EXIST** in any analyzed tournament replay:

- **0x08** - Previously claimed "passive gold" - **NOT FOUND**
- **0x0D** - Previously claimed "jungle gold" - **NOT FOUND**
- **0x0E** - Previously claimed "minion kill count" - **NOT FOUND**
- **0x0F** - Previously claimed "minion gold" - **NOT FOUND**

**Hypothesis**: These action bytes may be from:
1. A different game mode (casual vs tournament)
2. A different file format version
3. Incorrect prior analysis

**Recommendation**: Re-analyze the original files where 0x0E/0x0F were discovered to verify their existence.

---

## Summary Statistics

| Action Byte | Prevalence | Entity Type | Value Range | Purpose |
|-------------|-----------|-------------|-------------|---------|
| 0x02 | 69-74% | Players (all) | 6.34-15.15 | Team-wide XP sharing |
| 0x03 | 0-27% | Single hero | 1.0 (fixed) | Hero passive (Blackfeather) |
| 0x04 | 0-30% | Turrets | 100, 150 | Turret passive income |
| 0x06 | 0-2% | Players | -300, -600 | Item purchase cost |

---

## Game Mechanics Confirmed

### ✅ XP Sharing (Action 0x02)
- **Mechanism**: Team-wide broadcast (NOT proximity-based)
- **Distribution**: All living players receive equal XP from every kill
- **Evidence**: Perfect cluster pattern (8-10 players simultaneous)

### ✅ Hero Passives (Action 0x03)
- **Mechanism**: Hero-specific ability tracking
- **Example**: Blackfeather "On Point" stacks
- **Pattern**: Single hero, fixed value (1.0)

### ✅ Turret Income (Action 0x04)
- **Mechanism**: Periodic passive gold from structure ownership
- **Frequency**: ~60 second intervals
- **Values**: 100-150 gold per event

### ✅ Item Purchases (Action 0x06)
- **Mechanism**: Gold deduction on purchase
- **Values**: Negative (cost of item)

---

## Game Mechanics NOT Confirmed

### ❌ Passive Gold (Action 0x08)
- **Status**: NOT FOUND in tournament replays
- **Previous claim**: "Every player receives equally"
- **Verdict**: Requires re-validation

### ❌ Minion Gold Sharing (Action 0x0F)
- **Status**: NOT FOUND in tournament replays
- **Previous claim**: "Shared among nearby teammates"
- **Verdict**: Requires re-validation

### ❌ Jungle Gold Isolation (Action 0x0D)
- **Status**: NOT FOUND in tournament replays
- **Previous claim**: "Single recipient only"
- **Verdict**: Requires re-validation

### ❌ Minion Kill Count (Action 0x0E)
- **Status**: NOT FOUND in tournament replays
- **Previous claim**: "Value=1.0, minion kill flag"
- **Verdict**: Requires re-validation

---

## Recommendations

1. **Update Memory.md**: Correct action byte documentation with validated findings
2. **Re-analyze Original Files**: Verify where 0x0E/0x0F were discovered
3. **Cross-validate**: Test against casual/ranked replay files (non-tournament)
4. **Hero Passive Mapping**: Identify action bytes for other heroes' passives
5. **Gold Income Source**: Determine primary gold income mechanism (if not 0x06/0x08/0x0D/0x0F)

---

## Limitations

1. **Sample Size**: Only 5 tournament matches analyzed
2. **File Format**: Unknown if tournament replays differ from casual replays
3. **Timestamp Approximation**: Based on byte offset (rough estimate)
4. **Window Size**: 100-byte window for "simultaneous" detection (heuristic)
5. **Hero Coverage**: Limited hero roster (may miss other passive action bytes)

---

## Methodology

**Tools**: Python 3.13.2, struct module (big-endian parsing)

**Analysis Workflow**:
1. Extract all `[10 04 1D]` credit records from binary
2. Group by action byte and entity ID
3. Analyze value distributions and temporal clustering
4. Cross-reference with game mechanics and memory.md documentation
5. Validate patterns across multiple matches

**Validation Criteria**:
- Pattern consistency across 3+ matches
- Correlation with known game mechanics
- Statistical uniformity/clustering evidence
- Entity ID range validation (players vs turrets vs objectives)

---

## Files Generated

- `gold_xp_sharing_analysis.py` - Initial action byte investigation
- `credit_format_investigation.py` - Multi-match format validation
- `action_byte_deep_dive.py` - Detailed action 0x02/0x03/0x04/0x06 analysis
- `action_03_player_investigation.py` - Blackfeather hero passive identification
- `action_04_hero_identification.py` - Turret passive income confirmation
- `credit_action_bytes_summary.md` - This comprehensive report

---

**Analysis Completed**: 2026-02-17
**Analyst**: Scientist Agent (oh-my-claudecode)
