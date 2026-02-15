# VG Reverse Engineering Tools

Utility scripts for batch replay analysis.

## Tools

### replay_batch_parser.py - Batch Replay Analysis

Batch processes all VGR replay files and generates unified statistics.

**Features:**
- Parses all .vgr replays in a directory tree
- Aggregates players, heroes, items across all matches
- Calculates pick rates, win rates, KDA statistics
- Outputs JSON or CSV format

**Usage:**

```bash
# Basic usage (JSON to stdout)
python vg/tools/replay_batch_parser.py /path/to/replays/

# Save to file
python vg/tools/replay_batch_parser.py /path/to/replays/ -o summary.json

# CSV export (hero stats)
python vg/tools/replay_batch_parser.py /path/to/replays/ --format csv-heroes -o heroes.csv

# CSV export (player stats)
python vg/tools/replay_batch_parser.py /path/to/replays/ --format csv-players -o players.csv

# Enable hero detection
python vg/tools/replay_batch_parser.py /path/to/replays/ --detect-heroes -o summary.json

# Summary only (without full replay data)
python vg/tools/replay_batch_parser.py /path/to/replays/ --summary-only -o summary.json
```

**Output Structure:**

```json
{
  "metadata": {
    "total_replays": 50,
    "unique_players": 120,
    "unique_heroes": 35,
    "unique_items": 42
  },
  "heroes": {
    "summary": [
      {
        "hero": "Ringo",
        "picks": 25,
        "pick_rate": "50.0%"
      }
    ]
  },
  "players": {
    "summary": [
      {
        "player": "PlayerName",
        "games": 12,
        "most_played_hero": "Ringo"
      }
    ]
  },
  "replays": [...]
}
```

## Prerequisites

Uses the existing `VGRParser` from `vg/core/vgr_parser.py` - no additional dependencies needed.

**Troubleshooting:**

- **Import error for VGRParser**: Run from project root: `python -m vg.tools.replay_batch_parser`
- **No replays found**: Check that the directory path contains `.vgr` files in subdirectories

## Related

- [VGR Parser](../core/vgr_parser.py) - Core replay parsing module
- [VGR Mapping](../core/vgr_mapping.py) - Hero and item ID mappings (57 heroes, 80+ items)
- [Reverse Engineering Notes](../docs/REVERSE_ENGINEERING_NOTES.md) - Detailed research documentation
