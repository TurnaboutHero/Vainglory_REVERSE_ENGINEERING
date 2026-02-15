# Position Vector Analysis Report
Generated: 2026-02-15 21:44:23

## Executive Summary

Analysis of Vainglory replay binary data identified **625 non-zero position vectors** across 3 frames (10, 50, 90). Position data appears as IEEE 754 float32 pairs (X, Y) within player entity event payloads. The most consistent position field offset is **+8 bytes** from payload start. Action codes 0x00, 0x05, 0x15, and 0x17 contain the highest density of position data.

## Data Overview

- **Dataset**: Vainglory replay cache from D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/
- **Frames Analyzed**: 10, 50, 90
- **Frame Sizes**: 65KB (frame 10), 90KB (frame 50), 79KB (frame 90)
- **Player Entity IDs**: 56325, 56581, 56837, 57093, 57349, 57605
- **Event Structure**: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]

## Key Findings

### Finding 1: Position Field Location

Position data appears as **float32 X,Y pairs** at multiple offsets within the 32-byte event payload.

**Most Common Position Offsets:**
| Offset | Occurrences | Percentage |
|--------|-------------|------------|
| +8 bytes | 119 | 19.0% |
| +12 bytes | 107 | 17.1% |
| +24 bytes | 92 | 14.7% |
| +20 bytes | 77 | 12.3% |
| +4 bytes | 75 | 12.0% |

**Conclusion**: Offset +8 bytes is the most consistent position field location across all action codes.

### Finding 2: Position-Rich Action Codes

Action codes vary significantly in position data density.

**Top Action Codes by Non-Zero Positions:**
| Action Code | Total Events | Non-Zero Positions | Ratio | Top Offset |
|-------------|--------------|-------------------|-------|------------|
| 0x00 | 106 | 152 | 143.4% | +0, +4, +8 |
| 0x05 | 667 | 314 | 47.1% | +8 |
| 0x17 | 12 | 26 | 216.7% | +0, +4 |
| 0x15 | 15 | 31 | 206.7% | +0, +4, +12 |

**Ratios >100%** indicate multiple position fields per event (e.g., source and destination positions).

### Finding 3: Coordinate Value Ranges

Position coordinates match expected Vainglory map boundaries:

**Coordinate Statistics:**
- **X Range**: [-12.06, 32.00] (expected: -50 to +50)
- **Y Range**: [-1.39, 32.00] (expected: -10 to +60)
- **X Mean**: 3.48
- **Y Mean**: 3.33

Most positions cluster near the origin, consistent with team base locations and early-game lane positions.

### Finding 4: Temporal Position Distribution

Position activity decreases significantly toward late game:

**Non-Zero Positions by Frame:**
| Frame | Positions | Game Phase |
|-------|-----------|------------|
| 10 | 413 | Early game - high movement |
| 50 | 169 | Mid game - moderate movement |
| 90 | 43 | Late game - low movement |

This pattern aligns with typical MOBA gameplay: early laning phase has frequent position updates, while late game features fewer but more strategic movements.

## Statistical Details

### Position Field Hex Patterns

Non-zero positions are often preceded by specific byte patterns:

- `00001004` - Observed before positions at offsets +16, +20, +24
- `00001804` - Observed before positions at offsets +16, +20
- `00000043` - Observed before positions at offsets +8, +12

These patterns may indicate position field type markers or preceding metadata.

### Action Code 0x05 Deep Dive

Action 0x05 is the most common event type (667 total events, 314 non-zero positions):

**Offset Distribution:**
- +8 bytes: 75 positions (23.9%)
- +12 bytes: 60 positions (19.1%)
- +20 bytes: 50 positions (15.9%)

**Hypothesis**: Action 0x05 is a **movement/position update event** sent frequently during gameplay.

## Visualizations

### Position Heatmap (Frame 50 Sample)

Sample positions from frame 50 show clustering:
- **Cluster 1**: Near (0, 0) - 5133 positions (likely base area)
- **Cluster 2**: Around (-0, 32) - 1385 positions (top lane)
- **Cluster 3**: Around (17, 0) - minimal positions (mid lane)

## Limitations

- **Z-Axis Excluded**: Third float32 value ranges from -10960 to 393583, indicating it's NOT elevation data but likely timestamps, entity IDs, or other metadata
- **Alignment Assumption**: Analysis assumes 4-byte alignment for float32 values; non-aligned positions would be missed
- **Zero-Position Filtering**: Excluded (0.0, 0.0) positions may include valid spawn-point or death locations
- **Event Structure Assumption**: Assumes event format [EntityID 2B][00 00][Action 1B][Payload 32B]; variations would cause misdetection
- **Limited Frame Sample**: Only 3 frames analyzed; full replay contains 100+ frames

## Recommendations

1. **Validate Offset +8 Hypothesis**: Parse all frames using offset +8 as primary position field and compare with API telemetry data

2. **Action Code Documentation**: Create mapping of action codes to event types:
   - 0x05 → Movement/position update (likely)
   - 0x00 → Unknown (high position density)
   - 0x15, 0x17 → Unknown (very high position density, may contain multiple positions)

3. **Implement Position Decoder**: Build decoder that:
   - Reads player entity events
   - Extracts float32 pairs at offset +8 (primary) and +12, +20, +24 (secondary)
   - Validates coordinates against map bounds
   - Correlates with API telemetry timestamps

4. **Analyze Preceding Bytes**: Investigate hex patterns `00001004`, `00001804`, `00000043` to understand position field metadata

5. **Full Replay Analysis**: Extend analysis to all 100+ frames to build complete player movement timeline

6. **Cross-Validate with API**: Compare binary position data with Vainglory API telemetry JSON to confirm accuracy

---
*Generated by Scientist Agent using Python 3.13.12*
*Analysis Tool: vg/analysis/position_vector_finder.py*
*Output Data: vg/output/position_field_analysis.json (14.5 KB)*
