# VG Reverse Engineering Tools

Utility scripts for batch replay analysis.

## Tools

### replay_batch_parser.py - Batch Replay Analysis

Batch processes all `.0.vgr` replay files and generates a JSON summary.

**Features:**
- Parses all .vgr replays in a directory tree
- Aggregates players and heroes across all matches
- Emits one JSON summary file

**Usage:**

```bash
# Basic usage
python vg/tools/replay_batch_parser.py /path/to/replays/

# Save to file
python vg/tools/replay_batch_parser.py /path/to/replays/ -o summary.json
```

**Output Structure:**

```json
{
  "total_replays": 50,
  "successful": 50,
  "failed": 0,
  "unique_players": 120,
  "game_modes": {
    "GameMode_HF_Ranked": 28
  },
  "hero_picks": {
    "Ringo": 25
  },
  "replays": [...]
}
```

## Prerequisites

Uses the existing `VGRParser` from `vg/core/vgr_parser.py` - no additional dependencies needed.

**Troubleshooting:**

- **No replays found**: Check that the directory path contains `.vgr` files in subdirectories

## Related

- [VGR Parser](../core/vgr_parser.py) - Core replay parsing module
- [VGR Mapping](../core/vgr_mapping.py) - Hero and item ID mappings (57 heroes, 80+ items)
- [Reverse Engineering Notes](../docs/REVERSE_ENGINEERING_NOTES.md) - Detailed research documentation
