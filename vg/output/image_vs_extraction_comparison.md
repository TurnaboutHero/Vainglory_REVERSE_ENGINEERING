# Tournament Result Image vs Replay Extraction Comparison

**Match:** SFC vs Team Stooopid (Semi-Final) - Game 1
**Result:** 13-2 (Left team victory)
**Date:** Analysis performed 2026-02-09

---

## Critical Finding

**ALL TIER 3 ITEMS (121-129, 221-229, 321-328, 401-423) ARE MISSING FROM FF FF FF FF PATTERN EXTRACTION**

The replay extraction successfully found these items using the `FF FF FF FF [XX 00]` pattern, BUT:
- Crystal items (221-229): **0 found** ❌
- Defense items (321-328): **0 found** ❌
- Utility items (403-406, 414-415, 421-423): **0 found** ❌

Only **Weapon Tier 3 items (121-129)** were found in the pattern search.

---

## Game 1 Analysis: Image vs Extraction

### Left Team (Winners - 13 kills)

#### Player 1: 2600_IcyBang (Kestrel)
**Image Items:**
- Sorrowblade (121) ✅ FOUND
- Tension Bow (128) ✅ FOUND
- Tyrant's Monocle (124) ✅ FOUND
- Bonesaw (125) ✅ FOUND
- Journey Boots (403) ❌ NOT FOUND
- Defense item (appears to be shield-based) ❌ NOT FOUND

**Extraction Results:**
- Found: 121, 128, 124, 125 (all Weapon Tier 3)
- Missing: 403 (Journey Boots), Defense item

#### Player 2: 2600_staplers (Malene)
**Image Items:**
- Spellfire (228) ❌ NOT FOUND
- Dragon's Eye (227) ❌ NOT FOUND
- Broken Myth (224) ❌ NOT FOUND
- Eve of Harvest (223) ❌ NOT FOUND
- Halcyon Chargers (404) ❌ NOT FOUND
- Aegis (321) ❌ NOT FOUND

**Extraction Results:**
- Found: NONE of these items
- All are Crystal (221-229) or Defense (321-328) Tier 3 items

#### Player 3: 2600_Ghost (Inara)
**Image Items:**
- Breaking Point (127) ✅ FOUND
- Sorrowblade (121) ✅ FOUND
- Aegis (321) ❌ NOT FOUND
- Metal Jacket (322) ❌ NOT FOUND
- War Treads (405) ❌ NOT FOUND

**Extraction Results:**
- Found: 127, 121 (Weapon Tier 3)
- Missing: 321, 322 (Defense), 405 (Utility)

#### Player 4: 2600_TenshiiHime (Grumpjaw)
**Image Items:**
- Breaking Point (127) ✅ FOUND
- Pulseweave (327) ❌ NOT FOUND
- Metal Jacket (322) ❌ NOT FOUND
- Crucible (324) ❌ NOT FOUND
- War Treads (405) ❌ NOT FOUND

**Extraction Results:**
- Found: 127 (Weapon Tier 3)
- Missing: 327, 322, 324 (all Defense), 405 (Utility)

#### Player 5: 2600_Acex (Lyra)
**Image Items:**
- Fountain of Renewal (323) ❌ NOT FOUND
- Crucible (324) ❌ NOT FOUND
- Capacitor Plate (328) ❌ NOT FOUND
- War Treads (405) ❌ NOT FOUND

**Extraction Results:**
- Found: NONE
- All are Defense (321-328) or Utility (401-423) items

---

## Extraction Statistics for Game 1

### Items Successfully Found (48 unique items)

**Weapon Category (All Found):**
- Tier 1 (101-110): 10/10 items ✅
- Tier 2 (111-116): 6/6 items ✅
- Tier 3 (121-129): 9/9 items ✅

**Unknown Items (117-120, 130-143, 191, 193):**
- Found 21 unknown item IDs in the 117-157, 191-194 range

**Missing Categories:**
- Crystal Tier 1 (201-203): 0/3 ❌
- Crystal Tier 2 (211-215): 0/5 ❌
- Crystal Tier 3 (221-229): 0/9 ❌
- Defense Tier 1 (301-303): 0/3 ❌
- Defense Tier 2 (311-314): 0/4 ❌
- Defense Tier 3 (321-328): 0/8 ❌
- Utility Tier 1 (401, 411-412): 0/3 ❌
- Utility Tier 2 (402, 413): 0/2 ❌
- Utility Tier 3 (403-406, 414-415, 421-423): 0/10 ❌

---

## Pattern Analysis: Why Are Items Missing?

### Success Pattern: `FF FF FF FF [XX 00]`
This pattern successfully detects:
- All Weapon items (101-129) ✅
- System items (188, 255) ✅

### Failure Pattern: Items NOT stored with `FF FF FF FF`
The following categories are stored differently in replay files:
- Crystal items (201-229) - **Different storage format**
- Defense items (301-328) - **Different storage format**
- Utility items (401-423) - **Different storage format**

---

## Tournament-Wide Statistics (11 matches analyzed)

### Items Found Across All Matches
From `tournament_item_verification.json`:
- Total unique items found: **62**
- Known items: **27** (all Weapon category)
- Unknown items: **35** (IDs 117-157, 191-194)
- Missing items: **46** (all Crystal, Defense, and Utility)

### Consistent Pattern
ALL 11 tournament matches show the same pattern:
- ✅ Weapon items: Always found
- ❌ Crystal items: Never found
- ❌ Defense items: Never found
- ❌ Utility items: Never found

---

## Conclusions

### Image Evidence vs Extraction
The tournament result images clearly show players using:
- Crystal items (Spellfire, Dragon's Eye, Broken Myth, Eve of Harvest)
- Defense items (Aegis, Metal Jacket, Crucible, Fountain, Pulseweave, Capacitor Plate)
- Utility items (Journey Boots, Halcyon Chargers, War Treads)

However, the `FF FF FF FF [XX 00]` pattern extraction finds **NONE** of these items.

### Root Cause
The replay file format stores different item categories using different byte patterns:
1. **Weapon items (101-129)**: Use `FF FF FF FF [ID 00]` pattern ✅
2. **Crystal items (201-229)**: Use a different, unknown pattern ❌
3. **Defense items (301-328)**: Use a different, unknown pattern ❌
4. **Utility items (401-423)**: Use a different, unknown pattern ❌

### Next Steps Required
To extract Crystal, Defense, and Utility items, we need to:
1. Identify the byte pattern used for each category
2. Analyze hex dumps where these items are visible in-game
3. Search for alternative patterns like:
   - Different prefix bytes (not `FF FF FF FF`)
   - Different byte ordering (little-endian vs big-endian)
   - Compressed or encoded formats
   - Item IDs stored as single bytes vs two bytes

### Validation Method
The image evidence provides ground truth for what items should exist in each match, allowing us to:
1. Target specific frames where items are visible
2. Perform targeted hex analysis at those timestamps
3. Identify new patterns for missing item categories
4. Validate extraction accuracy against visual evidence

---

## Match Details: Semi-Final Game 1

**Replay File:** `D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\1`

**Frame Analysis:**
- Total frames: 105
- Frames analyzed: 11 (every ~10th frame)
- Weapon Tier 3 items appear from frame 2 onward
- Breaking Point (127): First seen frame 2, total 58 occurrences
- Sorrowblade (121): First seen frame 7, total 66 occurrences
- Tension Bow (128): First seen frame 2, total 70 occurrences

**Expected but Missing:**
- Spellfire (228): Should appear in Malene's inventory
- Dragon's Eye (227): Should appear in Malene's inventory
- Broken Myth (224): Should appear in Malene's inventory
- Eve of Harvest (223): Should appear in Malene's inventory
- Aegis (321): Should appear on multiple players
- Metal Jacket (322): Should appear on multiple players
- Crucible (324): Should appear on support/tank players
- Fountain of Renewal (323): Should appear on Lyra
- Pulseweave (327): Should appear on Grumpjaw
- Capacitor Plate (328): Should appear on Lyra
- Journey Boots (403): Should appear on Kestrel
- Halcyon Chargers (404): Should appear on Malene
- War Treads (405): Should appear on multiple players

---

## Recommendation

The current extraction method is **incomplete**. While it successfully extracts Weapon items, it misses 75% of the item categories. A comprehensive reverse engineering effort is needed to identify the storage patterns for:
1. Crystal items (9 Tier 3 items)
2. Defense items (8 Tier 3 items)
3. Utility items (10 Tier 3 items)

The tournament images serve as perfect validation datasets, as they show exactly what items should be present in each match.
